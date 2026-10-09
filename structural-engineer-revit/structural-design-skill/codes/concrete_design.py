"""
codes/concrete_design.py — BNBC 2020 (Part 6, Chapter 6, "Strength Design of
Reinforced Concrete Structures") flexural, shear, and column axial-moment
design provisions.

SOURCE AND VERIFICATION: read in full, verbatim, from
https://law.resource.org/pub/bd/bnbc.2012/gov.bd.bnbc.2012.06.06.pdf (the
same law.resource.org source family as dynamic-load's wind.py, under a
"bnbc.2012" path -- same provenance caveat as that module: likely an
earlier numbered draft cycle, treated with "verify before stamped use"
caution). Every equation number, coefficient, and limit below is
transcribed directly from that text -- Sec 6.1.7 (Ec=4700*sqrt(fck),
Es=200000 MPa) independently CONFIRMS the values structural-analysis's
codes/materials.py used before this chapter had been read at all; that
module's "not yet BNBC-verified" caveat on Ec can be removed on the
strength of this fetch.

WHAT THIS MODULE DELIBERATELY DOES NOT COVER (see SKILL.md's Known
Limitations for the full accounting) -- flagged here at the source, not
just in the skill's own docs:
  - Doubly-reinforced beam design (Sec 6.3.15.1(b)) -- singly-reinforced
    rectangular beams only.
  - T-beam design (Sec 6.3.15.2) -- every beam is designed as rectangular,
    even where a real slab flange would make it a T-beam. Conservative for
    positive moment capacity (ignores flange compression contribution),
    NOT conservative for negative moment / when the flange would actually
    be in tension -- a real limitation, not a safe-side simplification in
    every case.
  - Torsion (Sec 6.4.4) -- not designed for at all.
  - Column slenderness / moment magnification (Sec 6.3.10) -- this module
    assumes SHORT columns throughout. is_slenderness_negligible() is
    provided so a caller can at least CHECK the applicability condition,
    but nothing here applies Sec 6.3.10's magnification if it fails.
  - Biaxial column bending -- Mux and Muy are checked independently
    against their own uniaxial capacity, not combined via a true biaxial
    interaction surface (e.g. Bresler's method, which BNBC's Chapter 6
    doesn't itself specify a formula for either).
  - Spiral columns -- tied columns only.
  - Seismic detailing (Chapter 8, Sec 8.3: confinement, hoop spacing,
    strong-column-weak-beam ratios) -- not implemented. This is a real,
    significant gap for anything in Seismic Design Category C or D.
  - Development length, splices, bar spacing/cover detailing (Sec 8.1-8.2)
    -- not addressed; this module sizes required steel AREA only.
"""
import math

ES_MPA = 200_000.0  # Sec 6.1.7.2


def concrete_elastic_modulus_mpa(fck_mpa):
    """Sec 6.1.7.1, normalweight concrete: Ec = 4700*sqrt(fck). NOW
    CONFIRMED against BNBC's own text (structural-analysis's codes/
    materials.py used this same formula before this chapter had been
    read, flagged there as an unverified ACI default -- it wasn't wrong,
    just not yet checked against BNBC's own words)."""
    return 4700.0 * fck_mpa ** 0.5


def beta1(fck_mpa):
    """Eq 6.3.1 / Sec 6.3.2.7.3: beta1=0.85 for fck<=28 MPa, reduced
    linearly by 0.05 per 7 MPa above 28, floored at 0.65. Verified
    self-consistent: beta1(28)=0.85 exactly, beta1(56)=0.65 exactly (4
    steps of 7 MPa x 0.05 = 0.20 reduction over that range)."""
    b = 0.85 - 0.007143 * (fck_mpa - 28.0)
    return max(0.65, min(0.85, b))


def compression_controlled_strain_limit(fy_mpa):
    """Sec 6.3.3.3: 0.002 for Grade 420 reinforcement (the code's own
    stated shortcut); for other grades, fy/Es rounded to 4 significant
    digits (the code's own worked example: Grade 500 -> 0.0025)."""
    if abs(fy_mpa - 420.0) < 1e-6:
        return 0.002
    return round(fy_mpa / ES_MPA, 4)


def strength_reduction_factor(net_tensile_strain_et, fy_mpa, spiral=False):
    """Sec 6.2.3.2: phi=0.90 for tension-controlled (et>=0.005); phi=0.65
    (tied) or 0.75 (spiral) for compression-controlled (et <= the
    compression-controlled strain limit); linear interpolation between,
    rounded to 2 decimal places (the code's own permitted rounding)."""
    et_cc = compression_controlled_strain_limit(fy_mpa)
    phi_cc = 0.75 if spiral else 0.65
    if net_tensile_strain_et >= 0.005:
        return 0.90
    if net_tensile_strain_et <= et_cc:
        return phi_cc
    frac = (net_tensile_strain_et - et_cc) / (0.005 - et_cc)
    return round(phi_cc + frac * (0.90 - phi_cc), 2)


# ---------------------------------------------------------------------------
# Sec 6.3.15.1(a) -- Singly-reinforced rectangular beam flexural design
# ---------------------------------------------------------------------------
def max_reinforcement_ratio(fck_mpa, fy_mpa):
    """Eq 6.3.27: rho_max = 0.85*beta1*(fck/fy)*(eu/(eu+0.004)), eu=0.003.
    Net tensile strain floor of 0.004 for nonprestressed flexural members
    (Sec 6.3.3.5) is baked into this formula's own 0.004 term."""
    eu = 0.003
    return 0.85 * beta1(fck_mpa) * (fck_mpa / fy_mpa) * (eu / (eu + 0.004))


def min_flexural_reinforcement_area(fck_mpa, fy_mpa, bw_mm, d_mm):
    """Eq 6.3.4: As,min = 0.25*sqrt(fck)/fy * bw*d, not less than
    1.4*bw*d/fy (Sec 6.3.5.1)."""
    a = 0.25 * fck_mpa ** 0.5 / fy_mpa * bw_mm * d_mm
    b = 1.4 * bw_mm * d_mm / fy_mpa
    return max(a, b)


def design_singly_reinforced_beam(Mu_knm, fck_mpa, fy_mpa, b_mm, d_mm, needs_review, member_id=""):
    """Sec 6.3.15.1(a). Mu in kN.m (converted to N.mm internally, matching
    this chapter's own stated N/mm/MPa unit convention -- see module
    docstring). Iterates As/a per the code's own suggested procedure
    (estimate a, solve As, refine a, repeat) rather than the closed-form
    quadratic, since that's the method the code text itself describes.
    Returns a dict with As_required_mm2, phi, and the governing check, or
    a dict with 'reason' if Mu exceeds what this section can carry singly
    reinforced (i.e. a doubly-reinforced beam or a deeper section is
    needed -- Sec 6.3.15.1(b), not implemented here)."""
    Mu_nmm = Mu_knm * 1e6
    if Mu_nmm <= 0:
        return {"As_required_mm2": 0.0, "phi": 0.90, "note": "Mu <= 0 -- no tension reinforcement required by flexure"}

    phi = 0.90  # preliminary, per the code's own suggested starting point
    a = d_mm * 0.1  # initial guess
    for _ in range(50):
        Mn_nmm = Mu_nmm / phi
        As = Mn_nmm / (fy_mpa * (d_mm - a / 2.0))
        a_new = As * fy_mpa / (0.85 * fck_mpa * b_mm)
        if abs(a_new - a) < 1e-6:
            a = a_new
            break
        a = a_new

    rho = As / (b_mm * d_mm)
    rho_max = max_reinforcement_ratio(fck_mpa, fy_mpa)
    if rho > rho_max:
        needs_review.append({"element": member_id, "reason":
            f"required reinforcement ratio {rho:.4f} exceeds rho_max={rho_max:.4f} for a "
            f"singly-reinforced section -- needs compression steel (Sec 6.3.15.1(b), not "
            f"implemented) or a larger/deeper section. As NOT finalized."})
        return {"reason": "rho exceeds rho_max -- doubly-reinforced beam needed, not designed"}

    # Refine phi from the actual c/dt (Sec 6.3.15.1(a)'s own closing instruction)
    c = a / beta1(fck_mpa)
    et = 0.003 * (d_mm - c) / c if c > 0 else 0.005
    phi_final = strength_reduction_factor(et, fy_mpa)

    As_min = min_flexural_reinforcement_area(fck_mpa, fy_mpa, b_mm, d_mm)
    governed_by_min = As < As_min
    As_final = max(As, As_min)

    return {"As_required_mm2": round(As_final, 1), "As_calculated_mm2": round(As, 1),
            "As_min_mm2": round(As_min, 1), "governed_by_minimum": governed_by_min,
            "a_mm": round(a, 2), "c_mm": round(c, 2), "net_tensile_strain_et": round(et, 5),
            "phi": phi_final, "rho": round(rho, 5), "rho_max": round(rho_max, 5)}


# ---------------------------------------------------------------------------
# Sec 6.4 -- Beam shear design (simplified Vc method, Sec 6.4.2.1.1)
# ---------------------------------------------------------------------------
SHEAR_PHI = 0.75  # Sec 6.2.3.2.4


def concrete_shear_capacity_kn(fck_mpa, bw_mm, d_mm, lambda_factor=1.0):
    """Eq 6.4.3 (simplified method, members subject to shear and flexure
    only, no significant axial load): Vc = 0.17*lambda*sqrt(fck)*bw*d, N.
    lambda=1.0 for normalweight concrete (Sec 6.1.8.1)."""
    Vc_n = 0.17 * lambda_factor * fck_mpa ** 0.5 * bw_mm * d_mm
    return Vc_n / 1000.0  # N -> kN


def design_shear_reinforcement(Vu_kn, fck_mpa, fy_mpa, bw_mm, d_mm, needs_review, member_id=""):
    """Sec 6.4.1-6.4.3. Returns required Av/s (mm2/mm) and a max spacing,
    or a dict with 'reason' if Vu exceeds what Vs_max (Eq 6.4.3.6.9) can
    provide with the concrete's own contribution -- section is too small."""
    Vc = concrete_shear_capacity_kn(fck_mpa, bw_mm, d_mm)
    phi_Vc = SHEAR_PHI * Vc
    Vs_max = 0.66 * fck_mpa ** 0.5 * bw_mm * d_mm / 1000.0  # Eq 6.4.3.6.9, N->kN
    phi_Vn_max = SHEAR_PHI * (Vc + Vs_max)

    if Vu_kn > phi_Vn_max:
        needs_review.append({"element": member_id, "reason":
            f"Vu={Vu_kn:.1f}kN exceeds phi*(Vc+Vs,max)={phi_Vn_max:.1f}kN -- section is too "
            f"small for shear regardless of stirrup quantity (Sec 6.4.3.6.9). Not designed; "
            f"needs a larger section."})
        return {"reason": "Vu exceeds maximum shear capacity for this section size"}

    if Vu_kn <= 0.5 * phi_Vc:
        return {"stirrups_required": False, "phi_Vc_kn": round(phi_Vc, 2),
                "note": "Vu <= 0.5*phi*Vc -- no shear reinforcement required by Sec 6.4.3.5.1 "
                        "(this function does not check the (a)-(f) exemption list itself; "
                        "minimum shear reinforcement may still be required by member type)"}

    Av_min_over_s = max(0.062 * fck_mpa ** 0.5 * bw_mm / fy_mpa, 0.35 * bw_mm / fy_mpa)  # Eq 6.4.9, mm2/mm

    if Vu_kn <= phi_Vc:
        Av_over_s = Av_min_over_s
    else:
        Vs_required_n = (Vu_kn / SHEAR_PHI - Vc) * 1000.0
        Av_over_s = max(Vs_required_n / (fy_mpa * d_mm), Av_min_over_s)  # Eq 6.4.10 rearranged

    max_spacing_mm = d_mm / 2.0 if Vu_kn / SHEAR_PHI - Vc <= 0.33 * fck_mpa ** 0.5 * bw_mm * d_mm / 1000.0 \
        else d_mm / 4.0  # Sec 6.4.3.4.1/6.4.3.4.3 (halved when Vs > 0.33*sqrt(fck)*bw*d)
    max_spacing_mm = min(max_spacing_mm, 600.0)

    return {"stirrups_required": True, "phi_Vc_kn": round(phi_Vc, 2),
            "Av_over_s_mm2_per_mm": round(Av_over_s, 5), "max_spacing_mm": round(max_spacing_mm, 1)}


# ---------------------------------------------------------------------------
# Sec 6.3.3.6, 6.3.9 -- Tied rectangular column: capacity limits and a
# uniaxial P-M interaction diagram (numerical, strain-compatibility based
# -- Sec 6.3.2's own design assumptions, not a separate formula the code
# gives directly; the code specifies the ASSUMPTIONS, this function applies
# them the way a hand or spreadsheet interaction-diagram construction would).
# ---------------------------------------------------------------------------
def max_axial_capacity_kn(fck_mpa, fy_mpa, Ag_mm2, Ast_mm2, spiral=False):
    """Eq 6.3.2 (spiral, 0.85 factor) or Eq 6.3.3 (tied, 0.80 factor):
    Pn,max = factor*phi*[0.85*fck*(Ag-Ast) + fy*Ast]. Returns phi*Pn,max
    directly (already includes phi) since this is meant as the design
    envelope's own cap, not a bare nominal value."""
    phi = 0.75 if spiral else 0.65  # Sec 6.2.3.2.2, compression-controlled tied/spiral
    factor = 0.85 if spiral else 0.80
    Pn = 0.85 * fck_mpa * (Ag_mm2 - Ast_mm2) + fy_mpa * Ast_mm2
    return factor * phi * Pn / 1000.0  # N -> kN


def check_longitudinal_reinforcement_ratio(Ast_mm2, Ag_mm2, needs_review, member_id=""):
    """Sec 6.3.9.1: 0.01*Ag <= Ast <= 0.06*Ag; practical guidance (not a
    hard limit) to keep Ast <= 0.04*Ag to avoid placing/compaction
    difficulty. Returns True/False for the hard 0.01-0.06 limit; the 0.04
    guidance is flagged, not enforced."""
    rho_g = Ast_mm2 / Ag_mm2
    if rho_g < 0.01 or rho_g > 0.06:
        needs_review.append({"element": member_id, "reason":
            f"longitudinal reinforcement ratio {rho_g:.4f} outside Sec 6.3.9.1's 0.01-0.06 "
            f"hard limit"})
        return False
    if rho_g > 0.04:
        needs_review.append({"element": member_id, "reason":
            f"longitudinal reinforcement ratio {rho_g:.4f} exceeds 0.04 -- permitted by Sec "
            f"6.3.9.1 but flagged there as needing to be 'absolutely essential' due to "
            f"placing/compaction difficulty"})
    return True


def is_slenderness_negligible(k, lu_mm, r_mm, M1_over_M2=None, braced=True):
    """Sec 6.3.10.1: slenderness may be neglected if k*lu/r <= 22
    (unbraced) or <= 34-12*(M1/M2) <= 40 (braced). Returns True/False --
    if False, Sec 6.3.10's moment magnification procedure applies and is
    NOT implemented by this module (see module docstring); the caller
    must not proceed to a short-column P-M check without addressing that."""
    ratio = k * lu_mm / r_mm
    if not braced:
        return ratio <= 22
    limit = 34 - 12 * (M1_over_M2 if M1_over_M2 is not None else 0)
    return ratio <= min(limit, 40)


def pm_interaction_point(c_mm, b_mm, h_mm, fck_mpa, fy_mpa, d_prime_mm, Ast_total_mm2):
    """One (Pn, Mn) point on the uniaxial interaction diagram at neutral
    axis depth c, for a rectangular tied column with reinforcement
    idealized as two equal layers (Ast_total/2 each) at d_prime from the
    compression face and (h-d_prime) from it -- the standard simplification
    for a first-pass symmetric interaction diagram (see module docstring;
    a real column's bars are distributed around the full perimeter, which
    changes the diagram's shape somewhat, particularly near pure bending).
    eu=0.003 (Sec 6.3.2.3), equivalent rectangular stress block (Sec
    6.3.2.7). Moments taken about the section's geometric centroid (h/2)
    -- a simplification vs. the code's own 'plastic centroid' reference for
    asymmetric sections; exact for this function's own symmetric-
    reinforcement assumption."""
    b1 = beta1(fck_mpa)
    a = min(b1 * c_mm, h_mm)
    As_layer = Ast_total_mm2 / 2.0
    d_tension_mm = h_mm - d_prime_mm

    Cc = 0.85 * fck_mpa * a * b_mm  # N, compression block

    def layer_force(depth_from_compression_face):
        strain = 0.003 * (c_mm - depth_from_compression_face) / c_mm if c_mm > 0 else -0.003
        stress = max(-fy_mpa, min(fy_mpa, strain * ES_MPA))
        return As_layer * stress  # N, +compression

    F_comp_layer = layer_force(d_prime_mm)
    F_tension_layer = layer_force(d_tension_mm)

    Pn_n = Cc + F_comp_layer + F_tension_layer
    # Moments about mid-depth (h/2), N.mm:
    Mn_nmm = (Cc * (h_mm / 2.0 - a / 2.0)
              + F_comp_layer * (h_mm / 2.0 - d_prime_mm)
              - F_tension_layer * (d_tension_mm - h_mm / 2.0))
    return Pn_n / 1000.0, Mn_nmm / 1e6  # kN, kN.m


def build_interaction_diagram(b_mm, h_mm, fck_mpa, fy_mpa, Ast_total_mm2, d_prime_mm=None, num_points=40):
    """Sweeps neutral axis depth c from near-zero (pure tension) to well
    beyond h (approaching pure axial compression) and returns a list of
    {'c_mm':, 'Pn_kn':, 'Mn_knm':, 'phi':, 'phi_Pn_kn':, 'phi_Mn_knm':}
    points tracing the design (phi-included) interaction envelope. Not a
    closed-form BNBC equation -- see pm_interaction_point()'s own
    docstring for the strain-compatibility method and its simplifications.
    d_prime_mm defaults to 0.1*h (a common rule-of-thumb cover+bar-radius
    estimate; supply the real value when known)."""
    if d_prime_mm is None:
        d_prime_mm = 0.1 * h_mm
    Ag = b_mm * h_mm
    c_values = [h_mm * f for f in
                [0.02, 0.05, 0.1, 0.15, 0.2, 0.25, 0.3, 0.375, 0.45, 0.5, 0.6, 0.7,
                 0.8, 0.9, 1.0, 1.2, 1.5, 2.0, 3.0, 5.0, 10.0]][:num_points]
    points = []
    for c in c_values:
        Pn, Mn = pm_interaction_point(c, b_mm, h_mm, fck_mpa, fy_mpa, d_prime_mm, Ast_total_mm2)
        d_tension = h_mm - d_prime_mm
        et = 0.003 * (d_tension - c) / c if c > 0 else 0.01
        phi = strength_reduction_factor(et, fy_mpa)
        points.append({"c_mm": round(c, 1), "Pn_kn": round(Pn, 2), "Mn_knm": round(Mn, 2),
                       "phi": phi, "phi_Pn_kn": round(phi * Pn, 2), "phi_Mn_knm": round(phi * Mn, 2)})
    # Standard interaction-diagram practice: the theoretical strain-
    # compatibility curve is truncated by a HORIZONTAL line at the code's
    # own Pn,max (Eq 6.3.3's 0.80 accidental-eccentricity factor for tied
    # columns, matching this function's own tied-column-only scope) --
    # clip each point's Pn down to that ceiling (keeping its own Mn)
    # rather than dropping the point outright, which would understate
    # capacity right at the boundary instead of representing the code's
    # actual flat cutoff.
    Pn_max_nominal = max_axial_capacity_kn(fck_mpa, fy_mpa, Ag, Ast_total_mm2) / 0.65  # un-phi tied cap
    for p in points:
        if p["Pn_kn"] > Pn_max_nominal:
            p["Pn_kn"] = round(Pn_max_nominal, 2)
            p["phi_Pn_kn"] = round(p["phi"] * Pn_max_nominal, 2)
    return points


def check_demand_against_interaction(Pu_kn, Mu_knm, interaction_points, needs_review, member_id=""):
    """Checks whether (Pu, Mu) falls inside the (phi_Pn, phi_Mn) envelope
    by finding the two interaction points bracketing Pu and linearly
    interpolating the capacity Mn at that Pu -- adequate for a reasonably
    dense point set (build_interaction_diagram()'s default 20 points), not
    a substitute for a closed-form check. Returns {'adequate': bool,
    'capacity_phi_Mn_knm': ..., 'demand_Mu_knm': Mu_knm, 'utilization': ...}."""
    pts = sorted(interaction_points, key=lambda p: p["phi_Pn_kn"])
    if Pu_kn < pts[0]["phi_Pn_kn"] or Pu_kn > pts[-1]["phi_Pn_kn"]:
        needs_review.append({"element": member_id, "reason":
            f"Pu={Pu_kn:.1f}kN is outside the computed interaction diagram's range "
            f"({pts[0]['phi_Pn_kn']:.1f} to {pts[-1]['phi_Pn_kn']:.1f}kN) -- cannot check"})
        return {"reason": "Pu outside computed interaction diagram range"}
    for a, b in zip(pts, pts[1:]):
        if a["phi_Pn_kn"] <= Pu_kn <= b["phi_Pn_kn"]:
            frac = (Pu_kn - a["phi_Pn_kn"]) / (b["phi_Pn_kn"] - a["phi_Pn_kn"]) if b["phi_Pn_kn"] != a["phi_Pn_kn"] else 0.0
            capacity_phi_Mn = a["phi_Mn_knm"] + frac * (b["phi_Mn_knm"] - a["phi_Mn_knm"])
            adequate = abs(Mu_knm) <= capacity_phi_Mn
            return {"adequate": adequate, "capacity_phi_Mn_knm": round(capacity_phi_Mn, 2),
                    "demand_Mu_knm": round(Mu_knm, 2),
                    "utilization": round(abs(Mu_knm) / capacity_phi_Mn, 3) if capacity_phi_Mn > 0 else None}
    return {"reason": "interpolation failed -- check interaction_points ordering"}
