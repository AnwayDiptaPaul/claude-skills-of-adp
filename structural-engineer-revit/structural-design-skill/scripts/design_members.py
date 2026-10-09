#!/usr/bin/env python3
"""
scripts/design_members.py — the entry point for this skill. Reads a
structural_model.json already carrying structural-analysis's
analysis_results.member_forces, combines gravity and lateral member forces
per BNBC Sec 2.7's strength-design combinations, and runs beam flexural/
shear design and column axial-moment interaction checks per Chapter 6.

Usage:
    python3 design_members.py --structural-model structural_model.json \
        --design-input design_input.json --out output_dir/

SCOPE: singly-reinforced rectangular beams, tied rectangular columns with
uniaxial P-M interaction (short columns, no slenderness magnification, no
biaxial combination). See codes/concrete_design.py's own module docstring
and SKILL.md's Known Limitations for the full accounting of what's out of
scope (T-beams, doubly-reinforced beams, torsion, spiral columns, seismic
detailing, footings, development length/bar detailing).

THE MOST IMPORTANT CAVEAT, INHERITED FROM UPSTREAM AND NOT FIXABLE HERE:
structural-analysis's own gravity case is SELF-WEIGHT ONLY, not the full
D+SDL+L case revit-load-application actually computed. Every 'D' (dead
load effect) this script uses is therefore an UNDERESTIMATE of the real
dead load, and live load (L) is entirely absent (treated as zero) because
no live-load FE case exists upstream at all. Design results here are
demonstrations of the design METHOD against real (if incomplete) analysis
output -- not complete, code-compliant member designs. See SKILL.md.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "codes"))
import concrete_design as cd       # noqa: E402
import load_combinations as lc     # noqa: E402
import section_parsing as sp       # noqa: E402


def resolve_section_and_grade(element, needs_review, default_fy_mpa):
    section = sp.parse_rectangular_section(element.get("section_hint"))
    if section is None:
        needs_review.append({"element": element["id"], "reason":
            f"section_hint={element.get('section_hint')!r} did not parse -- not designed"})
        return None
    grade = sp.parse_concrete_grade((element.get("material") or {}).get("names"))
    if grade is None:
        needs_review.append({"element": element["id"], "reason":
            f"material.names={((element.get('material') or {}).get('names'))!r} has no "
            f"parseable Cxx/yy grade -- not designed"})
        return None
    return {"b_mm": section["width_mm"], "h_mm": section["depth_mm"],
            "fck_mpa": grade["fck_mpa"], "fy_mpa": default_fy_mpa}


def design_beam(element, gravity_forces, lateral_forces_by_dir, section_grade, needs_review):
    eid = element["id"]
    b, h, fck, fy = section_grade["b_mm"], section_grade["h_mm"], section_grade["fck_mpa"], section_grade["fy_mpa"]
    d_mm = h - 50.0  # assumed cover+half-bar-diameter to reinforcement centroid; not from real detailing

    D_moment_i = gravity_forces.get("gravity_moment_knm_i", 0.0) if gravity_forces else 0.0
    D_moment_j = gravity_forces.get("gravity_moment_knm_j", 0.0) if gravity_forces else 0.0
    D_shear_i = gravity_forces.get("shear_vertical_kn_i", 0.0) if gravity_forces else 0.0

    # Beams: lateral (E) contribution isn't extracted for beam gravity_moment
    # by structural-analysis's own verified mapping in a form this skill can
    # combine directly for beams (that skill's lateral_static case loads
    # columns with story shear, and beam moments under that case exist in
    # the same member_forces shape -- reuse them the same way as gravity).
    E_moment_i = 0.0
    for direction, forces in (lateral_forces_by_dir or {}).items():
        f = forces.get(eid)
        if f:
            candidate = f.get("gravity_moment_knm_i", 0.0)
            if abs(candidate) > abs(E_moment_i):
                E_moment_i = candidate

    combo_name, Mu = lc.governing_combination(D=D_moment_i, L=0.0, Lr=0.0, W=0.0, E=E_moment_i)
    combo_name_j, Mu_j = lc.governing_combination(D=D_moment_j, L=0.0, Lr=0.0, W=0.0, E=E_moment_i)
    combo_name_v, Vu = lc.governing_combination(D=D_shear_i, L=0.0, Lr=0.0, W=0.0, E=0.0)

    flex_i = cd.design_singly_reinforced_beam(abs(Mu), fck, fy, b, d_mm, needs_review, member_id=eid + " (end i)")
    flex_j = cd.design_singly_reinforced_beam(abs(Mu_j), fck, fy, b, d_mm, needs_review, member_id=eid + " (end j)")
    shear = cd.design_shear_reinforcement(abs(Vu), fck, fy, b, d_mm, needs_review, member_id=eid)

    return {"section": {"b_mm": b, "h_mm": h, "d_assumed_mm": d_mm, "fck_mpa": fck, "fy_mpa": fy},
            "demand": {"Mu_end_i_knm": round(Mu, 2), "governing_combo_i": combo_name,
                       "Mu_end_j_knm": round(Mu_j, 2), "governing_combo_j": combo_name_j,
                       "Vu_knm": round(Vu, 2), "governing_combo_v": combo_name_v},
            "flexure_end_i": flex_i, "flexure_end_j": flex_j, "shear": shear}


def design_column(element, gravity_forces, lateral_forces_by_dir, section_grade, Z, S, needs_review, d_prime_override=None):
    eid = element["id"]
    b, h, fck, fy = section_grade["b_mm"], section_grade["h_mm"], section_grade["fck_mpa"], section_grade["fy_mpa"]
    Ag = b * h

    D_axial = gravity_forces.get("axial_kn_i", 0.0) if gravity_forces else 0.0
    D_moment_x = gravity_forces.get("moment_for_x_load_knm_i", 0.0) if gravity_forces else 0.0
    D_moment_y = gravity_forces.get("moment_for_y_load_knm_i", 0.0) if gravity_forces else 0.0

    Eh_x = Eh_y = 0.0
    if lateral_forces_by_dir:
        fx = lateral_forces_by_dir.get("x_direction", {}).get(eid)
        fy_dir = lateral_forces_by_dir.get("y_direction", {}).get(eid)
        if fx:
            Eh_x = fx.get("moment_for_x_load_knm_i", 0.0)
        if fy_dir:
            Eh_y = fy_dir.get("moment_for_y_load_knm_i", 0.0)

    E_x = lc.seismic_load_effect_kn(Eh_x, Z, S, D_axial) if Z is not None and S is not None else Eh_x
    E_y = lc.seismic_load_effect_kn(Eh_y, Z, S, D_axial) if Z is not None and S is not None else Eh_y

    combo_p, Pu = lc.governing_combination(D=D_axial, L=0.0, Lr=0.0, W=0.0, E=max(abs(E_x), abs(E_y)))
    combo_mx, Mux = lc.governing_combination(D=D_moment_x, L=0.0, Lr=0.0, W=0.0, E=E_x)
    combo_my, Muy = lc.governing_combination(D=D_moment_y, L=0.0, Lr=0.0, W=0.0, E=E_y)

    Ast_ratio_assumed = 0.02  # 2% -- a placeholder starting assumption, NOT derived from any input
    Ast_mm2 = Ast_ratio_assumed * Ag
    needs_review.append({"element": eid, "reason":
        f"column longitudinal steel ratio assumed at {Ast_ratio_assumed:.0%} of gross area "
        f"({Ast_mm2:.0f}mm2) to build the interaction diagram -- this is a starting-point "
        f"assumption for checking, NOT a design output; iterate Ast until utilization is "
        f"reasonable, this script does not do that iteration itself"})

    ok_ratio = cd.check_longitudinal_reinforcement_ratio(Ast_mm2, Ag, needs_review, member_id=eid)
    d_prime = d_prime_override if d_prime_override is not None else 0.1 * h
    diagram_x = cd.build_interaction_diagram(b, h, fck, fy, Ast_mm2, d_prime_mm=d_prime)
    check_x = cd.check_demand_against_interaction(Pu, Mux, diagram_x, needs_review, member_id=eid + " (x-dir)")
    diagram_y = cd.build_interaction_diagram(h, b, fck, fy, Ast_mm2, d_prime_mm=d_prime)  # swapped b/h for y-bending
    check_y = cd.check_demand_against_interaction(Pu, Muy, diagram_y, needs_review, member_id=eid + " (y-dir)")

    return {"section": {"b_mm": b, "h_mm": h, "fck_mpa": fck, "fy_mpa": fy,
                         "Ast_assumed_mm2": round(Ast_mm2, 1), "reinforcement_ratio_ok": ok_ratio},
            "demand": {"Pu_kn": round(Pu, 2), "governing_combo_p": combo_p,
                       "Mux_knm": round(Mux, 2), "governing_combo_mx": combo_mx,
                       "Muy_knm": round(Muy, 2), "governing_combo_my": combo_my},
            "check_x_direction": check_x, "check_y_direction": check_y,
            "note": "Mux/Muy checked independently against uniaxial capacity -- not a true "
                    "biaxial interaction check (see SKILL.md)"}


def run(structural_model, design_input, out_dir):
    needs_review = []
    default_fy = design_input.get("fy_mpa", 420.0)
    d_prime_override = design_input.get("d_prime_mm")

    ar = structural_model.get("analysis_results", {})
    mf = ar.get("member_forces", {})
    gravity_mf = mf.get("gravity_self_weight_only", {})
    lateral_mf = mf.get("lateral_static", {})
    force_note = mf.get("note")
    if force_note:
        needs_review.append({"reason": f"analysis member-force qualification: {force_note}"})
    if not gravity_mf and not lateral_mf:
        needs_review.append({"reason": "no analysis_results.member_forces found at all -- run "
                                        "structural-analysis first. No members designed."})

    shared = structural_model.get("dynamic_loads", {}).get("seismic", {}).get("shared_inputs", {})
    Z = shared.get("zone_coefficient_Z")
    S = lc.SITE_CLASS_S.get(shared.get("site_class"))
    if Z is None or S is None:
        needs_review.append({"reason": "no dynamic_loads.seismic.shared_inputs zone/site_class found -- "
                                        "Ev (vertical seismic effect) treated as zero, E=Eh only"})

    beam_results = {}
    for beam in structural_model.get("elements", {}).get("framing", []):
        eid = beam["id"]
        if eid not in gravity_mf and not any(eid in d for d in lateral_mf.values()):
            continue
        sg = resolve_section_and_grade(beam, needs_review, default_fy)
        if sg is None:
            continue
        beam_results[eid] = design_beam(beam, gravity_mf.get(eid), lateral_mf, sg, needs_review)

    column_results = {}
    for col in structural_model.get("elements", {}).get("columns", []):
        eid = col["id"]
        if eid not in gravity_mf and not any(eid in d for d in lateral_mf.values()):
            continue
        sg = resolve_section_and_grade(col, needs_review, default_fy)
        if sg is None:
            continue
        column_results[eid] = design_column(col, gravity_mf.get(eid), lateral_mf, sg, Z, S,
                                             needs_review, d_prime_override)

    design_results = {
        "scope_note": "self-weight-only gravity case inherited from structural-analysis -- "
                       "see SKILL.md before treating any result here as a complete design",
        "fy_mpa_used": default_fy,
        "beams": beam_results,
        "columns": column_results,
        "needs_review": needs_review,
    }
    structural_model["design_results"] = design_results

    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    (out_path / "structural_model.json").write_text(json.dumps(structural_model, indent=2))

    print(f"Designed {len(beam_results)} beam(s), {len(column_results)} column(s). "
          f"{len(needs_review)} item(s) flagged -> {out_path}/structural_model.json")
    return structural_model


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--structural-model", required=True)
    ap.add_argument("--design-input", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    model = json.loads(Path(args.structural_model).read_text())
    design_input = json.loads(Path(args.design_input).read_text())
    run(model, design_input, args.out)


if __name__ == "__main__":
    main()
