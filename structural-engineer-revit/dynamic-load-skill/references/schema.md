# `structural_model.json` — the `dynamic_loads` section

Supplements `revit-structure-recognition`'s `references/schema.md`, which owns the rest of the document and stays the canonical reference for it. This skill only ever writes into the top-level `dynamic_loads` key, which that skill already stubs as `{}` (unlike `loads`, structure-recognition's own schema doc didn't pre-sketch a shape for this one — the shape below is this skill's own).

```json
{
  "dynamic_loads": {
    "seismic": {
      "method": "equivalent_static",
      "shared_inputs": {
        "location": "Chandpur", "zone": 2, "zone_coefficient_Z": 0.20,
        "site_class": "SD", "site_class_source": "spt",
        "occupancy_category": "II", "importance_factor_I": 1.0,
        "seismic_design_category": "D", "damping_pct": 5.0,
        "seismic_weight_kn": 43000.0, "is_regular": true,
        "has_independent_orthogonal_systems": true, "requires_3d_dynamic_model": false
      },
      "x_direction": {
        "structural_system": "special_rc_moment_frame", "R": 8, "Omega0": 3, "Cd": 5.5,
        "period": { "structure_type": "concrete_moment_resisting_frame",
                     "approximate_Ta_sec": 1.01, "computed_period_ceiling_sec": 1.414,
                     "used_T_sec": 1.01, "source": "approximate" },
        "design_spectral_acceleration_Sa_g": 0.0446,
        "base_shear_kn": 1916.1,
        "vertical_distribution_exponent_k": 1.255,
        "story_forces": [
          { "story_index": 0, "elevation_m": 3.05, "weight_kn": 4300.0,
            "Fx_kn": 21.6, "story_shear_Vx_kn": 1916.1,
            "accidental_torsion_kn_m": "...", "overturning_moment_kn_m": "..." }
        ],
        "dynamic_analysis_required": false, "static_analysis_permitted": true,
        "rsa": { "design_spectrum_g": [ { "T_sec": 0.0, "Sa_g": 0.0225 }, "... ~200 points to 4s ..." ],
                 "min_mass_participation_pct": 90.0,
                 "modal_combination_rule": "SRSS by default; CQC required for closely-spaced modes (Sec 2.5.9.4) -- ...",
                 "esfp_base_shear_kn_for_scaling": 1916.1,
                 "force_scaling_rule": "...", "displacement_scaling_rule": "...",
                 "modeling_requirements": ["..."] },
        "ltha": { "ground_motion_criteria": { "min_records": 3, "period_matching_range_s": [0.202, 1.515],
                                               "record_count_for_design_value": "...", "ground_motion_type": "...",
                                               "matching_rule": "..." },
                  "note": "target spectrum is rsa.design_spectrum_g, not recomputed" },
        "ntha": { "real_design_spectrum_g": [ "... same shape as rsa.design_spectrum_g, but R=1, I=1 (unreduced) ..." ],
                  "ground_motion_criteria": "... same shape as ltha's ..." }
      },
      "y_direction": { "...": "same shape as x_direction -- own structural_system, R, period, Sa, base shear, story_forces, rsa, ltha, ntha. BNBC Sec 2.5.5.5 explicitly permits a different system each way (e.g. shear wall one direction, moment frame the other), so nothing here is assumed shared between directions except shared_inputs." },
      "needs_review": [
        { "reason": "load combinations (E/Eh/Emh, Sec 2.5.13) not yet available in codes/bnbc2020/seismic.py -- see its KNOWN GAPS", "detail": "..." }
      ]
    },
    "wind": {
      "method": "mwfrs_method_2_analytical",
      "inputs": {
        "basic_wind_speed_v_ms": null, "exposure_category": null,
        "wind_importance_factor_I": null, "topographic_factor_Kzt": 1.0,
        "directionality_factor_Kd": null, "enclosure_classification": "enclosed",
        "internal_pressure_coefficient_GCpi": 0.18, "gust_effect_factor_G": 0.85,
        "is_rigid": true
      },
      "wall_pressures_by_story": [
        { "story_index": 0, "elevation_m": 3.05, "qz_kn_m2": null,
          "p_windward_kn_m2": null, "p_leeward_kn_m2": null, "p_side_kn_m2": null }
      ],
      "needs_review": [
        { "reason": "basic wind speed V not verified for this location -- see codes/bnbc2020/wind.py's KNOWN GAPS", "detail": "..." },
        { "reason": "Kz/Kd/wind importance factor tables not populated", "detail": "..." }
      ]
    }
  }
}
```

`seismic` and `wind` are independent siblings — a model can have one computed and the other still all-`null`/flagged, and `needs_review` on each side tracks that independently rather than one shared list.

`seismic.shared_inputs.site_class_source` records whether the site class came from `classify_site_class()` (`"vs"`, `"spt"`, or `"su"`) or was supplied directly by the engineer (`"engineer"`) — worth keeping since a Vs-based classification and an engineer's own judgment call are different kinds of evidence for whoever reads this later.

`x_direction`/`y_direction` are separate because BNBC Sec 2.5.5.5 explicitly permits a different structural system each way — a building can be a shear wall system one direction and a moment frame the other, with genuinely different `R`/`Cd`/`Omega0`, period, and base shear per direction. `shared_inputs` holds what's actually building-wide (zone, site class, importance factor, total seismic weight); everything system-dependent lives inside each direction's own block, including its own `period` (a moment frame and a shear wall system on the same building can have meaningfully different periods).

`period.source` is `"approximate"` (Eq 6.2.38, what `apply_dynamic_loads.py` actually computes) or `"computed"` (Rayleigh/modal, which needs `structural-analysis`'s stiffness model and isn't produced by this skill — `computed_period_ceiling_sec` is there so that skill, once it exists, has the 140%-of-approximate ceiling to check its own computed T against per Sec 2.5.7.2(a), without recomputing it).

`story_forces` is ordered base to roof (`story_index` matching `revit-structure-recognition`'s own story indexing) — the opposite order from `seismic.story_shear()`'s own top-to-bottom convention, since that function's docstring is explicit that it needs top-first input; `apply_dynamic_loads.py` reverses once at the boundary rather than carrying two different orderings through the rest of the file.

`rsa`/`ltha`/`ntha` are each direction's complete advanced-analysis *system* — the verified design spectrum curve (as portable data: ~200 `{T_sec, Sa_g}` points, not a formula another skill would need to reimplement), modal combination and force/displacement scaling rules, ground-motion selection criteria, and (for NTHA) the unreduced real spectrum — everything Sec 2.5.9-2.5.11 specify, ready for `structural-analysis` to run the actual eigenvalue/time-stepping solve against once it has a real stiffness model. This skill never runs that solve itself; `period.approximate_Ta_sec` stands in for the real period throughout (e.g. in `ltha.ground_motion_criteria`'s matching window) until `structural-analysis` has a computed one to re-derive these against. `shared_inputs.requires_3d_dynamic_model` (from `seismic.requires_3d_model()`, Sec 2.5.9.1) tells that skill whether it needs one 3D model or can get away with two independent 2D ones.

`shared_inputs.is_regular` and `has_independent_orthogonal_systems` are engineer-supplied judgment calls (`revit-structure-recognition` doesn't classify irregularity), not inferred — see `references/site_seismic_wind_input_format.md`.

Wind's `wall_pressures_by_story` entries are mostly `null` on a fresh run for any project until `codes/bnbc2020/wind.py`'s flagged gaps (basic wind speed by location, Kz, Kd, wind importance factor) are filled from a verified source — the *shape* is produced either way so a project's `needs_review` list makes clear exactly what's missing, rather than the wind key being absent entirely.
