#!/usr/bin/env python3
"""
Scanner Clipper - Detect and extract individual photos from flatbed scans.

Reads scanned images from an input folder, detects individual photos using
edge detection and contour analysis, then saves each extracted photo as a
separate file in the output folder.
"""

import argparse
import os
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path

import cv2
import numpy as np


# Supported image extensions
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".tiff", ".tif", ".bmp", ".webp"}

# --- Tunable parameters ---
MIN_AREA_RATIO = 0.005       # Minimum photo area as fraction of total image area
MAX_AREA_RATIO = 0.80        # Maximum photo area as fraction of total image area
BLUR_KERNEL = 5              # Gaussian blur kernel size
CANNY_LOW = 30               # Canny edge detection lower threshold
CANNY_HIGH = 100             # Canny edge detection upper threshold
DILATE_ITERATIONS = 3        # Dilation iterations to close edge gaps
MORPH_KERNEL_SIZE = 7        # Morphological kernel size
CONTOUR_APPROX_FACTOR = 0.02 # Contour approximation epsilon factor
PADDING_PX = 0               # Padding around extracted photos (pixels)
SHAVE_PX = 10                 # Pixels to shave off edges (to remove rounded corners)
TRIM_THRESHOLD = 240         # Grayscale threshold for whitespace (0-255)
OUTPUT_QUALITY = 90          # Default output quality (0-100)
OUTPUT_FORMAT = "webp"       # Default output format


def order_points(pts: np.ndarray) -> np.ndarray:
    """Order 4 points as: top-left, top-right, bottom-right, bottom-left."""
    # Sort the points based on their x-coordinates
    xSorted = pts[np.argsort(pts[:, 0]), :]

    # Grab the left-most and right-most points from the sorted x-coordinate points
    leftMost = xSorted[:2, :]
    rightMost = xSorted[2:, :]

    # Sort the left-most coordinates according to their y-coordinates 
    # to grab the top-left and bottom-left points, respectively
    leftMost = leftMost[np.argsort(leftMost[:, 1]), :]
    (tl, bl) = leftMost

    # Calculate the Euclidean distance between the top-left and right-most points;
    # the point with the largest distance will be our bottom-right point
    D = np.linalg.norm(rightMost - tl, axis=1)
    (br, tr) = rightMost[np.argsort(D)[::-1], :]

    return np.array([tl, tr, br, bl], dtype="float32")


def four_point_transform(image: np.ndarray, pts: np.ndarray) -> np.ndarray:
    """Apply a perspective transform to extract a rectangular region."""
    rect = order_points(pts)
    (tl, tr, br, bl) = rect

    # Compute the width of the new image
    width_a = np.linalg.norm(br - bl)
    width_b = np.linalg.norm(tr - tl)
    max_width = int(max(width_a, width_b))

    # Compute the height of the new image
    height_a = np.linalg.norm(tr - br)
    height_b = np.linalg.norm(tl - bl)
    max_height = int(max(height_a, height_b))

    dst = np.array([
        [0, 0],
        [max_width - 1, 0],
        [max_width - 1, max_height - 1],
        [0, max_height - 1],
    ], dtype="float32")

    M = cv2.getPerspectiveTransform(rect, dst)
    warped = cv2.warpPerspective(image, M, (max_width, max_height))
    return warped


def extract_with_bounding_rect(image: np.ndarray, contour: np.ndarray) -> np.ndarray:
    """Extract a photo using its minimum area rotated bounding rectangle."""
    rect = cv2.minAreaRect(contour)
    box = cv2.boxPoints(rect)
    box = np.intp(box)

    # Use perspective transform to de-rotate and extract
    pts = box.astype("float32")
    extracted = four_point_transform(image, pts)

    # If the image is extremely thin, it's probably not a real photo
    h, w = extracted.shape[:2]
    if h < 50 or w < 50:
        return None

    return extracted


def trim_photo(image: np.ndarray, threshold: int = TRIM_THRESHOLD, shave: int = SHAVE_PX) -> np.ndarray:
    """
    Trim white edges from an image and optionally shave off a few pixels.

    This handles rounded corners by cropping slightly into the photo content
    to ensure no scanner background (whitespace) is left at the corners.
    """
    if image is None:
        return None

    # Convert to grayscale for thresholding
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    # Threshold to find non-white pixels
    # Scanner background is usually very bright (> 240)
    _, mask = cv2.threshold(gray, threshold, 255, cv2.THRESH_BINARY_INV)

    # Clean up the mask to remove tiny noise pixels (dust)
    # Using a small opening operation
    kernel = np.ones((3, 3), np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)

    # Find non-zero coordinates to get the content's extent
    coords = cv2.findNonZero(mask)
    if coords is None:
        return image

    x, y, w, h = cv2.boundingRect(coords)

    # Crop to the detected content
    cropped = image[y:y+h, x:x+w]

    # Shave edges to remove rounded corner artifacts
    if shave > 0:
        ch, cw = cropped.shape[:2]
        if ch > 2 * shave and cw > 2 * shave:
            cropped = cropped[shave:ch-shave, shave:cw-shave]

    return cropped


def is_overlapping(box_a: np.ndarray, box_b: np.ndarray, threshold: float = 0.5) -> bool:
    """Check if two contours significantly overlap using bounding rectangles."""
    x1, y1, w1, h1 = cv2.boundingRect(box_a)
    x2, y2, w2, h2 = cv2.boundingRect(box_b)

    # Compute intersection
    ix = max(0, min(x1 + w1, x2 + w2) - max(x1, x2))
    iy = max(0, min(y1 + h1, y2 + h2) - max(y1, y2))
    intersection = ix * iy

    # Compute areas
    area_a = w1 * h1
    area_b = w2 * h2
    smaller_area = min(area_a, area_b)

    if smaller_area == 0:
        return False

    return (intersection / smaller_area) > threshold


def filter_overlapping_contours(contours: list) -> list:
    """Remove smaller contours that significantly overlap with larger ones."""
    # Sort by area descending
    contours = sorted(contours, key=cv2.contourArea, reverse=True)
    keep = []

    for contour in contours:
        overlaps = False
        for kept in keep:
            if is_overlapping(contour, kept, threshold=0.5):
                overlaps = True
                break
        if not overlaps:
            keep.append(contour)

    return keep


def detect_photos(image_path: str, debug: bool = False, shave_px: int = SHAVE_PX, threshold: int = TRIM_THRESHOLD) -> list[np.ndarray]:
    """
    Detect individual photos in a scanned image and return them as a list.

    Uses edge detection and contour analysis to find rectangular photo
    regions on the scanner bed.
    """
    image = cv2.imread(image_path)
    if image is None:
        print(f"  ERROR: Could not read image: {image_path}")
        return []

    h, w = image.shape[:2]
    total_area = h * w
    min_area = total_area * MIN_AREA_RATIO
    max_area = total_area * MAX_AREA_RATIO

    print(f"  Image size: {w}x{h} ({total_area:,} pixels)")
    print(f"  Min photo area: {min_area:,.0f}px | Max: {max_area:,.0f}px")

    # Convert to grayscale
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    # Apply Gaussian blur to reduce noise
    blurred = cv2.GaussianBlur(gray, (BLUR_KERNEL, BLUR_KERNEL), 0)

    # --- Method 1: Adaptive threshold to separate photos from white background ---
    # The scanner background is white, photos are generally darker
    # Use Otsu's thresholding to find the separation
    _, thresh = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

    # Morphological operations to clean up the mask
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (MORPH_KERNEL_SIZE, MORPH_KERNEL_SIZE))
    thresh = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel, iterations=DILATE_ITERATIONS)
    thresh = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, kernel, iterations=1)

    # --- Method 2: Canny edge detection for backup ---
    edges = cv2.Canny(blurred, CANNY_LOW, CANNY_HIGH)
    edges_dilated = cv2.dilate(edges, kernel, iterations=DILATE_ITERATIONS)
    edges_closed = cv2.morphologyEx(edges_dilated, cv2.MORPH_CLOSE, kernel, iterations=2)

    # Combine both methods
    combined = cv2.bitwise_or(thresh, edges_closed)

    # Additional closing to fill gaps
    large_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (15, 15))
    combined = cv2.morphologyEx(combined, cv2.MORPH_CLOSE, large_kernel, iterations=3)

    if debug:
        debug_dir = Path(image_path).parent.parent / "debug"
        debug_dir.mkdir(exist_ok=True)
        stem = Path(image_path).stem
        cv2.imwrite(str(debug_dir / f"{stem}_thresh.jpg"), thresh)
        cv2.imwrite(str(debug_dir / f"{stem}_edges.jpg"), edges_closed)
        cv2.imwrite(str(debug_dir / f"{stem}_combined.jpg"), combined)

    # Find contours
    contours, _ = cv2.findContours(combined, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    print(f"  Found {len(contours)} raw contours")

    # Filter contours by area and shape
    candidate_contours = []
    for i, contour in enumerate(contours):
        area = cv2.contourArea(contour)

        # Skip contours that are too small or too large
        if area < min_area:
            continue
        if area > max_area:
            continue

        # Get the minimum area bounding rectangle
        rect = cv2.minAreaRect(contour)
        rect_w, rect_h = rect[1]
        if rect_w == 0 or rect_h == 0:
            continue

        # Check aspect ratio isn't too extreme (photos are roughly rectangular)
        aspect = max(rect_w, rect_h) / min(rect_w, rect_h)
        if aspect > 5.0:
            continue

        # Check that the contour fills a reasonable portion of its bounding rect
        rect_area = rect_w * rect_h
        fill_ratio = area / rect_area if rect_area > 0 else 0
        if fill_ratio < 0.4:
            continue

        candidate_contours.append(contour)
        print(f"  Candidate {len(candidate_contours)}: area={area:,.0f} "
              f"aspect={aspect:.2f} fill={fill_ratio:.2f}")

    # Remove overlapping contours (keep the larger ones)
    filtered = filter_overlapping_contours(candidate_contours)
    print(f"  After overlap filtering: {len(filtered)} photos detected")

    if debug and filtered:
        debug_img = image.copy()
        for contour in filtered:
            rect = cv2.minAreaRect(contour)
            box = cv2.boxPoints(rect)
            box = np.intp(box)
            cv2.drawContours(debug_img, [box], 0, (0, 255, 0), 4)
        cv2.imwrite(str(debug_dir / f"{stem}_detected.jpg"), debug_img)

    # Extract and trim each photo
    extracted = []
    for contour in filtered:
        photo = extract_with_bounding_rect(image, contour)
        if photo is not None:
            # Post-process to remove whitespace and handle rounded corners
            photo = trim_photo(photo, threshold=threshold, shave=shave_px)
            if photo is not None:
                extracted.append(photo)

    return extracted


def process_images(image_files: list[Path], output_path: Path, prefix: str = None,
                   debug: bool = False, shave_px: int = SHAVE_PX, 
                   threshold: int = TRIM_THRESHOLD, quality: int = OUTPUT_QUALITY, 
                   output_format: str = OUTPUT_FORMAT) -> int:
    """
    Process a list of image files and save results to output_path.
    
    If prefix is provided, output files will be named sequentially: {prefix}_{count:03d}.ext
    Otherwise, they use the source filename: {img_file.stem}_photo_{i:02d}.ext
    """
    output_path.mkdir(parents=True, exist_ok=True)
    total_extracted = 0

    for img_file in image_files:
        print(f"\nProcessing: {img_file.name}")
        print("-" * 40)

        photos = detect_photos(str(img_file), debug=debug, shave_px=shave_px, threshold=threshold)

        if not photos:
            print(f"  No photos detected in {img_file.name}")
            continue

        for i, photo in enumerate(photos, 1):
            # Build output filename
            ext = output_format.lower()
            if not ext.startswith("."):
                ext = f".{ext}"
            
            if prefix:
                out_name = f"{prefix}_{total_extracted + 1:03d}{ext}"
            else:
                out_name = f"{img_file.stem}_photo_{i:02d}{ext}"
            
            out_path = output_path / out_name

            # Determine quality flags based on format
            params = []
            if ext == ".webp":
                params = [cv2.IMWRITE_WEBP_QUALITY, quality]
            elif ext in [".jpg", ".jpeg"]:
                params = [cv2.IMWRITE_JPEG_QUALITY, quality]
            elif ext == ".png":
                compression = 9 - int(quality / 11)
                params = [cv2.IMWRITE_PNG_COMPRESSION, compression]

            cv2.imwrite(str(out_path), photo, params)
            ph, pw = photo.shape[:2]
            print(f"  Saved: {out_name} ({pw}x{ph})")
            total_extracted += 1
            
    return total_extracted


def process_folder(input_dir: str, output_dir: str, debug: bool = False, 
                   shave_px: int = SHAVE_PX, threshold: int = TRIM_THRESHOLD,
                   quality: int = OUTPUT_QUALITY, output_format: str = OUTPUT_FORMAT) -> None:
    """Process all images and zip files in the input directory."""
    input_path = Path(input_dir)
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    # Find all image files in the top level
    image_files = sorted([
        f for f in input_path.iterdir()
        if f.is_file() and f.suffix.lower() in IMAGE_EXTENSIONS
    ])

    # Find all zip files
    zip_files = sorted([
        f for f in input_path.iterdir()
        if f.is_file() and f.suffix.lower() == ".zip"
    ])

    if not image_files and not zip_files:
        print(f"No images or zip files found in {input_dir}")
        print(f"Supported formats: {', '.join(IMAGE_EXTENSIONS)}, .zip")
        return

    print(f"Found {len(image_files)} image(s) and {len(zip_files)} zip file(s) in {input_dir}")
    print(f"Output directory: {output_dir}")
    print("=" * 60)

    total_extracted = 0

    # Process standalone images
    if image_files:
        print(f"Processing {len(image_files)} standalone images...")
        total_extracted += process_images(image_files, output_path, None, debug, shave_px, threshold, quality, output_format)

    # Process zip files
    for zip_file in zip_files:
        print(f"\nDelving into ZIP: {zip_file.name}")
        print("=" * 60)
        
        # Create a subdirectory for the zip's contents
        zip_output_path = output_path / zip_file.stem
        
        # Create a temporary directory to extract the zip
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            
            with zipfile.ZipFile(zip_file, 'r') as z:
                # Extract only image files, ignoring folder structure if any
                for i, member in enumerate(z.infolist()):
                    if member.is_dir():
                        continue
                    
                    filename = Path(member.filename).name
                    if Path(filename).suffix.lower() in IMAGE_EXTENSIONS:
                        # Use a counter to avoid collisions in the flat temp directory
                        target_file = temp_path / f"scan_{i:04d}_{filename}"
                        with z.open(member) as source, open(target_file, "wb") as target:
                            shutil.copyfileobj(source, target)
            
            # Find all extracted images
            extracted_images = sorted([
                f for f in temp_path.iterdir()
                if f.is_file() and f.suffix.lower() in IMAGE_EXTENSIONS
            ])
            
            if extracted_images:
                print(f"Found {len(extracted_images)} image(s) in {zip_file.name}")
                # Use the zip filename (stem) as prefix to disregard internal filenames
                total_extracted += process_images(extracted_images, zip_output_path, zip_file.stem, 
                                                 debug, shave_px, threshold, quality, output_format)
            else:
                print(f"No supported images found in {zip_file.name}")

    print("\n" + "=" * 60)
    print(f"Done! Total extracted {total_extracted} photo(s)")


def main():
    parser = argparse.ArgumentParser(
        description="Extract individual photos from flatbed scanner images.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                          # Use default input/ and output/ folders
  %(prog)s -i scans/ -o extracted/  # Custom folders
  %(prog)s --debug                  # Save debug images to debug/ folder
        """
    )
    parser.add_argument(
        "-i", "--input",
        default="input",
        help="Input directory containing scanned images (default: input/)"
    )
    parser.add_argument(
        "-o", "--output",
        default="output",
        help="Output directory for extracted photos (default: output/)"
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Save intermediate debug images (threshold, edges, detections)"
    )

    parser.add_argument(
        "--shave",
        type=int,
        default=SHAVE_PX,
        help=f"Pixels to shave off edges to remove rounded corners (default: {SHAVE_PX})"
    )
    parser.add_argument(
        "--threshold",
        type=int,
        default=TRIM_THRESHOLD,
        help=f"Grayscale threshold for whitespace trimming (default: {TRIM_THRESHOLD})"
    )
    parser.add_argument(
        "-q", "--quality",
        type=int,
        default=OUTPUT_QUALITY,
        help=f"Output quality 0-100 (default: {OUTPUT_QUALITY})"
    )
    parser.add_argument(
        "-f", "--format",
        default=OUTPUT_FORMAT,
        choices=["webp", "jpg", "png"],
        help=f"Output format (default: {OUTPUT_FORMAT})"
    )

    args = parser.parse_args()

    # Resolve paths relative to script location if not absolute
    script_dir = Path(__file__).parent
    input_dir = Path(args.input)
    output_dir = Path(args.output)

    if not input_dir.is_absolute():
        input_dir = script_dir / input_dir
    if not output_dir.is_absolute():
        output_dir = script_dir / output_dir

    if not input_dir.exists():
        print(f"Error: Input directory does not exist: {input_dir}")
        sys.exit(1)

    process_folder(
        str(input_dir),
        str(output_dir),
        debug=args.debug,
        shave_px=args.shave,
        threshold=args.threshold,
        quality=args.quality,
        output_format=args.format
    )


if __name__ == "__main__":
    main()
