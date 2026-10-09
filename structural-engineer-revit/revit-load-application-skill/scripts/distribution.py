"""
distribution.py — tributary-area gravity load distribution: slab -> beams,
slab -> columns (flat plate/slab), and beam -> beam (secondary onto primary).

This is standard practice for regular framed buildings, not a simplification
to be embarrassed about — tributary-area distribution (refined by the
45-degree/yield-line method for two-way panels below) is the ordinary,
code-endorsed method for gravity loads on a regular grid. It's lateral load
distribution where naive tributary area is the wrong tool (stiffness governs
there) — see SKILL.md for why gravity and lateral are treated differently.
Nothing here is stiffness-based, deliberately.

THE TWO-WAY FORMULAS BELOW WERE DERIVED AND VERIFIED SYMBOLICALLY (sympy),
not recalled — see the derivation and test transcript this file was built
from for the full working, including the sanity checks that caught a real
domain-of-validity issue (the formulas only hold for aspect ratio <= 2;
beyond that the model gives a wrong physical answer if applied blindly,
which the code below guards against explicitly rather than silently).

ONE MORE VERIFIED, NON-OBVIOUS PROPERTY WORTH KNOWING BEFORE IT LOOKS LIKE A
BUG: classify_and_distribute_panel() has a genuine discontinuity right at the
one-way/two-way cutoff (aspect ratio == 2). Just inside the two-way regime,
the short-edge beams still carry a triangular share (reaction-equivalent
w*a/4, constant, independent of aspect ratio); just past the cutoff, that
share vanishes and gets picked up entirely by the long-edge beams. Total load
is conserved exactly across the jump (verified: the long-edge increase equals
precisely half the short-edge beams' vanishing share, algebraically, not
approximately) — but the per-beam values are NOT continuous in aspect ratio.
This is an accepted property of switching between two different idealized
hand-calculation methods at a code-defined cutoff, the same way BNBC's own
one-way/two-way classification is a discrete switch, not a blend. It is not
a defect in either formula.
"""

ONE_WAY_ASPECT_RATIO_THRESHOLD = 2.0  # standard two-way/one-way cutoff (ACI-aligned, and consistent
                                        # with BNBC's own one-way-slab tributary-area limitation in
                                        # Sec 2.3.13.5, which caps a one-way slab's tributary width at
                                        # 1.5x its span — a related but distinct provision, for live
                                        # load reduction rather than distribution, worth knowing about
                                        # even though it isn't applied directly here)


def triangular_udl(w_kn_m2, short_span_m):
    """Load on a two-way panel's SHORT-edge beam (the beam whose own length
    equals the panel's short span) — a triangular distribution peaking at
    midspan. Returns (reaction_equivalent_kn_m, moment_equivalent_kn_m):
    use reaction_equivalent for total load / column reactions / shear,
    moment_equivalent for flexural beam design (usually the governing one)."""
    a = short_span_m
    return {
        "shape": "triangular",
        "peak_kn_m": w_kn_m2 * a / 2,
        "reaction_equivalent_kn_m": w_kn_m2 * a / 4,
        "moment_equivalent_kn_m": w_kn_m2 * a / 3,
        "total_load_kn": w_kn_m2 * a * a / 4,
    }


def trapezoidal_udl(w_kn_m2, short_span_m, aspect_ratio):
    """Load on a two-way panel's LONG-edge beam (own length = the panel's
    long span) — a trapezoidal distribution (ramps up, flat plateau, ramps
    down). aspect_ratio = long_span / short_span, valid for 1 <= m <= 2 —
    see module docstring; classify_and_distribute_panel() enforces this,
    call this directly only if you've already confirmed the panel is
    two-way."""
    m = aspect_ratio
    if not (1.0 <= m <= ONE_WAY_ASPECT_RATIO_THRESHOLD + 1e-9):
        raise ValueError(
            f"trapezoidal_udl() is only valid for 1 <= aspect_ratio <= {ONE_WAY_ASPECT_RATIO_THRESHOLD} "
            f"(got {m}). Beyond that the 45-degree construction no longer approximates real two-way "
            f"plate behaviour — use one_way_udl() instead, which is what "
            f"classify_and_distribute_panel() does automatically."
        )
    a = short_span_m
    return {
        "shape": "trapezoidal",
        "peak_kn_m": w_kn_m2 * a / 2,
        "reaction_equivalent_kn_m": w_kn_m2 * a * (2 * m - 1) / (4 * m),
        "moment_equivalent_kn_m": w_kn_m2 * a * (3 * m * m - 1) / (6 * m * m),
        "total_load_kn": w_kn_m2 * a * a * (2 * m - 1) / 4,
    }


def one_way_udl(w_kn_m2, span_m):
    """Simple one-way slab reaction: half the span's tributary width on each
    supporting beam. Both reaction- and moment-equivalent are the same value
    here since the distribution genuinely is uniform, not an approximation
    of something else."""
    value = w_kn_m2 * span_m / 2
    return {"shape": "uniform", "peak_kn_m": value, "reaction_equivalent_kn_m": value,
            "moment_equivalent_kn_m": value, "total_load_kn": value * span_m}


def classify_and_distribute_panel(w_kn_m2, dim_a_m, dim_b_m):
    """Full panel distribution: figures out which dimension is the short
    span, classifies one-way vs two-way at the standard aspect-ratio-2
    cutoff, and returns the load for all four edge beams.

    Returns:
        {
          "short_span_m", "long_span_m", "aspect_ratio", "classification": "one_way"|"two_way",
          "short_edge_beams": {...udl dict...},   # the two beams of length = short_span
          "long_edge_beams": {...udl dict...},    # the two beams of length = long_span
        }
    """
    short_span_m, long_span_m = (dim_a_m, dim_b_m) if dim_a_m <= dim_b_m else (dim_b_m, dim_a_m)
    if short_span_m <= 0 or long_span_m <= 0:
        raise ValueError(f"Panel dimensions must be positive, got {dim_a_m} x {dim_b_m}")
    m = long_span_m / short_span_m

    if m > ONE_WAY_ASPECT_RATIO_THRESHOLD:
        # One-way: all load to the long-edge beams (the ones the slab actually
        # spans onto); short-edge beams get none from this panel directly.
        long_result = one_way_udl(w_kn_m2, short_span_m)
        short_result = {"shape": "none", "peak_kn_m": 0.0, "reaction_equivalent_kn_m": 0.0,
                         "moment_equivalent_kn_m": 0.0, "total_load_kn": 0.0}
        classification = "one_way"
    else:
        short_result = triangular_udl(w_kn_m2, short_span_m)
        long_result = trapezoidal_udl(w_kn_m2, short_span_m, m)
        classification = "two_way"

    return {
        "short_span_m": short_span_m, "long_span_m": long_span_m, "aspect_ratio": m,
        "classification": classification,
        "short_edge_beams": short_result,   # two beams, each of length short_span_m
        "long_edge_beams": long_result,     # two beams, each of length long_span_m
    }


def column_tributary_area_m2(dist_left_m, dist_right_m, dist_up_m, dist_down_m):
    """Rectangular tributary area for a column (flat plate/slab, or as a
    cross-check for a beam-framed column's accumulated reaction), from the
    distance to the nearest neighbouring column/gridline in each of the four
    plan directions. Pass 0 for a direction with no neighbour (true building
    edge, no cantilever) — do NOT pass None; the caller is expected to have
    already decided whether a cantilever overhang applies and included it in
    the distance, since that's a modeling judgment this function shouldn't
    guess at.
    """
    for name, d in (("left", dist_left_m), ("right", dist_right_m), ("up", dist_up_m), ("down", dist_down_m)):
        if d < 0:
            raise ValueError(f"dist_{name}_m must be >= 0, got {d}")
    trib_width_x = dist_left_m / 2 + dist_right_m / 2
    trib_width_y = dist_up_m / 2 + dist_down_m / 2
    return trib_width_x * trib_width_y
