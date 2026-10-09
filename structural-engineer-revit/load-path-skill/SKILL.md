---
name: load-path
description: Traces gravity load paths (column/wall stacks to a footing, following revit-structure-recognition's own transfer flags) and lateral load path continuity (shear wall line-by-line, story to story) through a model recognition, load-application, and dynamic-load already built. Classifies the 4 of BNBC 2020's 10 Sec 2.5.5.3 irregularity types that are geometrically/story-weight determinable (mass, vertical in-plane discontinuity, plan out-of-plane offset, non-parallel systems) — feeding a partial is_regular determination back toward dynamic-load's engineer-guessed input — and flags the other 6 (torsion, soft/weak storey, re-entrant corners, diaphragm discontinuity, setbacks) as needing data this stage lacks. Firms up the low-confidence role field recognition left soft, and flags elements needing Sec 2.5.5.6 overstrength design. Use whenever the user asks to verify load path continuity, find transfer conditions, check building irregularity, or trace how a column's or wall's load reaches the foundation.
---

# Load Path

## What this actually is

`revit-structure-recognition`'s own SKILL.md put it plainly: it produces a **role** catalog, not a shape catalog, and left the hardest part of that catalog deliberately unfinished — "leave it low-confidence and let `load-path` firm it up once walls and framing are both classified." This skill is that firming-up step. It does two genuinely different things that happen to both be called "continuity":

**Gravity continuity** is graph-walking, not geometry. `revit-structure-recognition` already did the hard per-story geometric matching — `is_transfer_column`/`transfer_flag` tell you, for one column, whether its base lands cleanly on what's below it. This skill's job is chaining those individual per-story facts into a complete roof-to-foundation path for *every* column and wall, and being honest the moment a chain doesn't close (dangles with no footing, or hits a transfer beam whose own supports aren't recorded anywhere upstream).

**Lateral continuity** is a different question: not "does gravity get to the ground" but "does the *specific set of elements the engineer chose as the lateral system* actually run, uninterrupted, from roof to foundation." A wall can have a perfectly fine gravity path (it's sitting on something) while still being a serious lateral discontinuity (the thing it's sitting on isn't part of the lateral system, so the earthquake force that wall was supposed to carry down has nowhere continuous to go). BNBC treats this as a named, numbered irregularity condition (Sec 2.5.5.3 Type IV, both plan and vertical) with a specific downstream consequence (Sec 2.5.5.6's overstrength design requirement) — this skill traces it as that, not as a generic "wall stopped" note.

## Why grid-reference matching is right here (and moment frames get less rigor)

Shear walls have an unambiguous continuity signal: `grid_ref` plus canonical `base_story`/`top_story` references. Two wall records on the same gridline, at adjacent story references, are almost always the same physical lateral element continuing — matching on that is cheap, reliable, and exactly what `revit-structure-recognition`'s own geometry supports. The script accepts historical `story_range` only as a compatibility fallback; new producers must emit `base_story`/`top_story`. Moment frames and braced frames don't have an equally clean single signal (a moment frame's "continuity" is really about its columns AND its beam-column joints staying rigid, not just a wall existing on a line), and this skill doesn't attempt that fuller trace — `identify_lateral_elements()` is shear-wall-only today. A moment-frame or dual-system building gets a real, useful gravity trace and irregularity check from the parts that don't depend on frame-specific tracing (mass irregularity, non-parallel systems), but not a genuine lateral continuity trace. Don't read `lateral.lines_traced` being empty as "this building has no lateral discontinuities" when its system is a moment frame — it means the check wasn't attempted for that system type.

## Workflow

```bash
python3 scripts/trace_load_path.py --structural-model structural_model.json --out /path/to/output_dir
```
Reads `structural_model.json` as already enriched by the first three skills (it reads `dynamic_loads.seismic.*.story_forces` for mass irregularity — run `dynamic-load` first, or that specific check gets flagged and skipped, everything else still runs). Writes back the full model with `load_path` populated and the low-confidence `role` fields firmed up in place.

**Read `load_path.gravity.unresolved` and `load_path.lateral.discontinuities` before anything else.** An unresolved gravity path is either a real gap in the source Revit model or a genuinely unsupported column — both worth a human's eyes before this model goes anywhere near an analysis. A lateral discontinuity is a Sec 2.5.5.3 irregularity with a specific code-mandated consequence (see below), not just a modeling note.

**Feed `is_regular_computed` back into `dynamic-load`'s input, don't let it sit unused.** `dynamic-load`'s `site_seismic_wind_input.json` currently takes `is_regular` as a flat engineer guess because nothing upstream could do better. Now something can, partially — see `references/schema.md`'s note on exactly how to combine this skill's 4-type result with the engineer's own judgment on the other 6, and re-run `dynamic-load` if the combined value changes.

## Irregularities: what's computed, what's flagged, and why the split matters

BNBC 2020 Sec 2.5.5.3 names 10 irregularity types (5 plan, 5 vertical) with a real consequence for skipping them: an irregular building can't legally use the equivalent-static procedure alone (Sec 2.5.6), needs mandatory dynamic analysis at a much lower height threshold (Sec 2.5.8.1), and specific irregularity types trigger Sec 2.5.5.6's overstrength design and 25%-force-increase requirements. Given that much rides on the answer, this skill computes exactly the 4 types it can stand behind and refuses to guess at the other 6:

- **Computed**: mass irregularity (any storey >2x an adjacent storey's seismic weight — from `dynamic-load`'s own story weights, no new data needed), vertical in-plane discontinuity and plan out-of-plane offset (both from the shear wall continuity trace above), non-parallel systems (from lateral element axis angles).
- **Flagged, not computed**: torsion irregularity and soft storey need real storey displacements/stiffness from an actual analysis (`structural-analysis`'s job); weak storey needs storey strength/capacity (`structural-design`'s job); re-entrant corners and diaphragm discontinuity need floor plan outline/area data `revit-structure-recognition` doesn't capture today (only `thickness_mm`/`slab_type`/`diaphragm_class` — no footprint geometry); vertical geometric irregularity (setbacks) references Fig 6.2.28(c)'s own dimensional criteria, which weren't legible in the source PDF's extracted text.

`irregularities.is_regular_computed` is honestly labeled `partial` for exactly this reason — treat a clean result on the 4 computed types as "no red flags found in what we could check," never as "this building is regular."

## Known limitations

- **Continuity past a transfer beam isn't re-derived.** `revit-structure-recognition` records that a column transfers onto a specific beam (`transfer_flag.lands_on`) but not which columns *that beam's own ends* land on — there's no equivalent field for a beam the way there is for a column. Every gravity trace through a transfer beam stops there, flagged as such, rather than guessing at the beam's own supports from axis-point proximity (a materially harder and less reliable matching problem than confirming two existing records agree, which this skill does do).
- **The same gap applies to wall discontinuities.** `overstrength_required_elements` names the discontinuous wall itself, not the specific element supporting its base — that landing point isn't recorded anywhere upstream. Identify it manually before applying Sec 2.5.5.6.
- **Lateral tracing is shear-wall-only** — see the dedicated section above.
- **In-plane vs. out-of-plane offset decomposition isn't implemented** for the case where a gap has both a wall below and above it on a slightly different line — every such gap is classified as plan Type IV (out-of-plane offset, an existence check) and flagged in `needs_review` rather than measured against vertical Type IV's specific ">element length" numeric threshold, which needs the actual offset vector decomposed into in-plane/out-of-plane components.
- **Non-parallel system detection is a simplified proxy** (checks whether element axis angles cluster into two 90°-apart groups) — genuinely oddly-shaped or curved-plan buildings need an engineer's own judgment, not just this check.
- **6 of 10 irregularity types aren't computed at all** — see the dedicated section above for exactly which, and why each one's gap is a real data or sequencing limitation, not an oversight.

## Reference files

- **`references/schema.md`** — the `load_path` section shape, and exactly how `role_updates` and `is_regular_computed` are meant to feed back into earlier/later pipeline stages.

## Scripts and data

- **`scripts/trace_load_path.py`** — entry point; gravity trace, lateral continuity trace, irregularity classification, role firming, overstrength flagging.
- **`codes/bnbc2020/irregularity.py`** — verified Sec 2.5.5.3 thresholds and Sec 2.5.5.6 overstrength/force-increase trigger conditions, as pure classifier functions (each takes the relevant measurement as a plain argument — ready for `structural-analysis`/`structural-design` to call once they can supply displacement/stiffness/strength data this skill can't).
