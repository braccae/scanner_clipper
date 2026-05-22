import unittest
import os
import sys
import shutil
import tempfile
import numpy as np
import cv2
from pathlib import Path

# Import function to test
import image_resizer

class TestImageResizer(unittest.TestCase):
    def setUp(self):
        # Create a temporary directory for test input and output files
        self.test_dir = tempfile.mkdtemp()
        self.input_dir = os.path.join(self.test_dir, "input")
        self.output_dir = os.path.join(self.test_dir, "output")
        os.makedirs(self.input_dir, exist_ok=True)
        os.makedirs(self.output_dir, exist_ok=True)

    def tearDown(self):
        # Clean up temporary directory
        shutil.rmtree(self.test_dir)

    def create_dummy_image(self, filename="photo.webp", size=(1200, 800)):
        """Creates a dummy image with given width and height."""
        width, height = size
        # Create a colorful image
        img = np.zeros((height, width, 3), dtype=np.uint8)
        # Draw a gradient
        for y in range(height):
            img[y, :, 0] = int(y / height * 255)
        for x in range(width):
            img[:, x, 1] = int(x / width * 255)
            
        file_path = os.path.join(self.input_dir, filename)
        cv2.imwrite(file_path, img)
        return file_path

    def test_get_resized_dimensions_scale(self):
        # Scaling by factor
        w, h = image_resizer.get_resized_dimensions(1200, 800, scale=0.5)
        self.assertEqual((w, h), (600, 400))

        w, h = image_resizer.get_resized_dimensions(1200, 800, scale=0.33)
        self.assertEqual((w, h), (396, 264))

        w, h = image_resizer.get_resized_dimensions(1200, 800, scale=1.0)
        self.assertEqual((w, h), (1200, 800))

    def test_get_resized_dimensions_max_dim(self):
        # Max-dimension constraint
        # Portrait
        w, h = image_resizer.get_resized_dimensions(800, 1200, max_dim=600)
        self.assertEqual((w, h), (400, 600))

        # Landscape
        w, h = image_resizer.get_resized_dimensions(1200, 800, max_dim=600)
        self.assertEqual((w, h), (600, 400))

        # Small image (no resize needed)
        w, h = image_resizer.get_resized_dimensions(300, 200, max_dim=600)
        self.assertEqual((w, h), (300, 200))

    def test_process_directory_basic(self):
        self.create_dummy_image("photo1.webp", size=(1200, 800))
        self.create_dummy_image("photo2.png", size=(600, 900))

        # Process directory with 0.5 scale factor, converting to jpg
        count = image_resizer.process_directory(
            input_dir=Path(self.input_dir),
            output_dir=Path(self.output_dir),
            scale=0.5,
            output_format="jpg"
        )

        self.assertEqual(count, 2)
        
        # Verify output files exist and are JPG
        out_files = os.listdir(self.output_dir)
        self.assertIn("photo1.jpg", out_files)
        self.assertIn("photo2.jpg", out_files)

        # Check dimensions
        img1 = cv2.imread(os.path.join(self.output_dir, "photo1.jpg"))
        self.assertEqual(img1.shape[:2], (400, 600))  # height, width

        img2 = cv2.imread(os.path.join(self.output_dir, "photo2.jpg"))
        self.assertEqual(img2.shape[:2], (450, 300))  # height, width

    def test_process_directory_recursive(self):
        # Create nested folders
        sub_dir = os.path.join(self.input_dir, "subfolder")
        os.makedirs(sub_dir, exist_ok=True)
        
        # Image in root input
        self.create_dummy_image("photo_root.webp", size=(1000, 1000))
        
        # Image in subfolder
        img = np.zeros((600, 600, 3), dtype=np.uint8)
        sub_img_path = os.path.join(sub_dir, "photo_sub.webp")
        cv2.imwrite(sub_img_path, img)

        # Process directory recursively
        count = image_resizer.process_directory(
            input_dir=Path(self.input_dir),
            output_dir=Path(self.output_dir),
            scale=0.5,
            output_format="jpg",
            recursive=True
        )

        self.assertEqual(count, 2)
        
        # Check root output
        self.assertTrue(os.path.exists(os.path.join(self.output_dir, "photo_root.jpg")))
        
        # Check nested output
        sub_out_dir = os.path.join(self.output_dir, "subfolder")
        self.assertTrue(os.path.isdir(sub_out_dir))
        self.assertTrue(os.path.exists(os.path.join(sub_out_dir, "photo_sub.jpg")))

    def test_cli_execution(self):
        self.create_dummy_image("cli_photo.png", size=(1000, 800))
        
        import subprocess
        result = subprocess.run(
            [sys.executable, "image_resizer.py", "-i", self.input_dir, "-o", self.output_dir, "-s", "0.25", "-f", "jpg"],
            capture_output=True,
            text=True
        )
        
        self.assertEqual(result.returncode, 0)
        out_files = os.listdir(self.output_dir)
        self.assertIn("cli_photo.jpg", out_files)
        
        img = cv2.imread(os.path.join(self.output_dir, "cli_photo.jpg"))
        self.assertEqual(img.shape[:2], (200, 250))  # 1000x800 * 0.25 = 250x200

if __name__ == "__main__":
    unittest.main()
