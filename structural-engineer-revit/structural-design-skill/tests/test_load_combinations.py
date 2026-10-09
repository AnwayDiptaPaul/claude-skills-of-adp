import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "codes"))
import load_combinations as combinations  # noqa: E402


class LoadCombinationTests(unittest.TestCase):
    def test_strength_combinations_has_eight_unique_cases(self):
        cases = combinations.strength_design_combinations(D=10, L=5, Lr=2, W=3, E=4, H=1)
        self.assertEqual(len(cases), 8)
        self.assertEqual(len(set(cases)), 8)


if __name__ == "__main__":
    unittest.main()