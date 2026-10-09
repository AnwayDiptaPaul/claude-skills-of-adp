"""
scripts/build_fe_model.py — constructs an openseespy 3D linear-elastic
frame model (nodes, elements, boundary conditions, lumped mass) from a
structural_model.json already enriched by revit-structure-recognition,
revit-load-application, dynamic-load, and load-path.

UNITS -- READ THIS BEFORE TOUCHING ANYTHING BELOW: the whole model is built
in a consistent kN / metre / tonne / second system (matching this pipeline's
own kN-m convention throughout, rather than the mm/MPa convention
section_hint and material.names naturally parse into). Every quantity that
enters openseespy is converted at the boundary, once, in _to_model_units():
  - length: mm -> m (divide by 1000)
  - E, G (from codes/materials.py, in MPa = N/mm^2): MPa -> kN/m^2
    (multiply by 1000; 1 N/mm^2 = 1e6 N/m^2 = 1000 kN/m^2)
  - section area: mm^2 -> m^2 (divide by 1e6)
  - moment of inertia / J: mm^4 -> m^4 (divide by 1e12)
  - mass: a weight in kN becomes a mass of (kN)/(9.81 m/s^2), which -- in
    this kN-m-s system -- comes out numerically in tonnes (1 tonne mass
    under kN-m-s gives F(kN) = mass(tonne) * a(m/s^2) exactly, the same
    arithmetic as the more familiar kg/N/m/s system scaled by 1000).
Mixing an unconverted mm/MPa value into this model would silently produce
a stiffness matrix wrong by a large, unit-dependent factor -- there is
exactly one conversion point (this module) and every other script in this
skill works in kN-m from there on.

LOCAL AXES AND eleLoad -- VERIFIED EMPIRICALLY, NOT ASSUMED: with the
reference-vector convention used below (vertical elements: (1,0,0);
horizontal elements: (0,0,1)), a vertical (downward) uniform load on a
COLUMN belongs in eleLoad's third slot (Wx -- axial, since a column's
local-x runs along its own vertical length), while the SAME downward load
on a BEAM belongs in the SECOND slot (Wz -- transverse), regardless of
whether the beam runs along global-X or global-Y. This was confirmed with
an isolated two-node test (apply a unit load in each of the three slots,
observe which one produces global-vertical vs. global-horizontal tip
displacement) rather than assumed from the geomTransf documentation alone
-- getting this wrong silently produces a model that "runs" (no error) but
applies gravity as an axial beam force or an in-plane column shear instead
of the intended downward load. See run_analysis.py's apply_self_weight()
for where this actually gets used.

SCOPE: columns and beams (framing) only, as elasticBeamColumn elements --
a linear-elastic 3D moment-frame idealization. Walls are NOT modeled as
shell/wall elements here; see SKILL.md's Known Limitations for why (a
materially harder modeling problem, and this pipeline's stated practice is
RCC frame buildings). Boundary conditions are a simple fixed base at the
lowest story -- no soil-spring/geotechnical stiffness, which is out of
scope for this skill (substructure/geotechnical analysis isn't attempted
here at all -- see SKILL.md).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "codes"))
import materials as mat  # noqa: E402

MM_TO_M = 1.0 / 1000.0
MPA_TO_KN_M2 = 1000.0
MM2_TO_M2 = 1.0 / 1_000_000.0
MM4_TO_M4 = 1.0 / 1_000_000_000_000.0
G_ACCEL_M_S2 = 9.81


def _round_coord(pt_mm):
    """Rounds to the nearest mm before converting -- coordinate matching
    across elements needs exact-enough equality, and Revit-exported
    coordinates occasionally carry float noise at sub-mm scale."""
    return tuple(round(c, 0) for c in pt_mm)


class NodeRegistry:
    """Maps a (rounded) mm coordinate to a single integer openseespy node
    tag, creating the node the first time that coordinate is seen. Two
    elements whose endpoints coincide (a column meeting a beam at a floor
    level) automatically share one node -- this IS the mechanism that
    connects the model, not an afterthought."""
    def __init__(self, ops):
        self.ops = ops
        self._coord_to_tag = {}
        self._tag_to_coord = {}
        self._next_tag = 1

    def get_or_create(self, pt_mm):
        key = _round_coord(pt_mm)
        if key in self._coord_to_tag:
            return self._coord_to_tag[key]
        tag = self._next_tag
        self._next_tag += 1
        x_m, y_m, z_m = (c * MM_TO_M for c in pt_mm)
        self.ops.node(tag, x_m, y_m, z_m)
        self._coord_to_tag[key] = tag
        self._tag_to_coord[tag] = (x_m, y_m, z_m)
        return tag

    def tags_at_elevation(self, z_m, tol=1e-6):
        return [t for t, (x, y, z) in self._tag_to_coord.items() if abs(z - z_m) < tol]

    def all_tags(self):
        return list(self._tag_to_coord.keys())


def resolve_element_section_and_material(element, needs_review):
    """Shared by columns and framing. Returns (section_props_model_units,
    material_props_model_units) or (None, None) if either fails -- callers
    must skip the element (excluded from the model, not defaulted) and the
    failure is already appended to needs_review."""
    section_hint = element.get("section_hint")
    section = mat.parse_rectangular_section(section_hint)
    if section is None:
        needs_review.append({"element": element["id"], "reason":
            f"section_hint={section_hint!r} did not parse as a rectangular WIDTHxDEPTH "
            f"section -- excluded from the FE model entirely (not defaulted to a guessed size)"})
        return None, None
    geo = mat.rectangular_section_properties(section["width_mm"], section["depth_mm"])
    section_model = {
        "A_m2": geo["A_mm2"] * MM2_TO_M2, "Iz_m4": geo["Iz_mm4"] * MM4_TO_M4,
        "Iy_m4": geo["Iy_mm4"] * MM4_TO_M4, "J_m4": geo["J_mm4"] * MM4_TO_M4,
        "width_mm": section["width_mm"], "depth_mm": section["depth_mm"],
    }

    frame_type = (element.get("frame_type") or {}).get("value")
    material_result = mat.resolve_material(element.get("material"), frame_type)
    if "reason" in material_result:
        needs_review.append({"element": element["id"], "reason":
            f"material resolution failed: {material_result['reason']} -- excluded from the FE model"})
        return None, None
    material_model = {
        "E_kn_m2": material_result["E_mpa"] * MPA_TO_KN_M2,
        "G_kn_m2": material_result["G_mpa"] * MPA_TO_KN_M2,
        "unit_weight_kn_m3": material_result["unit_weight_kn_m3"],
        "source": material_result["source"],
    }
    return section_model, material_model


def build_model(structural_model, ops):
    """Constructs the full openseespy model in-place (calls ops.wipe(),
    ops.model(...), ops.node(...), ops.element(...), ops.fix(...)). Returns
    (node_registry, element_map, needs_review) where element_map maps this
    pipeline's own element id ('COL-A1-1') to the integer openseespy
    element tag actually created for it -- elements that failed to
    resolve a section/material are simply absent from element_map, not
    mapped to a placeholder."""
    needs_review = []
    ops.wipe()
    ops.model("basic", "-ndm", 3, "-ndf", 6)
    nodes = NodeRegistry(ops)
    element_map = {}
    transf_tag = 1
    ele_tag = 1

    stories = sorted(structural_model.get("stories", []), key=lambda s: s["elevation_mm"])
    base_elevation_mm = stories[0]["elevation_mm"] if stories else 0.0

    def make_frame_element(el, pt1_mm, pt2_mm, is_vertical):
        nonlocal transf_tag, ele_tag
        section, material = resolve_element_section_and_material(el, needs_review)
        if section is None:
            return
        n1 = nodes.get_or_create(pt1_mm)
        n2 = nodes.get_or_create(pt2_mm)
        if n1 == n2:
            needs_review.append({"element": el["id"], "reason":
                "both endpoints resolved to the same node (zero-length element) -- skipped"})
            return
        # Local-axis reference vector: openseespy's geomTransf needs a
        # vector NOT parallel to the element axis to define the local
        # y-z orientation. Vertical elements (columns) use a horizontal
        # reference (1,0,0); horizontal elements (beams) use the global
        # vertical (0,0,1) -- the standard convention for this exact
        # reason (a vertical element has no unique orientation from its
        # own axis alone; a horizontal one does, via gravity).
        ref_vector = (1.0, 0.0, 0.0) if is_vertical else (0.0, 0.0, 1.0)
        ops.geomTransf("Linear", transf_tag, *ref_vector)
        ops.element("elasticBeamColumn", ele_tag, n1, n2,
                    section["A_m2"], material["E_kn_m2"], material["G_kn_m2"],
                    section["J_m4"], section["Iy_m4"], section["Iz_m4"], transf_tag)
        element_map[el["id"]] = {"tag": ele_tag, "node_i": n1, "node_j": n2,
                                  "section": section, "material": material, "is_vertical": is_vertical,
                                  "length_m": sum((a - b) ** 2 for a, b in
                                                   zip((c * MM_TO_M for c in pt1_mm),
                                                       (c * MM_TO_M for c in pt2_mm))) ** 0.5}
        transf_tag += 1
        ele_tag += 1

    for col in structural_model.get("elements", {}).get("columns", []):
        pts = col.get("axis_points_mm")
        if not pts or len(pts) != 2:
            needs_review.append({"element": col["id"], "reason": "missing/malformed axis_points_mm -- excluded"})
            continue
        make_frame_element(col, pts[0], pts[1], is_vertical=True)

    for beam in structural_model.get("elements", {}).get("framing", []):
        pts = beam.get("axis_points_mm")
        if not pts or len(pts) != 2:
            needs_review.append({"element": beam["id"], "reason": "missing/malformed axis_points_mm -- excluded"})
            continue
        make_frame_element(beam, pts[0], pts[1], is_vertical=False)

    # Boundary conditions: fixed base at the lowest story's nodes. No
    # soil-spring stiffness -- see module/SKILL.md scope note.
    base_z_m = base_elevation_mm * MM_TO_M
    base_nodes = nodes.tags_at_elevation(base_z_m)
    if not base_nodes:
        needs_review.append({"reason": f"no nodes found at the base elevation ({base_elevation_mm}mm) "
                                        f"-- no boundary conditions applied, model is unrestrained"})
    for n in base_nodes:
        ops.fix(n, 1, 1, 1, 1, 1, 1)

    return nodes, element_map, needs_review, base_nodes
