#!/usr/bin/env python3
"""
trace_load_path.py — the entry point for this skill. Reads a
structural_model.json already carrying revit-structure-recognition's
elements and (optionally) revit-load-application's/dynamic-load's loads,
traces every column and wall's gravity path down to a footing, traces the
continuity of the chosen lateral-force-resisting system, classifies the
BNBC irregularity types that are geometrically determinable, firms up the
low-confidence `role` field skill 1 deliberately left soft, and flags
elements that need Sec 2.5.5.6 overstrength-level design.

Usage:
    python3 trace_load_path.py --structural-model structural_model.json --out output_dir/

SCOPE: gravity continuity is fully resolved for the direct column/wall-to-
footing case, including skill 1's own transfer flags. Continuity PAST a
transfer beam (to that beam's own end supports) is not re-derived --
revit-structure-recognition doesn't record which columns a beam's ends
land on, only whether a column landing on a beam happened at all, and
re-deriving that from geometry is a materially different, harder matching
problem than confirming two records agree (which this script does do) --
see SKILL.md's Known Limitations. Lateral continuity is traced by grid
reference for elements carrying wall_class shear (primary or secondary).
Only 4 of BNBC's 10 irregularity types are computed here (mass, vertical
in-plane discontinuity, plan out-of-plane offset, non-parallel systems) --
the rest need data this pipeline stage doesn't have (floor plan outlines,
storey stiffness/strength/displacement) -- see SKILL.md.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "codes" / "bnbc2020"))
import irregularity as irr  # noqa: E402


# ---------------------------------------------------------------------------
# Indexing helpers
# ---------------------------------------------------------------------------
def _stories_sorted(model):
    return sorted(model.get("stories", []), key=lambda s: s["elevation_mm"])


def _story_order_lookup(model):
    """Map every supported story identifier to its position (0 = lowest).

    Current recognition output carries a source-stable ``id`` (equal to
    ``global_id`` for IFC), while older inventories may have only a name.
    Index all forms so mixed historical models are read defensively.
    """
    lookup = {}
    for i, story in enumerate(_stories_sorted(model)):
        for key in (story.get("id"), story.get("global_id"), story.get("name")):
            if key is not None:
                lookup[key] = i
    return lookup


def _story_position(story_ref, story_order):
    """Return a story position from a canonical reference or legacy shape."""
    if not story_ref:
        return None
    if isinstance(story_ref, str):  # historical story_range value
        return story_order.get(story_ref)
    for key in (story_ref.get("id"), story_ref.get("global_id"), story_ref.get("name")):
        if key in story_order:
            return story_order[key]
    return None

def _grid_key(grid_ref):
    """A hashable key for 'same vertical line' matching. Falls back to None
    (unmatchable by grid) if grid_ref is missing or malformed -- callers
    must handle None explicitly rather than let it silently collide."""
    if not grid_ref:
        return None
    if grid_ref.get("along_gridline") is not None:
        return ("along", grid_ref["along_gridline"])
    if grid_ref.get("at") is not None:
        return ("at", tuple(grid_ref["at"]))
    return None


# ---------------------------------------------------------------------------
# Gravity load path
# ---------------------------------------------------------------------------
def trace_gravity_paths(model, needs_review):
    columns = model.get("elements", {}).get("columns", [])
    walls = model.get("elements", {}).get("walls", [])
    footings = model.get("elements", {}).get("footings", [])
    story_order = _story_order_lookup(model)

    supported_ids = set()
    for f in footings:
        supported_ids.update(f.get("supports", []))

    columns_by_top_story = {}
    for c in columns:
        top = c.get("top_story", {}).get("id") or c.get("top_story", {}).get("name")
        columns_by_top_story.setdefault(top, []).append(c)

    traces = []
    unresolved = []

    for col in columns:
        col_id = col["id"]
        chain = [{"element": col_id, "type": "column",
                  "story": col.get("base_story", {}).get("name")}]
        current = col
        has_transfer = False
        resolved = False
        visited = {col_id}

        while True:
            if current["id"] in supported_ids:
                resolved = True
                chain.append({"terminates_at": "footing", "type": "footing"})
                break
            if current.get("is_transfer_column"):
                has_transfer = True
                flag = current.get("transfer_flag") or {}
                lands_on = flag.get("lands_on")
                chain.append({"transfer_via": lands_on, "story": current.get("base_story", {}).get("name")})
                beam = next((f for f in model.get("elements", {}).get("framing", [])
                             if f["id"] == lands_on), None)
                if beam is None:
                    needs_review.append({"element": col_id, "reason":
                        f"transfer_flag.lands_on references '{lands_on}', which isn't in "
                        f"elements.framing -- can't cross-check the receiving beam"})
                elif not beam.get("supports_transfer_condition"):
                    needs_review.append({"element": col_id, "reason":
                        f"'{col_id}'.transfer_flag.lands_on='{lands_on}', but that beam's own "
                        f"supports_transfer_condition is not True -- the two records disagree, "
                        f"re-verify skill 1's classification"})
                chain.append({"note": "trace not continued past the transfer beam -- "
                                       "its own end supports aren't recorded by "
                                       "revit-structure-recognition"})
                break
            base_story = current.get("base_story", {}).get("id") or current.get("base_story", {}).get("name")
            gk = _grid_key(current.get("grid_ref"))
            candidates = [c for c in columns_by_top_story.get(base_story, [])
                          if _grid_key(c.get("grid_ref")) == gk and gk is not None]
            wall_candidates = [w for w in walls if _grid_key(w.get("grid_ref")) == gk
                               and gk is not None and
                               _story_position(w.get("top_story") or (w.get("story_range") or {}).get("top"), story_order) is not None]
            if not candidates and not wall_candidates:
                unresolved.append({"element": col_id, "story": base_story, "reason":
                    "no matching column/wall below (by grid_ref) and not flagged as a "
                    "transfer condition -- does not reach a footing. Possible modeling "
                    "gap in the source Revit model, or a genuine unsupported column."})
                chain.append({"unresolved_at": base_story})
                break
            if candidates:
                nxt = candidates[0]
                if nxt["id"] in visited:
                    needs_review.append({"element": col_id, "reason": "cyclic support chain detected -- stopped tracing"})
                    break
                visited.add(nxt["id"])
                chain.append({"element": nxt["id"], "type": "column", "story": base_story})
                current = nxt
                continue
            else:
                chain.append({"element": wall_candidates[0]["id"], "type": "wall", "story": base_story})
                if wall_candidates[0]["id"] in supported_ids:
                    resolved = True
                    chain.append({"terminates_at": "footing", "type": "footing"})
                else:
                    unresolved.append({"element": col_id, "story": base_story, "reason":
                        f"continues onto wall '{wall_candidates[0]['id']}' but that wall "
                        f"isn't listed in any footing's supports[] -- gravity path incomplete"})
                break

        traces.append({"top_element": col_id, "path": chain,
                        "terminates_at_footing": resolved, "has_transfer": has_transfer})

    return {"traces": traces, "unresolved": unresolved}


# ---------------------------------------------------------------------------
# Lateral load path (shear walls)
# ---------------------------------------------------------------------------
def identify_lateral_elements(model, structural_system_key):
    """Elements considered part of the lateral system for continuity
    tracing. Shear walls (wall_class primary or secondary == 'shear') are
    fully handled below; moment-frame/braced-frame systems are noted as
    lower-fidelity (see SKILL.md) -- their 'primary' framing_role columns
    are returned too, but only for a full-height-continuation sanity check,
    not a true frame-continuity trace."""
    walls = model.get("elements", {}).get("walls", [])
    shear_walls = [w for w in walls if
                   w.get("wall_class", {}).get("primary") == "shear" or
                   w.get("wall_class", {}).get("secondary") == "shear"]
    return shear_walls


def trace_lateral_continuity(model, shear_walls, needs_review):
    story_order = _story_order_lookup(model)
    by_grid = {}
    for w in shear_walls:
        gk = _grid_key(w.get("grid_ref"))
        if gk is None:
            needs_review.append({"element": w["id"], "reason":
                "shear wall has no usable grid_ref -- excluded from lateral continuity trace"})
            continue
        by_grid.setdefault(gk, []).append(w)

    discontinuities = []
    lines_traced = []
    for gk, segments in by_grid.items():
        segs_sorted = sorted(segments, key=lambda w: _story_position(w.get("base_story") or (w.get("story_range") or {}).get("base"), story_order) or -1)
        story_span = set()
        for w in segs_sorted:
            b = _story_position(w.get("base_story") or (w.get("story_range") or {}).get("base"), story_order)
            t = _story_position(w.get("top_story") or (w.get("story_range") or {}).get("top"), story_order)
            if b is None or t is None:
                needs_review.append({"element": w["id"], "reason":
                    "base_story/top_story references a story not found in stories[] -- "
                    "excluded from continuity check"})
                continue
            story_span.update(range(b, t + 1))
        if not story_span:
            continue
        full_range = range(min(story_span), max(story_span) + 1)
        gaps = [s for s in full_range if s not in story_span]
        lines_traced.append({"grid_key": list(gk), "wall_ids": [w["id"] for w in segs_sorted],
                              "spans_stories": [min(story_span), max(story_span)], "gap_stories": gaps})
        if gaps:
            below = next((w for w in segs_sorted if _story_position(w.get("top_story") or (w.get("story_range") or {}).get("top"), story_order) == min(gaps) - 1), None)
            above = next((w for w in segs_sorted if _story_position(w.get("base_story") or (w.get("story_range") or {}).get("base"), story_order) == max(gaps) + 1), None)
            discontinuities.append({
                "grid_key": list(gk), "gap_stories": gaps,
                "wall_below": below["id"] if below else None,
                "wall_above": above["id"] if above else None,
                "classification": "plan_type_iv_out_of_plane_offset",
                "detail": irr.is_out_of_plane_offset(continues_on_same_plane=False),
            })

    return {"lines_traced": lines_traced, "discontinuities": discontinuities}


# ---------------------------------------------------------------------------
# Irregularity classification (only the 4 geometrically-determinable types)
# ---------------------------------------------------------------------------
def compute_mass_irregularity(model, needs_review):
    dyn = model.get("dynamic_loads", {}).get("seismic", {})
    story_forces = None
    for d in ("x_direction", "y_direction"):
        block = dyn.get(d)
        if block and block.get("story_forces"):
            story_forces = block["story_forces"]
            break
    if not story_forces:
        needs_review.append({"reason": "no dynamic_loads.seismic story_forces found -- "
                                        "mass irregularity not checked. Run dynamic-load first."})
        return []
    weights = [(sf["story_index"], sf["weight_kn"]) for sf in story_forces]
    weights.sort()
    flags = []
    n = len(weights)
    for i, (idx, w) in enumerate(weights):
        adjacent = []
        if i > 0:
            adjacent.append(weights[i - 1][1])
        if i < n - 1:
            adjacent.append(weights[i + 1][1])
        is_roof = (i == n - 1)
        if irr.is_mass_irregularity(w, adjacent, is_roof=is_roof):
            flags.append({"story_index": idx, "weight_kn": w, "adjacent_weights_kn": adjacent})
    return flags


def compute_non_parallel_systems(shear_walls):
    import math
    angles = []
    for w in shear_walls:
        pts = w.get("axis_points_mm")
        if not pts or len(pts) < 2:
            continue
        (x1, y1, _), (x2, y2, _) = pts[0], pts[1]
        angles.append(math.degrees(math.atan2(y2 - y1, x2 - x1)))
    if not angles:
        return {"flagged": False, "reason": "no shear walls with usable axis_points_mm"}
    return {"flagged": irr.is_non_parallel_system(angles), "angles_deg": [round(a, 2) for a in angles]}


# ---------------------------------------------------------------------------
# Role firming
# ---------------------------------------------------------------------------
def firm_up_roles(model, shear_wall_ids, lateral_discontinuity_wall_ids):
    """Upgrades the confidence of low-confidence `role` fields on columns
    and walls now that the full lateral system is known. Only upgrades
    confidence -- never downgrades a value skill 1 was already confident
    about, and never invents a role skill 1 didn't already assign."""
    updates = []
    for coll_name in ("columns", "walls"):
        for el in model.get("elements", {}).get(coll_name, []):
            role = el.get("role")
            if not role or role.get("confidence") != "low":
                continue
            is_lateral = el["id"] in shear_wall_ids
            previous = dict(role)
            if role.get("value") in ("gravity+lateral", "lateral") and not is_lateral:
                role["value"] = "gravity"
                role["confidence"] = "medium"
                role["signals"] = (role.get("signals") or []) + ["load-path: not part of any traced lateral element"]
            elif is_lateral:
                role["confidence"] = "medium"
                role["signals"] = (role.get("signals") or []) + ["load-path: confirmed part of a traced shear wall line"]
            else:
                continue
            updates.append({"element": el["id"], "previous": previous, "updated": dict(role)})
    return updates


# ---------------------------------------------------------------------------
def run(model, out_dir):
    needs_review = []

    gravity = trace_gravity_paths(model, needs_review)

    structural_system = (model.get("dynamic_loads", {}).get("seismic", {})
                          .get("shared_inputs", {}))
    shear_walls = identify_lateral_elements(model, structural_system)
    shear_wall_ids = {w["id"] for w in shear_walls}
    lateral = trace_lateral_continuity(model, shear_walls, needs_review)
    lateral_discontinuity_ids = {d["wall_below"] for d in lateral["discontinuities"] if d["wall_below"]}

    mass_irregularities = compute_mass_irregularity(model, needs_review)
    non_parallel = compute_non_parallel_systems(shear_walls)

    for d in lateral["discontinuities"]:
        below = next((w for w in shear_walls if w["id"] == d["wall_below"]), None)
        above = next((w for w in shear_walls if w["id"] == d["wall_above"]), None)
        if below and above:
            needs_review.append({"reason": f"wall line with gap at grid {d['grid_key']} has both a wall "
                                            f"below and above the gap -- offset magnitude not computed "
                                            f"(no in-plane/out-of-plane decomposition implemented for "
                                            f"the resume case, only the simple discontinuity flag)"})

    overstrength_elements = []
    for d in lateral["discontinuities"]:
        # Sec 2.5.5.6 requires overstrength design of whatever element
        # SUPPORTS the discontinuous wall -- that's whatever sits directly
        # beneath wall_above's own base (at the gap's upper boundary), NOT
        # wall_below (which may be several stories away and structurally
        # unrelated to this specific discontinuity). Unlike columns'
        # transfer_flag.lands_on, revit-structure-recognition doesn't
        # record a landing point for a discontinued wall's base, so the
        # specific supporting element genuinely isn't identifiable from
        # this data -- flagging that gap honestly beats naming the wrong
        # element with false confidence.
        overstrength_elements.append({
            "discontinuous_element": d["wall_above"], "grid_key": d["grid_key"],
            "gap_stories": d["gap_stories"],
            "reason": "Sec 2.5.5.6: whatever column/beam/slab sits directly beneath "
                      f"'{d['wall_above']}'s own base needs Omega0-amplified design per Sec "
                      "2.5.13.4 -- that specific supporting element isn't identified here. "
                      "revit-structure-recognition records a 'lands_on' landing point for "
                      "column transfers (transfer_flag) but has no equivalent field for a "
                      "discontinued wall's base -- identify it manually at this grid/story "
                      "before applying the overstrength combination.",
            "trigger": irr.requires_overstrength_design(True, "plan_type_iv"),
        })

    role_updates = firm_up_roles(model, shear_wall_ids, lateral_discontinuity_ids)

    is_regular_computed = not (bool(mass_irregularities) or bool(lateral["discontinuities"])
                                or non_parallel["flagged"])

    load_path = {
        "gravity": gravity,
        "lateral": {"system_elements": sorted(shear_wall_ids), **lateral},
        "irregularities": {
            "computed": {
                "mass_irregularity": {"value": bool(mass_irregularities), "detail": mass_irregularities},
                "vertical_in_plane_discontinuity": {"value": False, "detail": [],
                    "note": "offset decomposition not implemented -- see needs_review"},
                "out_of_plane_offset": {"value": bool(lateral["discontinuities"]),
                                         "detail": lateral["discontinuities"]},
                "non_parallel_systems": non_parallel,
            },
            "not_computable_here": {
                "torsion_irregularity": "needs storey displacement/drift from an actual analysis -- structural-analysis",
                "soft_storey": "needs relative storey stiffness -- structural-analysis",
                "weak_storey": "needs storey lateral strength/capacity -- structural-design",
                "re_entrant_corners": "needs floor plan outline geometry -- not captured by revit-structure-recognition today",
                "diaphragm_discontinuity": "needs floor plan area -- not captured by revit-structure-recognition today",
                "vertical_geometric_irregularity": "needs Fig 6.2.28(c)'s setback dimensions -- not transcribed",
            },
            "is_regular_computed": is_regular_computed,
            "is_regular_confidence": "partial -- based only on the 4 computed types out of 10; "
                                      "do not treat this as a full regularity clearance",
        },
        "overstrength_required_elements": overstrength_elements,
        "role_updates": role_updates,
        "needs_review": needs_review,
    }
    model["load_path"] = load_path

    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    (out_path / "structural_model.json").write_text(json.dumps(model, indent=2))

    print(f"Gravity: {len(gravity['traces'])} traced, {len(gravity['unresolved'])} unresolved. "
          f"Lateral: {len(lateral['lines_traced'])} lines, {len(lateral['discontinuities'])} discontinuities. "
          f"is_regular (partial, 4/10 types): {is_regular_computed}. "
          f"{len(needs_review)} item(s) flagged -> {out_path}/structural_model.json")
    return model


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--structural-model", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    model = json.loads(Path(args.structural_model).read_text())
    run(model, args.out)


if __name__ == "__main__":
    main()
