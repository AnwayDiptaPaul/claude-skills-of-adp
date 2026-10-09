---
name: revit-structure-recognition
description: Recognizes and classifies structural elements in a Revit model — via live MCP (pyRevit-based mcp-server-for-revit-python or Autodesk's official Revit Public MCP Server), or IFC export as fallback — covering grid lines and stories, columns (RCC/steel/timber/composite), framing (beams/joists — primary/secondary/transfer), walls (shear vs. retaining vs. partition vs. cladding — IFC's own SHEAR predefined type does NOT reliably give this), floors/slabs by type, openings, and footings/foundation systems (isolated, combined, strap, mat, pile caps and piles), each resolved against the grid and story datum. Produces the canonical structural_model.json the other five pipeline skills read and build onto — run this first. Use whenever Revit is open with an MCP connection, a .rvt/.ifc file is shared, or the user asks to read/extract/audit a structural model, take off elements, classify a wall, or starts a BIM-based analysis/design workflow.
---

# Revit Structure Recognition

## What this actually is

This is the step a structural engineer does before touching a calculator: walk the model (or the drawings), and build a mental inventory of *what resists what*. Not "there are 42 columns" — "there are 42 columns, 6 of which are transfer columns landing on a beam instead of stacking to the footing, and 4 walls that look identical in plan but two are shear walls, one is a basement retaining wall, and one is doing both jobs at once."

The output of this skill is not a shape catalog. It's a **role** catalog. Every downstream skill (loads, seismic/wind, load path, analysis, design) depends on getting the role right, not just the geometry. A 250 mm concrete wall that gets misclassified as a partition instead of a shear wall doesn't fail loudly — it fails by quietly being left out of the lateral system, and nobody notices until a drift check or a base shear number looks wrong for reasons that trace back to this step.

Treat classification uncertainty as data, not a defect to hide. If two signals disagree, say so and flag it — don't silently pick one. An engineer reviewing flagged items in five minutes is the intended workflow, not a fully-automatic black box.

## The pipeline this feeds

```
revit-structure-recognition  ← you are here
        │  structural_model.json (grids, stories, elements, roles)
        ▼
revit-load-application        (occupancy → DL/SDL/LL onto the model)
dynamic-load                  (seismic + wind onto the model)
        │
        ▼
load-path                     (verify continuity, flag transfers/discontinuities)
        ▼
structural-analysis           (solve for demand: forces, moments, deflections)
        ▼
structural-design             (check/size members against demand, per code)
```

All six skills share one JSON document that gets progressively enriched — see `references/schema.md`. This skill only ever writes to `grids`, `stories`, and `elements`. It never invents loads or runs analysis.

**None of the six skills depend on write access to Revit, by design — not this one, and not `structural-design` at the far end either.** Read the model, compute the result, hand back a report (proposed sections, reinforcement, checks, code references — see `design_results` in `references/schema.md`); whether that ever gets typed back into Revit as parameters is a separate, optional step, not a prerequisite for any of this being useful. Two reasons that's the right default and not just today's limitation: no available MCP server can write reliably yet, and — independent of that — a consequential change like a resized column is worth a human's review before it lands in the model of record even once write access exists. Every element that flows through this pipeline carries its `global_id` (an IFC GlobalId or, on the MCP paths, a Revit `UniqueId`) specifically so that a future write-back step — automated once a server actually supports it, or manual, done by the engineer today — can look the right element up directly without redoing any of this skill's work.

## Workflow

**1. Check what's actually available in this session first**, since which of the three paths below applies depends entirely on that:

- **A pyRevit-based MCP connection** (`mcp-servers-for-revit/mcp-server-for-revit-python` or a fork) — the primary path. If `list_structural_columns` / `list_structural_framing` / `list_walls` / `list_floors` / `list_structural_foundations` / `list_grids` are in your tool list, the extension from `pyrevit_extension/` is already installed — go straight to step 2. If only the base tools are present (`get_revit_status`, `list_levels`, `execute_revit_code`, etc.) without those six, either walk the user through installing the extension (`pyrevit_extension/README.md` — two file copies, two small edits to files they already have) or use `execute_revit_code` directly per `references/mcp_pyrevit_python_guide.md`'s Path B.
- **Autodesk's official Revit Public MCP Server** — if `Query Model` / `Get Element Data` / `Get Running Revit Instances` are in your tool list instead (Revit 2027 only). Follow `references/mcp_autodesk_official_guide.md`. Read-only as of this writing — fine for recognition, but don't expect a write-back step to work through this server yet.
- **IFC export** — the fallback, and the only path available in an environment with no live MCP connection at all (this includes most cloud/sandboxed chat sessions — there's no route from a hosted assistant to a process running on someone's desktop). Walk the export settings in `references/ifc_export_guide.md` if this is the only option.

Don't guess which is available — check the tool list (or call `tool_search` for "revit" if tools are deferred) before picking a path.

**2. Gather the model.**
- **MCP paths:** call the tools per the relevant reference guide above, and assemble the results into `raw_inventory.json` matching the shape in `references/schema.md` (the six pyRevit-extension tools already return data shaped for a near-direct reshape, not a translation). Then:
  ```bash
  python3 scripts/build_model.py --raw-inventory raw_inventory.json --out /path/to/output_dir
  ```
- **IFC path:**
  ```bash
  python3 scripts/build_model.py --ifc /path/to/model.ifc --out /path/to/output_dir
  ```

Either way this writes, into `output_dir/`:
- `raw_inventory.json` — everything gathered, uninterpreted (copied through as-is on the MCP path, since assembling it *is* the extraction step there)
- `structural_model.json` — the classified, grid/story-resolved final output
- `review_report.html` — a human-readable summary, with every flagged item surfaced up top

`resolve_grid_story.py` and `classify_elements.py` are identical regardless of which path fed them — the classification logic (the actual engineering judgment) doesn't know or care whether an element came from a live Revit session or a parsed IFC file, only that it arrived in the shape `references/schema.md` describes.

**3. Open `review_report.html` first, not `structural_model.json`.** Walk the "Needs Review" section with the user before treating anything downstream as final. This is not optional politeness — it's the actual failure mode this skill exists to prevent. Common flags: a wall classified with conflicting signals (e.g., IFC or Revit says `SHEAR`/no clear function but it's a single-story 100 mm wall with a door in the middle — almost certainly *not* a real shear wall), a column with no matching column below or above it (possible transfer, possible modeling gap), a footing whose type couldn't be determined from geometry alone.

**4. Only once the user has confirmed or corrected the flagged items**, hand `structural_model.json` to the next skill in the pipeline (typically `revit-load-application`). On a live MCP connection with **write** access (not currently available through either MCP server covered here — see the reference guides), this is also the natural point to consider writing confirmed classifications back onto the Revit elements as parameters; that round-trip isn't built yet and shouldn't be improvised ad hoc when it matters (getting write transactions wrong corrupts a live model) — treat it as a deliberate future addition once a server actually exposes safe write tools.

## How to read a model the way an engineer does

**Geometry is only useful in service of a role.** Don't ask "what shape is this." Ask "what does this do — carry gravity down, resist lateral force, hold back soil, or just divide a room." The classification functions in `scripts/classify_elements.py` are built around that question, and `references/classification_heuristics.md` documents the full decision logic per element type — read it before trusting or modifying any classification, especially for walls and footings, where a single source (an IFC enum, a layer name) is never enough on its own.

**Multi-signal, always.** No classification in this skill relies on one field. Material, geometry (thickness, height-continuity across stories, aspect ratio), IFC predefined type, Revit-native parameters surfaced through property sets, and spatial context (below-grade vs. above-grade, adjacent to soil) are all weighed together, and where they disagree the element is flagged rather than force-classified. The three sharpest gotchas, worth knowing even before opening the heuristics file:

- **IFC's `SHEAR` wall predefined type is not a structural claim.** buildingSMART's own documentation for `IfcWallTypeEnum` says outright: *"The potentially misleading term SHEAR shall not impose a particular resistance against shear forces, but a particular shape."* Treat it as a weak, single-source hint, never as ground truth.
- **`RETAININGWALL` only exists in IFC4.3** (the infrastructure-oriented 2024 release). Revit's standard building export is plain IFC4, which has no dedicated retaining-wall type at all — so retaining walls have to be recognized from context (below grade, soil on one face, usually perimeter/basement, often a different reinforcing pattern than the lateral walls above), not from a PredefinedType lookup that likely isn't populated.
- **A wall can be both.** A basement perimeter wall can retain soil *and* be part of the lateral system for the levels above. Don't force a single label when the evidence supports a dual role — record both and let the design skill decide how to treat the boundary condition.

**Grid and story are the coordinate system for everything else.** Every element in the output carries its story (and, for vertical elements, base/top story) and its position relative to the grid — either "at" an intersection/line within tolerance, or an explicit offset if it isn't. `resolve_grid_story.py` computes this from geometry; it does not trust naming conventions (marks like "C-A1") as ground truth, though it does surface them as a cross-check signal when present, because office naming conventions are often more reliable than a geometric tolerance check on a model that wasn't perfectly drawn to grid.

**Flag load-path-relevant facts even though load-path analysis isn't this skill's job.** If a column's centerline doesn't land within tolerance on the column (or wall) below it, that's a transfer condition — the `load-path` skill will care a great deal, but the *fact* is purely geometric and belongs here. Same for large floor openings that interrupt a diaphragm, and for a shear wall that doesn't run continuously to the foundation. Recording these facts now saves the load-path skill from re-deriving them from scratch.

## Output quality bar

Before handing off `structural_model.json`, it should be true that:
- every element has a story (or base/top story pair) and a grid reference — `null` values here should be rare and each one should correspond to a flagged review item, not a silent gap
- every wall has a `wall_class` with a confidence and a signal list, not just a bare label
- every footing has both a `footing_type` (isolated/combined/strap/mat/pile_cap) and is rolled into the project-level `foundation_system_summary`
- transfer conditions (column-not-landing-on-column-or-wall) are flagged, not silently accepted
- nothing with conflicting signals was force-classified — it's in the `needs_review` list instead

## Known limitations

Worth knowing before relying on this in production, and worth extending rather than working around silently:

- **No slab footprint geometry yet.** `classify_slab` distinguishes flat-plate-vs-beam-supported and flags composite metal deck, but can't yet tell one-way from two-way from waffle — that needs bay aspect ratio, which needs the slab's actual footprint polygon, which this skill doesn't extract (only axis/centerline geometry for line-like elements). Extending `extract_ifc.py` to pull `IfcSlab` solid geometry via `ifcopenshell.geom` is the natural next step; until then, `beam_supported_unrefined` slabs need a manual glance at the framing plan.
- **One dominant grid system assumed.** Multi-grid buildings (a podium on its own grid under a tower) will have elements outside the primary grid's extents resolve poorly — `resolve_grid_story.py` warns to stderr when it sees more than one `IfcGrid`, but doesn't yet pick the right one per element.
- **Straight axis segments only.** `IfcPolyline`-based axes (the overwhelming majority of real structural members) parse cleanly; curved walls or arc'd grid lines fall back to insertion-point-only handling and lose the richer line-based grid/story resolution — they'll still get *a* position, just a less precise one, and won't be silently wrong (`has_axis_representation: false` marks them).
- **Opening area ratio is a coarse presence proxy**, not a true geometric ratio (any opening vs. none) — refining this needs opening + host-face geometry this skill doesn't pull yet. It's good enough to catch "heavily fenestrated, definitely not a shear wall" but not fine-grained capacity-impact analysis.
- **Validated against synthetic fixtures, not yet a real production export.** Testing so far covers the mechanisms that matter most — transfer detection, the wall dual-role and SHEAR-caveat logic, pile cap detection, steel/RCC frame typing across US/Euro/UK/Indian section-naming conventions — but a multi-hundred-element real project will surface patterns these fixtures don't. Treat the first real run's `review_report.html` with extra scrutiny, and feed anything it gets wrong back into `references/classification_heuristics.md`.
- **The MCP paths are untested against a live Revit session**, unlike the IFC path above. `pyrevit_extension/structural_recognition_routes.py` was written against the public Revit API (stable, long-documented calls) but there's no way to execute Revit API code from the environment it was built in — test it against a real model (see that file's own testing instructions) before trusting it on a real project the way the IFC path has already been proven out.
- **Pile vs. footing, on the MCP paths, is a family-name heuristic** ("does the family/type name contain 'pile'"), not a Revit API guarantee — Revit doesn't give piles their own category separate from structural foundations. Adjust the keyword check in `pyrevit_extension/structural_recognition_routes.py` if an office's pile family library doesn't include the word.
- **No write-back yet, on either MCP path.** Both are read-only as things stand (the pyRevit-based server's write tools are still pending upstream; Autodesk's official server is deliberately read-only pending a separate future write server) — recognition results can't currently be written back onto Revit elements as parameters through either. Worth revisiting once a server actually exposes safe write tools, not worth improvising around now.



## Reference files

- **`references/schema.md`** — full shape of `structural_model.json`, including the sections later skills will add (`loads`, `dynamic_loads`, `analysis_results`, `design_results`), so this skill's output stays forward-compatible with what's coming.
- **`references/classification_heuristics.md`** — the full per-element-type decision logic: signals used, how they're weighted, the confidence thresholds, and the reasoning behind each one. Read the relevant section before touching `classify_elements.py`.
- **`references/mcp_pyrevit_python_guide.md`** — how to gather data via `mcp-servers-for-revit/mcp-server-for-revit-python`: installing the six purpose-built tools in `pyrevit_extension/`, or the `execute_revit_code` fallback if you'd rather not touch the server yet.
- **`references/mcp_autodesk_official_guide.md`** — how to gather data via Autodesk's official Revit Public MCP Server (Revit 2027, read-only as of this writing).
- **`references/ifc_export_guide.md`** — exact Revit export settings for the fallback path, used when no live MCP connection is available at all.

## Scripts

- **`scripts/build_model.py`** — the entry point; orchestrates the stages below and writes `review_report.html`. Takes **either** `--ifc <file>` **or** `--raw-inventory <file>` — the latter for data already gathered via MCP tool calls (see the reference guides above for assembling it). Only the `--ifc` path needs `ifcopenshell` installed; the MCP path has no Python-side dependency beyond `numpy`.
- **`scripts/extract_ifc.py`** — reads an IFC file, produces `raw_inventory.json`. Only used by the `--ifc` path. Purely descriptive — no judgment calls.
- **`scripts/resolve_grid_story.py`** — resolves every element's story and grid position. Identical for both paths.
- **`scripts/classify_elements.py`** — applies the heuristics from `references/classification_heuristics.md`, producing role classifications with confidence and flags. Identical for both paths — this is the part that doesn't change no matter where the data came from.

## pyRevit extension

- **`pyrevit_extension/`** — drop-in files adding six structural-specific tools to `mcp-server-for-revit-python`. See `pyrevit_extension/README.md`. Written against the public Revit API but **not executed against a live Revit session** — there's no way to run Revit API code from the environment this was built in. Test `/structural_columns/` directly (instructions in that README) before trusting the full pipeline on a real project.

All scripts require `numpy`. `scripts/extract_ifc.py` additionally requires `ifcopenshell` (`pip install ifcopenshell --break-system-packages`) — only needed for the IFC fallback path.
