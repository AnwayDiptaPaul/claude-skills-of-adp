# occupancy_map.json format

What `apply_loads.py --occupancy-map` expects — one entry per story (or per
distinct occupancy area within a story, if a single floor mixes uses).

```json
{
  "entries": [
    {
      "story_index": 0,
      "room_name": "Office 201",
      "occupancy_param": null,
      "occupancy_key_override": null,
      "sdl_kn_m2_override": 2.155
    }
  ]
}
```

- **`story_index`** — matches the `index` field on the story in `structural_model.json` (0-based, sorted by elevation — see `revit-structure-recognition`'s `references/schema.md`).
- **`room_name`** — whatever the Revit Room/Space element is actually named. Fed to `occupancy_mapping.classify_room_occupancy()`.
- **`occupancy_param`** — the office's own explicit Occupancy/Department parameter value, if the model has one filled in. Stronger signal than the name when present.
- **`occupancy_key_override`** — skip inference entirely and force a specific key from `codes/bnbc2020/loads.OCCUPANCY_LIVE_LOADS`. Use this once a human has confirmed what `classify_room_occupancy()` guessed, or for anything it couldn't match at all.
- **`sdl_kn_m2_override`** — the composed SDL value for this story (from `sdl_estimation.compose_sdl()`, or a manually confirmed number). Required — `apply_loads.py` doesn't call `compose_sdl()` automatically yet, since finish/ceiling/partition choices are genuinely per-project and shouldn't be defaulted silently; compute it once per distinct floor buildup and paste the total in here.

A story with no entry at all, or an entry with neither a usable `room_name`/`occupancy_param` nor an `occupancy_key_override`, lands in `structural_model.json`'s `loads.needs_review` rather than being silently skipped without saying so.
