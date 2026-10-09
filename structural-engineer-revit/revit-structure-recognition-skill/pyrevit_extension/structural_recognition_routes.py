# -*- coding: UTF-8 -*-
"""
structural_recognition.py — Revit-side routes for revit-structure-recognition.

WHERE THIS FILE GOES: copy it to
    <your clone of mcp-server-for-revit-python>/revit-mcp-python.extension/revit_mcp/structural_recognition.py
following the exact "Part 1: Create the Route Module in Revit" pattern documented
in that repo's README. See pyrevit_extension/README.md in this skill for the two
remaining registration steps (Parts 2 and 3) — this file alone does nothing until
those are wired up.

WHAT THIS DOES: exposes one GET route per structural category (columns, framing,
walls, floors, foundations, grids — levels are already covered by the repo's
built-in list_levels tool, so it isn't duplicated here). Each route dumps every
element in that category with:
  - category / family / type name
  - EVERY parameter as a flat {name: value_string} dict (Revit's own parameter
    names, exactly as shown in the UI) — this is deliberate: rather than betting
    on a handful of specific BuiltInParameter enum names being exactly right
    (Revit API parameter access has real version-to-version variation, and this
    has not been run against a live Revit session — see the caveat in
    references/mcp_pyrevit_python_guide.md), a full generic dump lets
    classify_elements.py's existing fuzzy matching (_pset_value, which already
    scans every property name for a "function" substring) find what it needs
    even if a targeted lookup below misses. Treat the generic dump as the
    reliable fallback and the targeted fields as a confidence boost when they
    resolve.
  - location: a point (columns) or a start/end curve (framing, walls, grids),
    ALWAYS CONVERTED FROM REVIT'S INTERNAL FEET TO MILLIMETRES — Revit's
    internal length unit is decimal feet regardless of the project's display
    units; every coordinate below is multiplied by 304.8 before it leaves this
    file, so nothing downstream needs to know or care about Revit's unit
    convention.
  - a bounding-box-derived Z range in mm, used for vertical extent instead of
    parsing the base/top-constraint parameters directly — Wall in particular
    has enough different ways to define its top (a level, an offset, an
    "unconnected height") that reading the as-built bounding box is more
    robust than chasing every constraint parameter combination.

NOT YET TESTED AGAINST A LIVE REVIT SESSION. This was written from the public
Revit API surface (FilteredElementCollector / BuiltInCategory / Parameter
iteration / LocationPoint / LocationCurve / BoundingBoxXYZ are all long-stable,
well-documented parts of the API), not verified by running it — there is no way
to execute Revit API code from the environment this was written in. Test the
/structural_columns/ route first, the same way the repo's own README tests
/status/: open a browser to
    http://localhost:48884/revit_mcp/structural_columns/
with a project open in Revit, and check the response before wiring the rest in.
If a route 500s, the traceback in the response will point at which parameter
lookup failed — it's the most likely failure mode, by design (see above).
"""
from pyrevit import routes, revit, DB
import logging

logger = logging.getLogger(__name__)

FEET_TO_MM = 304.8


def _mm(feet_value):
    if feet_value is None:
        return None
    return round(feet_value * FEET_TO_MM, 2)


def _xyz_to_list(xyz):
    if xyz is None:
        return None
    return [_mm(xyz.X), _mm(xyz.Y), _mm(xyz.Z)]


def _element_id_str(elem_id):
    # Revit API renamed ElementId.IntegerValue -> .Value around the 2024 API;
    # try both rather than assume which one this Revit version exposes.
    val = getattr(elem_id, "Value", None)
    if val is None:
        val = getattr(elem_id, "IntegerValue", None)
    return str(val) if val is not None else None


def _dump_parameters(elem):
    """Every parameter on the element, by its Revit UI display name. This is
    intentionally generic (see module docstring) rather than a curated list."""
    out = {}
    try:
        for p in elem.Parameters:
            try:
                name = p.Definition.Name
                if p.StorageType == DB.StorageType.String:
                    val = p.AsString()
                elif p.StorageType == DB.StorageType.ElementId:
                    ref = revit.doc.GetElement(p.AsElementId())
                    val = ref.Name if ref and hasattr(ref, "Name") else p.AsValueString()
                else:
                    val = p.AsValueString()
                    if val is None:
                        val = p.AsDouble() if p.StorageType == DB.StorageType.Double else p.AsInteger()
                if name and val is not None:
                    out[name] = val
            except Exception:
                continue  # a single bad parameter shouldn't sink the whole element
    except Exception as e:
        logger.warning("Parameter dump failed: {}".format(str(e)))
    return out


def _location(elem):
    loc = getattr(elem, "Location", None)
    if loc is None:
        return {"kind": "none"}
    if isinstance(loc, DB.LocationPoint):
        return {"kind": "point", "point_mm": _xyz_to_list(loc.Point)}
    if isinstance(loc, DB.LocationCurve):
        curve = loc.Curve
        return {
            "kind": "curve",
            "start_mm": _xyz_to_list(curve.GetEndPoint(0)),
            "end_mm": _xyz_to_list(curve.GetEndPoint(1)),
        }
    return {"kind": "unknown"}


def _bbox_z_range_mm(elem):
    try:
        bbox = elem.get_BoundingBox(None)
        if bbox is None:
            return None, None
        return _mm(bbox.Min.Z), _mm(bbox.Max.Z)
    except Exception:
        return None, None


def _level_name(doc, elem):
    """Try the direct LevelId property first (populated for most structural
    categories); fall back to the handful of BuiltInParameters different
    categories use for their base/reference level if it isn't."""
    level_id = getattr(elem, "LevelId", None)
    if level_id and level_id != DB.ElementId.InvalidElementId:
        lvl = doc.GetElement(level_id)
        if lvl:
            return lvl.Name
    for bip_name in ("FAMILY_BASE_LEVEL_PARAM", "SCHEDULE_LEVEL_PARAM",
                      "WALL_BASE_CONSTRAINT", "LEVEL_PARAM", "INSTANCE_REFERENCE_LEVEL_PARAM"):
        bip = getattr(DB.BuiltInParameter, bip_name, None)
        if bip is None:
            continue
        try:
            p = elem.get_Parameter(bip)
            if p and p.StorageType == DB.StorageType.ElementId:
                lvl = doc.GetElement(p.AsElementId())
                if lvl:
                    return lvl.Name
        except Exception:
            continue
    return None


def _material_names(doc, elem):
    """Structural material for a FamilyInstance (column/framing) if the
    Structural Material parameter is set; empty for classes (Wall, Floor)
    that carry material via a compound structure instead — those are read
    separately in the wall/floor routes below, where .Width is also
    available directly rather than needing to sum layers by hand."""
    names = []
    p = elem.get_Parameter(DB.BuiltInParameter.STRUCTURAL_MATERIAL_PARAM) if hasattr(
        DB.BuiltInParameter, "STRUCTURAL_MATERIAL_PARAM") else None
    if p and p.StorageType == DB.StorageType.ElementId:
        mat = doc.GetElement(p.AsElementId())
        if mat and hasattr(mat, "Name"):
            names.append(mat.Name)
    return names


def _base_record(doc, elem, ifc_class):
    symbol = getattr(elem, "Symbol", None)
    family_name = symbol.Family.Name if symbol else None
    type_name = symbol.Name if symbol else (elem.Name if hasattr(elem, "Name") else None)
    z0, z1 = _bbox_z_range_mm(elem)
    return {
        "global_id": elem.UniqueId,
        "element_id": _element_id_str(elem.Id),
        "ifc_class": ifc_class,
        "name": getattr(elem, "Name", None),
        "family_name": family_name,
        "type_name": type_name,
        "object_type": "{} {}".format(family_name or "", type_name or "").strip() or None,
        "level_name": _level_name(doc, elem),
        "location": _location(elem),
        "bbox_z_min_mm": z0,
        "bbox_z_max_mm": z1,
        "revit_parameters": _dump_parameters(elem),
    }


def register_structural_recognition_routes(api):
    """Registers all revit-structure-recognition routes with the API object
    passed in from startup.py's register_routes()."""

    @api.route("/structural_columns/", methods=["GET"])
    def get_structural_columns(doc):
        try:
            elems = DB.FilteredElementCollector(doc).OfCategory(
                DB.BuiltInCategory.OST_StructuralColumns).WhereElementIsNotElementType().ToElements()
            out = []
            for e in elems:
                rec = _base_record(doc, e, "IfcColumn")
                rec["material_names"] = _material_names(doc, e)
                out.append(rec)
            return routes.make_response(data={"status": "success", "count": len(out), "elements": out})
        except Exception as ex:
            logger.error("get_structural_columns failed: {}".format(str(ex)))
            return routes.make_response(data={"error": str(ex)}, status=500)

    @api.route("/structural_framing/", methods=["GET"])
    def get_structural_framing(doc):
        try:
            elems = DB.FilteredElementCollector(doc).OfCategory(
                DB.BuiltInCategory.OST_StructuralFraming).WhereElementIsNotElementType().ToElements()
            out = []
            for e in elems:
                rec = _base_record(doc, e, "IfcBeam")
                rec["material_names"] = _material_names(doc, e)
                out.append(rec)
            return routes.make_response(data={"status": "success", "count": len(out), "elements": out})
        except Exception as ex:
            logger.error("get_structural_framing failed: {}".format(str(ex)))
            return routes.make_response(data={"error": str(ex)}, status=500)

    @api.route("/walls/", methods=["GET"])
    def get_walls(doc):
        try:
            elems = DB.FilteredElementCollector(doc).OfCategory(
                DB.BuiltInCategory.OST_Walls).WhereElementIsNotElementType().ToElements()
            out = []
            for e in elems:
                rec = _base_record(doc, e, "IfcWall")
                try:
                    rec["wall_type_name"] = e.WallType.Name if e.WallType else None
                except Exception:
                    rec["wall_type_name"] = None
                try:
                    rec["width_mm"] = _mm(e.Width)
                except Exception:
                    rec["width_mm"] = None
                try:
                    cs = e.WallType.GetCompoundStructure() if e.WallType else None
                    layer_materials = []
                    if cs:
                        for layer in cs.GetLayers():
                            mat = doc.GetElement(layer.MaterialId)
                            if mat and hasattr(mat, "Name"):
                                layer_materials.append(mat.Name)
                    rec["material_names"] = layer_materials
                except Exception:
                    rec["material_names"] = []
                out.append(rec)
            return routes.make_response(data={"status": "success", "count": len(out), "elements": out})
        except Exception as ex:
            logger.error("get_walls failed: {}".format(str(ex)))
            return routes.make_response(data={"error": str(ex)}, status=500)

    @api.route("/floors/", methods=["GET"])
    def get_floors(doc):
        try:
            elems = DB.FilteredElementCollector(doc).OfCategory(
                DB.BuiltInCategory.OST_Floors).WhereElementIsNotElementType().ToElements()
            out = []
            for e in elems:
                rec = _base_record(doc, e, "IfcSlab")
                try:
                    cs = e.FloorType.GetCompoundStructure() if hasattr(e, "FloorType") and e.FloorType else None
                    layer_materials, total_thickness = [], 0.0
                    if cs:
                        for layer in cs.GetLayers():
                            mat = doc.GetElement(layer.MaterialId)
                            if mat and hasattr(mat, "Name"):
                                layer_materials.append(mat.Name)
                            total_thickness += layer.Width
                    rec["material_names"] = layer_materials
                    rec["thickness_mm"] = _mm(total_thickness) if total_thickness else None
                except Exception:
                    rec["material_names"] = []
                    rec["thickness_mm"] = None
                out.append(rec)
            return routes.make_response(data={"status": "success", "count": len(out), "elements": out})
        except Exception as ex:
            logger.error("get_floors failed: {}".format(str(ex)))
            return routes.make_response(data={"error": str(ex)}, status=500)

    @api.route("/structural_foundations/", methods=["GET"])
    def get_structural_foundations(doc):
        try:
            elems = DB.FilteredElementCollector(doc).OfCategory(
                DB.BuiltInCategory.OST_StructuralFoundation).WhereElementIsNotElementType().ToElements()
            out = []
            for e in elems:
                symbol = getattr(e, "Symbol", None)
                fam_lower = (symbol.Family.Name.lower() if symbol and symbol.Family else "") + \
                            " " + (getattr(e, "Name", "") or "").lower()
                # Revit has no separate "pile" category from structural foundations in
                # most versions in the wild — piles and footings/pile-caps share
                # OST_StructuralFoundation and are told apart here only by family/type
                # naming. This is a coarse heuristic, not a Revit API guarantee — flag
                # it as such if your office's pile families don't include "pile" in the
                # name, and adjust the keyword list below to match your library.
                ifc_class = "IfcPile" if "pile" in fam_lower and "cap" not in fam_lower else "IfcFooting"
                rec = _base_record(doc, e, ifc_class)
                rec["material_names"] = _material_names(doc, e)
                out.append(rec)
            return routes.make_response(data={"status": "success", "count": len(out), "elements": out})
        except Exception as ex:
            logger.error("get_structural_foundations failed: {}".format(str(ex)))
            return routes.make_response(data={"error": str(ex)}, status=500)

    @api.route("/grids/", methods=["GET"])
    def get_grids(doc):
        try:
            elems = DB.FilteredElementCollector(doc).OfClass(DB.Grid).ToElements()
            out = []
            for e in elems:
                try:
                    curve = e.Curve
                    out.append({
                        "global_id": e.UniqueId,
                        "element_id": _element_id_str(e.Id),
                        "name": e.Name,
                        "start_mm": _xyz_to_list(curve.GetEndPoint(0)),
                        "end_mm": _xyz_to_list(curve.GetEndPoint(1)),
                    })
                except Exception:
                    continue
            return routes.make_response(data={"status": "success", "count": len(out), "grids": out})
        except Exception as ex:
            logger.error("get_grids failed: {}".format(str(ex)))
            return routes.make_response(data={"error": str(ex)}, status=500)

    logger.info("revit-structure-recognition routes registered successfully")
