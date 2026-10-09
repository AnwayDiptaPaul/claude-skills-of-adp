#!/usr/bin/env python3
"""
extract_ifc.py — pull raw geometric + semantic data for structural categories
out of an IFC file. This is the "site walk" step: gather everything visible
before any judgment gets applied. Classification happens later, in
classify_elements.py — keep this script honest and non-interpretive. Every
field here is either read straight off the IFC file or a light, unambiguous
geometric transform (global coordinates, unit conversion) — nothing that
requires engineering judgment belongs in this file.

Usage:
    python3 extract_ifc.py --ifc model.ifc --out raw_inventory.json
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np

try:
    import ifcopenshell
    import ifcopenshell.util.element as ue
    import ifcopenshell.util.placement as up
    import ifcopenshell.util.unit as uu
except ImportError:
    sys.exit(
        "ifcopenshell is required. Install with:\n"
        "    pip install ifcopenshell --break-system-packages"
    )

# Structural categories this skill cares about. IfcWallStandardCase is a legacy
# IFC2x3 subtype of IfcWall with the same semantics we need; both are covered
# by `ifc.by_type("IfcWall")` returning subtypes in ifcopenshell, but listing
# it explicitly costs nothing and protects against schema-version surprises.
STRUCTURAL_CLASSES = [
    "IfcColumn",
    "IfcBeam",
    "IfcMember",       # braces, collectors, and other line members
    "IfcWall",
    "IfcWallStandardCase",
    "IfcSlab",
    "IfcFooting",
    "IfcPile",
    "IfcOpeningElement",
]


def apply_matrix(matrix, point):
    """Transform a local 2D or 3D point through a 4x4 placement matrix."""
    x, y = point[0], point[1]
    z = point[2] if len(point) > 2 else 0.0
    v = np.array([x, y, z, 1.0])
    r = matrix @ v
    return (float(r[0]), float(r[1]), float(r[2]))


def polyline_points(item):
    """Return local (x,y[,z]) tuples for a curve item, or None if it isn't a
    shape this function knows how to read (e.g. an arc/trim we don't need to
    handle for a structural axis, which is almost always a straight segment)."""
    if item is None:
        return None
    if item.is_a("IfcPolyline"):
        return [tuple(p.Coordinates) for p in item.Points]
    return None  # IfcTrimmedCurve/arc axes etc. — flag via has_axis_representation=False downstream


def get_axis_points_mm(element, scale):
    """Global-coordinate endpoints of the element's analytical/Axis
    representation, in mm — or None if the model only carries physical
    (solid) geometry. See references/ifc_export_guide.md for why the
    analytical model matters here."""
    rep = getattr(element, "Representation", None)
    if not rep:
        return None
    matrix = up.get_local_placement(element.ObjectPlacement)
    for r in rep.Representations:
        if r.RepresentationIdentifier != "Axis":
            continue
        for item in r.Items:
            pts = polyline_points(item)
            if pts:
                global_pts = [apply_matrix(matrix, p) for p in pts]
                return [[c * scale for c in p] for p in global_pts]
    return None


def get_insertion_point_mm(element, scale):
    matrix = up.get_local_placement(element.ObjectPlacement)
    origin = (float(matrix[0, 3]), float(matrix[1, 3]), float(matrix[2, 3]))
    return [c * scale for c in origin]


def _material_layers(mat):
    """IfcMaterialLayer list for a (possibly Usage-wrapped) layered material.
    NOTE: this is deliberately NOT ifcopenshell.util.element.get_layers() —
    that function returns CAD *presentation* layers (drafting layers), an
    unrelated IFC concept that happens to share the word "layer". Material
    composition (what a wall/slab is actually built from, and how thick each
    part is) lives on IfcMaterialLayerSet.MaterialLayers, reached here
    directly."""
    if mat is None:
        return []
    if mat.is_a("IfcMaterialLayerSetUsage"):
        mat = mat.ForLayerSet
    if mat.is_a("IfcMaterialLayerSet"):
        return list(mat.MaterialLayers or [])
    return []


def _material_profiles(mat):
    if mat is None:
        return []
    if mat.is_a("IfcMaterialProfileSetUsage"):
        mat = mat.ForProfileSet
    if mat.is_a("IfcMaterialProfileSet"):
        return list(mat.MaterialProfiles or [])
    return []


def get_material_info(element, scale):
    """Normalizes IfcMaterial / IfcMaterialLayerSet(Usage) / IfcMaterialProfileSet(Usage)
    into one shape. `kind` tells classify_elements.py which fields are meaningful."""
    mat = ue.get_material(element, should_skip_usage=False, should_inherit=True)
    if mat is None:
        return {"kind": "none", "names": [], "category": None,
                "profile_names": [], "layer_thickness_mm": None}

    if mat.is_a("IfcMaterial"):
        return {"kind": "single", "names": [mat.Name],
                "category": getattr(mat, "Category", None),
                "profile_names": [], "layer_thickness_mm": None}

    layers = _material_layers(mat)
    if layers:
        names = [l.Material.Name for l in layers if l.Material]
        thickness = sum((l.LayerThickness or 0.0) for l in layers)
        return {"kind": "layered", "names": names, "category": None,
                "profile_names": [], "layer_thickness_mm": thickness * scale}

    profiles = _material_profiles(mat)
    if profiles:
        names = [p.Material.Name for p in profiles if p.Material]
        pnames = [p.Profile.ProfileName for p in profiles
                  if p.Profile and getattr(p.Profile, "ProfileName", None)]
        return {"kind": "profile", "names": names, "category": None,
                "profile_names": pnames, "layer_thickness_mm": None}

    return {"kind": "other", "names": [getattr(mat, "Name", None) or mat.is_a()],
            "category": None, "profile_names": [], "layer_thickness_mm": None}


def get_storey(element):
    storey = ue.get_container(element, ifc_class="IfcBuildingStorey")
    if storey is None:
        return None
    return {"global_id": storey.GlobalId, "name": storey.Name}


def get_host_global_id(opening):
    """An IfcOpeningElement is related to its host via IfcRelVoidsElement
    (inverse: VoidsElements on the opening)."""
    rels = getattr(opening, "VoidsElements", None) or []
    for rel in rels:
        host = getattr(rel, "RelatingBuildingElement", None)
        if host is not None:
            return host.GlobalId
    return None


def extract_grids(ifc, scale):
    grids = []
    for g in ifc.by_type("IfcGrid"):
        matrix = up.get_local_placement(g.ObjectPlacement) if g.ObjectPlacement else np.eye(4)
        axes = {"U": [], "V": [], "W": []}
        for label, axis_list in (("U", g.UAxes), ("V", g.VAxes), ("W", g.WAxes)):
            for ax in axis_list or []:
                pts = polyline_points(ax.AxisCurve) if ax.AxisCurve else None
                global_pts = [apply_matrix(matrix, p) for p in pts] if pts else None
                axes[label].append({
                    "tag": ax.AxisTag,
                    "points_mm": [[c * scale for c in p] for p in global_pts] if global_pts else None,
                })
        grids.append({"global_id": g.GlobalId, "name": g.Name, "axes": axes})
    return grids


def extract_storeys(ifc, scale):
    storeys = []
    for s in ifc.by_type("IfcBuildingStorey"):
        elev = s.Elevation
        storeys.append({
            # ``id`` is the canonical source-stable cross-skill identifier.
            # IFC inventories deliberately use the same value as global_id.
            "id": s.GlobalId,
            "global_id": s.GlobalId,
            "name": s.Name,
            "elevation_mm": (elev * scale) if elev is not None else None,
        })
    storeys.sort(key=lambda x: (x["elevation_mm"] is None, x["elevation_mm"]))
    for i, s in enumerate(storeys):
        s["index"] = i
        if i + 1 < len(storeys) and s["elevation_mm"] is not None and storeys[i + 1]["elevation_mm"] is not None:
            s["storey_height_mm"] = storeys[i + 1]["elevation_mm"] - s["elevation_mm"]
        else:
            s["storey_height_mm"] = None
    return storeys


def extract_elements(ifc, scale):
    out = []
    seen_ids = set()
    for cls in STRUCTURAL_CLASSES:
        for el in ifc.by_type(cls):
            if el.GlobalId in seen_ids:  # avoid double-count when a subtype overlaps a supertype query
                continue
            seen_ids.add(el.GlobalId)

            record = {
                "global_id": el.GlobalId,
                "ifc_class": el.is_a(),
                "name": el.Name,
                "object_type": el.ObjectType,
                "tag": getattr(el, "Tag", None),
                "predefined_type": getattr(el, "PredefinedType", None),
            }

            if el.is_a("IfcOpeningElement"):
                record["host_global_id"] = get_host_global_id(el)
            else:
                record["storey"] = get_storey(el)
                record["material"] = get_material_info(el, scale)
                try:
                    record["psets"] = ue.get_psets(el, psets_only=True)
                except Exception:
                    record["psets"] = {}
                try:
                    record["qtos"] = ue.get_psets(el, qtos_only=True)
                except Exception:
                    record["qtos"] = {}

            record["insertion_point_mm"] = get_insertion_point_mm(el, scale)
            axis = get_axis_points_mm(el, scale)
            record["axis_points_mm"] = axis
            record["has_axis_representation"] = axis is not None

            out.append(record)
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ifc", required=True, help="Path to the IFC file")
    ap.add_argument("--out", required=True, help="Path to write raw_inventory.json")
    args = ap.parse_args()

    ifc = ifcopenshell.open(args.ifc)
    # calculate_unit_scale gives file-units -> metres; we standardize the whole
    # pipeline on millimetres, hence the extra *1000.
    scale = uu.calculate_unit_scale(ifc, "LENGTHUNIT") * 1000.0

    projects = ifc.by_type("IfcProject")
    data = {
        "source_file": Path(args.ifc).name,
        "ifc_schema": ifc.schema,
        "project_name": projects[0].Name if projects else None,
        "grids": extract_grids(ifc, scale),
        "storeys": extract_storeys(ifc, scale),
        "elements": extract_elements(ifc, scale),
    }

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(data, indent=2))
    print(
        f"Extracted {len(data['elements'])} structural elements, "
        f"{len(data['storeys'])} storeys, {len(data['grids'])} grid system(s) "
        f"from {data['ifc_schema']} file -> {args.out}"
    )


if __name__ == "__main__":
    main()
