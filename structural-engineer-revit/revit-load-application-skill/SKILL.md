---
name: revit-load-application
description: Assigns dead, super dead, and live loads onto a structural model already recognized by revit-structure-recognition — infers occupancy per room/space, looks up code-verified live loads (BNBC 2020 built out first; other codes stubbed for later), composes super dead load from finishes/ceiling/MEP/partitions with each component labeled by source (code value vs. engineering-judgment default), and distributes the result to specific beams and columns via verified tributary-area and two-way (45-degree/yield-line) methods — not stiffness-based, deliberately, since that's the right tool for gravity loads unlike lateral ones. Produces the loads section of structural_model.json for dynamic-load, load-path, structural-analysis, and structural-design to build onto. Use after structure recognition, whenever the user asks to apply/assign loads, compute dead/live/super-dead load, size a tributary area, distribute a slab's load to beams or columns, or estimate SDL/finish/partition load.
---

# Revit Load Application

## What this actually is

Two genuinely separate judgment calls live inside "apply the loads," and conflating them is the usual way this goes wrong: **what's the load** (a code lookup, mostly — occupancy tells you the live load, material and buildup tell you dead and super dead load) and **where does it go** (a geometry problem — tributary area for gravity loads, unlike the stiffness-based reasoning lateral loads need). This skill keeps them as two distinct, separately-verifiable stages: `codes/bnbc2020/loads.py` + `scripts/occupancy_mapping.py` + `scripts/sdl_estimation.py` answer "what's the load"; `scripts/distribution.py` answers "where does it go." `scripts/apply_loads.py` is the orchestrator that runs both stages and writes the result.

**Every load-table value here was checked directly against the official BNBC 2020 Part 6 Chapter 2 text before being transcribed — not recalled.** Same discipline as `revit-structure-recognition`'s IFC/Revit-API facts, applied to code tables instead: a wrong live load value doesn't fail loudly, it just quietly under- or over-designs something. `codes/bnbc2020/loads.py`'s docstring says exactly what was verified and how.

**The two-way slab distribution formulas were derived and tested symbolically, not recalled either** — `scripts/distribution.py`'s docstring covers this, including a non-obvious verified property (a real discontinuity right at the one-way/two-way cutoff, aspect ratio = 2 — expected, load-conserving, not a bug) that's worth reading before it looks like one.

## Why tributary area is the right tool here (and wasn't, for lateral loads)

`revit-structure-recognition`'s SKILL.md makes a point of this for lateral force distribution: in an indeterminate structure, stiffness governs how lateral load actually distributes, and naive tributary-area reasoning gets that wrong. Gravity loads are different — for a regular framed building, tributary-area distribution (refined by the 45-degree/yield-line method for two-way panels, in `distribution.py`) is the ordinary, code-endorsed method, not a simplification to apologize for. That's why nothing in this skill is stiffness-based. If a floor plate is irregular enough that tributary area genuinely doesn't apply well, that's a `structural-analysis`-stage concern (a full FEA distributes load correctly regardless of geometry) — flag it and move on rather than trying to hand-solve it here.

## Workflow

**1. Get occupancy data.** This skill needs Room/Space information that `revit-structure-recognition` doesn't extract (it only pulls structural categories) — gather it the same way that skill gathers structural elements: via whichever MCP path is connected (`list_levels` is already available; a `list_spaces`/`list_rooms` tool doesn't exist yet in either MCP path covered by that skill's reference guides — extend `pyrevit_extension/` the same way that skill's six tools were added, following its exact documented pattern, when this becomes a recurring need) or by asking the engineer directly for a per-story occupancy breakdown when MCP Room/Space data isn't available yet. Either way, assemble an `occupancy_map.json` — see `references/occupancy_map_format.md`.

**2. Run the pipeline.**
```bash
python3 scripts/apply_loads.py --structural-model structural_model.json \
    --occupancy-map occupancy_map.json --out /path/to/output_dir
```
This reads the `structural_model.json` `revit-structure-recognition` produced, reconstructs rectangular slab panels from the grid + beam data already in it (no slab footprint geometry needed — see that skill's own known-limitations note; this works from the grid bay system instead, which is standard practice for regular framing), computes DL/SDL/LL per panel, distributes each to the surrounding beams, and writes the enriched model back out with `loads` populated.

**3. Open the `needs_review` list inside `loads` before trusting it.** A story with no occupancy_map entry, a panel not fully bounded by beams (candidate flat-plate area, or a real modeling gap), a slab with no thickness found — all flagged, none silently defaulted to zero and left that way without saying so.

**4. Keep DL, SDL, and LL separate all the way through.** `apply_loads.py` never pre-sums them — factored load combinations are `structural-analysis`'s job, and collapsing the distinction early would make that impossible to do correctly later.

## Composing SDL honestly

`sdl_estimation.compose_sdl()` returns a labeled breakdown, not just a number, because SDL is a mix of two genuinely different kinds of value: a BNBC 2020 Table 6.2.2 finish/ceiling weight is a verified code fact; an MEP/services allowance (ducts, conduit, sprinkler piping as a distributed area load) is ordinary engineering judgment with no BNBC-mandated figure behind it. Every component says which one it is. Don't let a judgment-call default quietly read as a code minimum three steps downstream — that's exactly the kind of assumption that should have a name attached when someone reviews the design later.

## Partition loads: two different provisions, don't conflate them

BNBC 2020 gives **two separate ways** to account for partitions, and they apply to different things:
- **Sec 2.2.5** (dead load): partitions **shown on the plans** get modeled as actual line loads at their real position.
- **Sec 2.3.6** (live load allowance): partitions **not yet shown** (anticipated, movable) — if light enough (≤ 5.5 kN/m run) — may instead use a blanket area UDL (33% of weight/m run, minimum 1.2 kN/m²) *in lieu of* guessing at future positions. `sdl_estimation.compose_sdl()` implements the second provision only, and `bnbc.partition_udl_allowance_kn_m2()` returns `None` (not a number) when a partition is too heavy for it — that's the signal to model it as an explicit line load per Sec 2.2.5 instead, not a bug to work around.

## Known limitations

- **Point loads and equipment aren't handled yet** (rooftop AHUs, generators, elevator machine rooms, transformers) — the original spec for this skill called for point loads "with punching area defined." That's a real, distinct piece of work (equipment footprint + weight, often from a cut sheet or a provisional allowance pending final MEP selection, checked as a local punching-shear condition separate from the general area-load tributary math above) that hasn't been built yet. Treat any equipment load as a manual addition to `structural-analysis`'s input until this is extended.
- **Panel detection needs a fully beam-bounded rectangular bay.** Irregular floor plates, non-orthogonal grids, and genuine flat-plate areas (no beams at all) all land in `needs_review` rather than being guessed at — flat-plate column tributary area (`distribution.column_tributary_area_m2()`) is implemented and tested, but `apply_loads.py` doesn't call it automatically yet for stories without beams.
- **Occupancy inference is name-pattern matching**, same honest limitation as anything else that reads free-text Revit data — `scripts/occupancy_mapping.py`'s `ROOM_NAME_PATTERNS` covers common English-language conventions, not every office's naming convention, and a handful of matched categories (a bare "Lab", "Factory") are inherently ambiguous from a name alone and always flagged regardless of match confidence.
- **Only BNBC 2020 is populated.** `codes/bnbc2020/` is the first code module of the pluggable-by-code architecture described when this pipeline was first planned — IS/Eurocode/NCC-AS-NZS/ASCE modules don't exist yet and shouldn't be guessed at; build each one against its own verified source the way this one was.
- **Live load reduction (`reduced_live_load()`) is implemented and tested against BNBC's Eq. 6.2.1**, but `apply_loads.py` doesn't call it yet — every panel currently uses the unreduced `L0` value from Table 6.2.3. Wiring in the reduction (it needs each member's actual tributary area and `KLL` value, both already computable from what this skill already has) is a natural next increment, not a redesign.

## Reference files

- **`references/occupancy_map_format.md`** — the `occupancy_map.json` shape `apply_loads.py` expects.
- **`references/schema.md`** — the `loads` section shape added to `structural_model.json` (supplements, doesn't replace, `revit-structure-recognition`'s own `references/schema.md`, which remains the canonical reference for everything that skill owns).

## Scripts and data

- **`scripts/apply_loads.py`** — entry point; orchestrates everything below.
- **`scripts/distribution.py`** — verified tributary-area distribution math (see its docstring for the derivation and the one-way/two-way discontinuity note).
- **`scripts/occupancy_mapping.py`** — room-name-to-occupancy classification.
- **`scripts/sdl_estimation.py`** — labeled SDL composition.
- **`codes/bnbc2020/loads.py`** — verified BNBC 2020 load data and lookup functions; the first module of what's meant to become a pluggable per-code architecture.
