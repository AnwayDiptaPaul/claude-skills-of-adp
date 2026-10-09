import sys
import types
import unittest
from pathlib import Path

# Import the orchestration module without requiring the optional OpenSeesPy
# binary in a documentation/test-only environment.
openseespy = types.ModuleType("openseespy")
opensees = types.ModuleType("openseespy.opensees")
openseespy.opensees = opensees
sys.modules.setdefault("openseespy", openseespy)
sys.modules.setdefault("openseespy.opensees", opensees)
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import run_analysis  # noqa: E402


class FakeOps:
    def eleForce(self, tag):
        return [10, 11, 12, 13, 14, 15, -10, -11, -12, -13, -14, -15]


class MemberForceRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.original_ops = run_analysis.ops
        run_analysis.ops = FakeOps()

    def tearDown(self):
        run_analysis.ops = self.original_ops

    def test_recovers_raw_actions_and_design_aliases(self):
        element_map = {
            "COL-1": {"tag": 1, "is_vertical": True},
            "BM-1": {"tag": 2, "is_vertical": False},
        }
        actions = run_analysis.recover_member_forces(element_map, [], "test")
        self.assertEqual(actions["COL-1"]["local_moment_y_knm_i"], 14.0)
        self.assertEqual(actions["COL-1"]["moment_for_x_load_knm_i"], 14.0)
        self.assertEqual(actions["COL-1"]["moment_for_y_load_knm_i"], 15.0)
        self.assertEqual(actions["BM-1"]["gravity_moment_knm_i"], 14.0)
        self.assertEqual(actions["BM-1"]["shear_vertical_kn_i"], 12.0)


if __name__ == "__main__":
    unittest.main()