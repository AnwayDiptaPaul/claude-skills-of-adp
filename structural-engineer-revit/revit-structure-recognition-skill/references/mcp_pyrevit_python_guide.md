# Gathering data via mcp-servers-for-revit/mcp-server-for-revit-python

This is the server you're running — a pyRevit Routes bridge (`main.py` MCP server
→ HTTP `localhost:48884` → pyRevit Routes inside Revit → Revit API). Two ways to
get structural data out of it, in order of preference:

## Path A — the six purpose-built tools (recommended)

`pyrevit_extension/` in this skill adds `list_structural_columns`,
`list_structural_framing`, `list_walls`, `list_floors`,
`list_structural_foundations`, and `list_grids` to your server, following the
base repo's own documented extension pattern. See `pyrevit_extension/README.md`
for the install steps — it's two file copies and two small edits to files you
already have, not a fork.

Once installed (and the Revit-side route tested directly per that README),
gathering a full model is:

1. Call `get_revit_model_info` and `list_levels` (both already built into the base
   server) — confirms you're talking to the right document and gives you the
   story list.
2. Call `list_grids`.
3. Call each of `list_structural_columns`, `list_structural_framing`,
   `list_walls`, `list_floors`, `list_structural_foundations`.
4. Assemble the results into `raw_inventory.json` in the shape
   `scripts/extract_ifc.py` already produces (see `references/schema.md`) —
   each tool's `elements` already carries the right field names
   (`global_id`, `ifc_class`, `location`, `bbox_z_min_mm`/`bbox_z_max_mm`,
   `revit_parameters`, `material_names`, `level_name`), so this is closer to
   a reshape than a translation. The one thing to compute that the tools don't
   hand you directly: `axis_points_mm` for line-like elements is just
   `[location.start_mm, location.end_mm]`; for point-like elements
   (columns), `insertion_point_mm` is `location.point_mm`.
5. Run `python3 scripts/build_model.py --raw-inventory raw_inventory.json --out output/`
   (see below — this flag skips IFC extraction and goes straight to grid/story
   resolution + classification on data you've already assembled).

`revit_parameters` (the generic per-element parameter dump every tool returns)
is deliberately shaped to work with `classify_elements.py`'s existing
`_pset_value()` helper unchanged — that function already scans every property
name across all supplied property sets for a "function" substring, so a Revit
wall's native `Function` parameter gets found the same way an IFC property set's
`Function` value would. Map `revit_parameters` into the `psets` field (wrap it as
`{"Revit Parameters": {...}}`) when assembling each element's record, and the
wall-classification logic needs no changes at all.

## Path B — `execute_revit_code` (works today, no install)

The base repo already implements `execute_revit_code`, which runs arbitrary
IronPython against the live document — no extension install needed. Below is a
column-listing example; the same shape (collect by `BuiltInCategory`, walk
`.Parameters`, print JSON) covers framing (`OST_StructuralFraming`), walls
(`OST_Walls`), floors (`OST_Floors`), and foundations
(`OST_StructuralFoundation`) — swap the category and, for walls/floors, read
`.Width` / `GetCompoundStructure()` instead of `STRUCTURAL_MATERIAL_PARAM` the
way `structural_recognition_routes.py` does.

```python
import json
from pyrevit import revit, DB

doc = revit.doc
FEET_TO_MM = 304.8
out = []
cols = DB.FilteredElementCollector(doc).OfCategory(
    DB.BuiltInCategory.OST_StructuralColumns).WhereElementIsNotElementType().ToElements()
for c in cols:
    loc = c.Location
    pt = loc.Point if isinstance(loc, DB.LocationPoint) else None
    out.append({
        "global_id": c.UniqueId,
        "family": c.Symbol.Family.Name if c.Symbol else None,
        "type": c.Symbol.Name if c.Symbol else None,
        "point_mm": [pt.X * FEET_TO_MM, pt.Y * FEET_TO_MM, pt.Z * FEET_TO_MM] if pt else None,
    })
print(json.dumps(out))
```

This tool call's exact parameter name for the code string, and exactly how its
result is returned to you, isn't something to guess at in advance — read the
tool's actual schema when it's in your tool list at call time (it'll be
authoritative over anything written here) and adapt the snippet's invocation
accordingly; the Revit API logic inside the snippet is what matters and doesn't
change.

Path B is a reasonable way to confirm the data is reachable at all before
installing Path A, or to patch a gap if one of the six tools needs a fix you
haven't applied yet — but it returns unstructured text you have to parse every
time, versus Path A's stable typed tools. For repeated use, install Path A.

## Neither path has write access to a live document (yet)

The write-capable route/tool entries in the base repo's own status table
(`modify_element`, `create_line_based_element`, `delete_elements`, etc.) are
still 🔄 Pending as of this writing — so writing classification results back
onto Revit elements as parameters isn't available through this server today,
regardless of which path above you use. `execute_revit_code` *can* technically
write (it's arbitrary code with a transaction), but doing that from a
recognition skill is out of scope here — recognition should stay read-only by
design (see SKILL.md); a future `revit-load-application` or a dedicated
write-back step is the right place to reconsider this, once the base repo's own
write tools land or a custom write route is added deliberately, with its own
review.
