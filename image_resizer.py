#!/usr/bin/env python3
"""
Image Resizer & Converter - Downsize and convert images for digital picture frames.

Reads images from an input folder, resizes them (using a scale factor or a target
maximum dimension), and saves them in JPEG format (or others) in an output folder.
"""

import argparse
import os
import sys
from pathlib import Path
import cv2

# Supported input image extensions
SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".tiff", ".tif", ".bmp"}


def get_resized_dimensions(width: int, height: int, scale: float = None, max_dim: int = None) -> tuple[int, int]:
    """Calculate new dimensions based on scale or max dimension, maintaining aspect ratio."""
    if max_dim is not None:
        if width > height:
            if width > max_dim:
                new_w = max_dim
                new_h = int(height * (max_dim / width))
                return new_w, new_h
        else:
            if height > max_dim:
                new_h = max_dim
                new_w = int(width * (max_dim / height))
                return new_w, new_h
        return width, height
    
    if scale is not None:
        new_w = int(width * scale)
        new_h = int(height * scale)
        # Ensure dimensions are at least 1 pixel
        return max(1, new_w), max(1, new_h)
        
    return width, height


def resize_and_convert_image(
    input_path: Path,
    output_path: Path,
    scale: float = None,
    max_dim: int = None,
    quality: int = 90,
    output_format: str = "jpg"
) -> bool:
    """Read, resize, and save an image to the destination path."""
    image = cv2.imread(str(input_path))
    if image is None:
        print(f"  ERROR: Could not read image: {input_path}")
        return False

    h, w = image.shape[:2]
    new_w, new_h = get_resized_dimensions(w, h, scale=scale, max_dim=max_dim)

    # Perform resizing if dimensions changed
    if (new_w, new_h) != (w, h):
        # Use INTER_AREA for downsizing (best quality for shrinking)
        # Use INTER_CUBIC if we are enlarging (unlikely here)
        interpolation = cv2.INTER_AREA if (new_w < w or new_h < h) else cv2.INTER_CUBIC
        resized = cv2.resize(image, (new_w, new_h), interpolation=interpolation)
        print(f"  Resized: {w}x{h} -> {new_w}x{new_h}")
    else:
        resized = image
        print(f"  Kept original size: {w}x{h}")

    # Determine saving params
    ext = output_format.lower()
    if not ext.startswith("."):
        ext = f".{ext}"

    params = []
    if ext in [".jpg", ".jpeg"]:
        params = [cv2.IMWRITE_JPEG_QUALITY, quality]
    elif ext == ".webp":
        params = [cv2.IMWRITE_WEBP_QUALITY, quality]
    elif ext == ".png":
        compression = 9 - int(quality / 11)
        params = [cv2.IMWRITE_PNG_COMPRESSION, compression]

    # Write output image
    output_path.parent.mkdir(parents=True, exist_ok=True)
    success = cv2.imwrite(str(output_path), resized, params)
    
    if success:
        print(f"  Saved: {output_path.name}")
    else:
        print(f"  ERROR: Failed to write image: {output_path}")
        
    return success


def process_directory(
    input_dir: Path,
    output_dir: Path,
    scale: float = None,
    max_dim: int = None,
    quality: int = 90,
    output_format: str = "jpg",
    recursive: bool = True
) -> int:
    """Traverse directories and process all matching images."""
    processed_count = 0
    
    # Standardize input/output path resolution
    input_dir = input_dir.resolve()
    output_dir = output_dir.resolve()

    if not input_dir.exists():
        print(f"Error: Input directory does not exist: {input_dir}")
        return 0

    print(f"Source Directory: {input_dir}")
    print(f"Output Directory: {output_dir}")
    if max_dim:
        print(f"Resizing Strategy: Limit maximum dimension to {max_dim}px (keep aspect ratio)")
    else:
        print(f"Resizing Strategy: Scale factor {scale:.2f}")
    print(f"Format: {output_format.upper()} (Quality: {quality})")
    print("=" * 60)

    # Walk or list directory
    if recursive:
        all_paths = sorted(input_dir.rglob("*"))
    else:
        all_paths = sorted(input_dir.iterdir())

    for path in all_paths:
        # Skip directories and files with unsupported extensions
        if not path.is_file() or path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            continue
            
        # Avoid processing files that are already inside the output directory
        # (in case output directory is a subdirectory of input directory)
        try:
            if path.relative_to(output_dir):
                continue
        except ValueError:
            pass

        # Compute output file path preserving subfolder structure
        rel_path = path.relative_to(input_dir)
        
        # Change file extension
        out_ext = output_format.lower()
        if not out_ext.startswith("."):
            out_ext = f".{out_ext}"
            
        out_rel_path = rel_path.with_suffix(out_ext)
        target_path = output_dir / out_rel_path

        print(f"\nProcessing: {rel_path}")
        if resize_and_convert_image(
            path,
            target_path,
            scale=scale,
            max_dim=max_dim,
            quality=quality,
            output_format=output_format
        ):
            processed_count += 1

    return processed_count


def main():
    parser = argparse.ArgumentParser(
        description="Downsize and convert scanned photos for digital frames.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Downsize to half resolution (50%) and convert to JPG (saved to downsized/):
  %(prog)s

  # Shrink images by 2/3 (scale factor of 0.33) and convert to JPG:
  %(prog)s -s 0.33

  # Downsize images so their maximum side is 1920px (standard HD frames):
  %(prog)s --max-dim 1920

  # Customize input and output folders, output quality, and format:
  %(prog)s -i output/ -o frame_photos/ -q 85 -f jpg
        """
    )
    parser.add_argument(
        "-i", "--input",
        default="output",
        help="Input directory containing photos to downsize (default: output/)"
    )
    parser.add_argument(
        "-o", "--output",
        default="downsized",
        help="Output directory for downsized photos (default: downsized/)"
    )
    
    # Scale or max-dim configuration
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "-s", "--scale",
        type=float,
        default=0.5,
        help="Scaling factor to resize images (default: 0.5, which is 50% / half size). For 2/3 size, use 0.67. To shrink by 2/3 (retain 1/3), use 0.33."
    )
    group.add_argument(
        "--max-dim",
        type=int,
        help="Scale down so the larger dimension (width or height) is at most this many pixels."
    )

    parser.add_argument(
        "-q", "--quality",
        type=int,
        default=90,
        help="JPEG/output quality 0-100 (default: 90)"
    )
    parser.add_argument(
        "-f", "--format",
        default="jpg",
        choices=["jpg", "jpeg", "webp", "png"],
        help="Output format (default: jpg)"
    )
    parser.add_argument(
        "--no-recursive",
        action="store_true",
        help="Do not process input directory recursively (only process top-level files)."
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

    scale_val = None if args.max_dim is not None else args.scale
    if scale_val is not None and scale_val <= 0:
        print("Error: Scale factor must be greater than 0.")
        sys.exit(1)

    count = process_directory(
        input_dir=input_dir,
        output_dir=output_dir,
        scale=scale_val,
        max_dim=args.max_dim,
        quality=args.quality,
        output_format=args.format,
        recursive=not args.no_recursive
    )

    print("\n" + "=" * 60)
    print(f"Done! Successfully processed {count} image(s).")


if __name__ == "__main__":
    main()
