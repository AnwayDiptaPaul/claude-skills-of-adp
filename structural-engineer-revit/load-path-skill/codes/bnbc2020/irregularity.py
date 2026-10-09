"""
codes/bnbc2020/irregularity.py — BNBC 2020 (Part 6, Chapter 2, Sec 2.5.5.3,
2.5.5.6, Eq 6.2.44) structural irregularity definitions, thresholds, and the
overstrength/force-increase triggers tied to them.

SOURCE AND VERIFICATION: Sec 2.5.5.3 (Building irregularity) was read in
full, verbatim, from the same source as dynamic-load's seismic.py
(https://iisee.kenken.go.jp/worldlist/06_Bangladesh/Bangladesh_BNBC_Part6_
Chap_2.pdf) -- every threshold below (1.2/1.4 for torsion, 15% for
re-entrant corners, 50% for diaphragm discontinuity, 70/80/60/70% for soft
storey, 2x for mass irregularity, ">length" for in-plane discontinuity,
80/65% for weak storey) is transcribed directly from that text, not
recalled from general ASCE-7-family knowledge. Table 6.2.19 (structural
systems) was independently cross-checked against this same fetch and found
byte-for-byte identical to dynamic-load's own STRUCTURAL_SYSTEMS table --
recorded here as a confidence note on that fetch's reliability, not as
something this module re-derives.

ONE RECONSTRUCTION, FLAGGED HONESTLY: Eq 6.2.44 (torsional amplification
factor As) was mangled by extraction ("dmax/2/1.2*davg" with the exponent
position lost). Reconstructed as As = (dmax/(1.2*davg))^2, capped at 3.0 --
the standard ASCE-7-lineage shape this formula's own 1.2 factor and 3.0 cap
are drawn from. Verified numerically: As=1.0 exactly at dmax=1.2*davg (the
code's own irregularity threshold -- no amplification right at the boundary,
which is the physically sensible behavior), confirming the reconstruction
rather than assuming it.

WHAT THIS MODULE DOES NOT DO: classify a specific building. It holds the
verified thresholds and pure classifier functions only; the geometric
matching (does this wall continue below? what's the actual mass at each
story?) lives in scripts/trace_load_path.py, which is what calls these.

WHY FOUR OF TEN IRREGULARITY TYPES AREN'T IMPLEMENTED AS DATA HERE (see
SKILL.md's Known Limitations for the full accounting -- this module only
holds what a downstream geometric check COULD use):
  - Torsion irregularity needs actual storey displacements (dmax/davg) from
    a real analysis -- structural-analysis's output, not this pipeline
    stage's. is_torsional_irregularity() below takes displacements as
    arguments rather than computing them, so it's ready the moment that
    skill exists, but trace_load_path.py has nothing to pass it yet.
  - Soft storey and weak storey need relative storey STIFFNESS and STRENGTH
    respectively -- also structural-analysis/structural-design outputs.
    Same treatment: the classifier functions exist and take the ratios as
    plain arguments; nothing computes those ratios in this skill.
  - Vertical geometric irregularity (setbacks) references Fig 6.2.28(c)'s
    own setback dimensions, which weren't legible in this OCR pass --
    flagged as not transcribed, not guessed at.
"""

# ---------------------------------------------------------------------------
# Sec 2.5.5.3 -- Plan (horizontal) irregularities
# ---------------------------------------------------------------------------
def is_torsional_irregularity(delta_max, delta_avg):
    """Type I (plan). delta_max/delta_avg computed INCLUDING accidental
    torsion, at rigid floor diaphragms. Returns (is_irregular, is_extreme).
    Needs real storey displacements from an actual analysis -- this
    function is ready for structural-analysis to call, not something
    load-path computes itself (see module docstring)."""
    ratio = delta_max / delta_avg
    return (ratio > 1.2, ratio >= 1.4)


def torsional_amplification_factor(delta_max, delta_avg):
    """Eq 6.2.44 (reconstructed -- see module docstring): As =
    (delta_max/(1.2*delta_avg))^2, capped at 3.0. Only applies (per Sec
    2.5.7.6) when torsional irregularity exists at Seismic Design Category
    C or D -- caller should gate this on is_torsional_irregularity()
    returning True and the project's SDC, not apply it unconditionally."""
    return min((delta_max / (1.2 * delta_avg)) ** 2, 3.0)


def is_reentrant_corner_irregularity(projection_a_m, projection_b_m, plan_dimension_m):
    """Type II (plan). Both projections beyond a re-entrant corner exceed
    15% of the plan dimension in that direction. Needs a floor plan outline
    (to identify the re-entrant corner and measure the two projections) --
    revit-structure-recognition doesn't capture floor plan geometry today
    (only thickness/slab_type/diaphragm_class), so nothing in this skill
    suite can call this yet. Kept here, ready, rather than omitted, so the
    gap is visible at the classifier level, not just in a comment."""
    threshold = 0.15 * plan_dimension_m
    return projection_a_m > threshold and projection_b_m > threshold


def is_diaphragm_discontinuity(opening_area_m2, gross_diaphragm_area_m2,
                                stiffness_change_pct=None):
    """Type III (plan). Either: cutout/opening area > 50% of the gross
    enclosed diaphragm area, OR effective diaphragm stiffness changes by
    more than 50% story to story. The first branch needs floor plan area --
    not captured by revit-structure-recognition today (see module
    docstring); the second needs diaphragm stiffness, which needs an actual
    analysis. Kept ready for both, computed by neither today."""
    area_trigger = gross_diaphragm_area_m2 > 0 and \
        (opening_area_m2 / gross_diaphragm_area_m2) > 0.50
    stiffness_trigger = stiffness_change_pct is not None and abs(stiffness_change_pct) > 50.0
    return area_trigger or stiffness_trigger


def is_out_of_plane_offset(continues_on_same_plane):
    """Type IV (plan). BNBC's own wording ("discontinuities in a lateral
    force resistance path, SUCH AS out-of-plane offsets") is an existence
    check, not a numeric threshold like its vertical Type IV counterpart --
    a lateral element that doesn't continue on the same plane as the one
    above/below it qualifies. continues_on_same_plane is a plain bool the
    caller determines geometrically (matching axis/gridline across
    stories) -- this function only encodes the code's own logic that ANY
    such discontinuity counts, not a magnitude test."""
    return not continues_on_same_plane


def is_non_parallel_system(element_axis_angles_deg, tolerance_deg=1.0):
    """Type V (plan). The vertical lateral-force-resisting elements aren't
    parallel to or symmetric about the building's major orthogonal axes.
    element_axis_angles_deg: list of each lateral element's in-plan axis
    angle (degrees, any consistent reference). Flags True if the angles
    don't cluster into two groups 90 degrees apart within tolerance --
    a simplified check (true non-parallel/non-symmetric detection is a
    genuine engineering judgment call for oddly-shaped buildings; this
    catches the common case of a lateral element at a stray angle)."""
    if len(element_axis_angles_deg) < 2:
        return False
    normalized = sorted(a % 90.0 for a in element_axis_angles_deg)
    spread = normalized[-1] - normalized[0]
    return spread > tolerance_deg and (90.0 - spread) > tolerance_deg


# ---------------------------------------------------------------------------
# Sec 2.5.5.3 -- Vertical irregularities
# ---------------------------------------------------------------------------
def is_soft_storey(this_storey_stiffness, storey_above_stiffness,
                    avg_stiffness_3_above=None):
    """Type I (vertical). Lateral stiffness < 70% of the storey above, OR
    < 80% of the average of the 3 storeys above. Returns (is_soft,
    is_extreme) where extreme is <60%/<70%. Needs relative storey
    stiffness -- structural-analysis's output, not computed here."""
    below_70 = this_storey_stiffness < 0.70 * storey_above_stiffness
    below_60 = this_storey_stiffness < 0.60 * storey_above_stiffness
    if avg_stiffness_3_above is not None:
        below_80avg = this_storey_stiffness < 0.80 * avg_stiffness_3_above
        below_70avg = this_storey_stiffness < 0.70 * avg_stiffness_3_above
        return (below_70 or below_80avg, below_60 or below_70avg)
    return (below_70, below_60)


def is_mass_irregularity(this_storey_weight_kn, adjacent_storey_weights_kn, is_roof=False):
    """Type II (vertical). Seismic weight of any storey > 2x that of an
    ADJACENT storey (need not be considered for roofs). Fully computable
    today from dynamic-load's own per-story seismic weights -- no
    additional data needed."""
    if is_roof:
        return False
    return any(this_storey_weight_kn > 2.0 * w for w in adjacent_storey_weights_kn if w > 0)


def is_vertical_in_plane_discontinuity(in_plane_offset_mm, element_length_mm):
    """Type IV (vertical). In-plane offset of a lateral force resisting
    element greater than the length of that element. Fully computable from
    geometry -- offset is a story-to-story centerline/gridline shift ALONG
    the element's own axis direction (in-plane), not perpendicular to it
    (that's the plan Type IV check, is_out_of_plane_offset())."""
    return in_plane_offset_mm > element_length_mm


def is_weak_storey(this_storey_strength_kn, storey_above_strength_kn):
    """Type V (vertical). Storey lateral strength (total strength of all
    seismic-force-resisting elements sharing the storey shear in the
    direction considered) < 80% of the storey above. Returns (is_weak,
    is_extreme) where extreme is <65%. Needs storey strength/capacity --
    structural-design's output, not computed here."""
    below_80 = this_storey_strength_kn < 0.80 * storey_above_strength_kn
    below_65 = this_storey_strength_kn < 0.65 * storey_above_strength_kn
    return (below_80, below_65)


# ---------------------------------------------------------------------------
# Sec 2.5.5.6 -- Overstrength and force-increase provisions tied to specific
# irregularity types (cross-referencing Table 6.1.4/6.1.5's Type numbering,
# which matches the (i)-(v) ordering used above: vertical Type IV = in-plane
# discontinuity, plan Type IV = out-of-plane offset).
# ---------------------------------------------------------------------------
def requires_overstrength_design(supports_discontinuous_element,
                                  discontinuity_type):
    """Sec 2.5.5.6, first bullet: columns/beams/trusses/slabs supporting a
    discontinuous wall or frame (vertical irregularity Type IV -- in-plane
    discontinuity -- or plan/horizontal irregularity Type IV -- out-of-plane
    offset) must have design strength for the maximum axial force
    developable under Sec 2.5.13.4's overstrength load combinations
    (Omega0-amplified). discontinuity_type: 'vertical_type_iv' or
    'plan_type_iv'. NOTE: Sec 2.5.13.4 itself (the exact overstrength
    combination formula) isn't transcribed in dynamic-load's seismic.py yet
    -- see that module's KNOWN GAPS -- so this function tells you an
    element NEEDS that treatment, not the factored force itself."""
    return supports_discontinuous_element and discontinuity_type in ("vertical_type_iv", "plan_type_iv")


def requires_25pct_force_increase(seismic_design_category, has_plan_irregularity_i_ii_iii_iv,
                                   has_vertical_irregularity_iv):
    """Sec 2.5.5.6, second bullet: for Seismic Design Category D (the code
    text says 'D through E'; BNBC's own Table 6.2.18 only assigns B/C/D, so
    'E' appears to be inherited phrasing from this section's ASCE lineage --
    treated here as applying at SDC D, the highest category BNBC actually
    assigns), diaphragm-to-vertical-element and collector connections need
    a 25% design force increase when ANY of plan irregularity Type I.a,
    I.b, II, III, or IV, or vertical irregularity Type IV, is present --
    UNLESS designed instead for the full overstrength combination (Sec
    2.5.13.4), in which case this increase doesn't stack with that."""
    return seismic_design_category.strip().upper() == "D" and \
        (has_plan_irregularity_i_ii_iii_iv or has_vertical_irregularity_iv)


def requires_overstrength_for_collectors(seismic_design_category):
    """Sec 2.5.5.6, third bullet: collector elements, splices, and their
    connections to resisting elements need Sec 2.5.13.4's overstrength load
    combination at Seismic Design Category C or D -- unconditionally,
    regardless of whether an irregularity is present (unlike the 25%
    increase rule above, which is irregularity-triggered)."""
    return seismic_design_category.strip().upper() in ("C", "D")
