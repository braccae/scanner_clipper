import unittest
import tkinter as tk
from pathlib import Path
import tempfile
import shutil

import gui

class TestGUITkinter(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Create a temp directory for any file tests
        cls.temp_dir = tempfile.mkdtemp()
        cls.temp_path = Path(cls.temp_dir)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.temp_dir)

    def test_date_guessing(self):
        # Test the custom regex date guessing logic
        self.assertEqual(gui.guess_date_from_folder_name("Scans_1995-08_Trip"), "August 1995")
        self.assertEqual(gui.guess_date_from_folder_name("Vacation Aug 1998"), "August 1998")
        self.assertEqual(gui.guess_date_from_folder_name("Album_1985"), "1985")
        self.assertEqual(gui.guess_date_from_folder_name("No_Date_Folder"), "")

    def test_app_instantiation(self):
        # Verify that the Tkinter application initializes successfully without crashing
        root = tk.Tk()
        root.withdraw() # Hide window during test
        try:
            app = gui.PhotoUtilitiesApp(root)
            self.assertEqual(app.is_running, False)
            self.assertEqual(len(app.panels), 3)
            self.assertIn("clipper", app.panels)
            self.assertIn("resizer", app.panels)
            self.assertIn("exif", app.panels)
        finally:
            root.destroy()

if __name__ == "__main__":
    unittest.main()
