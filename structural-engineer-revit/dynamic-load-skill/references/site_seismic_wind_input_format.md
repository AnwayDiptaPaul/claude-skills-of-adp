# site_seismic_wind_input.json format

What `apply_dynamic_loads.py --site-input` expects. Unlike `occupancy_map.json` (per-room, since occupancy genuinely varies floor to floor), almost everything here is project-level — a building has one location, one soil profile, one chosen lateral system per direction, not one per story. None of it comes from the Revit model or from `structural_model.json`; it's the classification and site judgment an engineer supplies, the same way `revit-load-application` requires an `sdl_kn_m2_override` because finish buildup is a per-project choice, not something inferred from geometry.

```json
{
  "location": "Chandpur",
  "site_class": "SD",
  "site_class_source": "spt",
  "site_class_inputs": { "spt_n": 12 },
  "occupancy_category": "II",
  "story_seismic_weights": [
    { "story_index": 0, "dead_load_kn": 3500.0, "sdl_kn": 1200.0,
      "live_load_kn": 1000.0, "live_load_intensity_kn_m2": 2.4 }
  ],
  "structural_system": {
    "x_direction": "special_rc_moment_frame",
    "y_direction": "special_rc_moment_frame"
  },
  "damping_pct": 5.0,
  "is_regular": true,
  "has_independent_orthogonal_systems": true,
  "analysis_method": "equivalent_static",
  "wind": {
    "exposure_category": "B",
    "basic_wind_speed_v_ms_override": null,
    "importance_factor_I_override": null,
    "directionality_factor_Kd_override": null,
    "kz_by_story_override": null,
    "enclosure_classification": "enclosed",
    "opening_areas_m2": { "windward_wall": null, "rest_of_envelope": null },
    "plan_dimensions_m": { "L_along_wind": null, "B_across_wind": null }
  }
}
```

- **`location`** — a town name matching a key in `codes/bnbc2020/seismic.SEISMIC_ZONE_COEFFICIENTS` (Table 6.2.15). If the project site isn't one of the listed towns, don't pick the nearest-sounding key — read `Z` off the actual Fig 6.2.24 zone map for the real site and set `zone_coefficient_Z_override` instead (below).
- **`zone_coefficient_Z_override`** — skip the `location` lookup entirely and supply `Z` directly. Use this once a human has confirmed the value against the zone map, or for a site the town table doesn't cover.
- **`site_class`** — one of `SA`–`SE`/`S1`/`S2` (Table 6.2.13). Either supplied directly (a human's own classification from a full boring log) or produced by `seismic.classify_site_class()` from `site_class_inputs`.
- **`site_class_source`** / **`site_class_inputs`** — which of `vs_m_s`/`spt_n`/`su_kpa` `classify_site_class()` was given, and the raw value(s), so `structural_model.json`'s `dynamic_loads.seismic.shared_inputs.site_class_source` can record real evidence rather than an unlabeled string. Set `site_class_source` to `"engineer"` and leave `site_class_inputs` empty when `site_class` was a direct human call instead of a `classify_site_class()` result.
- **`occupancy_category`** — `I`/`II`/`III`/`IV`, per Part 6 Chapter 1 Table 6.1.1 (a different chapter — not something this skill suite has read yet; see `codes/bnbc2020/seismic.py`'s module docstring). Ordinary buildings are typically `II`; get this from the engineer, don't default it.
- **`story_seismic_weights`** — per-story `DL`/`SDL`/`LL` totals (kN, whole-story sums, not per-m2), plus the live load intensity (kN/m2) `seismic.seismic_live_load_fraction()` needs to pick the 25%/50% threshold. Required per story that seismic is being computed for. This is a deliberate design choice, not a missing feature: `structural_model.json`'s `loads.panels` (written by `revit-load-application`) stores per-*beam* reaction-equivalents, not per-story totals, and re-deriving a story total would mean either re-summing that per-beam breakdown (real double-counting risk — an interior beam receives a contribution from each adjacent panel) or reaching into `revit-load-application`'s own occupancy tables from a different, independently-packaged skill (fragile — skills are distributed as separate `.skill` files, not a shared codebase). Summing `revit-load-application`'s own per-panel dead/SDL/live totals once per story (its `compute_panel_loads()` inputs, not its per-beam outputs) is a short, one-time step outside this skill's own scope.
- **`structural_system`** — a key into `codes/bnbc2020/seismic.STRUCTURAL_SYSTEMS`, one per orthogonal direction (a building can legitimately use different systems each way — e.g. moment frame one direction, shear wall the other — Sec 2.5.5.5 explicitly allows this). Both directions are required even when they're the same system, so nothing silently reuses one direction's `R`/`Cd`/`Omega0` for the other.
- **`damping_pct`** — viscous damping ratio (percent of critical). `5.0` (the code's own reference value, giving `eta=1.0`) unless a project genuinely has a different verified damping ratio.
- **`is_regular`** — whether the building is regular in plan and elevation per Sec 2.5.5.3's irregularity types. Feeds both `seismic.dynamic_analysis_required()` (irregular buildings trigger mandatory dynamic analysis at a much lower height) and `seismic.static_analysis_permitted()`. `revit-structure-recognition` doesn't classify irregularity today, so this is an engineer judgment call, not an inferred value — get it wrong and a building that actually needs RSA/time-history could be waved through on the ESFP path alone.
- **`has_independent_orthogonal_systems`** — whether the X and Y lateral systems are genuinely independent (Sec 2.5.9.1). Together with `is_regular`, decides whether `structural-analysis`'s eventual RSA/LTHA/NTHA model can be two independent 2D models or needs one full 3D model with torsional DOF at every level (`seismic.requires_3d_model()`). Omit it and the pipeline defaults to the conservative answer (3D required) and flags the assumption — safe, but possibly more model than the building actually needs.
- **`analysis_method`** — `"equivalent_static"` (what `apply_dynamic_loads.py` actually computes today), `"response_spectrum"`, or `"time_history"`. The latter two are accepted as a stated intent and recorded in `dynamic_loads.seismic.method`, but the skill only fills in the equivalent-static numbers plus the design spectrum curve inputs — see SKILL.md's Known Limitations for why the modal/time-history paths themselves aren't computed here.
- **`wind.exposure_category`** — `A`/`B`/`C` per Sec 2.4.8.3's surface-roughness definitions. Feeds `Kz` (Table 2.4.4) once that table is populated — see `codes/bnbc2020/wind.py`'s KNOWN GAPS.
- **`wind.basic_wind_speed_v_ms_override`** — the site's verified basic wind speed, once sourced from the actual BNBC zone map/table rather than `wind.py`'s flagged unverified approximations. Leave `null` until then; `apply_dynamic_loads.py` will flag wind pressures as `needs_review` rather than compute a number it can't stand behind.
- **`wind.importance_factor_I_override`** / **`directionality_factor_Kd_override`** — Table 2.4.2 and Table 2.4.5 values, once read off a physical copy of the code (both are genuinely missing from `wind.py` — see its KNOWN GAPS). Same `null`-means-flag treatment as the wind speed.
- **`wind.kz_by_story_override`** — a list of `{"story_index":..., "Kz":...}`, Table 2.4.4's velocity pressure exposure coefficient at each story's height, once sourced. Per-story because `Kz` genuinely varies with height up the building, unlike the other wind inputs above.
- **`wind.plan_dimensions_m`** — `L_along_wind` and `B_across_wind`, needed for `wind.leeward_wall_cp()`'s `L/B` lookup. From the building footprint — this one Revit *does* have; it just isn't in `structural_model.json` today (`revit-structure-recognition` records grid geometry, not an overall footprint bounding box), so it's an input here rather than a re-derivation.
- **`wind.enclosure_classification`** / **`opening_areas_m2`** — either state the classification directly, or give the windward-wall and rest-of-envelope opening areas (plus their gross wall areas — see `wind.classify_enclosure()`'s full signature) and let the script classify it.

A project with no `site_seismic_wind_input.json` at all, or one missing `structural_system` for a direction, lands the whole `dynamic_loads` section in `needs_review` rather than `apply_dynamic_loads.py` silently assuming a default system or zone. A project with the seismic inputs but none of the wind overrides gets a fully populated `seismic` block and a `wind` block that's present but `needs_review`-flagged at every number that depends on an unverified table -- the two halves succeed or get flagged independently.
