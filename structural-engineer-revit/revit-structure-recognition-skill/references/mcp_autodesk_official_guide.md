# Gathering data via the Autodesk Revit Public MCP Server

Autodesk's own server (Tech Preview, ships as a Revit 2027 addon, connects over
stdio to any MCP client — see Autodesk's announcement for the exact
`mcpServers` config). Different shape from the pyRevit-based server: seven
purpose-built tools rather than a general execution escape hatch, and — as of
this writing — **read-only**. Autodesk has stated write tools are planned
through a separate future "write server," kept deliberately apart from this
one. That's a real constraint on this path, not a gap in this skill: nothing
here can write classification results back into a Revit 2027 model via this
server today.

## Workflow

1. **Get Running Revit Instances** — call this first, always. It returns the
   process ID and open document name for each running Revit session; every
   other tool needs that process ID. If more than one project is open, confirm
   with the user which one before continuing.

2. **Query Model**, once per structural category, scoped to the entire model
   (not just the current view — a plan view rarely shows every structural
   element at once). Filter by category for: Structural Columns, Structural
   Framing, Walls, Floors, Structural Foundations. Each call returns element
   IDs plus an analysis summary (counts by category/level) — the counts alone
   are worth checking against expectations before pulling full data (a column
   count of 3 on a 12-story tower means something's wrong with the query, not
   the building).

3. **Get Element Data**, passing the ID list from each Query Model call.
   Request the full parameter set, not just "basic info" — the wall
   classification logic needs whatever Revit's `Function` parameter (or
   equivalent) resolves to, which only shows up in the full set.

4. Assemble into `raw_inventory.json` the same way as the pyRevit path (see
   `references/mcp_pyrevit_python_guide.md`'s Path A step 4) — wrap the
   returned parameters as a `psets`-shaped dict so `classify_elements.py`'s
   existing fuzzy matching finds them unchanged, and derive `axis_points_mm` /
   `insertion_point_mm` from whatever bounding-box or location data Get
   Element Data returns.

5. Run `python3 scripts/build_model.py --raw-inventory raw_inventory.json --out output/`.

Exact parameter names for Query Model's filter arguments and Get Element Data's
detail-level options aren't reproduced here as a fixed schema — read them off
the tool definitions in your own tool list when connected, since a Tech Preview
is exactly the kind of thing that changes shape between when this was written
and when you're using it. The workflow above (instance → query by category →
fetch full data → assemble) is the part that should hold regardless.

## Grids and levels

Query Model's category filter should cover Grids and Levels the same way it
covers structural categories — there's no indication in Autodesk's own
documentation that these are treated specially. Confirm with a quick Query
Model call scoped to "Grids" before assuming the six-category workflow above
needs a different tool for datum elements.

## Selection, zoom, and export tools

**Select Elements** and **Zoom to Elements** are worth using during review, not
during extraction — after `structural_model.json` is built and
`review_report.html` has flagged something ambiguous, passing the flagged
element's ID to Select Elements puts it directly in front of the engineer in
Revit instead of asking them to hunt for it by grid/story description. **Export
View** is unrelated to this skill's data path but is a reasonable way to attach
a snapshot of a flagged view to the review report if that's ever useful.

## Revit 2027 only

If the project isn't open in Revit 2027, this path isn't available regardless
of whether the addon is installed — fall back to the pyRevit-based server (if
connected) or IFC export.
