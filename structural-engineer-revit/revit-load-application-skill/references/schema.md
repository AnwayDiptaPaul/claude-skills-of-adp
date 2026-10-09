# `structural_model.json` — the `loads` section

Supplements `revit-structure-recognition`'s `references/schema.md`, which owns the rest of the document and stays the canonical reference for it. This skill only ever writes into the top-level `loads` key, which that skill already stubs as `{}`.

```json
{
  "loads": {
    "panels": [
      {
        "story_index": 0,
        "bay": { "U": ["1", "2"], "V": ["A", "B"] },
        "dim_u_m": 6.0, "dim_v_m": 4.0,
        "bounding_beams": { "U1": "BM-1", "U2": "BM-2", "V1": "BM-3", "V2": "BM-4" },
        "occupancy": "office_general",
        "loads": {
          "DL": { "classification": "two_way", "aspect_ratio": 1.5,
                   "u_direction_beams": { "shape": "triangular", "reaction_equivalent_kn_m": "...", "moment_equivalent_kn_m": "..." },
                   "v_direction_beams": { "shape": "trapezoidal", "reaction_equivalent_kn_m": "...", "moment_equivalent_kn_m": "..." } },
          "SDL": { "...": "same shape as DL" },
          "LL":  { "...": "same shape as DL" }
        }
      }
    ],
    "member_loads": {
      "BM-1": [ { "from_bay": { "U": ["1","2"], "V": ["A","B"] }, "direction": "U", "DL": {...}, "SDL": {...}, "LL": {...} } ]
    },
    "needs_review": [
      { "story": "Level 2", "reason": "panel not fully bounded by beams", "detail": "..." }
    ]
  }
}
```

`panels` is the per-bay record — one entry per fully beam-bounded rectangular panel found. `member_loads` is the same information reindexed by beam id, since that's what `structural-analysis` will actually want to iterate over (a beam can appear once per adjacent panel — an interior beam bounds two bays, and gets a load contribution from each, not summed together here since they may need different load-combination treatment downstream).

DL/SDL/LL are kept as separate sibling keys throughout, never pre-summed — see SKILL.md for why.

Column tributary loads (`distribution.column_tributary_area_m2()`, for flat-plate stories with no bounding beams) aren't wired into `apply_loads.py`'s output yet — see SKILL.md's known limitations. When they are, they'll land under a `column_loads` key at the same level as `member_loads`, keyed by column id, following the same DL/SDL/LL-separated shape.
