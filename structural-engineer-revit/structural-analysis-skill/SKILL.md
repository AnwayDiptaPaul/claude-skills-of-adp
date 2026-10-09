---
name: structural-analysis
description: Builds an openseespy 3D linear-elastic frame model (columns+beams -- walls excluded) from a structural_model.json the first four skills already built, parses section_hint/material.names into numeric properties (the one place in this pipeline that parses a Revit label string, since some numeric value is unavoidable here), assigns lumped mass from dynamic-load's story weights, and runs real eigenvalue/modal analysis -- computed periods, mode shapes, mass participation -- feeding dynamic-load's previously-null RSA with real numbers via SRSS against its own spectrum curve. Also runs gravity (self-weight only) and lateral (ESFP story forces) static analysis. Skips wall/shell modeling, substructure/geotechnical analysis, time-history, nonlinear/pushover, and detailed panel-level gravity loads -- all flagged, not approximated. Use whenever the user asks to run an actual structural analysis, compute real periods/mode shapes, run response spectrum analysis, or check equilibrium/base shear against expected values.
---

# Structural Analysis

## What this actually is

Every skill before this one has been careful to say some version of "this needs an actual stiffness model, which belongs to structural-analysis" — `dynamic-load`'s approximate period, its `rsa: null`-until-this-exists design, its `computed_period_ceiling_sec` sitting unused; `load-path`'s torsion/soft-storey/weak-storey irregularity checks flagged as needing "an actual analysis." This skill is that actual analysis. It's also the first skill in this pipeline that builds and solves a real finite element model rather than computing values from code formulas and geometry — a genuinely different kind of task, with a genuinely different failure mode: a code-formula bug produces an obviously wrong number; an FE modeling bug can produce a *plausible-looking* wrong number that only shows up as an equilibrium or symmetry check failing. Both bugs described below were caught exactly that way, not by inspection.

## Why linear-elastic frame analysis is the right tool here (and why two real bugs are documented, not hidden)

This skill builds a linear-elastic model because that's what every upstream skill's output is *for* — `dynamic-load`'s ESFP story forces, its RSA design spectrum, are themselves linear-elastic quantities (a response spectrum IS a linear-elastic concept; nonlinear analysis needs hinge models tied to final reinforcement design, which is `structural-design`'s territory, later). Building anything more sophisticated here would be solving a problem this pipeline stage doesn't have yet.

Two things went wrong during this skill's own build and are worth knowing about rather than quietly fixing and moving on:

1. **A gravity equilibrium check that flagged a perfectly correct model as broken.** Self-weight is applied downward; this environment's reaction convention reports the fixed base's vertical reaction with the *same* sign and magnitude as the applied load (both positive, both equal), not the opposite. An early version of the check assumed they should sum to zero and failed on a model where reactions matched the applied load exactly — caught by noticing the two printed numbers were identical while the check still said "failed."
2. **A mass-participation formula that let modes sum past 100%.** This skill's own test fixture — a perfectly symmetric grid of identical columns — produces two modes at an *identical* period (a genuine, expected structural fact for a symmetric building, not a bug). The eigenvalue solver returns an arbitrary rotated basis for that degenerate pair, so neither individual mode is purely X or purely Y. Computing each mode's effective mass as `Lx²/Mx` (dividing by that mode's OWN x-direction modal mass) blows up numerically the moment a mode's x-direction modal mass happens to be tiny — which is exactly what one half of a degenerate pair looks like. The fix: divide by the mode's *total* modal mass (`Lx²/M_full`, `M_full` summed over both X and Y together) instead of a direction-restricted one. After the fix, this skill's own test fixture sums to exactly 100.00% across 12 modes in both directions — the cleanest possible confirmation.

Both are documented in `scripts/run_analysis.py`'s own docstrings at the exact functions involved, not just here.

## Workflow

```bash
python3 scripts/run_analysis.py --structural-model structural_model.json --out /path/to/output_dir [--num-modes 12]
```
Reads `structural_model.json` as enriched by all four prior skills (needs `dynamic_loads.seismic.<direction>.story_forces` and `.rsa.design_spectrum_g` — run `dynamic-load` first, or modal/RSA/lateral-static get skipped and flagged for whichever direction is missing them). Writes back the full model with `analysis_results` populated.

**Check `model_summary.elements_excluded` before anything else.** Every column or beam whose `section_hint`/`material.names` didn't parse is simply absent from the FE model — not approximated with a guessed section. A non-trivial exclusion count means real structural elements are missing from every result below it.

**Read `gravity_self_weight_only.equilibrium_error_kn` as a pass/fail gate**, not a detail — a non-near-zero value means something about the model itself is wrong (per the bug account above, verify the check's own sign convention holds in your environment before trusting it blindly either).

**Feed `modal.<direction>[0].period_s` back toward `dynamic-load`, checked against its own ceiling.** `dynamic-load`'s `computed_period_ceiling_sec` (140% of its approximate period, per Sec 2.5.7.2(a)) exists specifically to bound this number — this skill checks it automatically and flags a violation, but the corrective action (use the ceiling value, not the raw computed T1, for `Sa`) is on whoever consumes this output next.

## Known limitations

- **Walls aren't modeled at all** — not approximated as equivalent columns, not modeled as shells. A shear-wall building gets a real gravity/modal analysis of its *frame* elements only; the walls' real contribution to stiffness and mass distribution is absent. This is the single biggest scope gap for any building that isn't a pure moment frame.
- **Gravity analysis is self-weight only.** The analysis now publishes traceable per-member end actions, but `revit-load-application`'s actual panel-derived DL/SDL/LL loads still are not applied. Treat those actions as preliminary self-weight demand and verify local-axis/sign conventions before design use; they are not a complete gravity design case.
- **Lateral loads are distributed equally across each story's nodes**, not by relative stiffness to individual columns. Per-member end actions are recovered after each lateral-static solve, but their fidelity is bounded by that equal-node loading assumption; use them as a transparent preliminary check, not a substitute for a stiffness- or diaphragm-based load distribution.
- **Response spectrum analysis is a simplified SRSS scalar combination** (`combined_spectral_acceleration_g_approx`), not full multi-mode force and displacement recovery at every node. CQC (required by Sec 2.5.9.4 for closely-spaced modes, which a symmetric building's own degenerate pairs are a textbook example of) isn't implemented — this skill's own test fixture is exactly the case that would need it, and gets SRSS instead, flagged as such.
- **No substructure or geotechnical analysis at all** — footings are excluded from the FE model, boundary conditions are a simple fixed base (no soil-spring stiffness), and settlement/bearing-capacity checks aren't attempted despite the pipeline's original "substructure + superstructure" framing. This entire domain is out of scope for this version.
- **Time-history (linear or nonlinear) and nonlinear static (pushover) aren't run** — `dynamic-load`'s LTHA/NTHA ground-motion criteria are ready to use, but this skill doesn't select, scale, or apply actual ground motion records.
- **Concrete elastic modulus uses the ACI 318 formula** (`Ec = 4700*sqrt(fck)`), not yet checked against BNBC Part 6's own concrete chapter (a different chapter from the load provisions every other number in this pipeline has been verified against) — see `codes/materials.py`'s docstring.
- **Section parsing is rectangular-only.** Circular columns and steel section designations are excluded from the model rather than guessed at — see `codes/materials.py`'s explicit test case for why a steel `W12X26` must never be parsed the way a `300x300` RC section is.

## Reference files

- **`references/schema.md`** — the `analysis_results` section shape.

## Scripts and data

- **`scripts/build_fe_model.py`** — constructs the openseespy model: nodes (deduplicated by coordinate), elements, sections, boundary conditions. Owns the mm/MPa-to-kN-m unit conversion (one place, documented in its own module docstring) and the empirically-verified `eleLoad` slot convention for vertical vs. horizontal elements.
- **`scripts/run_analysis.py`** — entry point; gravity static, mass assignment, eigenvalue/modal, response spectrum, lateral static.
- **`codes/materials.py`** — `section_hint`/`material.names` string parsing into numeric section/material properties, with the reasoning for why this is the one pipeline module that parses a Revit label string at all.
