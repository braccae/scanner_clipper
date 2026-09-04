#!/usr/bin/env python3
"""
Date Imprint Detector - Detect, extract, and parse vintage camera date stamps from photos.

Typical 35mm compact cameras from the 1980s through 2000s printed date stamps onto photos
using amber/orange/red LED dot-matrix or 7-segment imprints in one of the photo corners.
This module locates candidate date stamps across photo corners, enhances contrast,
reads them with EasyOCR, and parses them into datetime objects to write to EXIF.
"""

import re
from datetime import datetime
from typing import Optional, Tuple, List, Dict, Any
from pathlib import Path

import cv2
import numpy as np

# Global cached EasyOCR reader (lazy-loaded on first use)
_EASYOCR_READER = None


def get_ocr_reader():
    """Lazy-load and cache the EasyOCR reader."""
    global _EASYOCR_READER
    if _EASYOCR_READER is None:
        import easyocr
        # Use CPU mode by default for broad compatibility
        _EASYOCR_READER = easyocr.Reader(["en"], gpu=False)
    return _EASYOCR_READER


def parse_date_imprint(text: str, default_order: str = "auto") -> Optional[Tuple[datetime, str]]:
    """
    Parse a camera date imprint string into a datetime object.

    Supported patterns:
    - Leading year:  "'94 1 5", "'94 15", "'94 01 05", "'94.1.5", "'94-1-5"
    - Trailing year: "9 24 '02", "9 25 '02", "9 25 2", "9 25 02", "924 '02"
    - Plain digits:  "94 1 5", "9 24 02"

    Disambiguation:
    - If one number is > 12, it is definitively the Day.
    - If year is first ('YY ...): defaults to YY-MM-DD unless default_order is YY-DD-MM.
    - If year is last (... 'YY): defaults to MM-DD-YY unless default_order is DD-MM-YY.
    """
    if not text:
        return None

    # Replace periods, slashes, dashes, colons with spaces, keeping apostrophes
    cleaned = re.sub(r"[^0-9\x27\s]", " ", text).strip()
    if not cleaned:
        return None

    # Separate merged apostrophes e.g. 24'02 -> 24 '02, 25'02 -> 25 '02
    cleaned = re.sub(r"(\d+)\x27(\d+)", r"\1 '\2", cleaned)

    # Disambiguate leading 3-digit year misreads caused by camera LED dot-matrix apostrophe merging with '9'
    # e.g., '94 misread as 294, 794, 094, 194, 394 -> '94; 44 -> 94
    cleaned = re.sub(r"\b[01237](9\d)\b", r"'\1", cleaned)
    cleaned = re.sub(r"\b44\b", r"94", cleaned)
    # Faint top-left dot/segment turns 9 into 3 for years 94-99 (e.g. '34 -> '94)
    cleaned = re.sub(r"\x273([4-9])\b", r"'9\1", cleaned)
    cleaned = re.sub(r"\b3([4-9])\b", r"'9\1", cleaned)
    # Disambiguate trailing 3-digit year misreads caused by apostrophe merging with '0'
    # e.g., '02 misread as 802, 902, 502 -> '02
    cleaned = re.sub(r"\b[589](0\d)\b", r"'\1", cleaned)

    tokens = re.findall(r"\x27?\d+", cleaned)
    if not (1 <= len(tokens) <= 4):
        return None

    current_year = datetime.now().year
    year = None
    rem_tokens = []
    year_was_first = False

    # Check for apostrophe indicating 2-digit year (e.g. '94, '02)
    for idx, t in enumerate(tokens):
        if t.startswith("\x27"):
            y_str = t.lstrip("\x27")
            if len(y_str) == 2:
                y_val = int(y_str)
                year = 1900 + y_val if y_val > 30 else 2000 + y_val
                year_was_first = (idx == 0)
                continue
        rem_tokens.append(t.lstrip("\x27"))

    # If no apostrophe was detected, check for plausible 2-digit years (> 31)
    if year is None:
        try:
            raw_vals = [int(t.lstrip("\x27")) for t in tokens]
        except ValueError:
            return None

        if raw_vals[0] > 31:
            year = 1900 + raw_vals[0] if raw_vals[0] > 30 else 2000 + raw_vals[0]
            year_was_first = True
            rem_tokens = [t.lstrip("\x27") for t in tokens[1:]]
        elif raw_vals[-1] > 31:
            year = 1900 + raw_vals[-1] if raw_vals[-1] > 30 else 2000 + raw_vals[-1]
            year_was_first = False
            rem_tokens = [t.lstrip("\x27") for t in tokens[:-1]]
        elif len(tokens) == 3 and tokens[-1].lstrip("\x27") in ("2", "02", "3", "03", "4", "04", "5", "05"):
            # Trailing single/double digit year e.g. 9 25 2 -> 2002
            y_val = int(tokens[-1].lstrip("\x27"))
            year = 2000 + y_val
            year_was_first = False
            rem_tokens = [t.lstrip("\x27") for t in tokens[:-1]]

    if year is None or not (1970 <= year <= current_year):
        return None

    month = None
    day = None

    if len(rem_tokens) == 1:
        s = rem_tokens[0]
        if year_was_first and len(s) == 2:
            # Leading year format 'YY M D (e.g. '94 15 -> 1994-01-05)
            month, day = int(s[0]), int(s[1])
        elif len(s) == 3:  # e.g. "924" -> 9, 24
            month, day = int(s[0]), int(s[1:])
        elif len(s) == 4:  # e.g. "0105" -> 1, 5, or "0924" -> 9, 24
            month, day = int(s[:2]), int(s[2:])
        else:
            return None
    elif len(rem_tokens) == 2:
        try:
            n1, n2 = int(rem_tokens[0]), int(rem_tokens[1])
        except ValueError:
            return None
        if n1 > 12 >= n2:
            day, month = n1, n2
        elif n2 > 12 >= n1:
            month, day = n1, n2
        elif default_order in ("YY-DD-MM", "DD-MM-YY"):
            day, month = n1, n2
        else:
            month, day = n1, n2
    elif len(rem_tokens) == 3 and year_was_first:
        # e.g. ["1", "5"] with an extra trailing artifact
        try:
            n1, n2 = int(rem_tokens[0]), int(rem_tokens[1])
        except ValueError:
            return None
        if n1 > 12 >= n2:
            day, month = n1, n2
        else:
            month, day = n1, n2
    else:
        return None

    if month and day and 1 <= month <= 12 and 1 <= day <= 31:
        try:
            dt = datetime(year, month, day, 12, 0, 0)
            formatted = f"{year:04d}-{month:02d}-{day:02d}"
            return dt, formatted
        except ValueError:
            return None

    return None


def extract_photo_corners(image: np.ndarray, width_ratio: float = 0.35, height_ratio: float = 0.28) -> Dict[str, np.ndarray]:
    """Extract 4 corner subregions from an image."""
    h, w = image.shape[:2]
    cw = max(50, min(int(w * width_ratio), w // 2))
    ch = max(50, min(int(h * height_ratio), h // 2))

    return {
        "BR": image[h - ch:h, w - cw:w],
        "BL": image[h - ch:h, 0:cw],
        "TR": image[0:ch, w - cw:w],
        "TL": image[0:ch, 0:cw],
    }


def get_amber_signal(img: np.ndarray) -> np.ndarray:
    """
    Compute the amber/orange LED emission signal.
    Amber light adds high Red, moderate Green, and minimal Blue.
    Signal = (R - B) + 0.5 * (G - B).
    """
    r = img[:, :, 2].astype(np.int32)
    g = img[:, :, 1].astype(np.int32)
    b = img[:, :, 0].astype(np.int32)
    signal = (r - b) + 0.5 * (g - b)
    return signal


def detect_date_imprint(
    image: np.ndarray,
    date_format: str = "auto",
    min_confidence: float = 0.30,
    verbose: bool = False
) -> Optional[Dict[str, Any]]:
    """
    Scan an image for a camera date imprint.

    Checks corners prioritizing Bottom-Right and Bottom-Left.
    Uses amber signal analysis to locate and isolate the date text strip,
    then tests cardinal orientations with EasyOCR.

    Returns:
        Dictionary with keys:
            'datetime': datetime object
            'formatted': str (YYYY-MM-DD)
            'raw_text': str
            'confidence': float
            'corner': str ('BR', 'BL', 'TR', 'TL')
            'rotation': int (0, 90, 180, 270)
        or None if no date stamp was detected.
    """
    corners = extract_photo_corners(image)
    reader = get_ocr_reader()

    corner_priority = ["BR", "BL", "TR", "TL"]
    rotations = [
        (0, None),
        (270, cv2.ROTATE_90_COUNTERCLOCKWISE),
        (90, cv2.ROTATE_90_CLOCKWISE),
        (180, cv2.ROTATE_180),
    ]

    candidates = []

    for cname in corner_priority:
        cimg = corners[cname]
        signal = get_amber_signal(cimg)

        # Amber dots have signal > 75
        amber_dots = signal > 75
        cnt = int(np.count_nonzero(amber_dots))
        if cnt < 40:
            continue

        # Check if corner is dominated by warm background colors (e.g. carpet, wood, skin)
        is_warm_bg = (cnt > 25000 or (cnt / (cimg.shape[0] * cimg.shape[1])) > 0.08)

        if is_warm_bg:
            # Use local background subtraction to isolate high-frequency LED dots from warm background
            bg = cv2.GaussianBlur(signal.astype(np.float32), (51, 51), 0)
            dots_sig = signal - bg
            th_dots = 13
            active_mask = (dots_sig > th_dots).astype(np.uint8) * 255
            pts = np.argwhere(active_mask > 0)
            if len(pts) < 40:
                continue
        else:
            dots_sig = None
            th_dots = 75
            active_mask = amber_dots.astype(np.uint8) * 255
            pts = np.argwhere(active_mask > 0)

        # Find bounding box of amber dots with margin
        y0, x0 = pts.min(axis=0)
        y1, x1 = pts.max(axis=0)
        bw, bh = x1 - x0, y1 - y0
        pad = 35

        # If bounding box is too large (due to scattered noise or warm background), search for compact date-like clusters
        candidate_boxes = []
        if bw > 850 or bh > 850 or is_warm_bg:
            kh = cv2.getStructuringElement(cv2.MORPH_RECT, (160, 7))
            kv = cv2.getStructuringElement(cv2.MORPH_RECT, (7, 160))
            ch = cv2.morphologyEx(active_mask, cv2.MORPH_CLOSE, kh)
            cv_ = cv2.morphologyEx(active_mask, cv2.MORPH_CLOSE, kv)
            for closed, orient in [(ch, "H"), (cv_, "V")]:
                n, _, stats, _ = cv2.connectedComponentsWithStats(closed)
                for i in range(1, n):
                    cx, cy, cw, ch_comp, _ = stats[i]
                    asp = cw / max(1, ch_comp)
                    if orient == "H" and (1.8 <= asp <= 15 and 120 <= cw <= 750 and 15 <= ch_comp <= 130):
                        sub_d = (dots_sig if is_warm_bg and dots_sig is not None else signal)[cy:cy + ch_comp, cx:cx + cw]
                        dots_in_box = np.count_nonzero(sub_d > th_dots)
                        density = dots_in_box / max(1, cw * ch_comp)
                        if (not is_warm_bg) or (dots_in_box >= 300 and density >= 0.03):
                            candidate_boxes.append((cx, cy, cx + cw, cy + ch_comp, is_warm_bg, orient, density))
                    elif orient == "V" and (1.8 <= (ch_comp / max(1, cw)) <= 15 and 120 <= ch_comp <= 750 and 15 <= cw <= 130):
                        sub_d = (dots_sig if is_warm_bg and dots_sig is not None else signal)[cy:cy + ch_comp, cx:cx + cw]
                        dots_in_box = np.count_nonzero(sub_d > th_dots)
                        density = dots_in_box / max(1, cw * ch_comp)
                        if (not is_warm_bg) or (dots_in_box >= 300 and density >= 0.03):
                            candidate_boxes.append((cx, cy, cx + cw, cy + ch_comp, is_warm_bg, orient, density))
            if not candidate_boxes:
                continue
            candidate_boxes.sort(key=lambda b: b[6], reverse=True)
        else:
            asp_box = bw / max(1, bh)
            if asp_box >= 1.8:
                box_orient = "H"
            elif (bh / max(1, bw)) >= 1.8:
                box_orient = "V"
            else:
                box_orient = "ALL"
            candidate_boxes.append((x0, y0, x1, y1, False, box_orient, 1.0))

        corner_found = False
        for bx0, by0, bx1, by1, box_warm, orient, _ in candidate_boxes:
            sub_raw = cimg[max(0, by0 - pad):min(cimg.shape[0], by1 + pad),
                           max(0, bx0 - pad):min(cimg.shape[1], bx1 + pad)]

            sub_signal = signal[max(0, by0 - pad):min(signal.shape[0], by1 + pad),
                                max(0, bx0 - pad):min(signal.shape[1], bx1 + pad)]

            if sub_raw.size == 0 or sub_raw.shape[0] < 15 or sub_raw.shape[1] < 40:
                continue

            base_images = [sub_raw]

            if box_warm and dots_sig is not None:
                sub_dots = dots_sig[max(0, by0 - pad):min(dots_sig.shape[0], by1 + pad),
                                    max(0, bx0 - pad):min(dots_sig.shape[1], bx1 + pad)]
                m = (sub_dots > 12).astype(np.uint8) * 255
                dil = cv2.dilate(m, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3)), iterations=1)
                base_images.append(cv2.cvtColor(255 - dil, cv2.COLOR_GRAY2BGR))
            else:
                # Dilated mask (bridges dots into characters)
                th_mask = (sub_signal > 80).astype(np.uint8) * 255
                if np.count_nonzero(th_mask) > 30:
                    dil_mask = cv2.dilate(th_mask, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3)), iterations=1)
                    base_images.append(cv2.cvtColor(dil_mask, cv2.COLOR_GRAY2BGR))

                # Normalized signal (grayscale contrast enhancement)
                sig_clipped = np.clip(sub_signal, 0, None)
                if np.max(sig_clipped) > 0:
                    sig_norm = cv2.normalize(sig_clipped, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
                    base_images.append(cv2.cvtColor(sig_norm, cv2.COLOR_GRAY2BGR))

            if orient == "H":
                cand_rotations = [(0, None), (180, cv2.ROTATE_180)]
            elif orient == "V":
                cand_rotations = [(270, cv2.ROTATE_90_COUNTERCLOCKWISE), (90, cv2.ROTATE_90_CLOCKWISE)]
            else:
                cand_rotations = rotations

            corner_found = False
            for rot_deg, rot_code in cand_rotations:
                for bimg in base_images:
                    rot_img = bimg if rot_code is None else cv2.rotate(bimg, rot_code)
                    border_val = (255, 255, 255) if np.mean(bimg) > 127 else (0, 0, 0)
                    bordered = cv2.copyMakeBorder(rot_img, 20, 20, 20, 20, cv2.BORDER_CONSTANT, value=border_val)
                    try:
                        ocr_results = reader.readtext(bordered, allowlist="0123456789\x27:/- .", detail=1)
                    except Exception as e:
                        if verbose:
                            print(f"  OCR error: {e}")
                        continue

                    if not ocr_results:
                        continue

                    sorted_boxes = sorted(ocr_results, key=lambda res: min(pt[0] for pt in res[0]))
                    valid_boxes = [r for r in sorted_boxes if r[2] >= min_confidence]
                    if not valid_boxes:
                        continue

                    combined_text = " ".join(r[1].strip() for r in valid_boxes)
                    avg_conf = float(np.mean([r[2] for r in valid_boxes]))

                    parsed = parse_date_imprint(combined_text, default_order=date_format)
                    if parsed:
                        dt, fmt = parsed
                        candidate = {
                            "datetime": dt,
                            "formatted": fmt,
                            "raw_text": combined_text,
                            "confidence": avg_conf,
                            "corner": cname,
                            "rotation": rot_deg,
                        }
                        candidates.append(candidate)
                        if verbose:
                            print(f"  Candidate: {fmt} in {cname} (rot {rot_deg}deg, conf={avg_conf:.2f}, text={combined_text!r})")
                        if avg_conf >= 0.45:
                            corner_found = True
                            break
                if corner_found:
                    break
            if corner_found:
                break

        # If we already found a confident match (>= 0.45) in this corner, stop evaluating other corners
        if candidates and any(c["confidence"] >= 0.45 for c in candidates):
            break

    if candidates:
        best = max(candidates, key=lambda c: c["confidence"])
        return best

    return None


def apply_date_to_image_exif(
    image_path: Path,
    output_path: Optional[Path] = None,
    date_format: str = "auto",
    dry_run: bool = False,
    verbose: bool = False
) -> Optional[Dict[str, Any]]:
    """
    Read an image file, detect any camera date stamp, and write it to EXIF.
    Uses update_exif_date from exif_date_editor.
    """
    from exif_date_editor import update_exif_date

    img = cv2.imread(str(image_path))
    if img is None:
        return None

    result = detect_date_imprint(img, date_format=date_format, verbose=verbose)
    if not result:
        return None

    target_path = output_path if output_path else image_path
    dt = result["datetime"]

    success = update_exif_date(
        input_path=Path(image_path),
        output_path=Path(target_path),
        new_datetime=dt,
        dry_run=dry_run,
        verbose=verbose
    )

    if success:
        result["exif_written"] = True
        return result
    return None
