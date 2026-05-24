#!/usr/bin/env python3
"""
EXIF Date Editor - Bulk edit and set 'Date Taken' tags in image metadata.

Supports JPEGs, WebP, and PNGs. Can modify files in-place or copy them to an output
folder. Offers both a flexible non-interactive CLI mode and a powerful interactive
walkthrough mode to date folders one-by-one (ideal for physical albums that have been scanned).
"""

import argparse
import os
import re
import sys
import shutil
import random
from pathlib import Path
from datetime import datetime, timedelta
from PIL import Image, ExifTags

# Supported image extensions that Pillow can handle EXIF for
SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".webp", ".png", ".tif", ".tiff"}


def parse_date(date_str: str) -> datetime:
    """
    Parse a wide variety of date/time formats and return a datetime object.
    
    Supported formats:
    - YYYY-MM-DD, YYYY:MM:DD, YYYY/MM/DD
    - YYYY-MM, YYYY:MM, YYYY/MM (defaults to 1st day of month)
    - YYYY (defaults to January 1st)
    - Month Name Year (e.g., "August 1995", "Aug 1995")
    - Year Month Name (e.g., "1995 August", "1995 Aug")
    """
    date_str = date_str.strip()
    if not date_str:
        raise ValueError("Empty date string")

    # Try full ISO-like dates (YYYY-MM-DD)
    for fmt in ("%Y-%m-%d", "%Y:%m:%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(date_str, fmt).replace(hour=12, minute=0, second=0)
        except ValueError:
            pass

    # Try year-month dates (YYYY-MM)
    for fmt in ("%Y-%m", "%Y:%m", "%Y/%m"):
        try:
            return datetime.strptime(date_str, fmt).replace(day=1, hour=12, minute=0, second=0)
        except ValueError:
            pass

    # Try single year (YYYY)
    if re.match(r"^\d{4}$", date_str):
        try:
            return datetime.strptime(date_str, "%Y").replace(month=1, day=1, hour=12, minute=0, second=0)
        except ValueError:
            pass

    # Normalized English Month Names
    months = {
        "january": 1, "jan": 1,
        "february": 2, "feb": 2,
        "march": 3, "mar": 3,
        "april": 4, "apr": 4,
        "may": 5,
        "june": 6, "jun": 6,
        "july": 7, "jul": 7,
        "august": 8, "aug": 8,
        "september": 9, "sep": 9, "sept": 9,
        "october": 10, "oct": 10,
        "november": 11, "nov": 11,
        "december": 12, "dec": 12
    }

    # Match Month + Year (e.g., "August 1995" or "Aug 1995")
    m1 = re.match(r"^([a-zA-Z]+)\s+(\d{4})$", date_str)
    if m1:
        month_name = m1.group(1).lower()
        year = int(m1.group(2))
        if month_name in months:
            return datetime(year, months[month_name], 1, 12, 0, 0)

    # Match Year + Month (e.g., "1995 August" or "1995 Aug")
    m2 = re.match(r"^(\d{4})\s+([a-zA-Z]+)$", date_str)
    if m2:
        year = int(m2.group(1))
        month_name = m2.group(2).lower()
        if month_name in months:
            return datetime(year, months[month_name], 1, 12, 0, 0)

    raise ValueError(
        f"Unsupported date format: '{date_str}'.\n"
        "Supported formats include: YYYY-MM-DD, YYYY-MM, YYYY, 'August 1995', '1995 August'"
    )


def update_exif_date(
    input_path: Path,
    output_path: Path,
    new_datetime: datetime,
    quality: int = 95,
    dry_run: bool = False,
    verbose: bool = False
) -> bool:
    """
    Open an image, update its EXIF date taken fields, and save it.
    
    Tags updated:
    - Base DateTime (306): date/time file was modified
    - Exif DateTimeOriginal (36867): date/time original photo was taken
    - Exif DateTimeDigitized (36868): date/time original photo was digitized
    """
    if dry_run:
        if verbose:
            print(f"[DRY RUN] Would update EXIF date of {input_path} to {new_datetime.strftime('%Y:%m:%d %H:%M:%S')}")
        return True

    try:
        # Load image
        with Image.open(input_path) as img:
            fmt = img.format
            exif = img.getexif()

            # Format datetime for EXIF specification (YYYY:MM:DD HH:MM:SS)
            date_str = new_datetime.strftime("%Y:%m:%d %H:%M:%S")

            # 1. Update Base tag (DateTime - 306)
            exif[ExifTags.Base.DateTime] = date_str

            # 2. Update Exif IFD tags (DateTimeOriginal - 36867, DateTimeDigitized - 36868)
            exif_ifd = exif.get_ifd(ExifTags.IFD.Exif)
            exif_ifd[ExifTags.Base.DateTimeOriginal] = date_str
            exif_ifd[ExifTags.Base.DateTimeDigitized] = date_str

            # Prepare safe save arguments
            save_args = {"exif": exif}
            if fmt in ("JPEG", "MPO", "WEBP"):
                save_args["quality"] = quality

            # Ensure parent directories exist
            output_path.parent.mkdir(parents=True, exist_ok=True)

            # If editing in-place, save to a temp file and replace to prevent corruption
            if input_path.resolve() == output_path.resolve():
                temp_path = output_path.with_name(f".tmp_{output_path.name}")
                try:
                    img.save(temp_path, format=fmt, **save_args)
                    # Close the original image context before replacing the file
                except Exception as e:
                    if temp_path.exists():
                        temp_path.unlink()
                    raise e
            else:
                img.save(output_path, format=fmt, **save_args)
                temp_path = None

        # Swap in-place if temp file was created
        if temp_path is not None:
            temp_path.replace(output_path)

        if verbose:
            print(f"Updated: {output_path.name} -> {date_str}")
        return True

    except Exception as e:
        print(f"  ERROR: Failed to update EXIF for {input_path.name}: {e}")
        return False


def get_image_files(directory: Path, recursive: bool = True) -> list[Path]:
    """Find all supported image files in a directory."""
    if recursive:
        paths = sorted(directory.rglob("*"))
    else:
        paths = sorted(directory.iterdir())
    
    return [p for p in paths if p.is_file() and p.suffix.lower() in SUPPORTED_EXTENSIONS]


def process_images(
    images: list[Path],
    input_dir: Path,
    output_dir: Path,
    base_date: datetime,
    increment_seconds: int = 60,
    random_time: bool = False,
    quality: int = 95,
    dry_run: bool = False,
    verbose: bool = False
) -> int:
    """Process a list of images, updating their EXIF dates sequentially."""
    if not images:
        return 0

    success_count = 0
    current_time = base_date

    # If random_time is requested, select a random start time during daylight hours (e.g. 09:00 - 17:00)
    if random_time:
        start_hour = random.randint(9, 16)
        start_minute = random.randint(0, 59)
        start_second = random.randint(0, 59)
        current_time = current_time.replace(hour=start_hour, minute=start_minute, second=start_second)

    for path in images:
        # Determine output file path (preserving structure if output_dir is different)
        if input_dir.resolve() == output_dir.resolve():
            target_path = path
        else:
            rel_path = path.relative_to(input_dir)
            target_path = output_dir / rel_path

        # Update metadata
        if update_exif_date(
            input_path=path,
            output_path=target_path,
            new_datetime=current_time,
            quality=quality,
            dry_run=dry_run,
            verbose=verbose
        ):
            success_count += 1

        # Increment time for the next image (maintains original sequence order)
        current_time += timedelta(seconds=increment_seconds)

    return success_count


def run_interactive_mode(
    input_dir: Path,
    output_dir: Path,
    recursive: bool = True,
    increment_seconds: int = 60,
    random_time: bool = False,
    quality: int = 95,
    dry_run: bool = False,
    verbose: bool = False
) -> int:
    """Interactively walk directories and ask the user for dates."""
    input_dir = input_dir.resolve()
    output_dir = output_dir.resolve()

    print("\n=== EXIF Date Editor: Interactive Walkthrough ===")
    print("This mode walks through each folder and asks you for its album date.")
    print("Press Enter to skip folders with no dates. Type 'q' or 'exit' to quit.\n")

    # Gather directories containing images
    dirs_to_check = [input_dir]
    if recursive:
        for p in sorted(input_dir.rglob("*")):
            if p.is_dir():
                dirs_to_check.append(p)

    total_processed = 0

    for current_dir in dirs_to_check:
        # Avoid traversing inside output directory if output is subfolder of input
        try:
            if current_dir.relative_to(output_dir) and current_dir.resolve() != output_dir.resolve():
                continue
        except ValueError:
            pass

        # Find images directly in this directory (non-recursively for interactive step)
        images = [
            p for p in sorted(current_dir.iterdir())
            if p.is_file() and p.suffix.lower() in SUPPORTED_EXTENSIONS
        ]

        if not images:
            continue

        rel_dir = current_dir.relative_to(input_dir)
        dir_display_name = str(rel_dir) if rel_dir != Path(".") else "Root Folder"
        
        print(f"\nFolder: '{dir_display_name}' ({len(images)} photo(s) found)")
        
        while True:
            user_input = input(
                "Enter date (e.g. '1995-08', 'Aug 1995', '1995', or press Enter to skip): "
            ).strip()

            if not user_input:
                print("Skipped.")
                break

            if user_input.lower() in ("q", "exit", "quit"):
                print("Exiting interactive mode.")
                return total_processed

            try:
                parsed_date = parse_date(user_input)
                print(f"Applying date: {parsed_date.strftime('%B %d, %Y at %I:%M %p')} (with {increment_seconds}s sequential increment)...")
                
                count = process_images(
                    images=images,
                    input_dir=input_dir,
                    output_dir=output_dir,
                    base_date=parsed_date,
                    increment_seconds=increment_seconds,
                    random_time=random_time,
                    quality=quality,
                    dry_run=dry_run,
                    verbose=verbose
                )
                
                print(f"Successfully updated {count} photo(s) in '{dir_display_name}'.")
                total_processed += count
                break
            except ValueError as e:
                print(f"Error: {e}. Please try again.")

    return total_processed


def main():
    parser = argparse.ArgumentParser(
        description="Bulk update EXIF 'Date Taken' metadata for photo albums.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Date Formats Supported:
  - YYYY-MM-DD (e.g., 1995-08-15)
  - YYYY-MM    (e.g., 1995-08)
  - YYYY       (e.g., 1995)
  - Month Year (e.g., "August 1995", "Aug 1995")
  - Year Month (e.g., "1995 August", "1995 Aug")

Examples:
  # Interactively walk folders in 'albums/' and set dates in-place:
  %(prog)s -i albums/

  # Set all photos in 'summer_vacation/' to July 1998 in-place without prompting:
  %(prog)s -i summer_vacation/ -d "July 1998"

  # Copy photos from 'raw_scans/' to 'dated_photos/' and apply a date sequentially:
  %(prog)s -i raw_scans/ -o dated_photos/ -d "1995-08-01"

  # Non-interactive update with random starting times and 2-minute steps:
  %(prog)s -i album/ -d "1996" --random-time --increment 120
        """
    )
    
    parser.add_argument(
        "-i", "--input",
        required=True,
        help="Input folder containing images, or path to a single image."
    )
    parser.add_argument(
        "-o", "--output",
        help="Output folder. If specified, photos are copied and saved here. If omitted, files are updated in-place."
    )
    parser.add_argument(
        "-d", "--date",
        help="Date to apply to photos. If omitted, script runs in Interactive Walkthrough mode."
    )
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Force Interactive Walkthrough mode, even if a directory is specified without a date."
    )
    parser.add_argument(
        "--no-recursive",
        action="store_true",
        help="Do not traverse input directories recursively."
    )
    parser.add_argument(
        "--increment",
        type=int,
        default=60,
        help="Time increment in seconds between sequential photos (default: 60)"
    )
    parser.add_argument(
        "--random-time",
        action="store_true",
        help="Randomize the starting time of day (between 9:00 AM and 5:00 PM) instead of using 12:00 PM."
    )
    parser.add_argument(
        "-q", "--quality",
        type=int,
        default=95,
        help="Saving quality 0-100 for JPEG/WebP formats (default: 95)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate the updates without writing changes to disk."
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print detailed execution logs."
    )

    args = parser.parse_args()

    # Resolve input and output paths
    script_dir = Path(__file__).parent
    input_path = Path(args.input)
    if not input_path.is_absolute():
        input_path = script_dir / input_path

    if not input_path.exists():
        print(f"Error: Input path does not exist: {input_path}")
        sys.exit(1)

    # Output defaults to input (in-place modification)
    if args.output:
        output_dir = Path(args.output)
        if not output_dir.is_absolute():
            output_dir = script_dir / output_dir
    else:
        output_dir = input_path if input_path.is_dir() else input_path.parent

    recursive = not args.no_recursive

    # Decide Mode: Interactive or Bulk
    is_single_file = input_path.is_file()
    
    # Force interactive mode if requested or if no date is specified for directory bulk
    run_interactive = args.interactive or (not is_single_file and not args.date)

    if run_interactive:
        if is_single_file:
            print("Error: Interactive walkthrough cannot be run on a single file. Provide a directory.")
            sys.exit(1)
        
        count = run_interactive_mode(
            input_dir=input_path,
            output_dir=output_dir,
            recursive=recursive,
            increment_seconds=args.increment,
            random_time=args.random_time,
            quality=args.quality,
            dry_run=args.dry_run,
            verbose=args.verbose or args.dry_run
        )
    else:
        # Non-interactive / bulk mode
        if not args.date:
            print("Error: A date is required in non-interactive/bulk mode. Use -d/--date.")
            sys.exit(1)

        try:
            parsed_date = parse_date(args.date)
        except ValueError as e:
            print(f"Error: {e}")
            sys.exit(1)

        if is_single_file:
            if input_path.suffix.lower() not in SUPPORTED_EXTENSIONS:
                print(f"Error: Single file format not supported: {input_path.name}")
                sys.exit(1)
            
            target_path = output_dir / input_path.name if args.output else input_path
            print(f"Processing single file: {input_path.name}")
            success = update_exif_date(
                input_path=input_path,
                output_path=target_path,
                new_datetime=parsed_date,
                quality=args.quality,
                dry_run=args.dry_run,
                verbose=True
            )
            count = 1 if success else 0
        else:
            # Multi-file directory bulk process
            images = get_image_files(input_path, recursive=recursive)
            if not images:
                print(f"No matching photos found in {input_path}")
                sys.exit(0)

            print(f"Found {len(images)} photo(s) in {input_path}")
            print(f"Applying date: {parsed_date.strftime('%B %d, %Y at %I:%M %p')} (incrementing sequentially)...")
            
            count = process_images(
                images=images,
                input_dir=input_path,
                output_dir=output_dir,
                base_date=parsed_date,
                increment_seconds=args.increment,
                random_time=args.random_time,
                quality=args.quality,
                dry_run=args.dry_run,
                verbose=args.verbose or args.dry_run
            )

    print("\n" + "=" * 60)
    if args.dry_run:
        print(f"[DRY RUN Completed] Would have processed {count} image(s).")
    else:
        print(f"Done! Successfully processed {count} image(s).")


if __name__ == "__main__":
    main()
