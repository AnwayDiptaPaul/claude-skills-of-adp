#!/usr/bin/env python3
"""
apply_loads.py — the entry point for this skill. Reads a structural_model.json
(from revit-structure-recognition), an occupancy_map.json (which story/room
gets which BNBC occupancy — see references/occupancy_map_format.md), computes
DL+SDL+LL per floor panel, distributes it to the surrounding beams (or to
columns directly for flat-plate stories), and writes an enriched
structural_model.json with the `loads` section populated.

Usage:
    python3 apply_loads.py --structural-model structural_model.json \
        --occupancy-map occupancy_map.json --out output_dir/

PANEL DETECTION SCOPE: reconstructs rectangular bays directly from the grid
system and each beam's grid_ref (along_gridline / spans_bay, from
revit-structure-recognition) — this covers the regular-grid case, which is
most buildings, without needing slab footprint geometry. A story where beams
don't cleanly bound a rectangle on all four sides (irregular floor plates,
mixed flat-plate/beam-supported areas, non-orthogonal grids) gets flagged
into needs_review rather than guessing a panel shape — see
references/known_limitations.md.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "codes" / "bnbc2020"))
import loads as bnbc                       # noqa: E402
import distribution as dist                # noqa: E402
from occupancy_mapping import classify_room_occupancy  # noqa: E402


def find_rectangular_panels(story_index, grids, beams_at_story):
    """Reconstruct rectangular bays at one story from the grid + beam data.
    A panel exists at the intersection of consecutive U-gridlines (u1,u2) and
    consecutive V-gridlines (v1,v2) when all four bounding beams are present
    at this story: two beams along u1 and u2 (each spanning bay [v1,v2]), and
    two beams along v1 and v2 (each spanning bay [u1,u2]).

    Returns (panels, unbounded_bays) — unbounded_bays are bay combinations
    where fewer than 4 bounding beams were found (candidate flat-plate areas
    or a genuine gap; both get surfaced to needs_review by the caller, not
    silently resolved here).
    """
    if not grids:
        return [], []
    grid = grids[0]
    u_tags = [ax["tag"] for ax in grid["axes"]["U"] if ax.get("points_mm")]
    v_tags = [ax["tag"] for ax in grid["axes"]["V"] if ax.get("points_mm")]

    def axis_pos(tag, family):
        for ax in grid["axes"][family]:
            if ax["tag"] == tag and ax.get("points_mm"):
                return ax["points_mm"][0][:2]
        return None

    def dist_between(tag_a, tag_b, family):
        pa, pb = axis_pos(tag_a, family), axis_pos(tag_b, family)
        if pa is None or pb is None:
            return None
        import math
        return math.hypot(pa[0] - pb[0], pa[1] - pb[1]) / 1000.0  # mm -> m

    along_lookup = {}  # (gridline_tag, bay_tuple) -> beam id
    for b in beams_at_story:
        ref = b.get("grid_ref") or {}
        if ref.get("along_gridline") and ref.get("spans_bay"):
            bay = tuple(sorted(ref["spans_bay"]))
            if len(bay) == 2:
                along_lookup[(ref["along_gridline"], bay)] = b["id"]

    panels, unbounded = [], []
    for i in range(len(u_tags) - 1):
        u1, u2 = u_tags[i], u_tags[i + 1]
        for j in range(len(v_tags) - 1):
            v1, v2 = v_tags[j], v_tags[j + 1]
            u_bay, v_bay = tuple(sorted((u1, u2))), tuple(sorted((v1, v2)))
            b_u1 = along_lookup.get((u1, v_bay))
            b_u2 = along_lookup.get((u2, v_bay))
            b_v1 = along_lookup.get((v1, u_bay))
            b_v2 = along_lookup.get((v2, u_bay))
            dim_u = dist_between(u1, u2, "U")
            dim_v = dist_between(v1, v2, "V")
            if None in (dim_u, dim_v) or dim_u <= 0 or dim_v <= 0:
                continue
            found = [x for x in (b_u1, b_u2, b_v1, b_v2) if x]
            entry = {
                "story_index": story_index, "bay": {"U": list(u_bay), "V": list(v_bay)},
                "dim_u_m": dim_u, "dim_v_m": dim_v,
                "bounding_beams": {"U1": b_u1, "U2": b_u2, "V1": b_v1, "V2": b_v2},
            }
            if len(found) == 4:
                panels.append(entry)
            else:
                entry["beams_found"] = len(found)
                unbounded.append(entry)
    return panels, unbounded


def compute_panel_loads(panel, live_load_kn_m2, sdl_kn_m2, dead_load_kn_m2):
    """Applies classify_and_distribute_panel() once per load type (DL, SDL,
    LL kept separate — see references/schema.md, load combinations are a
    structural-analysis concern, not this skill's) and returns the load each
    of the four bounding beams receives.
    """
    result = {}
    for load_type, w in (("DL", dead_load_kn_m2), ("SDL", sdl_kn_m2), ("LL", live_load_kn_m2)):
        dist_result = dist.classify_and_distribute_panel(w, panel["dim_u_m"], panel["dim_v_m"])
        # A beam "along gridline U=u1" runs perpendicular to U, spanning the V-bay --
        # its own physical length is dim_v_m, NOT dim_u_m (and symmetrically for V-beams
        # and dim_u_m). Get this backwards and every panel's short/long beam treatment
        # is swapped -- caught by testing against a known 6m x 4m fixture, where it was.
        u_beams_are_short = panel["dim_v_m"] <= panel["dim_u_m"]
        u_beam_result = dist_result["short_edge_beams"] if u_beams_are_short else dist_result["long_edge_beams"]
        v_beam_result = dist_result["long_edge_beams"] if u_beams_are_short else dist_result["short_edge_beams"]
        result[load_type] = {
            "classification": dist_result["classification"], "aspect_ratio": dist_result["aspect_ratio"],
            "u_direction_beams": u_beam_result, "v_direction_beams": v_beam_result,
        }
    return result


def slab_self_weight_kn_m2(thickness_mm, reinforcement_pct=1.0):
    if not thickness_mm:
        return None
    unit_weight = bnbc.reinforced_concrete_unit_weight_kn_m3(reinforcement_pct)
    return unit_weight * (thickness_mm / 1000.0)


def run(structural_model, occupancy_map, out_dir):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    needs_review = []

    stories = structural_model["stories"]
    grids = structural_model["grids"]
    beams = structural_model["elements"]["framing"]
    floors = structural_model["elements"]["floors"]

    occ_by_story = {entry["story_index"]: entry for entry in occupancy_map.get("entries", [])}

    loads_out = {"panels": [], "member_loads": {}, "needs_review": []}

    for story in stories:
        idx = story["index"]
        occ_entry = occ_by_story.get(idx)
        if not occ_entry:
            needs_review.append({"story": story["name"], "reason": "no occupancy_map entry for this story — every panel here will be skipped"})
            continue

        occ_result = classify_room_occupancy(occ_entry.get("room_name"), occ_entry.get("occupancy_param"), idx)
        occupancy_key = occ_entry.get("occupancy_key_override") or occ_result["value"]
        if not occupancy_key:
            needs_review.append({"story": story["name"], "reason": "occupancy could not be classified", "detail": "; ".join(occ_result["signals"])})
            continue
        live_load, _ = bnbc.get_live_load(occupancy_key)

        sdl_kn_m2 = occ_entry.get("sdl_kn_m2_override")
        if sdl_kn_m2 is None:
            needs_review.append({"story": story["name"], "reason": "no SDL specified for this story", "detail": "using 0.0 — supply sdl_kn_m2_override in the occupancy map, ideally via sdl_estimation.compose_sdl()"})
            sdl_kn_m2 = 0.0

        beams_here = [b for b in beams if (b.get("story") or {}).get("name") == story["name"]]
        panels, unbounded = find_rectangular_panels(idx, grids, beams_here)
        for u in unbounded:
            needs_review.append({"story": story["name"], "reason": "panel not fully bounded by beams",
                                  "detail": f"bay U={u['bay']['U']} V={u['bay']['V']} has {u['beams_found']}/4 bounding beams — "
                                            f"candidate flat-plate area or a real gap; verify manually"})

        # slab thickness for DL, if a floor element at this story has one
        story_floors = [f for f in floors if (f.get("story") or {}).get("name") == story["name"]]
        thickness = story_floors[0].get("thickness_mm") if story_floors else None
        dead_load = slab_self_weight_kn_m2(thickness) if thickness else 0.0
        if not thickness:
            needs_review.append({"story": story["name"], "reason": "no slab thickness found — panel dead load set to 0.0", "detail": "check elements.floors for this story"})

        for panel in panels:
            panel_loads = compute_panel_loads(panel, live_load, sdl_kn_m2, dead_load)
            loads_out["panels"].append({**panel, "occupancy": occupancy_key, "loads": panel_loads})
            for direction, beam_id in (("U1", panel["bounding_beams"]["U1"]), ("U2", panel["bounding_beams"]["U2"])):
                if beam_id:
                    loads_out["member_loads"].setdefault(beam_id, []).append(
                        {"from_bay": panel["bay"], "direction": "U", **panel_loads})
            for direction, beam_id in (("V1", panel["bounding_beams"]["V1"]), ("V2", panel["bounding_beams"]["V2"])):
                if beam_id:
                    loads_out["member_loads"].setdefault(beam_id, []).append(
                        {"from_bay": panel["bay"], "direction": "V", **panel_loads})

    loads_out["needs_review"] = needs_review
    structural_model["loads"] = loads_out

    (out_dir / "structural_model.json").write_text(json.dumps(structural_model, indent=2))
    print(f"{len(loads_out['panels'])} panel(s) loaded, {len(loads_out['member_loads'])} member(s) received a load, "
          f"{len(needs_review)} item(s) flagged for review -> {out_dir}/structural_model.json")
    return structural_model


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--structural-model", required=True)
    ap.add_argument("--occupancy-map", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    structural_model = json.loads(Path(args.structural_model).read_text())
    occupancy_map = json.loads(Path(args.occupancy_map).read_text())
    run(structural_model, occupancy_map, args.out)


if __name__ == "__main__":
    main()
