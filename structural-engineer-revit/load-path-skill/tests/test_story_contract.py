import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import trace_load_path as load_path  # noqa: E402


class StoryContractTests(unittest.TestCase):
    def setUp(self):
        self.model = {
            "stories": [
                {"id": "ifc-ground", "global_id": "ifc-ground", "name": "Ground", "index": 0, "elevation_mm": 0},
                {"id": "ifc-l01", "global_id": "ifc-l01", "name": "Level 1", "index": 1, "elevation_mm": 3000},
                {"id": "ifc-l02", "global_id": "ifc-l02", "name": "Level 2", "index": 2, "elevation_mm": 6000},
            ]
        }

    def test_canonical_wall_story_references_trace_without_key_error(self):
        walls = [{
            "id": "WALL-1", "grid_ref": {"along_gridline": "A"},
            "base_story": {"id": "ifc-ground", "name": "Ground"},
            "top_story": {"id": "ifc-l02", "name": "Level 2"},
        }]
        review = []
        result = load_path.trace_lateral_continuity(self.model, walls, review)
        self.assertEqual(review, [])
        self.assertEqual(result["lines_traced"][0]["gap_stories"], [])

    def test_legacy_story_range_remains_readable(self):
        walls = [{
            "id": "WALL-legacy", "grid_ref": {"along_gridline": "A"},
            "story_range": {"base": "ifc-ground", "top": "ifc-l01"},
        }]
        result = load_path.trace_lateral_continuity(self.model, walls, [])
        self.assertEqual(len(result["lines_traced"]), 1)


if __name__ == "__main__":
    unittest.main()