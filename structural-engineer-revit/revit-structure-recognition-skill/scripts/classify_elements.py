#!/usr/bin/env python3
"""
classify_elements.py — apply the decision logic in
references/classification_heuristics.md to a grid/story-resolved inventory.
This is where engineering judgment lives; every function here should be
readable next to the corresponding section of that reference file.

Nothing in this file decides silently. Every classification carries a
confidence and the signals behind it, and anything low-confidence or
conflicting lands in review.needs_review instead of being forced into a
single answer — see the "Confidence rubric" section of the heuristics doc.

Usage:
    python3 classify_elements.py --in resolved_inventory.json --out structural_model.json [--grade-story "Ground Floor"]
"""
import argparse
import json
import math
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import resolve_grid_story as rgs  # reuse the line-geometry helpers for wall-continuity matching

ID_PREFIXES = {
    "IfcColumn": "COL", "IfcBeam": "BM", "IfcMember": "MBR",
    "IfcWall": "WALL", "IfcWallStandardCase": "WALL",
    "IfcSlab": "SLAB", "IfcOpeningElement": "OPEN",
    "IfcFooting": "FTG", "IfcPile": "PILE",
}

STEEL_PROFILE_RE = re.compile(
    r"\b(W\d+[xX]\d+|HE\d{2,3}[AB]?\b|UC\d{2,4}|UB\d{2,4}|ISMB\d*|ISHB\d*|ISLB\d*|ISWB\d*|ISA\d*|ISC\d*|"
    r"HSS[\d.]+[xX][\d.]+(?:[xX][\d.]+)?|RHS\d*|CHS[\d.]*|SHS\d*|L\d{2,4}\s*[xX]\s*\d{2,4}|"
    r"C\d{2,4}\s*[xX]\s*\d{2,4}(?:\.\d+)?|PFC\b)", re.I,
)
STEEL_GRADE_RE = re.compile(r"\bA(36|53|500|572|588|992)\b|\bS(235|275|355|420|460)\b|\bFe\s?\d{3}\b|\bE\d{3}\b", re.I)
DIM_PATTERN_RE = re.compile(r"\b\d{2,4}\s*[xX×]\s*\d{2,4}\b")


def clsf(value, confidence, signals):
    return {"value": value, "confidence": confidence, "signals": signals}


# ---------------------------------------------------------------- frame type

def classify_frame_type(element):
    mat = element.get("material") or {}
    names = " ".join(mat.get("names") or []).lower()
    profile_names = " ".join(mat.get("profile_names") or [])
    object_type = element.get("object_type") or ""

    scores = {"RCC": 0, "Steel": 0, "Timber": 0, "Masonry": 0}
    signals = []

    if "concrete" in names:
        scores["RCC"] += 2
        signals.append("material name contains 'concrete'")
    if "steel" in names or STEEL_GRADE_RE.search(names):
        scores["Steel"] += 2
        signals.append("material name contains 'steel' or matches a steel grade pattern (A36/A992/S355/Fe415-style)")
    if any(k in names for k in ("timber", "wood", "glulam", "clt")):
        scores["Timber"] += 2
        signals.append("material name contains a timber/wood keyword")
    if any(k in names for k in ("masonry", "brick", "block", " cmu", "cmu ")):
        scores["Masonry"] += 2
        signals.append("material name contains a masonry keyword")
    if profile_names and STEEL_PROFILE_RE.search(profile_names):
        scores["Steel"] += 2
        signals.append(f"profile name matches a steel section pattern ('{profile_names.strip()}')")
    if DIM_PATTERN_RE.search(object_type) and scores["RCC"] > 0:
        scores["RCC"] += 1
        signals.append("object type matches a rectangular concrete-style dimension pattern")

    if mat.get("kind") == "profile" and scores["RCC"] >= scores["Steel"] and scores["RCC"] > 0:
        signals.append("CONFLICT: material is defined as a profile set (steel-typical) but material name reads as concrete")

    if not any(scores.values()):
        return clsf("Unknown", "low", ["no usable material or profile signal found"])

    best_type, best_score = max(scores.items(), key=lambda kv: kv[1])
    second_score = sorted(scores.values(), reverse=True)[1]
    if best_score > second_score and best_score >= 2:
        confidence = "high" if (best_score >= 3 and second_score == 0) else "medium"
    else:
        confidence = "low"
    return clsf(best_type, confidence, signals)


# --------------------------------------------------------------------- walls

def _pset_value(psets, key_substrings):
    for props in (psets or {}).values():
        for prop_name, value in (props or {}).items():
            if any(k in prop_name.lower() for k in key_substrings):
                return value
    return None


def compute_wall_story_span(wall, all_walls, story_index_by_id, xy_tol_mm=200.0):
    """A wall's Axis representation is its plan centerline, so — unlike a
    column — base_story == top_story for a single wall instance; that's
    correct, not a bug (see resolve_grid_story.refine_story). Real continuity
    across stories shows up as *separate* wall instances at consecutive
    stories sharing the same plan line, which is how most Revit models
    actually build a tall shear wall (one instance per story, stacked).
    This finds the contiguous run of stories, including this wall's own,
    that have a horizontally-coincident wall — that run length is the
    "continuous through N stories" signal classify_wall wants."""
    axis = wall.get("axis_points_mm")
    my_story = wall.get("base_story")
    if not axis or len(axis) < 2 or not my_story or my_story.get("id") not in story_index_by_id:
        return 1
    my_idx = story_index_by_id[my_story["id"]]
    p1, p2 = axis[0][:2], axis[1][:2]
    my_dir = rgs.line_direction(p1, p2)
    if not my_dir:
        return 1

    coincident_indices = {my_idx}
    for other in all_walls:
        if other is wall:
            continue
        o_story = other.get("base_story")
        o_axis = other.get("axis_points_mm")
        if not o_story or o_story.get("id") not in story_index_by_id or not o_axis or len(o_axis) < 2:
            continue
        o_p1, o_p2 = o_axis[0][:2], o_axis[1][:2]
        o_dir = rgs.line_direction(o_p1, o_p2)
        if not o_dir or not rgs.is_parallel(my_dir, o_dir):
            continue
        if rgs.point_to_line_distance(o_p1, p1, p2) <= xy_tol_mm:
            coincident_indices.add(story_index_by_id[o_story["id"]])

    run = {my_idx}
    idx = my_idx - 1
    while idx in coincident_indices:
        run.add(idx)
        idx -= 1
    idx = my_idx + 1
    while idx in coincident_indices:
        run.add(idx)
        idx += 1
    return len(run)


def classify_wall(element, all_walls, story_index_by_id, grade_index, opening_ratio):
    mat = element.get("material") or {}
    thickness = mat.get("layer_thickness_mm")
    predefined = (element.get("predefined_type") or "").upper()
    base = element.get("base_story") or {}

    scores = {"shear": 0, "retaining": 0, "partition_or_cladding": 0}
    signals = {"shear": [], "retaining": [], "partition_or_cladding": []}
    strong = {"shear": False, "retaining": False, "partition_or_cladding": False}

    func_value = _pset_value(element.get("psets"), ["function"])
    if func_value:
        fv = str(func_value).lower()
        if "retain" in fv:
            scores["retaining"] += 4
            signals["retaining"].append(f"Revit Function parameter = '{func_value}'")
            strong["retaining"] = True
        elif "foundation" in fv:
            scores["retaining"] += 3
            signals["retaining"].append(f"Revit Function parameter = '{func_value}'")
            strong["retaining"] = True
        elif "interior" in fv or "core" in fv:
            signals["shear"].append(f"Revit Function parameter = '{func_value}' (weak, informational)")

    if predefined == "RETAININGWALL":
        scores["retaining"] += 4
        signals["retaining"].append("IFC PredefinedType = RETAININGWALL")
        strong["retaining"] = True
    if predefined == "SHEAR":
        scores["shear"] += 1
        signals["shear"].append(
            "IFC PredefinedType = SHEAR (weak only — buildingSMART's own schema note: "
            "this denotes wall shape, not shear resistance)"
        )

    story_span = compute_wall_story_span(element, all_walls, story_index_by_id)
    if story_span >= 3:
        scores["shear"] += 2
        signals["shear"].append(f"continuous through {story_span} stories (stacked, coincident wall instances)")
    elif story_span == 1:
        scores["partition_or_cladding"] += 1
        signals["partition_or_cladding"].append("present at only one story")

    if thickness is not None:
        if thickness >= 150:
            scores["shear"] += 1
            scores["retaining"] += 1
            signals["shear"].append(f"thickness {thickness:.0f}mm (>= 150mm)")
            signals["retaining"].append(f"thickness {thickness:.0f}mm (>= 150mm)")
        elif thickness <= 115:
            scores["partition_or_cladding"] += 2
            signals["partition_or_cladding"].append(f"thickness {thickness:.0f}mm (<= 115mm)")

    if opening_ratio is not None:
        if opening_ratio > 0.25:
            scores["partition_or_cladding"] += 2
            signals["partition_or_cladding"].append(f"opening area ~{opening_ratio:.0%} of wall face")
        elif opening_ratio > 0:
            signals["shear"].append(f"opening area ~{opening_ratio:.0%} of wall face — modest, doesn't rule out shear/retaining")

    below_grade = None
    if grade_index is not None and base.get("id") in story_index_by_id:
        below_grade = story_index_by_id[base["id"]] < grade_index
        if below_grade:
            scores["retaining"] += 1
            signals["retaining"].append("base story is below the project's grade-level story")

    ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    top_role, top_score = ranked[0]
    second_role, second_score = ranked[1]

    if top_score <= 0:
        return {"primary": "unknown", "secondary": None, "confidence": "low",
                "dual_role": False, "signals": ["no usable signal for any role"]}, True

    dominant = top_score >= 2 * max(second_score, 1) or (top_score - second_score) >= 3
    both_structural_plausible = scores["shear"] >= 2 and scores["retaining"] >= 2

    if both_structural_plausible and not dominant:
        return {
            "primary": "shear", "secondary": "retaining", "confidence": "medium",
            "dual_role": True,
            "signals": signals["shear"] + signals["retaining"],
        }, True  # boundary-condition treatment always needs an engineer's confirmation

    if dominant and (strong.get(top_role) or top_score >= 4):
        return {
            "primary": top_role, "secondary": None,
            "confidence": "high" if strong.get(top_role) else "medium",
            "dual_role": False, "signals": signals[top_role],
        }, False

    return {
        "primary": top_role, "secondary": None, "confidence": "low",
        "dual_role": False, "signals": signals[top_role],
    }, True


# --------------------------------------------------------------------- slabs

def classify_slab(element, has_nearby_framing, steel_building_prior):
    mat = element.get("material") or {}
    names = " ".join(mat.get("names") or []).lower()
    signals = []

    if "deck" in names or "corrugated" in names:
        signals.append("material name contains 'deck'/'corrugated'")
        return clsf("composite_metal_deck", "medium", signals)
    if steel_building_prior and not has_nearby_framing:
        signals.append("no concrete signal, and building's framing is predominantly steel (prior)")
        return clsf("composite_metal_deck", "low", signals)

    if not has_nearby_framing:
        signals.append("no framing beams found at this story near this slab")
        return clsf("flat_plate", "medium", signals)

    signals.append("framing beams present at this story near this slab")
    signals.append(
        "NOTE: this skill does not currently extract slab footprint geometry, so one-way vs. "
        "two-way vs. waffle cannot be distinguished from bay aspect ratio yet — treat as "
        "'beam-supported, sub-type unresolved' until that extension is added (see SKILL.md "
        "known limitations), or confirm manually from the framing plan."
    )
    return clsf("beam_supported_unrefined", "low", signals)


# ------------------------------------------------------------------ footings

def horiz_distance(p1, p2):
    return math.hypot(p1[0] - p2[0], p1[1] - p2[1])


def classify_footing(footing, columns, piles, proximity_mm=1500.0, pile_proximity_mm=2500.0):
    predefined = (footing.get("predefined_type") or "").upper()
    fpt = footing.get("insertion_point_mm")
    signals = []

    supports = []
    if fpt:
        for c in columns:
            cpt = c.get("insertion_point_mm")
            if cpt and horiz_distance(fpt, cpt) <= proximity_mm:
                supports.append(c["id"])
    footing["supports"] = supports

    nearby_piles = []
    if fpt:
        for p in piles:
            ppt = p.get("insertion_point_mm")
            if ppt and horiz_distance(fpt, ppt) <= pile_proximity_mm:
                nearby_piles.append(p["id"])

    if nearby_piles or predefined == "PILE_CAP":
        signals.append(f"{len(nearby_piles)} pile(s) within {pile_proximity_mm:.0f}mm")
        if predefined == "PILE_CAP":
            signals.append("IFC PredefinedType = PILE_CAP")
        for p in piles:
            if p["id"] in nearby_piles:
                p["pile_cap_id"] = footing["id"]
        return clsf("pile_cap", "high" if predefined == "PILE_CAP" else "medium", signals)

    if predefined == "STRIP_FOOTING":
        return clsf("strip", "high", ["IFC PredefinedType = STRIP_FOOTING"])

    if predefined == "PAD_FOOTING" or len(supports) == 1:
        signals.append("IFC PredefinedType = PAD_FOOTING" if predefined == "PAD_FOOTING"
                        else f"exactly 1 column ({supports[0]}) within {proximity_mm:.0f}mm")
        return clsf("isolated", "high" if predefined == "PAD_FOOTING" else "medium", signals)
    if len(supports) == 2:
        signals.append(f"2 columns within proximity: {supports}")
        return clsf("combined", "medium", signals)
    if len(supports) >= 3:
        signals.append(f"{len(supports)} columns within proximity — large footprint")
        return clsf("mat_raft", "medium", signals)

    return clsf("unknown", "low", ["no supported columns found within proximity, and no usable PredefinedType"])


# ------------------------------------------------------------- framing role

def endpoint_matches(pt, candidates, tol_mm):
    for c in candidates:
        cpt = c.get("insertion_point_mm")
        if cpt and horiz_distance(pt, cpt) <= tol_mm:
            return c["id"]
        axis = c.get("axis_points_mm")
        if axis:
            for ap in axis:
                if horiz_distance(pt, ap) <= tol_mm:
                    return c["id"]
    return None


def classify_framing_role(beam, columns, other_beams, walls, tol_mm=300.0):
    axis = beam.get("axis_points_mm")
    predefined = (beam.get("predefined_type") or "").upper()
    name_text = f"{beam.get('object_type') or ''} {beam.get('name') or ''}".lower()
    signals = []

    # NOTE: IfcBeamTypeEnum in plain IFC4 is {BEAM, JOIST, HOLLOWCORE, LINTEL,
    # SPANDREL, T_BEAM, USERDEFINED, NOTDEFINED} — there is no GIRDER value,
    # confirmed against the schema itself (ifcopenshell.ifcopenshell_wrapper
    # .schema_by_name("IFC4").declaration_by_name("IfcBeamTypeEnum")). Office
    # naming conventions still use the word "girder" constantly though, so it's
    # kept as a text-pattern signal on the name/object type instead of a
    # PredefinedType lookup that would simply never fire.
    if predefined == "JOIST":
        signals.append("IFC PredefinedType = JOIST")
        base_guess, base_conf = "secondary", "medium"
    elif predefined == "SPANDREL":
        signals.append("IFC PredefinedType = SPANDREL (perimeter/edge beam)")
        base_guess, base_conf = "primary", "medium"
    elif predefined == "LINTEL":
        signals.append("IFC PredefinedType = LINTEL (opening header, not primary framing)")
        base_guess, base_conf = "secondary", "medium"
    elif "girder" in name_text:
        signals.append("name/object type contains 'girder'")
        base_guess, base_conf = "primary", "low"
    else:
        base_guess, base_conf = None, None

    if not axis or len(axis) < 2:
        return clsf(base_guess or "unknown", base_conf or "low", signals or ["no axis geometry available"])

    p1, p2 = axis[0], axis[1]
    dz = abs(p1[2] - p2[2])
    dxy = horiz_distance(p1, p2)
    if dxy < 1e-3 and dz > 1e-3:
        return clsf("vertical_member_not_framing", "medium", ["axis is vertical — likely miscategorized or a brace, see IfcMember review"])
    if dxy > 1e-3 and dz / max(dxy, 1e-6) > 0.15:
        signals.append(f"axis rises {dz:.0f}mm over {dxy:.0f}mm run — diagonal")
        return clsf("brace", "medium", signals)

    end1 = endpoint_matches(p1, columns, tol_mm) or endpoint_matches(p1, walls, tol_mm)
    end2 = endpoint_matches(p2, columns, tol_mm) or endpoint_matches(p2, walls, tol_mm)
    if end1 and end2:
        signals.append(f"both ends land on vertical elements ({end1}, {end2})")
        return clsf("primary", "high" if base_guess in (None, "primary") else "medium", signals)
    if end1 or end2:
        other_end_beam = endpoint_matches(p2 if end1 else p1, other_beams, tol_mm)
        if other_end_beam:
            signals.append("one end on a column/wall, other end on another beam")
            return clsf("secondary", "medium", signals)
        signals.append("one end free — no column, wall, or beam found within tolerance")
        return clsf("cantilever", "medium", signals)

    e1b = endpoint_matches(p1, other_beams, tol_mm)
    e2b = endpoint_matches(p2, other_beams, tol_mm)
    if e1b and e2b:
        signals.append(f"both ends land on other beams ({e1b}, {e2b})")
        return clsf("secondary", "medium", signals)

    if base_guess:
        return clsf(base_guess, base_conf, signals + ["endpoints did not resolve geometrically — falling back to PredefinedType"])
    return clsf("unknown", "low", ["neither PredefinedType nor endpoint geometry resolved a role"] + signals)


# ------------------------------------------------------------------ transfers

def detect_column_transfers(columns, walls, beams, storeys, tol_mm=300.0):
    idx_by_id = {s["global_id"]: s["index"] for s in storeys}

    for col in columns:
        base = col.get("base_story")
        if not base or base.get("id") not in idx_by_id:
            continue
        base_idx = idx_by_id[base["id"]]
        if base_idx == 0:
            col["is_transfer_column"] = False
            col["transfer_flag"] = None
            continue  # lowest story — lands on foundation, not a transfer condition

        pt = col.get("insertion_point_mm")
        if not pt:
            continue

        # A genuine support reaches UP TO this column's base elevation — i.e.
        # its own top_story matches this column's base_story (both reference
        # the same elevation where they meet). It is NOT "the story below by
        # index": a column based at Ground Floor is supported by something
        # whose top is *at* Ground Floor, not at Basement.
        supports_below = [
            c for c in columns
            if c.get("top_story") and idx_by_id.get(c["top_story"]["id"]) == base_idx
        ] + [
            w for w in walls
            if w.get("top_story") and idx_by_id.get(w["top_story"]["id"]) == base_idx
        ]
        landing = endpoint_matches(pt, supports_below, tol_mm)
        if landing:
            col["is_transfer_column"] = False
            col["transfer_flag"] = None
            continue

        beams_below = [b for b in beams
                       if b.get("story") and idx_by_id.get(b["story"].get("id")) == base_idx]
        beam_hit = None
        for b in beams_below:
            axis = b.get("axis_points_mm")
            if not axis or len(axis) < 2:
                continue
            d = point_to_segment_distance(pt, axis[0], axis[1])
            if d <= tol_mm:
                beam_hit = b["id"]
                break

        col["is_transfer_column"] = True
        col["transfer_flag"] = {
            "lands_on": beam_hit,
            "note": ("lands on framing member " + beam_hit) if beam_hit else
                    "no column, wall, or beam found within tolerance directly below — verify manually",
        }
        if beam_hit:
            for b in beams:
                if b["id"] == beam_hit:
                    b["supports_transfer_condition"] = True


def point_to_segment_distance(pt, seg_a, seg_b):
    ax, ay = seg_a[0], seg_a[1]
    bx, by = seg_b[0], seg_b[1]
    px, py = pt[0], pt[1]
    dx, dy = bx - ax, by - ay
    length_sq = dx * dx + dy * dy
    if length_sq < 1e-6:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / length_sq))
    proj_x, proj_y = ax + t * dx, ay + t * dy
    return math.hypot(px - proj_x, py - proj_y)


# ------------------------------------------------------------------- openings

def classify_opening(opening, walls_by_id):
    host_id = opening.get("_host_id")
    flags = []
    if host_id and host_id in walls_by_id:
        wall = walls_by_id[host_id]
        wc = wall.get("wall_class", {})
        if wc.get("primary") == "shear" or wc.get("secondary") == "shear":
            flags.append("within_shear_wall")
        if wc.get("primary") == "retaining" or wc.get("secondary") == "retaining":
            flags.append("unusual_for_retaining_wall — verify wall classification")
    opening["flags"] = flags
    return opening


# --------------------------------------------------------------- orchestration

def assign_ids(elements):
    counters = {}
    for el in elements:
        prefix = ID_PREFIXES.get(el["ifc_class"], "EL")
        counters[prefix] = counters.get(prefix, 0) + 1
        el["id"] = f"{prefix}-{counters[prefix]:04d}"


def classify(data, grade_story_name=None):
    elements = data["elements"]
    storeys = data["storeys"]
    assign_ids(elements)

    columns = [e for e in elements if e["ifc_class"] == "IfcColumn"]
    beams = [e for e in elements if e["ifc_class"] in ("IfcBeam", "IfcMember")]
    walls = [e for e in elements if e["ifc_class"] in ("IfcWall", "IfcWallStandardCase")]
    slabs = [e for e in elements if e["ifc_class"] == "IfcSlab"]
    footings = [e for e in elements if e["ifc_class"] == "IfcFooting"]
    piles = [e for e in elements if e["ifc_class"] == "IfcPile"]
    openings = [e for e in elements if e["ifc_class"] == "IfcOpeningElement"]

    needs_review = []

    def flag(el, reason, detail):
        needs_review.append({"element_id": el["id"], "element_type": el["ifc_class"], "reason": reason, "detail": detail})

    # --- frame type: columns + framing ---
    for el in columns + beams:
        result = classify_frame_type(el)
        el["frame_type"] = result
        if result["confidence"] == "low":
            flag(el, "frame_type low confidence", "; ".join(result["signals"]) or "no signal")

    # --- grade story index ---
    grade_index = None
    if grade_story_name:
        for s in storeys:
            if s["name"] and grade_story_name.lower() in s["name"].lower():
                grade_index = s["index"]
                break
    else:
        # heuristic default: first story whose name suggests ground/grade
        for s in storeys:
            if s["name"] and re.search(r"\bground\b|\bg\.?f\.?\b|\bgrade\b", s["name"], re.I):
                grade_index = s["index"]
                break
    story_index_by_id = {s["global_id"]: s["index"] for s in storeys}

    # --- openings -> host lookup; opening_ratio is a coarse presence proxy (see
    # classify_slab / SKILL.md limitations — true area ratio needs opening+wall
    # face geometry this skill doesn't extract yet) ---
    walls_by_id = {}
    for op in openings:
        host_gid = op.get("host_global_id")
        op["_host_id"] = None
        for w in walls:
            if w["global_id"] == host_gid:
                op["_host_id"] = w["id"]
                break
    for w in walls:
        walls_by_id[w["id"]] = w

    # --- walls ---
    for w in walls:
        host_openings = [o for o in openings if o.get("_host_id") == w["id"]]
        opening_ratio = 0.15 if host_openings else 0.0  # coarse proxy: presence of any opening;
        # true area ratio needs opening + wall face geometry this skill doesn't extract yet (see limitations)
        wc, review_flag = classify_wall(w, walls, story_index_by_id, grade_index, opening_ratio)
        w["wall_class"] = wc
        w["thickness_mm"] = (w.get("material") or {}).get("layer_thickness_mm")
        if review_flag:
            flag(w, "wall_class needs confirmation",
                 f"primary={wc['primary']}, dual_role={wc['dual_role']}, confidence={wc['confidence']}; "
                 + "; ".join(wc["signals"]))

    for op in openings:
        classify_opening(op, walls_by_id)

    # --- transfers (also marks beam.supports_transfer_condition) ---
    for b in beams:
        b["supports_transfer_condition"] = False
    detect_column_transfers(columns, walls, beams, storeys)
    for c in columns:
        if c.get("is_transfer_column"):
            flag(c, "transfer column", (c.get("transfer_flag") or {}).get("note", ""))

    # --- framing role ---
    for b in beams:
        other_beams = [x for x in beams if x["id"] != b["id"]]
        role = classify_framing_role(b, columns, other_beams, walls)
        b["framing_role"] = role
        if b.get("supports_transfer_condition"):
            b["framing_role"] = clsf("transfer", "high", ["supports a transfer column landing on this member"])
        if role["confidence"] == "low":
            flag(b, "framing_role low confidence", "; ".join(role["signals"]) or "no signal")

    # --- slabs ---
    steel_count = sum(1 for c in columns if c.get("frame_type", {}).get("value") == "Steel")
    steel_prior = steel_count > len(columns) / 2 if columns else False
    for s in slabs:
        story_id = (s.get("story") or {}).get("id")
        nearby_beams = [b for b in beams if (b.get("story") or {}).get("id") == story_id]
        result = classify_slab(s, bool(nearby_beams), steel_prior)
        s["slab_type"] = result
        if result["confidence"] == "low":
            flag(s, "slab_type low confidence", "; ".join(result["signals"]))

    # --- footings + piles ---
    for f in footings:
        result = classify_footing(f, columns, piles)
        f["footing_type"] = result
        if result["confidence"] == "low":
            flag(f, "footing_type low confidence", "; ".join(result["signals"]))
    for p in piles:
        p.setdefault("pile_cap_id", None)

    # --- foundation system summary ---
    type_counts = {"isolated": 0, "combined": 0, "strap": 0, "mat_raft": 0, "pile_cap": 0, "strip": 0, "unknown": 0}
    for f in footings:
        type_counts[f["footing_type"]["value"]] = type_counts.get(f["footing_type"]["value"], 0) + 1
    type_counts["piles_total"] = len(piles)
    shallow = type_counts["isolated"] + type_counts["combined"] + type_counts["strap"] + type_counts["mat_raft"]
    deep = type_counts["pile_cap"]
    if shallow and deep:
        predominant = "mixed"
    elif deep:
        predominant = "deep_pile"
    elif type_counts["mat_raft"] and not (type_counts["isolated"] or type_counts["combined"]):
        predominant = "mat"
    else:
        predominant = "shallow"
    foundation_summary = {
        "predominant_system": predominant,
        "counts": type_counts,
        "mixed_system_flag": bool(shallow and deep),
    }
    if foundation_summary["mixed_system_flag"]:
        needs_review.append({
            "element_id": None, "element_type": "foundation_system_summary",
            "reason": "mixed shallow + deep foundation systems in one model",
            "detail": f"{shallow} shallow footing(s) and {deep} pile cap(s) found — confirm this is "
                      f"intentional (e.g. a lightly loaded canopy/stair core vs. a piled main structure "
                      f"on different bearing strata) rather than a modeling inconsistency.",
        })

    # --- assemble final structural_model.json ---
    for el in elements:
        el.pop("psets", None)
        el.pop("qtos", None)
        el.pop("storey", None)

    model = {
        "meta": {
            "schema_version": "0.1.0",
            "generated_by": "revit-structure-recognition",
            "source_file": data.get("source_file"),
            "ifc_schema": data.get("ifc_schema"),
        },
        "project": {"name": data.get("project_name"), "length_unit": "mm"},
        "grids": data.get("grids"),
        "stories": storeys,
        "elements": {
            "columns": columns, "framing": beams, "walls": walls, "floors": slabs,
            "openings": openings, "footings": footings, "piles": piles,
        },
        "foundation_system_summary": foundation_summary,
        "review": {
            "needs_review": needs_review,
            "counts": {
                "columns": len(columns), "framing": len(beams), "walls": len(walls),
                "floors": len(slabs), "openings": len(openings), "footings": len(footings),
                "piles": len(piles), "needs_review": len(needs_review),
            },
        },
        "loads": {}, "dynamic_loads": {}, "load_path": {},
        "analysis_results": {}, "design_results": {},
    }
    return model


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--in", dest="infile", required=True)
    ap.add_argument("--out", dest="outfile", required=True)
    ap.add_argument("--grade-story", default=None,
                     help="Name (or substring) of the story that represents grade level, e.g. 'Ground Floor'. "
                          "If omitted, the script guesses from story names containing 'ground'/'grade'/'GF'.")
    args = ap.parse_args()

    data = json.loads(Path(args.infile).read_text())
    model = classify(data, grade_story_name=args.grade_story)

    Path(args.outfile).parent.mkdir(parents=True, exist_ok=True)
    Path(args.outfile).write_text(json.dumps(model, indent=2))
    r = model["review"]["counts"]
    print(
        f"Classified {r['columns']} columns, {r['framing']} framing, {r['walls']} walls, "
        f"{r['floors']} floors, {r['footings']} footings, {r['piles']} piles "
        f"({r['needs_review']} flagged for review) -> {args.outfile}"
    )


if __name__ == "__main__":
    main()
