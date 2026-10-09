# `structural_model.json` — the `analysis_results` section

Supplements `revit-structure-recognition`'s `references/schema.md`. Unlike `dynamic_loads` and `load_path`, this key wasn't pre-stubbed by that skill (it predates this skill's existence in the pipeline) — it's added fresh here.

```json
{
  "analysis_results": {
    "model_summary": { "node_count": 27, "element_count": 42, "elements_excluded": 0 },
    "gravity_self_weight_only": { "total_self_weight_kn": 760.32, "sum_vertical_reactions_kn": 760.32, "equilibrium_error_kn": 0.0 },
    "modal": {
      "x_direction": [
        { "mode": 1, "period_s": 0.27758, "mass_participation_x_pct": 86.03, "mass_participation_y_pct": 0.0 },
        { "mode": 2, "period_s": 0.27758, "mass_participation_x_pct": 0.0, "mass_participation_y_pct": 86.03 }
      ],
      "y_direction": [ "... same shape, from a separately-built model pass ..." ]
    },
    "response_spectrum": {
      "x_direction": {
        "combination_method": "SRSS", "cumulative_mass_participation_pct": 100.0,
        "combined_spectral_acceleration_g_approx": 0.04865,
        "modal_results": [ { "mode": 1, "period_s": 0.27758, "Sa_g": 0.05625, "mass_participation_pct": 86.03 } ],
        "note": "a simplified SRSS combination of per-mode Sa, NOT a full multi-mode force/displacement recovery at every node"
      }
    },
    "lateral_static": {
      "x_direction": { "base_shear_from_reactions_kn": -63.56, "expected_base_shear_kn": 63.56 }
    },
    "member_forces": {
      "gravity_self_weight_only": {
        "COL-0001": { "local_axial_kn_i": -120.0, "local_moment_y_knm_i": 0.0, "axial_kn_i": -120.0 },
        "BM-0001": { "local_shear_z_kn_i": 15.0, "local_moment_y_knm_i": -22.5, "gravity_moment_knm_i": -22.5 }
      },
      "lateral_static": {
        "x_direction": { "COL-0001": { "moment_for_x_load_knm_i": 18.4 } }
      },
      "note": "Raw local end actions are retained; verify local axes and signs before final design use."
    },
    "needs_review": [ { "reason": "..." } ]
  }
}
```

**`model_summary.elements_excluded`** counts columns/framing whose `section_hint` or `material.names` didn't parse (see `codes/materials.py`) — those elements are simply absent from the FE model, not approximated with a guessed section. A non-zero count here means the model is missing real structural elements; check `needs_review` for which ones and why before trusting anything downstream of it.

**`gravity_self_weight_only`** is exactly what its name says — self-weight only, not a complete gravity load case. `equilibrium_error_kn` should be at or near zero (sum of vertical reactions should equal total self-weight); anything else means the model or the load application has a real problem, not a rounding artifact.

**`modal`** is computed **separately per direction** (`x_direction`/`y_direction`), each from its own fresh model-build pass, because `dynamic-load` allows a different lateral system (and therefore this skill assigns the same geometry but could in principle support direction-specific modeling assumptions later) per direction — today the FE model itself doesn't actually change between the two passes (same frame either way), but the mass assignment is read from each direction's own `dynamic_loads.seismic.<direction>.story_forces`, so keeping the passes separate is what lets a future version vary the model itself without restructuring this output shape. Periods appearing identical across directions (as in the example above) reflects a genuinely symmetric structure, not a bug — see SKILL.md's account of catching and fixing the mass-participation formula that once made this case look broken.

**`response_spectrum.<direction>.combined_spectral_acceleration_g_approx`** is a single SRSS-combined spectral acceleration value, weighted by mass participation — useful as a sanity cross-check against the ESFP `design_spectral_acceleration_Sa_g` `dynamic-load` already computed, **not** a substitute for genuine multi-mode force and displacement recovery at every node (that needs per-mode elastic analysis runs combined mode-by-mode at each response quantity, which this skill doesn't do — see Known Limitations).

**`lateral_static`** applies `dynamic-load`'s own ESFP story forces as point loads (split equally across each story's nodes — the same simplification as mass assignment) and reports the resulting base shear from reactions as a cross-check against `dynamic-load`'s own expected value. A mismatch beyond a couple of percent means something in the load application or model itself is wrong, not that the codes disagree with each other.

**`member_forces`** is keyed by this pipeline's member IDs, never OpenSees integer tags. Each record retains all 12 OpenSees local end actions (`local_axial`, `local_shear_y/z`, `local_torsion`, `local_moment_y/z` at both ends) plus the narrow semantic aliases consumed by `structural-design`. The aliases rely on `build_fe_model.py`'s present local-axis convention: for horizontal members, `Vz`/`My` are the self-weight shear/bending pair; for vertical members, `My`/`Mz` are mapped to the X/Y lateral planes. Verify local axes and signs for the actual model before treating these as final design actions. The gravity case remains self-weight only and the lateral case remains equally distributed story load, so this enables a traceable preliminary design check — not a complete code-compliant design.
