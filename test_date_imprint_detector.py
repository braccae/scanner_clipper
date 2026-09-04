#!/usr/bin/env python3
import unittest
from datetime import datetime
import numpy as np
import cv2
from date_imprint_detector import parse_date_imprint, extract_photo_corners, get_amber_signal

class TestDateImprintDetector(unittest.TestCase):
    def test_parse_leading_year(self):
        # 'YY M D formats
        res = parse_date_imprint("'94 1 5")
        self.assertIsNotNone(res)
        dt, formatted = res
        self.assertEqual(formatted, "1994-01-05")
        self.assertEqual(dt.year, 1994)
        self.assertEqual(dt.month, 1)
        self.assertEqual(dt.day, 5)

        # 'YY MM DD
        res = parse_date_imprint("'94 01 05")
        self.assertIsNotNone(res)
        self.assertEqual(res[1], "1994-01-05")

        # Merged digits '94 15 -> 1994-01-05
        res = parse_date_imprint("'94 15")
        self.assertIsNotNone(res)
        self.assertEqual(res[1], "1994-01-05")

        # '94 1 1
        res = parse_date_imprint("'94 1 1")
        self.assertIsNotNone(res)
        self.assertEqual(res[1], "1994-01-01")

        # OCR apostrophe merger misreads: '94 read as 294, 794, 094, 44
        self.assertEqual(parse_date_imprint("294 1 5")[1], "1994-01-05")
        self.assertEqual(parse_date_imprint("794 1 5")[1], "1994-01-05")
        self.assertEqual(parse_date_imprint("44 1 5")[1], "1994-01-05")

    def test_parse_trailing_year(self):
        # MM DD 'YY formats
        res = parse_date_imprint("9 24 '02")
        self.assertIsNotNone(res)
        dt, formatted = res
        self.assertEqual(formatted, "2002-09-24")
        self.assertEqual(dt.year, 2002)
        self.assertEqual(dt.month, 9)
        self.assertEqual(dt.day, 24)

        # 9 25 '02
        res = parse_date_imprint("9 25 '02")
        self.assertIsNotNone(res)
        self.assertEqual(res[1], "2002-09-25")

        # 9 25 2
        res = parse_date_imprint("9 25 2")
        self.assertIsNotNone(res)
        self.assertEqual(res[1], "2002-09-25")

    def test_parse_disambiguation(self):
        # Day > 12 forces day position regardless of input order
        res1 = parse_date_imprint("9 25 '02")
        self.assertEqual(res1[1], "2002-09-25")

        res2 = parse_date_imprint("25 9 '02")
        self.assertEqual(res2[1], "2002-09-25")

    def test_invalid_dates_rejected(self):
        # Incomplete (only day and year, missing month)
        self.assertIsNone(parse_date_imprint("24 '02"))
        self.assertIsNone(parse_date_imprint("25 '02"))

        # Year in the future (e.g. upside down read '94 as 2066)
        self.assertIsNone(parse_date_imprint("5 1 66"))

        # Invalid month/day combinations (both > 12, or month 0)
        self.assertIsNone(parse_date_imprint("'94 13 32"))
        self.assertIsNone(parse_date_imprint("'94 00 05"))

        # Invalid day
        self.assertIsNone(parse_date_imprint("'94 02 30"))

    def test_extract_photo_corners(self):
        dummy = np.zeros((1000, 1200, 3), dtype=np.uint8)
        corners = extract_photo_corners(dummy, width_ratio=0.35, height_ratio=0.25)
        self.assertIn("BR", corners)
        self.assertIn("BL", corners)
        self.assertIn("TR", corners)
        self.assertIn("TL", corners)
        self.assertEqual(corners["BR"].shape[0], 250)
        self.assertEqual(corners["BR"].shape[1], 420)

    def test_get_amber_signal(self):
        # Amber pixel (high R, medium G, low B)
        amber_img = np.zeros((10, 10, 3), dtype=np.uint8)
        amber_img[:, :] = [50, 180, 240]  # BGR
        signal = get_amber_signal(amber_img)
        self.assertTrue(np.all(signal > 100))

        # White pixel (equal R, G, B)
        white_img = np.ones((10, 10, 3), dtype=np.uint8) * 255
        signal_white = get_amber_signal(white_img)
        self.assertTrue(np.all(signal_white <= 0))

if __name__ == "__main__":
    unittest.main()
