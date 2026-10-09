# `structural_model.json` — the `design_results` section, and `design_input.json`

`design_results` is added fresh (not pre-stubbed by `revit-structure-recognition`, like `structural-analysis`'s own `analysis_results`).

```json
{
  "design_results": {
    "scope_note": "self-weight-only gravity case inherited from structural-analysis -- see SKILL.md before treating any result here as a complete design",
    "fy_mpa_used": 420.0,
    "beams": {
      "BEAM-1": {
        "section": { "b_mm": 300.0, "h_mm": 500.0, "d_assumed_mm": 450.0, "fck_mpa": 30.0, "fy_mpa": 420.0 },
        "demand": { "Mu_end_i_knm": -13.88, "governing_combo_i": "1.4D", "Mu_end_j_knm": 23.43,
                     "governing_combo_j": "1.2D+1.0E+1.0L", "Vu_knm": 14.82, "governing_combo_v": "1.4D" },
        "flexure_end_i": { "As_required_mm2": 450.0, "As_calculated_mm2": 82.0, "As_min_mm2": 450.0,
                            "governed_by_minimum": true, "phi": 0.9, "rho": 0.00061, "rho_max": 0.02175 },
        "flexure_end_j": { "...": "same shape as flexure_end_i" },
        "shear": { "stirrups_required": false, "phi_Vc_kn": 94.28, "note": "..." }
      }
    },
    "columns": {
      "COL-9": {
        "section": { "b_mm": 400.0, "h_mm": 400.0, "fck_mpa": 30.0, "fy_mpa": 420.0,
                      "Ast_assumed_mm2": 3200.0, "reinforcement_ratio_ok": true },
        "demand": { "Pu_kn": 168.85, "governing_combo_p": "1.2D+1.0E+1.0L",
                     "Mux_knm": -8.49, "governing_combo_mx": "0.9D+1.0E+1.6H",
                     "Muy_knm": 29.41, "governing_combo_my": "0.9D+1.0E+1.6H" },
        "check_x_direction": { "adequate": true, "capacity_phi_Mn_knm": 217.35, "demand_Mu_knm": -8.49, "utilization": 0.037 },
        "check_y_direction": { "adequate": true, "capacity_phi_Mn_knm": 217.35, "demand_Mu_knm": 29.41, "utilization": 0.129 },
        "note": "Mux/Muy checked independently against uniaxial capacity -- not a true biaxial interaction check"
      }
    },
    "needs_review": [ { "element": "...", "reason": "..." } ]
  }
}
```

**`scope_note` is not decorative — read it before reading anything else in this section.** `structural-analysis`'s gravity case is self-weight only (see that skill's own Known Limitations). Every `D` (dead load) value this skill combines is therefore missing superimposed dead load and, since no live-load FE case exists upstream at all, `L` is always zero. Every `Pu`/`Mu`/`Vu` here is a *demonstration of the design method* against real (if incomplete) analysis output, not a complete, code-compliant member design. Wiring in `revit-load-application`'s actual panel loads is `structural-analysis`'s own documented next step, not something this skill can fix on its own end.

**`columns.*.section.Ast_assumed_mm2`** is exactly what its name says — assumed (2% of gross area, a common starting point for a first check), not derived from any input or iterated to a target utilization. This skill checks whether an *assumed* reinforcement quantity is adequate; it doesn't search for the minimum adequate one. `needs_review` carries an explicit note on this for every column, not just once.

**`governing_combo_*`** names which of BNBC Sec 2.7's eight strength-design combinations produced the largest-magnitude demand — see `codes/load_combinations.py`'s module docstring for why these combination factors, and the `E` (seismic) term inside them, are sourced from a secondary reference rather than the primary BNBC text this pipeline otherwise verifies against everywhere else.

**Beams’ `E` contribution** comes from `structural-analysis`'s own lateral-static case results for that same beam ID, taking whichever direction (X or Y) produced the larger-magnitude `gravity_moment_knm_i` — not a true envelope across every load pattern, just the two lateral cases that exist upstream.

**Columns’ `check_x_direction`/`check_y_direction`** are independent uniaxial checks, not a combined biaxial one — see SKILL.md.

## `design_input.json`

```json
{ "fy_mpa": 420.0, "d_prime_mm": null }
```
- **`fy_mpa`** — reinforcement yield strength. Defaults to 420 (BNBC's own Chapter 6 worked examples center on Grade 420) if omitted. Not inferred from anywhere in `structural_model.json` — rebar grade isn't a property `revit-structure-recognition` captures (it's a specification-level choice, not usually a per-element BIM property), so this is a genuine engineer input, the same way `dynamic-load`'s `structural_system` is.
- **`d_prime_mm`** — override for the column interaction diagram's assumed cover-to-reinforcement-centroid distance (default `0.1*h` if omitted, a common rule-of-thumb — see `codes/concrete_design.py`'s `build_interaction_diagram()`). Supply the real value once actual bar layout is known.
