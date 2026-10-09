#!/usr/bin/env python3
"""
scripts/run_analysis.py — the entry point for this skill. Builds the FE
model (build_fe_model.build_model), runs a static gravity analysis
(self-weight only -- see Known Limitations), assigns lumped mass from
dynamic-load's own story weights and runs a real eigenvalue analysis
(computed periods, mode shapes, mass participation -- the thing every
upstream skill's "approximate period" and "rsa: null-until-this-exists"
language has been pointing at), applies dynamic-load's ESFP story forces as
a static lateral case per direction, and runs response spectrum analysis by
combining these real modal properties with dynamic-load's own verified
design spectrum curve (consumed as portable DATA, not by importing
dynamic-load's code -- see that skill's schema.md on why the curve is
shaped that way).

Usage:
    python3 run_analysis.py --structural-model structural_model.json --out output_dir/

SCOPE: linear-elastic static and eigenvalue/response-spectrum analysis of
the superstructure frame (columns + beams) only. NOT attempted, all for
reasons documented in SKILL.md: substructure/geotechnical analysis (soil-
structure interaction, settlement, bearing capacity), wall/shell modeling
(shear walls are excluded from the FE model entirely, not approximated),
time-history analysis of either kind (needs actual ground motion records),
nonlinear static/pushover, and superimposed-dead/live gravity load detail
beyond self-weight (see apply_self_weight()'s own docstring).
"""
import argparse
import json
import sys
from pathlib import Path

import openseespy.opensees as ops

sys.path.insert(0, str(Path(__file__).parent))
from build_fe_model import build_model, G_ACCEL_M_S2  # noqa: E402


def apply_self_weight(element_map):
    """Self-weight only -- NOT superimposed dead load, live load, or any
    of revit-load-application's panel-derived beam loads. Applying those
    correctly means mapping each panel's reaction-equivalent intensity onto
    the matching FE beam element, which needs a beam-ID-to-tributary-load
    join this skill doesn't attempt yet (see SKILL.md). Self-weight alone
    is enough to validate the model (equilibrium, period sanity) but is NOT
    a complete gravity load case -- don't read gravity analysis results
    here as design-ready member forces.

    Uses the empirically-verified eleLoad slot convention documented in
    build_fe_model.py's module docstring: vertical elements take the load
    in the axial (Wx, third) slot; horizontal elements take it in the
    transverse-Z (Wz, second) slot, regardless of which horizontal
    direction they run in."""
    ops.timeSeries("Linear", 1)
    ops.pattern("Plain", 1, 1)
    for eid, e in element_map.items():
        w = e["section"]["A_m2"] * e["material"]["unit_weight_kn_m3"]  # kN/m, magnitude
        if e["is_vertical"]:
            ops.eleLoad("-ele", e["tag"], "-type", "-beamUniform", 0.0, 0.0, -w)
        else:
            ops.eleLoad("-ele", e["tag"], "-type", "-beamUniform", 0.0, -w, 0.0)


def run_gravity_static(element_map, needs_review):
    apply_self_weight(element_map)
    ops.system("BandGeneral")
    ops.numberer("RCM")
    ops.constraints("Plain")
    ops.integrator("LoadControl", 1.0)
    ops.algorithm("Linear")
    ops.analysis("Static")
    ok = ops.analyze(1)
    if ok != 0:
        needs_review.append({"reason": f"gravity static analysis did not converge (code {ok})"})
        return False
    return True


def assign_mass_from_story_weights(nodes, stories, story_forces, base_nodes, needs_review):
    """Distributes each story's seismic weight (dynamic-load's own
    DL+SDL+reduced-LL sum, already computed and verified by that skill) as
    lumped translational mass, split EQUALLY among that story's FE nodes.
    Only X/Y translational mass is assigned (rotational and vertical mass
    are left at zero) -- standard practice for a seismic eigenvalue
    analysis focused on horizontal response, but it does mean a torsional
    mode's frequency here reflects only the model's own rotational
    stiffness/mass distribution from equal nodal masses, not a genuine
    mass moment of inertia computed from the real floor plan -- a further
    simplification worth knowing about before reading torsional mode
    results as authoritative.

    base_nodes (the fixed-support nodes from build_model()) are skipped
    entirely -- a restrained DOF can't move, so mass assigned there is
    both numerically pointless and, if counted in a mass-participation
    denominator later, wrongly dilutes every percentage (see
    run_eigen_analysis()'s own fix for the matching numerator-side bug)."""
    weight_by_index = {sf["story_index"]: sf["weight_kn"] for sf in story_forces}
    assigned = {}
    base_node_set = set(base_nodes)
    for story in stories:
        z_m = story["elevation_mm"] / 1000.0
        node_tags = [n for n in nodes.tags_at_elevation(z_m) if n not in base_node_set]
        if not node_tags:
            continue
        w = weight_by_index.get(story["index"])
        if w is None:
            needs_review.append({"story": story["name"], "reason":
                "no matching dynamic_loads story weight -- zero mass assigned at this level"})
            continue
        mass_per_node = (w / G_ACCEL_M_S2) / len(node_tags)
        for n in node_tags:
            ops.mass(n, mass_per_node, mass_per_node, 1e-9, 0.0, 0.0, 0.0)  # tiny non-zero Z mass for solver stability
        assigned[story["index"]] = {"total_mass_tonne": w / G_ACCEL_M_S2, "nodes": node_tags, "mass_per_node": mass_per_node}
    return assigned


def run_eigen_analysis(nodes, mass_by_story, num_modes, needs_review):
    """Returns a list of {'mode':, 'period_s':, 'mass_participation_x_pct':,
    'mass_participation_y_pct':}. Mass participation is computed directly
    from the known lumped masses and mode shapes -- openseespy doesn't
    expose a ready-made 'participation ratio' call, so this is derived
    explicitly rather than assumed available.

    NUMERICALLY IMPORTANT: effective modal mass in direction X is
    Lx^2 / M_full, where M_full = sum of m*(phi_x^2 + phi_y^2) over BOTH
    translational directions together -- NOT Lx^2/Mx using an X-only
    modal mass in the denominator. The X-only version blows up for any
    mode whose X-direction modal mass happens to be tiny (a near-pure-Y
    mode, or one half of a degenerate same-period pair from a symmetric
    structure -- exactly what a symmetric grid of identical columns
    produces): a small Lx divided by an even smaller Mx can spuriously
    exceed 100%, which is what a first version of this function actually
    did on this skill's own test fixture (two modes at an identical period
    each showing ~55% X participation, summing past 100%) before this was
    caught and fixed. M_full stays honest because it's dominated by
    whichever direction the mode actually moves in."""
    try:
        eigenvalues = ops.eigen(num_modes)
    except Exception as e:
        needs_review.append({"reason": f"eigenvalue analysis failed: {e}"})
        return []

    all_nodes_mass = []  # (node_tag, mass_per_node) -- base/fixed nodes already excluded upstream
    for story_id, info in mass_by_story.items():
        for n in info["nodes"]:
            all_nodes_mass.append((n, info["mass_per_node"]))
    total_mass = sum(m for _, m in all_nodes_mass)

    import math
    modes = []
    for i, ev in enumerate(eigenvalues, start=1):
        if ev <= 0:
            needs_review.append({"reason": f"mode {i} has non-positive eigenvalue ({ev}) -- skipped, "
                                            f"likely an unrestrained/mechanism DOF in the model"})
            continue
        T = 2 * math.pi / math.sqrt(ev)
        Lx = sum(m * ops.nodeEigenvector(n, i, 1) for n, m in all_nodes_mass)
        Ly = sum(m * ops.nodeEigenvector(n, i, 2) for n, m in all_nodes_mass)
        M_full = sum(m * (ops.nodeEigenvector(n, i, 1) ** 2 + ops.nodeEigenvector(n, i, 2) ** 2)
                     for n, m in all_nodes_mass)
        eff_mass_x = (Lx ** 2 / M_full) if M_full > 1e-12 else 0.0
        eff_mass_y = (Ly ** 2 / M_full) if M_full > 1e-12 else 0.0
        modes.append({
            "mode": i, "period_s": round(T, 5),
            "mass_participation_x_pct": round(100 * eff_mass_x / total_mass, 2) if total_mass > 0 else 0.0,
            "mass_participation_y_pct": round(100 * eff_mass_y / total_mass, 2) if total_mass > 0 else 0.0,
        })
    return modes


def cumulative_mass_participation(modes, direction_key):
    return round(sum(m[direction_key] for m in modes), 2)


def interpolate_spectrum(curve, T):
    """Linear interpolation on dynamic-load's own design_spectrum_g curve
    (a list of {'T_sec':, 'Sa_g':} points). Consumes it as portable data --
    no import of dynamic-load's seismic.py, matching the cross-skill-
    package boundary this whole pipeline has kept since revit-load-
    application (see load-path's/dynamic-load's own reference docs)."""
    pts = sorted(curve, key=lambda p: p["T_sec"])
    if T <= pts[0]["T_sec"]:
        return pts[0]["Sa_g"]
    if T >= pts[-1]["T_sec"]:
        return pts[-1]["Sa_g"]
    for a, b in zip(pts, pts[1:]):
        if a["T_sec"] <= T <= b["T_sec"]:
            frac = (T - a["T_sec"]) / (b["T_sec"] - a["T_sec"]) if b["T_sec"] != a["T_sec"] else 0.0
            return a["Sa_g"] + frac * (b["Sa_g"] - a["Sa_g"])
    return pts[-1]["Sa_g"]


def run_response_spectrum(modes, design_spectrum_curve, direction_key, needs_review, mass_participation_threshold=90.0):
    """Sec 2.5.9's SRSS combination (dynamic-load's rsa.modal_combination_rule
    already documents CQC as required instead where modes are closely
    spaced -- this function implements SRSS only; flagging that choice
    rather than silently picking one with no note, per that same
    documented rule)."""
    cumulative = cumulative_mass_participation(modes, direction_key)
    if cumulative < mass_participation_threshold:
        needs_review.append({"reason": f"cumulative {direction_key} mass participation across {len(modes)} "
                                        f"modes is {cumulative}%, below Sec 2.5.9.2's required 90% -- "
                                        f"request more modes before trusting this RSA result"})
    modal_results = []
    srss_sum_sq = 0.0
    for m in modes:
        Sa_g = interpolate_spectrum(design_spectrum_curve, m["period_s"])
        contribution_pct = m[direction_key]
        modal_results.append({"mode": m["mode"], "period_s": m["period_s"], "Sa_g": Sa_g,
                               "mass_participation_pct": contribution_pct})
        srss_sum_sq += (Sa_g * (contribution_pct / 100.0)) ** 2
    combined_Sa_g = srss_sum_sq ** 0.5
    return {"combination_method": "SRSS", "modal_results": modal_results,
            "cumulative_mass_participation_pct": cumulative,
            "combined_spectral_acceleration_g_approx": round(combined_Sa_g, 5),
            "note": "combined_spectral_acceleration_g_approx is a simplified SRSS combination of "
                    "per-mode Sa weighted by mass participation fraction, NOT a full multi-mode force/"
                    "displacement recovery at every node -- see SKILL.md for exactly what this does "
                    "and doesn't replace."}


def recover_member_forces(element_map, needs_review, case_name):
    """Recover elasticBeamColumn end actions keyed by pipeline element ID.

    OpenSees returns the 12 local end actions as [P, Vy, Vz, T, My, Mz]
    at i and j.  Preserve that raw, local result in every record.  The
    semantic aliases below are intentionally limited to this model's fixed
    local-axis convention: horizontal members receive gravity through Wz,
    so Vz/My are the vertical-shear/gravity-bending pair; vertical members
    use the build_fe_model reference vector, which maps My/Mz to the
    X-/Y-lateral loading planes.  They are suitable for this skill chain,
    not a substitute for a project-specific local-axis audit.
    """
    recovered = {}
    labels = ("axial_kn", "shear_y_kn", "shear_z_kn", "torsion_knm",
              "moment_y_knm", "moment_z_knm")
    for eid, element in element_map.items():
        try:
            values = [float(v) for v in ops.eleForce(element["tag"])]
        except Exception as exc:
            needs_review.append({"element": eid, "reason":
                f"{case_name}: OpenSees element-force recovery failed: {exc}"})
            continue
        if len(values) != 12:
            needs_review.append({"element": eid, "reason":
                f"{case_name}: expected 12 elasticBeamColumn end actions, got {len(values)}"})
            continue
        record = {"force_basis": "OpenSees local end actions; see analysis_results.member_forces.note"}
        for end, offset in (("i", 0), ("j", 6)):
            for label, value in zip(labels, values[offset:offset + 6]):
                record[f"local_{label}_{end}"] = round(value, 5)
        if element["is_vertical"]:
            record.update({
                "axial_kn_i": record["local_axial_kn_i"],
                "axial_kn_j": record["local_axial_kn_j"],
                "moment_for_x_load_knm_i": record["local_moment_y_knm_i"],
                "moment_for_x_load_knm_j": record["local_moment_y_knm_j"],
                "moment_for_y_load_knm_i": record["local_moment_z_knm_i"],
                "moment_for_y_load_knm_j": record["local_moment_z_knm_j"],
            })
        else:
            record.update({
                "gravity_moment_knm_i": record["local_moment_y_knm_i"],
                "gravity_moment_knm_j": record["local_moment_y_knm_j"],
                "shear_vertical_kn_i": record["local_shear_z_kn_i"],
                "shear_vertical_kn_j": record["local_shear_z_kn_j"],
            })
        recovered[eid] = record
    return recovered

def apply_lateral_static(element_map, nodes, story_forces, direction):
    """Applies dynamic-load's own ESFP story forces (already computed and
    verified) as point loads at each story's nodes, split equally --
    the same simplification used for mass, and for the same load-path-vs-
    stiffness reason revit-load-application drew for gravity (this skill
    doesn't yet have a real horizontal-stiffness-based distribution to
    individual lateral elements -- see SKILL.md)."""
    ops.timeSeries("Linear", 2)
    ops.pattern("Plain", 2, 2)
    dof = 1 if direction == "x" else 2
    for sf in story_forces:
        z_m = sf["elevation_m"]
        node_tags = nodes.tags_at_elevation(z_m)
        if not node_tags:
            continue
        force_per_node = sf["Fx_kn"] / len(node_tags)
        for n in node_tags:
            load_vec = [0.0] * 6
            load_vec[dof - 1] = force_per_node
            ops.load(n, *load_vec)


def run(structural_model, out_dir, num_modes=12):
    needs_review = []
    nodes, element_map, model_review, base_nodes = build_model(structural_model, ops)
    needs_review.extend(model_review)

    gravity_ok = run_gravity_static(element_map, needs_review)
    gravity_results = None
    gravity_member_forces = {}
    if gravity_ok:
        ops.reactions()
        total_reaction_z = sum(ops.nodeReaction(n)[2] for n in base_nodes)
        total_self_weight = sum(e["section"]["A_m2"] * e["length_m"] * e["material"]["unit_weight_kn_m3"]
                                 for e in element_map.values())
        # Self-weight is applied downward; a fixed base's vertical reaction
        # is reported matching that same positive magnitude (verified
        # empirically against this skill's own test fixture: both summed
        # to identical 760.32kN) -- equilibrium means these two are EQUAL,
        # not opposite in sign. (An earlier version of this check assumed
        # they should sum to zero and flagged a perfectly balanced model as
        # an error -- fixed after noticing the two numbers matched exactly
        # while the check still reported failure.)
        equilibrium_error_kn = abs(total_reaction_z - total_self_weight)
        if equilibrium_error_kn > 0.01 * total_self_weight:
            needs_review.append({"reason": f"gravity equilibrium check failed: reactions sum to "
                                            f"{total_reaction_z:.2f}kN, expected {total_self_weight:.2f}kN"})
        gravity_results = {"total_self_weight_kn": round(total_self_weight, 2),
                            "sum_vertical_reactions_kn": round(total_reaction_z, 2),
                            "equilibrium_error_kn": round(equilibrium_error_kn, 4)}
        gravity_member_forces = recover_member_forces(element_map, needs_review, "gravity self-weight")

    dyn = structural_model.get("dynamic_loads", {}).get("seismic", {})
    stories = sorted(structural_model.get("stories", []), key=lambda s: s["elevation_mm"])

    modal_results = {}
    rsa_results = {}
    lateral_results = {}
    lateral_member_forces = {}
    for direction, dof_key in (("x_direction", "x"), ("y_direction", "y")):
        block = dyn.get(direction)
        if not block or not block.get("story_forces"):
            needs_review.append({"reason": f"no dynamic_loads.seismic.{direction} story_forces -- "
                                            f"skipping modal/RSA/lateral-static for this direction"})
            continue

        # Reset and rebuild for a clean mass/eigen state per direction pass
        # (mass assignment doesn't depend on direction, but keeping the
        # model fresh avoids any load-pattern carryover between passes).
        nodes2, element_map2, _, base_nodes2 = build_model(structural_model, ops)
        mass_by_story = assign_mass_from_story_weights(nodes2, stories, block["story_forces"], base_nodes2, needs_review)
        modes = run_eigen_analysis(nodes2, mass_by_story, num_modes, needs_review)
        modal_results[direction] = modes

        approx_Ta = block.get("period", {}).get("approximate_Ta_sec")
        ceiling = block.get("period", {}).get("computed_period_ceiling_sec")
        computed_T1 = modes[0]["period_s"] if modes else None
        if computed_T1 and ceiling and computed_T1 > ceiling:
            needs_review.append({"reason": f"{direction}: computed T1={computed_T1}s exceeds dynamic-load's "
                                            f"140%-of-approximate ceiling ({ceiling}s per Sec 2.5.7.2(a)) -- "
                                            f"use the ceiling value for Sa, not this computed T1, per that "
                                            f"section's own limit"})

        rsa_curve = block.get("rsa", {}).get("design_spectrum_g")
        if rsa_curve and modes:
            rsa_results[direction] = run_response_spectrum(modes, rsa_curve, f"mass_participation_{dof_key}_pct", needs_review)

        apply_lateral_static(element_map2, nodes2, block["story_forces"], dof_key)
        ops.system("BandGeneral"); ops.numberer("RCM"); ops.constraints("Plain")
        ops.integrator("LoadControl", 1.0); ops.algorithm("Linear"); ops.analysis("Static")
        ok = ops.analyze(1)
        if ok == 0:
            ops.reactions()
            dof_index = 0 if dof_key == "x" else 1
            base_shear = sum(ops.nodeReaction(n)[dof_index] for n in base_nodes2)
            expected = block.get("base_shear_kn")
            lateral_results[direction] = {"base_shear_from_reactions_kn": round(base_shear, 2),
                                           "expected_base_shear_kn": expected}
            lateral_member_forces[direction] = recover_member_forces(
                element_map2, needs_review, f"{direction} lateral static")
            if expected and abs(abs(base_shear) - expected) > 0.02 * expected:
                needs_review.append({"reason": f"{direction}: FE base shear from reactions "
                                                f"({base_shear:.1f}kN) doesn't match dynamic-load's "
                                                f"expected {expected}kN within 2% -- check load application"})
        else:
            needs_review.append({"reason": f"{direction}: lateral static analysis did not converge (code {ok})"})

    analysis_results = {
        "model_summary": {"node_count": len(nodes.all_tags()), "element_count": len(element_map),
                           "elements_excluded": len(model_review)},
        "gravity_self_weight_only": gravity_results,
        "modal": modal_results,
        "response_spectrum": rsa_results,
        "lateral_static": lateral_results,
        "member_forces": {
            "gravity_self_weight_only": gravity_member_forces,
            "lateral_static": lateral_member_forces,
            "note": "Raw local end actions are retained for every modeled member. Semantic aliases use the current build_fe_model local-axis convention; verify sign and local-axis orientation before treating them as final design actions.",
        },
        "needs_review": needs_review,
    }
    structural_model["analysis_results"] = analysis_results

    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    (out_path / "structural_model.json").write_text(json.dumps(structural_model, indent=2))

    print(f"Model: {len(nodes.all_tags())} nodes, {len(element_map)} elements "
          f"({len(model_review)} excluded). Gravity: {'OK' if gravity_ok else 'FAILED'}. "
          f"Modal directions solved: {list(modal_results.keys())}. "
          f"{len(needs_review)} item(s) flagged -> {out_path}/structural_model.json")
    return structural_model


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--structural-model", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--num-modes", type=int, default=12)
    args = ap.parse_args()
    model = json.loads(Path(args.structural_model).read_text())
    run(model, args.out, num_modes=args.num_modes)


if __name__ == "__main__":
    main()
