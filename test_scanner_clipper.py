import unittest
import os
import sys
import shutil
import tempfile
import zipfile
import numpy as np
import cv2
from pathlib import Path

# Import functions to test
import scanner_clipper

class TestScannerClipper(unittest.TestCase):
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

    def create_dummy_scan(self, filename="scan1.webp", num_photos=2):
        """Creates a dummy scanned image with distinct 'photos' inside a white background."""
        # 1000x1000 white canvas
        img = np.ones((1000, 1000, 3), dtype=np.uint8) * 255
        
        # Add a couple of distinct darker rectangles (photos)
        # Photo 1: Top-Left, roughly 300x200
        cv2.rectangle(img, (100, 100), (400, 300), (50, 50, 50), -1)
        
        # Photo 2: Bottom-Right, roughly 400x300
        if num_photos > 1:
            cv2.rectangle(img, (500, 500), (900, 800), (100, 100, 100), -1)
            
        file_path = os.path.join(self.input_dir, filename)
        cv2.imwrite(file_path, img)
        return file_path

    def test_order_points(self):
        pts = np.array([[100, 100], [400, 100], [400, 300], [100, 300]], dtype="float32")
        # Shuffle order to test ordering logic
        shuffled = np.array([pts[2], pts[0], pts[3], pts[1]], dtype="float32")
        ordered = scanner_clipper.order_points(shuffled)
        
        # top-left, top-right, bottom-right, bottom-left
        np.testing.assert_array_almost_equal(ordered[0], pts[0])
        np.testing.assert_array_almost_equal(ordered[1], pts[1])
        np.testing.assert_array_almost_equal(ordered[2], pts[2])
        np.testing.assert_array_almost_equal(ordered[3], pts[3])

    def test_detect_photos(self):
        scan_path = self.create_dummy_scan("scan_detect.webp", num_photos=2)
        photos = scanner_clipper.detect_photos(scan_path, debug=False)
        
        # Expecting at least 2 photos
        self.assertEqual(len(photos), 2)
        for photo in photos:
            self.assertIsNotNone(photo)
            self.assertTrue(photo.shape[0] > 50)
            self.assertTrue(photo.shape[1] > 50)

    def test_process_folder_standalone(self):
        # Create a single scanned image
        self.create_dummy_scan("scan_standalone.webp", num_photos=2)
        
        # Process the folder
        scanner_clipper.process_folder(self.input_dir, self.output_dir, debug=False)
        
        # Check files in output directory
        output_files = os.listdir(self.output_dir)
        # Should have scan_standalone_photo_01.webp and scan_standalone_photo_02.webp
        expected_files = ["scan_standalone_photo_01.webp", "scan_standalone_photo_02.webp"]
        for f in expected_files:
            self.assertIn(f, output_files)

    def test_process_folder_zip(self):
        # Create temporary dummy scan and zip it
        dummy_scan_path = self.create_dummy_scan("zip_scan.webp", num_photos=1)
        
        zip_path = os.path.join(self.input_dir, "scans.zip")
        with zipfile.ZipFile(zip_path, 'w') as z:
            z.write(dummy_scan_path, arcname="zip_scan.webp")
            
        # Delete original image so we only process the zip
        os.remove(dummy_scan_path)
        
        # Process the folder
        scanner_clipper.process_folder(self.input_dir, self.output_dir, debug=False)
        
        # Should have created a subdirectory named 'scans' with the extracted images
        zip_out_dir = os.path.join(self.output_dir, "scans")
        self.assertTrue(os.path.isdir(zip_out_dir))
        
        zip_out_files = os.listdir(zip_out_dir)
        # The script renames files sequentially when in a ZIP: {zip_name}_{count:03d}.ext
        self.assertEqual(len(zip_out_files), 1)
        self.assertEqual(zip_out_files[0], "scans_001.webp")

    def test_cli_execution(self):
        # Verify execution via subprocess as a CLI tool
        self.create_dummy_scan("scan_cli.webp", num_photos=1)
        
        import subprocess
        result = subprocess.run(
            [sys.executable, "scanner_clipper.py", "-i", self.input_dir, "-o", self.output_dir],
            capture_output=True,
            text=True
        )
        
        self.assertEqual(result.returncode, 0)
        output_files = os.listdir(self.output_dir)
        self.assertIn("scan_cli_photo_01.webp", output_files)

if __name__ == "__main__":
    unittest.main()
