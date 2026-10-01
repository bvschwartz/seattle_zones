import unittest

from seattle_zones.directions import NONE, parse_direction


class ParseDirectionTest(unittest.TestCase):
    def test_prefix(self):
        self.assertEqual(parse_direction("NE 45th St"), "NE")
        self.assertEqual(parse_direction("Northeast 45th Street"), "NE")
        self.assertEqual(parse_direction("Southwest Alaska Street"), "SW")
        self.assertEqual(parse_direction("E Pine St"), "E")
        self.assertEqual(parse_direction("W. Mercer St."), "W")

    def test_suffix(self):
        self.assertEqual(parse_direction("15th Ave NE"), "NE")
        self.assertEqual(parse_direction("Aurora Avenue North"), "N")
        self.assertEqual(parse_direction("Rainier Avenue South"), "S")
        self.assertEqual(parse_direction("23rd Avenue East"), "E")
        self.assertEqual(parse_direction("California Ave SW"), "SW")

    def test_suffix_wins_over_prefix(self):
        self.assertEqual(parse_direction("East Marginal Way South"), "S")
        self.assertEqual(parse_direction("West Marginal Way Southwest"), "SW")

    def test_no_direction(self):
        self.assertEqual(parse_direction("Pike Street"), NONE)
        self.assertEqual(parse_direction("3rd Avenue"), NONE)
        self.assertEqual(parse_direction("West Seattle Bridge"), NONE)
        self.assertEqual(parse_direction("Eastlake"), NONE)
        self.assertIsNone(parse_direction(""))


if __name__ == "__main__":
    unittest.main()
