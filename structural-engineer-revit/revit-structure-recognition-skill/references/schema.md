# structural_model.json — schema reference

This is the one document all six skills in the pipeline read from and write to. `revit-structure-recognition` creates it and populates `meta`, `project`, `grids`, `stories`, `elements`, `foundation_system_summary`, and `review`. Later skills add their own top-level sections without touching these. Treat the shape below as the contract between skills — if you need to change a field name that another skill already depends on, update this file in the same edit.

A formal JSON Schema for the sections this skill owns lives in `schema/structural_model.schema.json`; this document is the readable version, with the reasoning for why fields exist.

## Top level

```json
{
  "meta": {
    "schema_version": "0.1.0",
    "generated_by": "revit-structure-recognition",
    "source_file": "Tower-A-Structural.ifc",
    "ifc_schema": "IFC4"
  },
  "project": { "name": "...", "length_unit": "mm" },
  "grids": [ ... ],
  "stories": [ ... ],
  "elements": {
    "columns": [ ... ],
    "framing": [ ... ],
    "walls": [ ... ],
    "floors": [ ... ],
    "openings": [ ... ],
    "footings": [ ... ],
    "piles": [ ... ]
  },
  "foundation_system_summary": { ... },
  "review": { "needs_review": [ ... ], "counts": { ... } },

  "loads": {},            
  "dynamic_loads": {},    
  "load_path": {},        
  "analysis_results": {}, 
  "design_results": {}    
}
```

The last five keys are written as empty objects by this skill and exist purely so downstream skills have a stable place to write into without needing to restructure the document. Their shapes mostly belong to those skills, not this one — don't pre-guess them here. **One deliberate exception: `design_results`**, sketched below now rather than left blank, because its shape has a cross-cutting constraint worth settling early — see that section for why.

## `grids`

```json
{
  "global_id": "1a2B...",
  "name": "Grid",
  "axes": {
    "U": [ { "tag": "A", "points_mm": [[0,0,0],[24000,0,0]] }, { "tag": "B", ... } ],
    "V": [ { "tag": "1", "points_mm": [[0,0,0],[0,18000,0]] }, ... ],
    "W": []
  }
}
```

U/V/W mirrors IFC's own `IfcGrid` structure (two families of parallel-ish lines, plus an optional third for radial/skewed layouts). Points are the axis line's endpoints in project global coordinates, already transformed through the grid's own placement — nothing downstream should need to re-apply a transform.

## `stories`

```json
{
  "id": "1uKqf_9O3A4pH2bCzX7L02",
  "global_id": "1uKqf_9O3A4pH2bCzX7L02",
  "name": "Level 2",
  "index": 1,
  "elevation_mm": 3500.0,
  "storey_height_mm": 3200.0
}
```

`index` is 0-based, sorted by elevation — use it for "is story A above story B" comparisons instead of comparing names, which don't sort reliably (`"Level 10"` < `"Level 2"` as strings). `storey_height_mm` is the gap to the *next* story up and is `null` for the topmost story.
`stories[].id` is the canonical, source-stable story identifier. The IFC extractor currently sets it equal to `global_id`; it is **not** a friendly level label such as `L02`. Every `story`, `base_story`, and `top_story` reference uses that same value in its `id` field. Consumers may use `name` only as a compatibility fallback for inventories produced before this field was added.

## `elements.columns`

```json
{
  "id": "COL-0001",
  "global_id": "...",
  "ifc_class": "IfcColumn",
  "name": "C1",
  "story": { "id": "L02", "name": "Level 2" },
  "base_story": { "id": "L01", "name": "Level 1" },
  "top_story": { "id": "L02", "name": "Level 2" },
  "grid_ref": { "at": ["A", "1"], "offset_mm": 0.0, "on_grid": true },
  "material": { "kind": "single", "names": ["Concrete C30/37"], "category": "Concrete",
                "profile_names": [], "layer_thickness_mm": null },
  "frame_type": { "value": "RCC", "confidence": "high",
                  "signals": ["material=Concrete", "object_type matches '\\d+x\\d+.*Column'"] },
  "role": { "value": "gravity+lateral", "confidence": "low",
            "signals": ["no lateral-system geometry available yet — provisional"] },
  "section_hint": "300x300",
  "insertion_point_mm": [6000.0, 3000.0, 0.0],
  "axis_points_mm": [[6000.0, 3000.0, 0.0], [6000.0, 3000.0, 3500.0]],
  "is_transfer_column": false,
  "transfer_flag": null
}
```

`role` here is deliberately weak — a real gravity/lateral role call needs the lateral system (shear walls, braced bays) to be fully classified first, which is a chicken-and-egg problem at extraction time. Leave it low-confidence and let `load-path` firm it up once walls and framing are both classified.

`is_transfer_column` / `transfer_flag`: set when this column's `insertion_point_mm` at its base story doesn't land within tolerance on a column or wall centerline at the story below. `transfer_flag` then holds `{"lands_on": "BEAM-0043", "offset_mm": 1800.0}` or similar. This is a load-path fact, recorded here because it's purely geometric and cheap to compute once, not because this skill judges its structural consequence.

## `elements.framing`

Beams, girders, joists, and braces share a shape (all are line-like elements between two points).

```json
{
  "id": "BM-0012",
  "global_id": "...",
  "ifc_class": "IfcBeam",
  "story": { "id": "L02", "name": "Level 2" },
  "material": { ... },
  "frame_type": { "value": "Steel", "confidence": "high", "signals": [...] },
  "framing_role": { "value": "primary", "confidence": "medium",
                     "signals": ["name contains 'girder'", "spans full bay A-B"] },
  "grid_ref": { "along": null, "spans_bay": ["A", "B"], "at_gridline": "2" },
  "axis_points_mm": [[0,6000,3500], [6000,6000,3500]],
  "supports_transfer_condition": false
}
```

`framing_role` values: `primary`, `secondary`, `transfer`, `cantilever`, `brace`, `collector`. A `transfer` beam is one that a column above lands on (cross-referenced from that column's `transfer_flag.lands_on`) — always double-check these two records agree with each other after classification.

## `elements.walls`

```json
{
  "id": "WALL-0004",
  "global_id": "...",
  "base_story": { "id": "1uKqf_9O3A4pH2bCzX7L00", "name": "Ground Floor" },
  "top_story": { "id": "1uKqf_9O3A4pH2bCzX7L02", "name": "Level 2" },
  "material": { ... },
  "thickness_mm": 250.0,
  "frame_type": { "value": "RCC", "confidence": "high", "signals": [...] },
  "wall_class": {
    "primary": "shear",
    "secondary": null,
    "confidence": "medium",
    "dual_role": false,
    "signals": ["continuous 3 stories", "250mm >= typical shear wall minimum",
                "IFC PredefinedType=SHEAR (weak signal only, see heuristics doc)"]
  },
  "grid_ref": { "along_gridline": "B", "between": null },
  "axis_points_mm": [[6000,0,0],[6000,6000,0]],
  "openings": ["OPEN-0002"]
}
```

`wall_class.secondary` is where the dual-role case lives (e.g. `primary: "retaining"`, `secondary: "shear"`) — see `references/classification_heuristics.md` for when to populate it. Never leave `primary` as a forced single value when the signals genuinely conflict; that's what `needs_review` is for.

## `elements.floors`

```json
{
  "id": "SLAB-0003",
  "story": { "id": "L02", "name": "Level 2" },
  "material": { ... },
  "thickness_mm": 150.0,
  "slab_type": { "value": "flat_plate", "confidence": "medium", "signals": [...] },
  "diaphragm_class": { "value": "rigid", "confidence": "low", "signals": ["concrete, thickness >= 100mm — provisional"] }
}
```

## `elements.openings`

```json
{
  "id": "OPEN-0002",
  "host_id": "WALL-0004",
  "host_type": "wall",
  "size_mm": { "width": 900.0, "height": 2100.0 },
  "flags": ["within_shear_wall"]
}
```

## `elements.footings` / `elements.piles`

```json
{
  "id": "FTG-0001",
  "footing_type": { "value": "isolated", "confidence": "high", "signals": ["IFC PredefinedType=PAD_FOOTING", "supports exactly 1 column"] },
  "supports": ["COL-0001"],
  "grid_ref": { "at": ["A", "1"], "offset_mm": 0.0 }
}
```
```json
{
  "id": "PILE-0014",
  "pile_type": { "value": "unknown", "confidence": "low", "signals": ["no ConstructionType attribute in source file"] },
  "pile_cap_id": "FTG-0009"
}
```

## `foundation_system_summary`

```json
{
  "predominant_system": "deep_pile",
  "counts": { "isolated": 2, "combined": 0, "strap": 0, "mat_raft": 0, "pile_cap": 18, "piles_total": 72 },
  "mixed_system_flag": true,
  "notes": "2 isolated footings at grid E — likely a lightly loaded canopy/stair core; verify against soil report before assuming same bearing stratum as the piled main structure."
}
```

## `review`

```json
{
  "needs_review": [
    { "element_id": "WALL-0011", "element_type": "wall", "reason": "conflicting wall_class signals",
      "detail": "IFC PredefinedType=SHEAR but single-story, 100mm thick, door opening centered — looks like a partition, not a shear wall" }
  ],
  "counts": { "columns": 42, "framing": 118, "walls": 26, "floors": 9, "openings": 34, "footings": 20, "piles": 72,
              "needs_review": 3 }
}
```

Every `needs_review` entry should be resolvable by a human in seconds — write `detail` as if you're handing a colleague a redline, not a stack trace.

## `design_results` (shape sketched now, not built yet — for `structural-design` to fill in)

Sketched ahead of that skill existing because of one constraint worth locking in early: **this skill does not assume write access to the model, now or later, and its output has to be a complete, trustworthy deliverable without it.** A design report — proposed sections, reinforcement, governing checks, code references — is the actual valuable output; whether those results ever get typed back into Revit as parameters is a separate, optional convenience layer, not a dependency. That's true today because no available MCP server can write yet, and it stays true even once one can, because a consequential change like a resized column is worth a human's review before it lands in the model of record regardless of what's technically possible. Given that, this shape is built to be genuinely useful standalone, and *also* trivial to wire into a write step later without redesigning anything — every entry below carries the same `element_id` and `global_id` used throughout this document, specifically so a future write step (or you, applying it by hand) can look an element up directly rather than re-deriving the mapping.

```json
{
  "status": "proposed",
  "code_basis": "BNBC 2020 / ACI 318-19 / ASCE 7-22",
  "members": [
    {
      "element_id": "COL-0001",
      "global_id": "1a2B...",
      "existing": { "section": "300x300 RCC Column", "material": "Concrete C30/37" },
      "adequate_as_is": false,
      "proposed": {
        "section": "400x400 RCC Column",
        "material": "Concrete C30/37",
        "reinforcement": { "longitudinal": "8-T20", "ties": "T10 @ 150mm c/c", "reinforcement_ratio_pct": 1.8 }
      },
      "governing_check": {
        "load_combination": "1.2DL + 1.6LL",
        "demand": { "Pu_kN": 2450, "Mu_x_kNm": 85, "Mu_y_kNm": 42 },
        "capacity": { "phiPn_kN": 2680 },
        "utilization_ratio": 0.91,
        "code_reference": "ACI 318-19 §22.4 / BNBC 2020 Part 6 Ch 8"
      }
    }
  ],
  "summary": { "total_members_designed": 42, "members_requiring_resize": 6, "members_adequate_as_designed": 36 },
  "write_back": {
    "applied": false,
    "note": "No write-capable MCP tool was available when this was generated — apply manually in Revit, or re-run the apply step once one exists. Every member above carries global_id for exactly that purpose."
  }
}
```

Expect `members_adequate_as_designed` to usually be the larger number in practice — most of a design pass confirms what's already there rather than resizing it, which is itself worth surfacing prominently rather than burying in a per-member list, since "nothing needs to change" is a real and common result, not a null one.

