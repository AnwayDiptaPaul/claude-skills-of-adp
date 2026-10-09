# `structural_model.json` — the `load_path` section

Supplements `revit-structure-recognition`'s `references/schema.md`, which owns the rest of the document and stubs this key as `{}` ("shape not yet formalized" — this is that formalization). Also updates `role` fields in-place on existing `elements.columns`/`elements.walls` entries (see `role_updates` below) — the only section in this pipeline so far that edits an earlier skill's own element records rather than only adding a new top-level key.

```json
{
  "load_path": {
    "gravity": {
      "traces": [
        { "top_element": "COL-A1-4", "terminates_at_footing": true, "has_transfer": false,
          "path": [ { "element": "COL-A1-4", "type": "column", "story": "L04" },
                    { "element": "COL-A1-3", "type": "column", "story": "L04" },
                    "... one entry per storey walked down ...",
                    { "terminates_at": "footing", "type": "footing" } ] },
        { "top_element": "COL-C1-4", "terminates_at_footing": false, "has_transfer": true,
          "path": [ "...", { "transfer_via": "BEAM-T1", "story": "L02" },
                    { "note": "trace not continued past the transfer beam -- its own end supports aren't recorded by revit-structure-recognition" } ] }
      ],
      "unresolved": [
        { "element": "COL-E1-1", "story": "L01", "reason": "no matching column/wall below (by grid_ref) and not flagged as a transfer condition -- does not reach a footing. Possible modeling gap in the source Revit model, or a genuine unsupported column." }
      ]
    },
    "lateral": {
      "system_elements": ["WALL-B-1", "WALL-B-2", "..."],
      "lines_traced": [
        { "grid_key": ["along", "B"], "wall_ids": ["WALL-B-1", "WALL-B-2", "WALL-B-3", "WALL-B-4"], "spans_stories": [0, 4], "gap_stories": [] },
        { "grid_key": ["along", "D"], "wall_ids": ["WALL-D-1", "WALL-D-4"], "spans_stories": [0, 4], "gap_stories": [2] }
      ],
      "discontinuities": [
        { "grid_key": ["along", "D"], "gap_stories": [2], "wall_below": "WALL-D-1", "wall_above": "WALL-D-4",
          "classification": "plan_type_iv_out_of_plane_offset", "detail": true }
      ]
    },
    "irregularities": {
      "computed": {
        "mass_irregularity": { "value": true, "detail": [ { "story_index": 3, "weight_kn": 4500.0, "adjacent_weights_kn": [2000.0, 1500.0] } ] },
        "vertical_in_plane_discontinuity": { "value": false, "detail": [], "note": "offset decomposition not implemented -- see needs_review" },
        "out_of_plane_offset": { "value": true, "detail": [ "... same shape as lateral.discontinuities ..." ] },
        "non_parallel_systems": { "flagged": false, "angles_deg": [90.0, 90.0, 90.0, 90.0, 0.0, 0.0] }
      },
      "not_computable_here": {
        "torsion_irregularity": "needs storey displacement/drift from an actual analysis -- structural-analysis",
        "soft_storey": "needs relative storey stiffness -- structural-analysis",
        "weak_storey": "needs storey lateral strength/capacity -- structural-design",
        "re_entrant_corners": "needs floor plan outline geometry -- not captured by revit-structure-recognition today",
        "diaphragm_discontinuity": "needs floor plan area -- not captured by revit-structure-recognition today",
        "vertical_geometric_irregularity": "needs Fig 6.2.28(c)'s setback dimensions -- not transcribed"
      },
      "is_regular_computed": false,
      "is_regular_confidence": "partial -- based only on the 4 computed types out of 10; do not treat this as a full regularity clearance"
    },
    "overstrength_required_elements": [
      { "discontinuous_element": "WALL-D-4", "grid_key": ["along", "D"], "gap_stories": [2],
        "reason": "Sec 2.5.5.6: whatever column/beam/slab sits directly beneath 'WALL-D-4's own base needs Omega0-amplified design -- that specific supporting element isn't identified here (see reference doc)", "trigger": true }
    ],
    "role_updates": [
      { "element": "COL-A1-1", "previous": { "value": "gravity+lateral", "confidence": "low", "signals": [] },
        "updated": { "value": "gravity", "confidence": "medium", "signals": ["load-path: not part of any traced lateral element"] } }
    ],
    "needs_review": [ { "reason": "..." } ]
  }
}
```

**`gravity.traces`** — one entry per column (walls are folded into a column's trace only if a column's chain continues onto a wall; a wall's own independent gravity trace as a load-bearing element in its own right isn't separately produced today — see Known Limitations). `path` is ordered top to bottom, ending in exactly one of `{"terminates_at": "footing"}`, a `transfer_via` note, or `{"unresolved_at": ...}`. `has_transfer` is `true` the moment ANY segment of the chain transfers, even if the chain is otherwise fine below that point — a trace can have `has_transfer: true` and still not reach `terminates_at_footing: true`, since continuation past a transfer beam isn't attempted (see SKILL.md).

**`lateral.lines_traced`** — one entry per distinct grid position (`grid_key`) that carries at least one shear-classified wall (`wall_class.primary` or `.secondary == "shear"`) anywhere in the building. `gap_stories` is a list of storey indices between the line's lowest and highest storey where no wall covers that story-height. An empty `gap_stories` list *doesn't* mean the wall reaches the roof and foundation — only that it's continuous across whatever range it does span; check `spans_stories` against the building's full storey range separately if "reaches the roof" matters for a specific question.

**`irregularities.computed`** covers exactly 4 of BNBC's 10 irregularity types (Sec 2.5.5.3) — the ones genuinely computable from `revit-structure-recognition`'s geometry plus `dynamic-load`'s story weights, with no further data needed. `is_regular_computed` is `false` the moment any of those 4 trip — it is never `true` in a way that clears the other 6; `is_regular_confidence` says as much explicitly so a caller doesn't mistake a clean 4-type result for a full regularity determination. **This is the field `dynamic-load`'s `site_seismic_wind_input.json` currently takes as an engineer's guess (`is_regular`)** — once this skill has run, a project should feed `is_regular_computed` back into that input (AND-ed with the engineer's own judgment on the 6 uncomputed types, not used alone) rather than guessing cold, and re-run `dynamic-load` if the value changes what `dynamic_analysis_required()` returns.

**`overstrength_required_elements`** names the *discontinuous* element (the one whose base isn't picked up by a continuing wall), not a specific supporting element — see the `reason` field's own explanation of why: `revit-structure-recognition` records a landing point (`transfer_flag.lands_on`) for column transfers but has no equivalent for a wall whose base simply doesn't continue. Don't read `discontinuous_element` as "the element needing redesign" — it's "the element whose *support* needs redesign, not yet identified."

**`role_updates`** only ever moves a `low`-confidence `role` to `medium` (up or down in *value*, e.g. `"gravity+lateral"` to `"gravity"`, but never claims `high` confidence and never touches a role skill 1 was already confident about) — this skill's own lateral trace has real gaps (moment frames/braced frames aren't traced with the same rigor as shear walls; see SKILL.md), so `medium` is the honest ceiling here, not `high`.
