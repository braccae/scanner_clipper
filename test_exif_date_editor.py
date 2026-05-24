import unittest
import os
import sys
import shutil
import tempfile
from pathlib import Path
from datetime import datetime
from PIL import Image, ExifTags

# Import module to test
import exif_date_editor


class TestExifDateEditor(unittest.TestCase):
    def setUp(self):
        # Create a temporary directory for test files
        self.test_dir = tempfile.mkdtemp()
        self.input_dir = os.path.join(self.test_dir, "input")
        self.output_dir = os.path.join(self.test_dir, "output")
        os.makedirs(self.input_dir, exist_ok=True)
        os.makedirs(self.output_dir, exist_ok=True)

    def tearDown(self):
        # Clean up temporary directory
        shutil.rmtree(self.test_dir)

    def create_dummy_image(self, filename="photo.jpg", size=(100, 100)):
        """Creates a dummy image using Pillow and saves it."""
        img = Image.new("RGB", size, color="blue")
        file_path = os.path.join(self.input_dir, filename)
        img.save(file_path)
        return Path(file_path)

    def test_parse_date_formats(self):
        # Full date YYYY-MM-DD
        dt = exif_date_editor.parse_date("1995-08-15")
        self.assertEqual(dt.year, 1995)
        self.assertEqual(dt.month, 8)
        self.assertEqual(dt.day, 15)
        self.assertEqual(dt.hour, 12)

        # Full date colon/slash separated
        dt = exif_date_editor.parse_date("1995:08:15")
        self.assertEqual(dt.year, 1995)
        self.assertEqual(dt.month, 8)
        self.assertEqual(dt.day, 15)

        dt = exif_date_editor.parse_date("1995/08/15")
        self.assertEqual(dt.year, 1995)
        self.assertEqual(dt.month, 8)
        self.assertEqual(dt.day, 15)

        # Month and year YYYY-MM
        dt = exif_date_editor.parse_date("1995-08")
        self.assertEqual(dt.year, 1995)
        self.assertEqual(dt.month, 8)
        self.assertEqual(dt.day, 1)

        # Single Year
        dt = exif_date_editor.parse_date("1995")
        self.assertEqual(dt.year, 1995)
        self.assertEqual(dt.month, 1)
        self.assertEqual(dt.day, 1)

        # Named Month and Year (Aug 1995, August 1995)
        dt = exif_date_editor.parse_date("August 1995")
        self.assertEqual(dt.year, 1995)
        self.assertEqual(dt.month, 8)
        self.assertEqual(dt.day, 1)

        dt = exif_date_editor.parse_date("Aug 1995")
        self.assertEqual(dt.year, 1995)
        self.assertEqual(dt.month, 8)

        dt = exif_date_editor.parse_date("1995 Aug")
        self.assertEqual(dt.year, 1995)
        self.assertEqual(dt.month, 8)

        # Unsupported formats should raise ValueError
        with self.assertRaises(ValueError):
            exif_date_editor.parse_date("not-a-date")

        with self.assertRaises(ValueError):
            exif_date_editor.parse_date("95-08-15") # Only 4-digit years supported

    def test_update_exif_date(self):
        img_path = self.create_dummy_image("test_exif.jpg")
        target_date = datetime(1993, 5, 20, 14, 30, 0)

        # Run update
        success = exif_date_editor.update_exif_date(
            input_path=img_path,
            output_path=img_path,
            new_datetime=target_date,
            quality=90
        )
        self.assertTrue(success)

        # Reload and check EXIF tags
        with Image.open(img_path) as reloaded_img:
            exif = reloaded_img.getexif()
            
            # Base tag Check
            date_str = target_date.strftime("%Y:%m:%d %H:%M:%S")
            self.assertEqual(exif.get(ExifTags.Base.DateTime), date_str)

            # Exif IFD Subtags Check
            exif_ifd = exif.get_ifd(ExifTags.IFD.Exif)
            self.assertEqual(exif_ifd.get(ExifTags.Base.DateTimeOriginal), date_str)
            self.assertEqual(exif_ifd.get(ExifTags.Base.DateTimeDigitized), date_str)

    def test_process_images_sequential(self):
        # Create 3 images
        img1 = self.create_dummy_image("img1.jpg")
        img2 = self.create_dummy_image("img2.jpg")
        img3 = self.create_dummy_image("img3.jpg")
        images = [img1, img2, img3]

        start_date = datetime(1996, 7, 4, 12, 0, 0)
        
        # Process and increment by 10 minutes (600 seconds)
        count = exif_date_editor.process_images(
            images=images,
            input_dir=Path(self.input_dir),
            output_dir=Path(self.output_dir), # Save to output_dir
            base_date=start_date,
            increment_seconds=600,
            quality=95
        )

        self.assertEqual(count, 3)

        # Verify sequential times in output dir
        out_img1 = Path(self.output_dir) / "img1.jpg"
        out_img2 = Path(self.output_dir) / "img2.jpg"
        out_img3 = Path(self.output_dir) / "img3.jpg"

        with Image.open(out_img1) as im1:
            ex1 = im1.getexif()
            self.assertEqual(ex1.get(ExifTags.Base.DateTime), "1996:07:04 12:00:00")

        with Image.open(out_img2) as im2:
            ex2 = im2.getexif()
            self.assertEqual(ex2.get(ExifTags.Base.DateTime), "1996:07:04 12:10:00")

        with Image.open(out_img3) as im3:
            ex3 = im3.getexif()
            self.assertEqual(ex3.get(ExifTags.Base.DateTime), "1996:07:04 12:20:00")


if __name__ == "__main__":
    unittest.main()
