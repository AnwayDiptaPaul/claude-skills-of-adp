"""
codes/load_combinations.py — BNBC 2020 Sec 2.7 (Strength Design load
combinations) and Sec 2.5.13 (Earthquake load effect, E).

SOURCE AND VERIFICATION -- A DIFFERENT STANDARD THAN THE REST OF THIS
PIPELINE, READ THIS FIRST: every other verified code module in this
pipeline (dynamic-load's seismic.py/wind.py, load-path's irregularity.py,
this skill's own concrete_design.py) was checked against the primary BNBC
PDF text directly. Sec 2.7 and Sec 2.5.13 were NOT independently found in
that primary text within this pipeline's own research (dynamic-load's
seismic.py's own KNOWN GAPS already flagged Sec 2.5.13 as unread for
exactly this reason). What's below is transcribed from a secondary source
(a Bangladeshi structural-engineering blog post specifically about BNBC
2020's Sec 2.7, citing exact section numbers -- socebd.com/bnbc-2020-load-
combination) that is internally consistent, cites specific sub-section
numbers matching this chapter's own numbering pattern, and independently
corroborates something this pipeline had already inferred from the
response-spectrum equation's own notation: that BIBC's seismic load
provisions are Eurocode-8-derived, not ASCE-7-derived (the source
explicitly states this). Treated with real but SECOND-TIER confidence --
one step below every other verified number in this pipeline. Confirm
against a primary copy of Sec 2.7/2.5.13 before this matters for a
stamped drawing, the same way dynamic-load's wind speed-by-location gap
asks for before IT matters.

E, Eh, Ev (Sec 2.5.13, per that source): E = Eh + Ev (additive) or
E = Eh - Ev (counteractive, whichever governs); Eh = the horizontal
seismic load effect (dynamic-load's own base shear V, Sec 2.5.7/2.5.9's
output -- already computed by that skill, not re-derived here); Ev = the
vertical seismic load effect = 0.50*ah*D, where ah = (2/3)*Z*S (the same
Z and S dynamic-load's seismic.py already carries) and D is the dead load
effect being combined. NOTABLY DIFFERENT FROM ASCE 7's Ev=0.2*SDS*D and
absence of a redundancy factor rho matches what dynamic-load's seismic.py
already flagged as likely (BNBC has no rho in its own Sec 2.1.4 symbol
list) -- this secondary source's Ev formula is consistent with, not
contradicting, that earlier reasoning.
"""

STRENGTH_PHI_NOTE = "Strength (ultimate) design combinations -- Sec 2.7.3.2, secondary-sourced (see module docstring)"

# Site soil factor S, by site class -- a small, deliberately-duplicated
# copy of dynamic-load's own codes/bnbc2020/seismic.py SITE_CLASS_PARAMETERS
# table (Table 6.2.16, verified there against the primary BNBC PDF text).
# Duplicated rather than imported for the same cross-skill-package-
# independence reason documented throughout this pipeline since dynamic-
# load's own site_seismic_wind_input_format.md -- skills communicate via
# structural_model.json, not by importing each other's code. Only the S
# column is needed here (Ev's own formula, not the full spectrum shape).
SITE_CLASS_S = {"SA": 1.00, "SB": 1.20, "SC": 1.15, "SD": 1.35, "SE": 1.40}


def vertical_seismic_effect_kn(Z, S, dead_load_effect_kn):
    """Ev = 0.50*ah*D, ah=(2/3)*Z*S (Sec 2.5.13.2 per the secondary
    source). Z and S are the same values dynamic-load's seismic.py already
    computed/holds (zone coefficient, site soil factor) -- pass them
    through rather than re-deriving."""
    ah = (2.0 / 3.0) * Z * S
    return 0.50 * ah * dead_load_effect_kn


def seismic_load_effect_kn(Eh_kn, Z, S, dead_load_effect_kn, counteracting=False):
    """E = Eh +/- Ev (Sec 2.5.13.1). Use counteracting=True where dead
    load effect and seismic effect act in opposing senses (e.g. checking
    net uplift/overturning) -- the code requires checking both senses,
    not just the additive one, for members where it matters."""
    Ev = vertical_seismic_effect_kn(Z, S, dead_load_effect_kn)
    return Eh_kn - Ev if counteracting else Eh_kn + Ev


def strength_design_combinations(D, L, Lr, W, E, H=0.0):
    """Sec 2.7.3.2's eight strength-design (USD) combinations, matching
    the widely-used ASCE-7-2005-vintage pattern this source states BNBC's
    own Sec 2.7 follows (D=dead, L=live, Lr=roof live, W=wind, E=seismic
    per seismic_load_effect_kn() above, H=lateral earth pressure effect,
    0.0 if not applicable). Returns {'combo_name': factored_value}, one
    entry per combination, for whatever single load-effect quantity D/L/
    Lr/W/E/H each represents (axial, moment, or shear -- call this
    function once per quantity, not once per member, since D/L/W/E don't
    combine linearly across different effect types)."""
    return {
        "1.4D": 1.4 * D,
        "1.2D+1.6L+0.5Lr": 1.2 * D + 1.6 * L + 0.5 * Lr,
        "1.2D+1.6Lr+1.0L": 1.2 * D + 1.6 * Lr + 1.0 * L,
        "1.2D+1.6Lr+0.8W": 1.2 * D + 1.6 * Lr + 0.8 * W,
        "1.2D+1.6W+1.0L+0.5Lr": 1.2 * D + 1.6 * W + 1.0 * L + 0.5 * Lr,
        "1.2D+1.0E+1.0L": 1.2 * D + 1.0 * E + 1.0 * L,
        "0.9D+1.6W+1.6H": 0.9 * D + 1.6 * W + 1.6 * H,
        "0.9D+1.0E+1.6H": 0.9 * D + 1.0 * E + 1.6 * H,
    }


def governing_combination(D, L, Lr, W, E, H=0.0):
    """Returns (combo_name, value) for whichever of
    strength_design_combinations()'s results has the largest ABSOLUTE
    value -- the usual 'governing case' for sizing a section. Doesn't
    distinguish sign (a large negative moment governs tension steel on the
    opposite face from a large positive one) -- the caller must still
    check sign/direction, this just picks the magnitude that governs."""
    combos = strength_design_combinations(D, L, Lr, W, E, H)
    name = max(combos, key=lambda k: abs(combos[k]))
    return name, combos[name]
