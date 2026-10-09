---
name: structural-design
description: Combines structural-analysis's gravity+lateral member forces per BNBC Sec 2.7 strength design combinations (secondary-sourced, unlike everything else this pipeline verifies against primary text) and designs singly-reinforced rectangular beams (flexure+shear, Sec 6.3.15/6.4) and tied rectangular columns (uniaxial P-M interaction, built numerically from Sec 6.3.2's strain-compatibility rules) per BNBC 2020 Chapter 6, read here for the first time and confirming structural-analysis's concrete modulus assumption. Key caveat -- gravity is self-weight only, so dead load is underestimated and live load is absent, so results demonstrate the design method against incomplete analysis, not complete designs. Explicitly out of scope are T-beams, doubly-reinforced beams, torsion, column slenderness/biaxial interaction, spiral columns, seismic detailing, footings, and bar/development-length detailing. Use whenever the user asks to design reinforcement, check a beam/column, or run strength design checks.
---

# Structural Design

## What this actually is, and where the pipeline's own honesty catches up with it

This is the sixth and last skill in the suite `revit-structure-recognition` opened. Every upstream skill has been careful to say "not this skill's job, needs X from a later stage" — and this is that later stage, which means every deferred limitation from every earlier skill lands here as an input this skill has to work with, not fix. Most consequentially: `structural-analysis`'s own Known Limitations say its gravity case is self-weight only, not `revit-load-application`'s actual computed dead+superimposed-dead+live loads. This skill combines forces and designs sections against whatever `structural-analysis` produced — it cannot manufacture the missing load magnitude, so **every result here is real design *method* applied to admittedly incomplete demand, not a finished design.** This isn't a caveat to skim past; it's the single fact that determines how any of this output should be used.

On a more encouraging note: this is also the first skill to read BNBC 2020 Chapter 6 (concrete design) at all — and it independently CONFIRMS something `structural-analysis` had to assume without verification. That skill's `codes/materials.py` used `Ec = 4700*sqrt(fck)` (the standard ACI formula) with an explicit "not yet checked against BNBC's own concrete chapter" flag. Chapter 6's own Sec 6.1.7.1 states exactly that formula, verbatim. That flag can now be read as resolved.

## Why singly-reinforced rectangular beams and uniaxial tied-column interaction are the right scope for a first pass

Every scope cut below (see Known Limitations) shares a common thread: this skill implements the design method that applies to the *ordinary* case (a beam without unusual torsion or a flange-dependent capacity, a column with a symmetric two-layer reinforcement idealization and no unusual slenderness) — the case that's both most common in typical frame buildings and most amenable to reliable, verified formulas rather than iterative or figure-based procedures. A doubly-reinforced beam or a slender column isn't wrong to design by hand or by other software; it's a **materially different calculation** (Sec 6.3.15.1(b)'s compression-steel formulas, Sec 6.3.10's moment magnification) that deserves its own verified implementation rather than a rushed extension bolted onto this one. Flagging a section that needs it (rho exceeds rho_max, Vu exceeds Vs,max) and stopping there is more honest than silently approximating.

## Workflow

```bash
python3 scripts/design_members.py --structural-model structural_model.json \
    --design-input design_input.json --out /path/to/output_dir
```
Needs `analysis_results.member_forces` from `structural-analysis` (run that first) and a `design_input.json` supplying reinforcement grade (`fy_mpa`, since rebar grade isn't a `revit-structure-recognition` BIM property — see `references/schema.md`).

**Read `design_results.scope_note` and every `needs_review` entry before reading a single utilization number.** A column's `Ast_assumed_mm2` is a starting assumption this skill checks, not a design it arrived at — every column carries an explicit flag saying so. A beam whose required ratio exceeds `rho_max`, or whose shear demand exceeds what stirrups alone can provide, is flagged and left undesigned rather than silently pushed through.

**Treat `utilization < 1.0` as "adequate against incomplete demand," never as "this member is fine."** Given the self-weight-only gravity case, a comfortable utilization ratio here says less about the real member than it would in a design built on complete loads — see the section above.

## Known limitations

- **The gravity demand is incomplete, inherited from `structural-analysis`** — see the opening section. This is the limitation that matters most; every other one below is a scope boundary within the design method itself.
- **Beams are always designed as rectangular, never as T-beams** (Sec 6.3.15.2 not implemented) — conservative for positive-moment capacity (ignoring a real flange's compression contribution costs nothing but extra steel), but NOT conservative wherever the flange would actually be in tension (negative moment regions near supports, for a beam that really does have a compression flange elsewhere) — a real limitation, not a uniformly safe simplification.
- **Doubly-reinforced beam design isn't implemented** (Sec 6.3.15.1(b)) — a beam whose demand exceeds singly-reinforced capacity is flagged, not designed with compression steel.
- **Torsion isn't designed for at all** (Sec 6.4.4).
- **Column slenderness / moment magnification isn't applied** (Sec 6.3.10) — `codes/concrete_design.py`'s `is_slenderness_negligible()` lets a caller check the applicability condition, but this skill's own orchestrator doesn't call it or apply magnification when it fails.
- **Column biaxial bending is two independent uniaxial checks, not a true interaction surface** — no Bresler's-method-style combination of `Mux` and `Muy` demand.
- **Column reinforcement is idealized as two symmetric layers** for interaction-diagram purposes, not the real distributed-perimeter bar layout a real column would have — changes the diagram's shape somewhat, particularly near pure bending.
- **Spiral columns aren't supported** — tied columns only.
- **Seismic detailing is completely absent** (Chapter 8, Sec 8.3: confinement zones, special hoop spacing, strong-column-weak-beam ratio checks). This is a significant, deliberate gap for anything in Seismic Design Category C or D — this pipeline has computed seismic *loads* in real depth (three skills' worth) without yet reaching seismic *detailing*, and that gap deserves to be named plainly rather than left implicit.
- **No footing or substructure design** — `structural-analysis` excluded footings from its FE model entirely; this skill has nothing to design them against, and bearing capacity/geotechnical data isn't part of this pipeline yet.
- **No development length, splice, spacing, or cover detailing** (Sec 8.1-8.2) — this skill sizes required steel *area* only, never a bar count, size, or layout.
- **BNBC Sec 2.7 and Sec 2.5.13's exact combination factors and `Ev` formula are secondary-sourced** — see `codes/load_combinations.py`'s own module docstring for exactly what that means and why (unlike literally every other verified number across all six skills in this suite, which came from the primary BNBC PDF text directly).

## Reference files

- **`references/schema.md`** — the `design_results` section shape and the `design_input.json` format.

## Scripts and data

- **`scripts/design_members.py`** — entry point; combines forces per Sec 2.7, runs beam and column design.
- **`codes/concrete_design.py`** — verified BNBC Chapter 6 flexural, shear, and column interaction provisions.
- **`codes/load_combinations.py`** — Sec 2.7/2.5.13 combination factors and seismic effect formula (secondary-sourced — see its own docstring).
- **`codes/section_parsing.py`** — minimal, deliberately-duplicated `section_hint`/`material.names` parsing (see `structural-analysis`'s own `codes/materials.py` for the fuller version and the reasoning behind parsing a Revit label string at all).
