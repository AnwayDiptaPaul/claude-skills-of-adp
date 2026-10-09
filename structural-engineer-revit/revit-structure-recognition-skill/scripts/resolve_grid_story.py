#!/usr/bin/env python3
"""
resolve_grid_story.py — resolve every element's position relative to the
grid line + story system. Takes raw_inventory.json (from extract_ifc.py) and
adds, per element: a refined story assignment (base/top for vertical-extent
elements, since the IFC container relationship only reliably gives the story
an element was *drawn on*, not necessarily every story it spans), and a
grid_ref describing where it sits relative to the grid.

This does not classify anything — "on grid A/1" is a geometric fact, not a
judgment call. Classification lives in classify_elements.py.

Usage:
    python3 resolve_grid_story.py --in raw_inventory.json --out resolved_inventory.json [--tolerance-mm 50]
"""
import argparse
import json
import math
import sys
from pathlib import Path

LINE_LIKE_CLASSES = {"IfcBeam", "IfcMember", "IfcWall", "IfcWallStandardCase"}


# ---------- plane geometry (grids are read and matched in plan, XY only) ----------

def line_direction(p1, p2):
    dx, dy = p2[0] - p1[0], p2[1] - p1[1]
    length = math.hypot(dx, dy)
    if length < 1e-6:
        return None
    return (dx / length, dy / length)


def point_to_line_distance(pt, p1, p2):
    x0, y0 = pt
    x1, y1 = p1
    x2, y2 = p2
    dx, dy = x2 - x1, y2 - y1
    length = math.hypot(dx, dy)
    if length < 1e-6:
        return math.hypot(x0 - x1, y0 - y1)
    return abs(dx * (y1 - y0) - (x1 - x0) * dy) / length


def is_parallel(d1, d2, tol_deg=3.0):
    if d1 is None or d2 is None:
        return False
    dot = max(-1.0, min(1.0, abs(d1[0] * d2[0] + d1[1] * d2[1])))
    return math.degrees(math.acos(dot)) <= tol_deg


def nearest_grid_axis(point_xy, axis_list):
    """Closest axis in one grid family. Returns (tag, distance_mm) or (None, None)."""
    best_tag, best_dist = None, None
    for ax in axis_list:
        pts = ax.get("points_mm")
        if not pts:
            continue
        d = point_to_line_distance(point_xy, pts[0][:2], pts[1][:2])
        if best_dist is None or d < best_dist:
            best_tag, best_dist = ax["tag"], d
    return best_tag, best_dist


def family_direction(axis_list):
    for ax in axis_list:
        pts = ax.get("points_mm")
        if pts:
            d = line_direction(pts[0][:2], pts[1][:2])
            if d:
                return d
    return None


def resolve_point_grid_ref(point_mm, grid, tolerance_mm):
    xy = point_mm[:2]
    u_tag, u_dist = nearest_grid_axis(xy, grid["axes"]["U"])
    v_tag, v_dist = nearest_grid_axis(xy, grid["axes"]["V"])
    offset = None
    if u_dist is not None and v_dist is not None:
        offset = math.hypot(u_dist, v_dist)
    return {
        "at": [u_tag, v_tag],
        "offset_mm": round(offset, 1) if offset is not None else None,
        "on_grid": offset is not None and offset <= tolerance_mm,
    }


def resolve_line_grid_ref(axis_points_mm, grid, tolerance_mm):
    U, V = grid["axes"]["U"], grid["axes"]["V"]
    p1, p2 = axis_points_mm[0][:2], axis_points_mm[1][:2]
    el_dir = line_direction(p1, p2)

    if el_dir is None:  # degenerate/zero-length axis — treat as a point
        return resolve_point_grid_ref(axis_points_mm[0], grid, tolerance_mm)

    # Coincident with one line in a family -> spans the bay in the other family
    for this_family, other_family in ((U, V), (V, U)):
        fam_dir = family_direction(this_family)
        if not is_parallel(el_dir, fam_dir):
            continue
        tag1, d1 = nearest_grid_axis(p1, this_family)
        tag2, d2 = nearest_grid_axis(p2, this_family)
        if tag1 is not None and tag1 == tag2 and d1 is not None and d1 <= tolerance_mm:
            other_tag1, _ = nearest_grid_axis(p1, other_family)
            other_tag2, _ = nearest_grid_axis(p2, other_family)
            bay = sorted({t for t in (other_tag1, other_tag2) if t is not None})
            return {"along_gridline": tag1, "spans_bay": bay or None, "on_grid": True}

    # Didn't resolve cleanly — report each endpoint's nearest reference and
    # let classify_elements.py / the review report decide whether that's fine
    # (plenty of real framing legitimately doesn't sit on a gridline) or worth
    # a human glance (off-grid by an amount that looks like a modeling slip).
    return {
        "along_gridline": None,
        "spans_bay": None,
        "on_grid": False,
        "endpoint_refs": [
            resolve_point_grid_ref(axis_points_mm[0], grid, tolerance_mm),
            resolve_point_grid_ref(axis_points_mm[1], grid, tolerance_mm),
        ],
    }


# ---------- story resolution ----------

def nearest_storey(z_mm, storeys):
    candidates = [s for s in storeys if s["elevation_mm"] is not None]
    if not candidates or z_mm is None:
        return None
    return min(candidates, key=lambda s: abs(s["elevation_mm"] - z_mm))


def refine_story(element, storeys):
    """For elements with axis geometry, decide base/top story from the axis
    itself — but only when the axis is *predominantly vertical* (columns,
    vertical braces), where Z-range genuinely means "how tall". A wall's or
    beam's Axis representation is its plan centerline — near-constant Z — so
    running the same Z-range logic on it doesn't give a vertical extent, it
    gives noise (and, worse, can coincidentally land on the wrong story if
    the wall sits at an unusual elevation). For predominantly horizontal
    axes, prefer the IFC containment relationship (already reliable for the
    common one-instance-per-story modeling pattern), falling back to the
    axis midpoint's Z only if no container was found.
    """
    axis = element.get("axis_points_mm")
    if axis and len(axis) >= 2:
        p1, p2 = axis[0], axis[1]
        dz = abs(p1[2] - p2[2])
        dxy = math.hypot(p1[0] - p2[0], p1[1] - p2[1])

        if dz > dxy:  # predominantly vertical -> Z-range genuinely is the extent
            z_values = [p1[2], p2[2]]
            base = nearest_storey(min(z_values), storeys)
            top = nearest_storey(max(z_values), storeys)
            return (
                {"id": base["global_id"], "name": base["name"]} if base else None,
                {"id": top["global_id"], "name": top["name"]} if top else None,
            )

        container = element.get("storey")
        if container:
            ref = {"id": container["global_id"], "name": container["name"]}
            return ref, ref
        z = (p1[2] + p2[2]) / 2.0
        nearest = nearest_storey(z, storeys)
        single = {"id": nearest["global_id"], "name": nearest["name"]} if nearest else None
        return single, single

    # No axis — insertion point + IFC container fallback
    container = element.get("storey")
    if container:
        ref = {"id": container["global_id"], "name": container["name"]}
        return ref, ref
    z = element.get("insertion_point_mm", [None, None, None])[2]
    nearest = nearest_storey(z, storeys)
    single = {"id": nearest["global_id"], "name": nearest["name"]} if nearest else None
    return single, single


def resolve(data, tolerance_mm):
    grids = data.get("grids") or []
    storeys = data.get("storeys") or []
    grid = grids[0] if grids else None
    if len(grids) > 1:
        print(
            f"WARNING: {len(grids)} grid systems found; using '{grid['name']}' for all "
            f"elements. Multi-grid buildings (e.g. tower + separately-gridded podium) need "
            f"manual review of grid_ref for elements outside the primary grid's extents.",
            file=sys.stderr,
        )

    for el in data["elements"]:
        cls = el["ifc_class"]

        if cls != "IfcOpeningElement":
            base, top = refine_story(el, storeys)
            el["base_story"] = base
            el["top_story"] = top
            # keep "story" as the more specific one for single-story elements;
            # for elements spanning stories, base_story/top_story are authoritative
            el["story"] = base if base == top else el.get("storey")

        if grid is None:
            el["grid_ref"] = None
            continue

        axis = el.get("axis_points_mm")
        if axis and len(axis) >= 2 and cls in LINE_LIKE_CLASSES:
            el["grid_ref"] = resolve_line_grid_ref(axis, grid, tolerance_mm)
        elif el.get("insertion_point_mm"):
            el["grid_ref"] = resolve_point_grid_ref(el["insertion_point_mm"], grid, tolerance_mm)
        else:
            el["grid_ref"] = None

    return data


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--in", dest="infile", required=True)
    ap.add_argument("--out", dest="outfile", required=True)
    ap.add_argument("--tolerance-mm", type=float, default=50.0,
                     help="Snap tolerance for 'on grid' — default 50mm, generous enough for "
                          "typical formwork tolerance without masking a genuine deliberate offset.")
    args = ap.parse_args()

    data = json.loads(Path(args.infile).read_text())
    data = resolve(data, args.tolerance_mm)

    Path(args.outfile).parent.mkdir(parents=True, exist_ok=True)
    Path(args.outfile).write_text(json.dumps(data, indent=2))
    print(f"Resolved grid/story references for {len(data['elements'])} elements -> {args.outfile}")


if __name__ == "__main__":
    main()
