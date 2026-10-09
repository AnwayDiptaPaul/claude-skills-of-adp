# Classification heuristics

## Contents
1. [General principles](#general-principles)
2. [Frame type — columns and framing](#frame-type)
3. [Wall classification](#wall-classification)
4. [Slab/floor type](#slab-type)
5. [Footing type and foundation system](#footing-type)
6. [Framing role](#framing-role)
7. [Openings](#openings)
8. [Confidence rubric](#confidence-rubric)

---

## General principles

Every heuristic below follows the same shape: gather whatever signals are actually available in the model, weigh them, and either commit to a classification (with the signals recorded, so the "why" is auditable later) or flag for review. None of them treat a single field as ground truth — not even an IFC `PredefinedType`, and especially not a name string, because both are things a modeler can set wrong, leave at a Revit default, or simply never touch.

The reason this matters more here than in typical BIM data extraction: a wrong wall classification doesn't produce a visibly broken model. It produces a model that looks fine and quietly omits a lateral element from the seismic system, or asks the design skill to size a partition for earth pressure it will never see. The cost of a wrong silent guess is much higher than the cost of a flagged item the engineer has to glance at, so every heuristic here is tuned to flag rather than guess when signals disagree.

## Frame type

Applies to columns and framing (beams/girders/joists/members).

| Signal | What it tells you | Strength |
|---|---|---|
| Material category (`IfcMaterial.Category` or name) contains "concrete" | RCC | Strong |
| Material name contains "steel", or a section profile is present (`IfcMaterialProfileSet`) with a recognizable shape name (`W\d`, `HE\d`, `UC`, `UB`, `ISMB`, `ISHB`, `HSS`, `RHS`, `CHS`, `L\d+x\d+`, `C\d+x\d+`) | Steel | Strong |
| Material name contains "timber", "wood", "glulam", "CLT" | Timber | Strong |
| Material name contains "masonry", "brick", "block", "CMU" | Masonry | Strong |
| Object type / name matches a rectangular dimension pattern (`\d{2,4}\s*[xX×]\s*\d{2,4}`) together with a concrete material | RCC | Confirms above, doesn't stand alone |
| No material association at all, or a generic placeholder ("Default", "Structural Material") | — | Flag — don't guess |
| Profile name (steel-shaped) present but material says "Concrete", or vice versa | — | Flag — this is very likely a data-entry inconsistency in the source model, and it's cheap to catch here before it corrupts a section lookup three skills downstream |

Concrete grade notation is worth carrying through even though it isn't part of `frame_type`: `M25`/`M30` (IS-code cube-strength convention), `C25/30` (Eurocode cylinder/cube convention), or a bare `f'c` / psi / MPa value (ACI/BNBC convention) is a useful hint about which code convention the original modeler was working in, and the design skill will want it. Record whatever grade string is present in `material.names` verbatim rather than trying to normalize it here — normalization is a design-skill concern, not a recognition-skill one.

## Wall classification

This is the highest-stakes call in the whole skill — a missed shear wall silently weakens the lateral system, and a wall misread as shear when it's really just a thick partition inflates apparent stiffness and pulls seismic force toward a member that was never detailed for it. No single signal is trusted alone; **especially not IFC's `SHEAR` predefined type** — buildingSMART's own schema documentation for `IfcWallTypeEnum` states outright: *"The potentially misleading term SHEAR shall not impose a particular resistance against shear forces, but a particular shape."* It's a shape descriptor that happens to share a word with a structural role. Treat it as one weak vote, nothing more.

Score each wall against three candidate roles — `shear`, `retaining`, `partition_or_cladding` — using the signals below, then apply the decision rule at the end.

| Signal | Points toward | Strength | Notes |
|---|---|---|---|
| Revit-native `Function` parameter (surfaced in psets, typically `Pset_WallCommon.Function` or similar) = "Retaining" | retaining | **Strong** | This is the engineer's own stated intent in the source model — the single most reliable signal when present |
| Same parameter = "Foundation" | retaining or foundation_wall | Strong | Distinguish from retaining by checking whether soil is asymmetric (below) |
| IFC `PredefinedType` = `RETAININGWALL` | retaining | Strong when present | Only exists in IFC4.3; Revit's standard building IFC4 export usually won't have it — absence proves nothing |
| IFC `PredefinedType` = `SHEAR` | shear | **Weak only** | See caveat above — never sufficient alone |
| Continuous through 3+ stories, tied into a diaphragm at each | shear | Medium-strong | Partitions essentially never do this; genuine shear walls almost always do |
| Present at only one story | shear | Weak-against | Doesn't rule it out (top-story or mezzanine shear walls exist) but lowers confidence |
| Thickness ≥ ~150 mm (RCC) | shear or retaining | Weak | Doesn't distinguish between them; codes don't set a hard minimum, this just rules out lightweight partitions |
| Thickness ≤ ~115 mm | partition_or_cladding | Medium | Below the range where RCC lateral or retaining design is practical |
| High opening ratio (large window/door area relative to wall face) | partition_or_cladding | Medium-strong | Both shear walls and retaining walls are typically solid or near-solid; heavy fenestration is a strong tell for infill/cladding |
| Below the project's grade-level story (see note below) | retaining (candidate) | Medium | Necessary but not sufficient — a below-grade wall can just as easily be an interior basement partition or the below-grade continuation of a core shear wall |
| Perimeter location (building edge, not core) | retaining | Weak | Retaining walls are almost always perimeter; shear walls can be either, so this only helps distinguish, never confirms |
| Asymmetric adjacency — occupied space one side, no adjacent `IfcSpace` the other (implying backfill) — *only checkable if the model has space-boundary data, which structural models often don't* | retaining | Strong when available | Use it if present; don't expect it |

**"Grade level" is not always story index 0.** Podium and multi-basement configurations mean the reference story for "below grade" has to come from context — prefer a story explicitly named/tagged as ground/grade (`"Ground"`, `"GF"`, `"G.L."`, or similar), and fall back to elevation 0 only if nothing is tagged. If genuinely ambiguous, ask the user which story is grade rather than guessing — it's a five-second question that prevents every basement wall in the model from being silently mis-scored.

**Decision rule:**
- One candidate role clearly dominates (roughly 2:1 or better over the next) **and** at least one Strong signal supports it → classify, confidence scaled to signal strength.
- Two roles score comparably, or the only support is Weak signals → `needs_review`. Do not force a label.
- Both `shear` and `retaining` score meaningfully (common for basement perimeter walls that continue as the lateral system above grade) → record **both** in `wall_class.primary` / `wall_class.secondary`, set `dual_role: true`, and leave a note that the boundary condition (how the wall's earth-pressure demand and its lateral-system demand combine, or whether they're checked as separate load cases) needs the engineer's call — this skill records the fact, it doesn't resolve the mechanics.

## Slab type

| Signal | Points toward |
|---|---|
| No beams beneath/around at the same story, thin (~125–200 mm), spans directly onto columns | `flat_plate` |
| Same as above but with a visibly thickened zone or a distinct drop-panel element around columns | `flat_slab_drop_panel` |
| Beams present under most of the perimeter and interior, bay aspect ratio (long span : short span) < ~2 | `two_way_beam_supported` |
| Beams present, bay aspect ratio ≥ ~2 | `one_way` |
| Steel framing beneath (cross-reference the framing elements' `frame_type` at this story), shallow overall depth, material name containing "deck"/"corrugated" | `composite_metal_deck` |
| Repeated close-spaced ribs/joists in one direction with a thin topping | `ribbed_waffle` (one-way) or `waffle` (two-way, ribs both directions) |
| Column at the story below doesn't land on a column at or above this slab, and doesn't land on a specific beam either (lands generally within the slab) | `transfer_slab` — also mirror this onto the source column's `transfer_flag` |
| Grid spacing pattern changes materially between the story below and the story above this slab (tower-over-podium condition) | `podium` |

Use the building's overall structural material as a prior, not just this slab in isolation: a building where most columns/framing classified `Steel` is far more likely to have `composite_metal_deck` floors than a cast RCC slab type, even if this particular slab's own signals are ambiguous.

## Footing type

IFC's footing/pile enums are more reliable than the wall ones — `IfcFootingTypeEnum` (`PAD_FOOTING`, `STRIP_FOOTING`, `PILE_CAP`, `CAISSON_FOUNDATION`) and the presence of `IfcPile` elements are decent ground truth when populated. Still cross-check against the geometric facts, because `PredefinedType` on foundation elements is frequently left `NOTDEFINED` in practice.

| Signal | Classification |
|---|---|
| `PredefinedType = PAD_FOOTING`, or: exactly one column/wall lands on this footing and no piles are nearby | `isolated` |
| Exactly two columns share one continuous footing polygon | `combined` |
| Two separate footing pads joined by a slender strap/beam element (not one continuous pad) | `strap` |
| One large footing polygon underlying many columns / a large fraction of the building footprint | `mat_raft` |
| `PredefinedType = PILE_CAP`, or one or more `IfcPile` elements cluster beneath this footing | `pile_cap` — this overrides the count-based rules above; a single-column footing sitting on piles is a pile cap, not an "isolated footing" in the shallow-foundation sense |
| `PredefinedType = STRIP_FOOTING`, or a long continuous footing running beneath a load-bearing/foundation wall rather than discrete columns | `strip` (recorded under wall-supported footings, not the column-footing list) |

**`foundation_system_summary`**: roll `isolated`/`combined`/`strap`/`mat_raft` up to `shallow`, and `pile_cap` up to `deep_pile`. Set `mixed_system_flag` when both appear in the same model — this is a real, common condition (a light canopy or stair core on isolated pads next to a piled main tower) but worth surfacing explicitly rather than burying it in a footing-by-footing list, since it changes how the geotechnical engineer needs to read the soil report (two different bearing strata may be in play).

## Framing role

| Signal | Points toward |
|---|---|
| IFC `PredefinedType` = `JOIST` | `secondary` |
| IFC `PredefinedType` = `SPANDREL` (perimeter/edge beam) | `primary` |
| IFC `PredefinedType` = `LINTEL` (opening header) | `secondary`, and usually minor — flag rather than treat as a real gravity path member |
| Name or object type text contains "girder" | Weak toward `primary` — **not** an IFC `PredefinedType` value in plain IFC4 (confirmed against the schema: `IfcBeamTypeEnum` = `BEAM, JOIST, HOLLOWCORE, LINTEL, SPANDREL, T_BEAM, USERDEFINED, NOTDEFINED`); it's purely an office-naming-convention signal |
| Endpoints land on column centerlines (within tolerance) at both ends | `primary` |
| Endpoints land on other beams (not columns) at both ends | `secondary` |
| Runs along a gridline directly | Weak toward `primary` |
| A column's `transfer_flag.lands_on` references this beam's id | `transfer` — definitional once the geometric match is made, not probabilistic |
| One end free (no connection within tolerance to any column, wall, or other beam) | `cantilever` |
| `IfcMember` with `PredefinedType = BRACE`, or a linear member whose axis is neither vertical nor horizontal (diagonal), especially where `frame_type = Steel` | `brace` |
| A beam terminating at a classified shear-wall end, running in-line with or perpendicular to it | `collector` (candidate only) — flag as a candidate; confirming it as a true collector needs the full lateral system laid out, which is `load-path`'s job, not this skill's |

## Openings

- Hosted in a wall already classified `shear` (primary or secondary) → flag `within_shear_wall`. This skill doesn't evaluate capacity impact, just surfaces the fact for the design skill.
- Hosted in a floor, sized above roughly 15–20% of its local bay/diaphragm-segment area, or repeating in the same footprint across multiple consecutive stories (a stair/elevator/mechanical shaft) → flag `diaphragm_discontinuity_candidate`.
- Hosted in a wall classified `retaining` → flag `unusual_for_retaining_wall — verify`. Openings in true retaining walls are rare; this is often a sign the wall was misclassified (it's actually an above-grade wall with a window) rather than that the opening itself is unusual.

## Confidence rubric

Applied uniformly across every classifier in `classify_elements.py`:

- **`high`** — at least one Strong signal present, and nothing contradicts it.
- **`medium`** — only Medium/Weak signals available, but they agree with each other.
- **`low`** — signals conflict, or nothing beyond a default/absent value is available.

Any `low`-confidence classification **must** also produce a `review.needs_review` entry — never let one pass through silently. `medium` classifications don't need a review entry by default, but add one anyway if two signals point in different directions even though a third breaks the tie (the tie-break is often right, but it's cheap to let the engineer see the disagreement rather than hide it).
