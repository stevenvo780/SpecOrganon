"""Executed outside SpecOrganon and retained with the source under test."""

import unittest

from count_units import count_units


class CountUnitsTests(unittest.TestCase):
    def test_total(self):
        self.assertEqual(count_units([1, 2, 3, 4]), 10)

    def test_empty(self):
        self.assertEqual(count_units([]), 0)

    def test_zero(self):
        self.assertEqual(count_units([0, 3]), 3)

    def test_invalid(self):
        for values in ([-1], [True], ["2"], [1.5]):
            with self.subTest(values=values), self.assertRaises(ValueError):
                count_units(values)


if __name__ == "__main__":
    unittest.main()
