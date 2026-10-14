import unittest
from textutil import slugify, wrap, parse_duration


class T(unittest.TestCase):
    def test_slug_basic(self):
        self.assertEqual(slugify("Hello, World!"), "hello-world")

    def test_slug_accents(self):
        self.assertEqual(slugify("Crème Brûlée"), "creme-brulee")

    def test_slug_edges(self):
        self.assertEqual(slugify("  --A  b--  "), "a-b")

    def test_wrap(self):
        self.assertEqual(wrap("the quick brown fox jumps", 10), ["the quick", "brown fox", "jumps"])

    def test_wrap_long_word(self):
        self.assertEqual(wrap("a supercalifragilistic b", 5), ["a", "supercalifragilistic", "b"])

    def test_duration(self):
        self.assertEqual(parse_duration("1h30m"), 5400)
        self.assertEqual(parse_duration("45s"), 45)

    def test_duration_invalid(self):
        with self.assertRaises(ValueError):
            parse_duration("abc")
        with self.assertRaises(ValueError):
            parse_duration("")


if __name__ == "__main__":
    unittest.main()
