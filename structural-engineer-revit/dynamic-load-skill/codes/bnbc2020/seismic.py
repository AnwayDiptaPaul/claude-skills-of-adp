"""
codes/bnbc2020/seismic.py — BNBC 2020 (Part 6, Chapter 2, Section 2.5) earthquake
load data and formulas.

SOURCE AND VERIFICATION: checked directly against the official BNBC 2020 Part 6
Chapter 2 text, Section 2.5 "Earthquake Loads" (Sec 2.5.1 through 2.5.11 read in
full; source: https://iisee.kenken.go.jp/worldlist/06_Bangladesh/Bangladesh_BNBC_
Part6_Chap_2.pdf, an IISEE-hosted compilation whose running header reads "BNBC
2017" -- i.e. the pre-gazette draft. BNBC 2020 was substantively finalized from
that draft; nothing here should be assumed identical to the final gazetted 2020
text without a spot-check if a discrepancy ever surfaces on a real project).
Values re-expressed here as plain Python data with this module's own key names --
nothing below is a copy of the code's own table formatting or prose. Section/
equation/table numbers are cited in comments so a value can be checked against a
physical copy of the code in seconds.

ONE RECONSTRUCTION, FLAGGED HONESTLY: the design response spectrum equations
(6.2.35a-d) were badly mangled by PDF text extraction (operators and fraction
bars dropped). What survived was unambiguous enough to reconstruct with high
confidence -- BNBC's own S/TB/TC/TD/eta notation is drawn directly from Eurocode
8's Type 1 spectrum, and the reconstructed 4-branch shape was verified
symbolically (sympy) to be continuous at every branch boundary (T=TB, T=TC,
T=TD) -- a real, load-conserving spectrum shape rather than an invented one.
Still: spot-check design_spectral_acceleration() against a clean copy of the
code before relying on it for a stamped drawing.

UNITS: kN and metres throughout (kN/m2 for pressures, m for lengths), matching
revit-load-application's convention. Sa and Cs are dimensionless (units of g).

KNOWN GAPS -- referenced in the source text but not transcribed here, either
because the OCR didn't yield reliable numbers or because the section wasn't
reached before the fetch tool's extraction limit cut off (do not guess these):
  - Sec 2.5.12 Non-Linear Static Analysis (pushover) -- deliberately deferred.
    This is a performance-based method that needs an actual nonlinear solve;
    it belongs to structural-analysis once that skill exists with openseespy,
    not to this load-application-stage skill. Confirmed via a table of
    contents found separately (a slideshare-hosted BNBC intro deck) that this
    is genuinely 2.5.12's title, not a guess.
  - Sec 2.5.13 Earthquake Load Combinations (E, Eh, Emh, Ev definitions with
    BNBC's own redundancy-factor and overstrength-factor treatment) -- not
    transcribed. Almost certainly structurally similar to ASCE 7's
    E=Eh+-Ev, Eh=rho*QE, Ev=0.2*SDS*D, Em=Omega0*QE+-Ev (BNBC's earthquake
    chapter is otherwise a close structural relative of ASCE 7), but BNBC's
    own symbol list notably does NOT define a redundancy factor rho anywhere
    in Sec 2.1.4, and BNBC's primary spectral parameter is Sa, not ASCE 7's
    SDS/SD1 split (SDS appears only inside BNBC's own "alternatively use
    ASCE 7-02 Appendix C" shortcut, not its native Sa-based path) -- so the
    ASCE 7 formula must NOT be assumed to transplant unchanged. Get this
    section's actual text before implementing load combinations.
  - Sec 2.5.14 Drift and Deformation -- the allowable storey drift limit
    Delta_a (referenced throughout 2.5.7.7 as the thing story_drift() gets
    checked against) is not transcribed. design_deflection() and
    story_drift() below compute the demand side only; there is currently no
    Delta_a to compare it against.
  - Sec 2.5.15 (nonstructural components), 2.5.16 (seismic isolation),
    2.5.17 (soft storey design), 2.5.18 (non-building structures) -- out of
    scope for a first pass; niche relative to ordinary RCC/steel frame
    buildings, which is this pipeline's primary target per the project's
    own stated practice.
  - Eq 6.2.39/6.2.40 (masonry/shear-wall-specific period formula, Cw-based)
    -- the OCR came through too garbled to reconstruct responsibly (unlike
    the response spectrum, this shear-wall Cw formula isn't a universally
    standardized shape I could cross-check it against). approximate_period()
    below only implements the general Ct*hn^m formula (Eq 6.2.38, Table
    6.2.20's "all other structural systems" row and named frame types),
    which covers ordinary RCC and steel frame buildings -- this project's
    stated practice -- without needing the shear-wall-specific alternative.
"""
import math

# ---------------------------------------------------------------------------
# Sec 2.5.4.2 / Table 6.2.14 / Table 6.2.15 -- Seismic zoning
# ---------------------------------------------------------------------------
ZONE_DESCRIPTIONS = {
    1: {"intensity": "low", "coefficient_Z": 0.12,
        "region": "Southwestern part including Barisal, Khulna, Jessore, Rajshahi"},
    2: {"intensity": "moderate", "coefficient_Z": 0.20,
        "region": "Lower Central and Northwestern part including Noakhali, Dhaka, Pabna, "
                  "Dinajpur, and the Southwestern corner including the Sundarbans"},
    3: {"intensity": "severe", "coefficient_Z": 0.28,
        "region": "Upper Central and Northwestern part including Brahmanbaria, Sirajganj, Rangpur"},
    4: {"intensity": "very severe", "coefficient_Z": 0.36,
        "region": "Northeastern part including Sylhet, Mymensingh, Kurigram"},
}

# Table 6.2.15 -- Seismic Zone Coefficient Z for important towns of Bangladesh.
# Transcribed in full (every town the table lists) -- not a subset.
SEISMIC_ZONE_COEFFICIENTS = {
    "bagerhat": 0.12, "gaibandha": 0.28, "magura": 0.12, "patuakhali": 0.12,
    "bandarban": 0.28, "gazipur": 0.20, "manikganj": 0.20, "pirojpur": 0.12,
    "barguna": 0.12, "gopalganj": 0.12, "maulvibazar": 0.36, "rajbari": 0.20,
    "barisal": 0.12, "habiganj": 0.36, "meherpur": 0.12, "rajshahi": 0.12,
    "bhola": 0.12, "jaipurhat": 0.20, "mongla": 0.12, "rangamati": 0.28,
    "bogra": 0.28, "jamalpur": 0.36, "munshiganj": 0.20, "rangpur": 0.28,
    "brahmanbaria": 0.28, "jessore": 0.12, "mymensingh": 0.36, "satkhira": 0.12,
    "chandpur": 0.20, "jhalokati": 0.12, "narail": 0.12, "shariatpur": 0.20,
    "chapainababganj": 0.12, "jhenaidah": 0.12, "narayanganj": 0.20, "sherpur": 0.36,
    "chittagong": 0.28, "khagrachari": 0.28, "narsingdi": 0.28, "sirajganj": 0.28,
    "chuadanga": 0.12, "khulna": 0.12, "natore": 0.20, "srimangal": 0.36,
    "comilla": 0.20, "kishoreganj": 0.36, "naogaon": 0.20, "sunamganj": 0.36,
    "cox's bazar": 0.28, "kurigram": 0.36, "netrakona": 0.36, "sylhet": 0.36,
    "dhaka": 0.20, "kushtia": 0.20, "nilphamari": 0.12, "tangail": 0.28,
    "dinajpur": 0.20, "lakshmipur": 0.20, "noakhali": 0.20, "thakurgaon": 0.20,
    "faridpur": 0.20, "lalmanirhat": 0.28, "pabna": 0.20,
    "feni": 0.20, "madaripur": 0.20, "panchagarh": 0.20,
    # Common alternate spellings this project's own practice area uses.
    "cumilla": 0.20,  # = comilla
}


def get_zone_coefficient(location):
    """Returns Z for a town name (case-insensitive). Raises rather than
    guessing an unmatched location -- see get_live_load() in
    revit-load-application/codes/bnbc2020/loads.py for the same discipline
    applied to occupancy live loads. Table 6.2.15 doesn't cover every upazila
    in Bangladesh; for an unlisted location, the correct move is reading Z
    directly off the Fig 6.2.24 zone map (not included in this module --
    it's an image, not extractable text) against the nearest listed town, not
    picking the nearest-sounding key."""
    key = location.strip().lower()
    if key not in SEISMIC_ZONE_COEFFICIENTS:
        raise KeyError(
            f"'{location}' is not in SEISMIC_ZONE_COEFFICIENTS (Table 6.2.15). "
            f"Read Z directly off the Fig 6.2.24 zone map for this location instead "
            f"of guessing from a nearby town -- zone boundaries do not follow "
            f"district lines (e.g. Chandpur=0.20 vs neighbouring Chittagong=0.28)."
        )
    return SEISMIC_ZONE_COEFFICIENTS[key]


# ---------------------------------------------------------------------------
# Sec 2.5.3.2 / Table 6.2.13 -- Site classification
# ---------------------------------------------------------------------------
# Numeric boundaries only (the descriptive soil-profile text is BNBC's own
# prose and isn't reproduced here -- see the code directly for the qualitative
# description of each class). Bounds are on average properties of the top 30m
# (Eqs 6.2.31-6.2.33): shear-wave velocity Vs (m/s), SPT N-value (blows/30cm,
# uncorrected), undrained shear strength Su (kPa).
SITE_CLASS_BOUNDS = {
    "SA": {"vs_m_s": (800, None), "spt_n": None, "su_kpa": None},
    "SB": {"vs_m_s": (360, 800), "spt_n": (50, None), "su_kpa": (250, None)},
    "SC": {"vs_m_s": (180, 360), "spt_n": (15, 50), "su_kpa": (70, 250)},
    "SD": {"vs_m_s": (None, 180), "spt_n": (None, 15), "su_kpa": (None, 70)},
    # SE: surface alluvium (SC/SD-like, 5-20m thick) over Vs>800 m/s material --
    # a layering condition, not a single-band cutoff; can't be reduced to a
    # (min,max) tuple the way SA-SD can. Identify SE by profile shape, not by
    # plugging an average Vs into this table.
    "S1": {"note": "layer >=10m thick of soft clay/silt, PI>40, high water content -- site-specific study required"},
    "S2": {"note": "liquefiable soils, sensitive clays, or anything not fitting SA-SE/S1 -- site-specific study required"},
}


def classify_site_class(vs_m_s=None, spt_n=None, su_kpa=None):
    """Sec 2.5.3.2 / Table 6.2.13: classify SA-SD from average top-30m soil
    properties. Prefer vs_m_s (shear wave velocity) when available; fall back
    to spt_n, then su_kpa, per the code's own stated preference order ("site
    classification should be done using average shear wave velocity if this
    can be estimated, otherwise N may be used"). Returns None (not a guess)
    if nothing conclusive is passed, or if the values suggest SE, S1, or S2 --
    all three need the engineer's own judgement (SE is a layering condition;
    S1/S2 need a site-specific study per Sec 2.5.3.2), not a numeric cutoff.
    This is a classification aid, not a replacement for reading the actual
    borehole log the way this project's practice already does (SPT-based
    pile capacity work -- see topics/engineering-practice.md)."""
    if vs_m_s is not None:
        if vs_m_s > 800:
            return "SA"
        if 360 < vs_m_s <= 800:
            return "SB"
        if 180 < vs_m_s <= 360:
            return "SC"
        if vs_m_s <= 180:
            return "SD"
    if spt_n is not None:
        if spt_n > 50:
            return "SB"
        if 15 <= spt_n <= 50:
            return "SC"
        if spt_n < 15:
            return "SD"
    if su_kpa is not None:
        if su_kpa > 250:
            return "SB"
        if 70 <= su_kpa <= 250:
            return "SC"
        if su_kpa < 70:
            return "SD"
    return None


# Table 6.2.16 -- Site-dependent soil factor S and response-spectrum period
# breakpoints TB, TC, TD (seconds), by site class.
SITE_CLASS_PARAMETERS = {
    "SA": {"S": 1.00, "TB_s": 0.15, "TC_s": 0.40, "TD_s": 2.0},
    "SB": {"S": 1.20, "TB_s": 0.15, "TC_s": 0.50, "TD_s": 2.0},
    "SC": {"S": 1.15, "TB_s": 0.20, "TC_s": 0.60, "TD_s": 2.0},
    "SD": {"S": 1.35, "TB_s": 0.20, "TC_s": 0.80, "TD_s": 2.0},
    "SE": {"S": 1.40, "TB_s": 0.15, "TC_s": 0.50, "TD_s": 2.0},
    # S1/S2 deliberately absent -- Sec 2.5.4.3 requires a site-specific
    # spectrum for these, not a table lookup.
}


# ---------------------------------------------------------------------------
# Sec 2.5.5.1 / Table 6.2.17 -- Importance factor by occupancy category
# ---------------------------------------------------------------------------
# The occupancy CATEGORY (I/II/III/IV) definitions themselves live in Table
# 6.1.1, Part 6 Chapter 1 -- a different chapter, not reached by this
# project's source fetch. This module only has the resulting factor, not the
# rule for assigning a building to a category. Get the category from the
# engineer (occupancy_input in the dynamic-load input file -- see
# references/site_seismic_wind_input_format.md) rather than inferring it.
IMPORTANCE_FACTORS_SEISMIC = {"I": 1.00, "II": 1.00, "III": 1.25, "IV": 1.50}


def get_seismic_importance_factor(occupancy_category):
    """Table 6.2.17. occupancy_category is one of 'I','II','III','IV' as
    independently assigned by the engineer per Part 6 Chapter 1 Table 6.1.1
    (ordinary buildings are typically II; essential facilities -- hospitals,
    fire/police stations, emergency shelters -- are typically IV)."""
    key = occupancy_category.strip().upper()
    if key not in IMPORTANCE_FACTORS_SEISMIC:
        raise KeyError(f"'{occupancy_category}' is not I/II/III/IV.")
    return IMPORTANCE_FACTORS_SEISMIC[key]


# ---------------------------------------------------------------------------
# Sec 2.5.5.2 / Table 6.2.18 -- Seismic Design Category (B/C/D)
# ---------------------------------------------------------------------------
# Keyed [site_class][zone][occupancy_group] where occupancy_group is
# "I_II_III" or "IV". Transcribed exactly from the table (SE/S1/S2 all read D
# across every zone and occupancy group in the source table -- not a
# simplification, that's what the table actually says).
_SDC_TABLE = {
    "SA": {1: {"I_II_III": "B", "IV": "C"}, 2: {"I_II_III": "C", "IV": "D"},
           3: {"I_II_III": "C", "IV": "D"}, 4: {"I_II_III": "D", "IV": "D"}},
    "SB": {1: {"I_II_III": "B", "IV": "C"}, 2: {"I_II_III": "C", "IV": "D"},
           3: {"I_II_III": "D", "IV": "D"}, 4: {"I_II_III": "D", "IV": "D"}},
    "SC": {1: {"I_II_III": "B", "IV": "C"}, 2: {"I_II_III": "C", "IV": "D"},
           3: {"I_II_III": "D", "IV": "D"}, 4: {"I_II_III": "D", "IV": "D"}},
    "SD": {1: {"I_II_III": "C", "IV": "D"}, 2: {"I_II_III": "D", "IV": "D"},
           3: {"I_II_III": "D", "IV": "D"}, 4: {"I_II_III": "D", "IV": "D"}},
    "SE": {1: {"I_II_III": "D", "IV": "D"}, 2: {"I_II_III": "D", "IV": "D"},
           3: {"I_II_III": "D", "IV": "D"}, 4: {"I_II_III": "D", "IV": "D"}},
    "S1": {1: {"I_II_III": "D", "IV": "D"}, 2: {"I_II_III": "D", "IV": "D"},
           3: {"I_II_III": "D", "IV": "D"}, 4: {"I_II_III": "D", "IV": "D"}},
    "S2": {1: {"I_II_III": "D", "IV": "D"}, 2: {"I_II_III": "D", "IV": "D"},
           3: {"I_II_III": "D", "IV": "D"}, 4: {"I_II_III": "D", "IV": "D"}},
}


def seismic_design_category(site_class, zone, occupancy_category):
    """Table 6.2.18. site_class in SA-SE/S1/S2, zone in 1-4, occupancy_category
    in I/II/III/IV (I/II/III share a column in the source table; IV is
    separate). Returns 'B', 'C', or 'D'."""
    group = "IV" if occupancy_category.strip().upper() == "IV" else "I_II_III"
    try:
        return _SDC_TABLE[site_class.strip().upper()][int(zone)][group]
    except KeyError:
        raise KeyError(f"site_class={site_class!r}, zone={zone!r} not recognized -- "
                        f"site_class must be SA-SE/S1/S2, zone must be 1-4.")


# ---------------------------------------------------------------------------
# Sec 2.5.5.4 / Table 6.2.19 -- Response reduction factor R, system
# overstrength Omega0, deflection amplification Cd, and height limits by
# Seismic Design Category, for every structural system the table lists.
# height_limit_m: None means "NL" (no limit); 0 means "NP" (not permitted)
# for that SDC -- check for 0 explicitly, don't treat it as "no restriction".
# ---------------------------------------------------------------------------
STRUCTURAL_SYSTEMS = {
    # A. BEARING WALL SYSTEMS (no frame)
    "special_rc_shear_walls_bearing": {"R": 5, "Omega0": 2.5, "Cd": 5,
        "height_limit_m": {"B": None, "C": None, "D": 50}},
    "ordinary_rc_shear_walls_bearing": {"R": 4, "Omega0": 2.5, "Cd": 4,
        "height_limit_m": {"B": None, "C": None, "D": 0}},
    "ordinary_reinforced_masonry_shear_walls_bearing": {"R": 2, "Omega0": 2.5, "Cd": 1.75,
        "height_limit_m": {"B": None, "C": 50, "D": 0}},
    "ordinary_plain_masonry_shear_walls_bearing": {"R": 1.5, "Omega0": 2.5, "Cd": 1.25,
        "height_limit_m": {"B": 18, "C": 0, "D": 0}},
    # B. BUILDING FRAME SYSTEMS (with bracing or shear wall)
    "steel_eccentric_braced_moment_resisting_at_columns": {"R": 8, "Omega0": 2, "Cd": 4,
        "height_limit_m": {"B": None, "C": None, "D": 50}},
    "steel_eccentric_braced_non_moment_resisting_at_columns": {"R": 7, "Omega0": 2, "Cd": 4,
        "height_limit_m": {"B": None, "C": None, "D": 50}},
    "special_steel_concentric_braced_frame": {"R": 6, "Omega0": 2, "Cd": 5,
        "height_limit_m": {"B": None, "C": None, "D": 50}},
    "ordinary_steel_concentric_braced_frame": {"R": 3.25, "Omega0": 2, "Cd": 3.25,
        "height_limit_m": {"B": None, "C": None, "D": 11}},
    "special_rc_shear_walls_frame": {"R": 6, "Omega0": 2.5, "Cd": 5,
        "height_limit_m": {"B": None, "C": None, "D": 50}},
    "ordinary_rc_shear_walls_frame": {"R": 5, "Omega0": 2.5, "Cd": 4.25,
        "height_limit_m": {"B": None, "C": None, "D": 0}},
    "ordinary_reinforced_masonry_shear_walls_frame": {"R": 2, "Omega0": 2.5, "Cd": 2,
        "height_limit_m": {"B": None, "C": 50, "D": 0}},
    "ordinary_plain_masonry_shear_walls_frame": {"R": 1.5, "Omega0": 2.5, "Cd": 1.25,
        "height_limit_m": {"B": 18, "C": 0, "D": 0}},
    # C. MOMENT RESISTING FRAME SYSTEMS (no shear wall)
    "special_steel_moment_frame": {"R": 8, "Omega0": 3, "Cd": 5.5,
        "height_limit_m": {"B": None, "C": None, "D": None}},
    "intermediate_steel_moment_frame": {"R": 4.5, "Omega0": 3, "Cd": 4,
        "height_limit_m": {"B": None, "C": None, "D": 35}},
    "ordinary_steel_moment_frame": {"R": 3.5, "Omega0": 3, "Cd": 3,
        "height_limit_m": {"B": None, "C": None, "D": 0}},
    "special_rc_moment_frame": {"R": 8, "Omega0": 3, "Cd": 5.5,
        "height_limit_m": {"B": None, "C": None, "D": None}},
    "intermediate_rc_moment_frame": {"R": 5, "Omega0": 3, "Cd": 4.5,
        "height_limit_m": {"B": None, "C": None, "D": 0}},
    "ordinary_rc_moment_frame": {"R": 3, "Omega0": 3, "Cd": 2.5,
        "height_limit_m": {"B": None, "C": 0, "D": 0}},
    # D. DUAL SYSTEMS: SPECIAL MOMENT FRAMES (>=25% of seismic force) + bracing/shear wall
    "dual_special_steel_eccentric_braced": {"R": 8, "Omega0": 2.5, "Cd": 4,
        "height_limit_m": {"B": None, "C": None, "D": None}},
    "dual_special_steel_concentric_braced": {"R": 7, "Omega0": 2.5, "Cd": 5.5,
        "height_limit_m": {"B": None, "C": None, "D": None}},
    "dual_special_rc_shear_walls": {"R": 7, "Omega0": 2.5, "Cd": 5.5,
        "height_limit_m": {"B": None, "C": None, "D": None}},
    "dual_ordinary_rc_shear_walls": {"R": 6, "Omega0": 2.5, "Cd": 5,
        "height_limit_m": {"B": None, "C": None, "D": 0}},
    # E. DUAL SYSTEMS: INTERMEDIATE MOMENT FRAMES (>=25% of seismic force) + bracing/shear wall
    "dual_intermediate_special_steel_concentric_braced": {"R": 6, "Omega0": 2.5, "Cd": 5,
        "height_limit_m": {"B": None, "C": None, "D": 11}},
    "dual_intermediate_special_rc_shear_walls": {"R": 6.5, "Omega0": 2.5, "Cd": 5,
        "height_limit_m": {"B": None, "C": None, "D": 50}},
    "dual_intermediate_ordinary_reinforced_masonry_shear_walls": {"R": 3, "Omega0": 3, "Cd": 3,
        "height_limit_m": {"B": None, "C": 50, "D": 0}},
    "dual_intermediate_ordinary_rc_shear_walls": {"R": 5.5, "Omega0": 2.5, "Cd": 4.5,
        "height_limit_m": {"B": None, "C": None, "D": 0}},
    # F. DUAL SHEAR WALL-FRAME: ordinary RC moment frame + ordinary RC shear walls
    "dual_shear_wall_frame_ordinary_rc": {"R": 4.5, "Omega0": 2.5, "Cd": 4,
        "height_limit_m": {"B": None, "C": 0, "D": 0}},
    # G. STEEL SYSTEMS NOT SPECIFICALLY DETAILED FOR SEISMIC RESISTANCE
    "steel_not_specifically_detailed": {"R": 3, "Omega0": 3, "Cd": 3,
        "height_limit_m": {"B": None, "C": None, "D": 0}},
}
# Note 4 under Table 6.2.19: "Where data specific to a structure type is not
# available in this table, reference may be made to Table 12.2-1 of ASCE
# 7-05" -- BNBC's own text, not a limitation invented here.


def get_structural_system(system_key, seismic_design_category):
    """Returns {"R":..., "Omega0":..., "Cd":..., "height_limit_m":...} for a
    system key from STRUCTURAL_SYSTEMS, resolved for one SDC ('B'/'C'/'D').
    Raises if the system is not permitted (height_limit_m entry of 0, i.e.
    "NP" in the source table) at that SDC -- this is a real code violation to
    surface loudly, not a number to silently pass through."""
    if system_key not in STRUCTURAL_SYSTEMS:
        raise KeyError(f"'{system_key}' is not in STRUCTURAL_SYSTEMS. See Table 6.2.19 "
                        f"for the full system list; add new entries verified against "
                        f"the code, not guessed at.")
    entry = STRUCTURAL_SYSTEMS[system_key]
    sdc = seismic_design_category.strip().upper()
    limit = entry["height_limit_m"][sdc]
    if limit == 0:
        raise ValueError(f"'{system_key}' is NOT PERMITTED (NP) at Seismic Design "
                          f"Category {sdc} per Table 6.2.19 -- this is a real code "
                          f"restriction, not a data gap.")
    return {"R": entry["R"], "Omega0": entry["Omega0"], "Cd": entry["Cd"], "height_limit_m": limit}


# ---------------------------------------------------------------------------
# Sec 2.5.4.3 -- Design response spectrum (Eq 6.2.34, 6.2.35a-d)
# See the RECONSTRUCTION note in the module docstring: mangled by extraction,
# reconstructed as the standard EC8 Type-1 shape, verified continuous at
# every branch boundary via sympy -- confirm against a clean source before
# stamped use.
# ---------------------------------------------------------------------------
def normalized_response_spectrum(period_s, site_class, damping_pct=5.0):
    """Eq 6.2.35a-d: Cs(T), the normalized acceleration response spectrum
    (dimensionless), as a function of building period T (s) and site class.

    Cs = S*(1 + (T/TB)*(2.5*eta - 1))     for 0 <= T <= TB
    Cs = 2.5*S*eta                         for TB <= T <= TC
    Cs = 2.5*S*eta*(TC/T)                  for TC <= T <= TD
    Cs = 2.5*S*eta*(TC*TD/T^2)             for TD <= T <= 4s

    eta (damping correction, Eq 6.2.36) = sqrt(10/(5+damping_pct)), floored
    at 0.55 (eta=1.0 at the reference 5% damping)."""
    if site_class.strip().upper() not in SITE_CLASS_PARAMETERS:
        raise KeyError(f"'{site_class}' has no entry in SITE_CLASS_PARAMETERS -- "
                        f"S1/S2 need a site-specific spectrum per Sec 2.5.4.3, not "
                        f"this table lookup.")
    p = SITE_CLASS_PARAMETERS[site_class.strip().upper()]
    S, TB, TC, TD = p["S"], p["TB_s"], p["TC_s"], p["TD_s"]

    eta = max(math.sqrt(10.0 / (5.0 + damping_pct)), 0.55)  # Eq 6.2.36

    T = period_s
    if T < 0 or T > 4.0:
        raise ValueError(f"period_s={T} outside the spectrum's defined domain (0 to 4s).")
    if T <= TB:
        return S * (1 + (T / TB) * (2.5 * eta - 1)) if TB > 0 else 2.5 * S * eta
    if T <= TC:
        return 2.5 * S * eta
    if T <= TD:
        return 2.5 * S * eta * (TC / T)
    return 2.5 * S * eta * (TC * TD / T ** 2)


def design_spectral_acceleration(period_s, Z, I, R, site_class, damping_pct=5.0, beta=0.11):
    """Eq 6.2.34: Sa = (2/3) * Z * I / R * Cs, floored at 0.67*beta*Z*I*S
    (beta's recommended value is 0.11 per the code text). Returns Sa in units
    of g. R/I is capped implicitly by the caller choosing a valid R from
    get_structural_system() -- the code states R/I "cannot be greater than
    one", i.e. R must be >= I; this function doesn't re-check that itself."""
    site_class = site_class.strip().upper()
    Cs = normalized_response_spectrum(period_s, site_class, damping_pct)
    S = SITE_CLASS_PARAMETERS[site_class]["S"]
    sa = (2.0 / 3.0) * Z * I / R * Cs
    sa_min = 0.67 * beta * Z * I * S
    return max(sa, sa_min)


# ---------------------------------------------------------------------------
# Sec 2.5.7.1 -- Design base shear (Eq 6.2.37)
# ---------------------------------------------------------------------------
def base_shear(Sa, seismic_weight_kn):
    """Eq 6.2.37: V = Sa * W. Sa in units of g (dimensionless), W in kN,
    returns V in kN. Keep W as the honest DL+SDL+(reduced)LL sum from
    seismic_weight_kn() below -- don't pre-factor it."""
    return Sa * seismic_weight_kn


# ---------------------------------------------------------------------------
# Sec 2.5.7.2 / Table 6.2.20 -- Approximate fundamental period (Eq 6.2.38)
# ---------------------------------------------------------------------------
PERIOD_COEFFICIENTS = {
    "concrete_moment_resisting_frame": {"Ct": 0.0466, "m": 0.9},
    "steel_moment_resisting_frame": {"Ct": 0.0724, "m": 0.8},
    "eccentrically_braced_steel_frame": {"Ct": 0.0731, "m": 0.75},
    "other": {"Ct": 0.0488, "m": 0.75},  # "all other structural systems"
}


def approximate_period(height_m, structure_type="other"):
    """Eq 6.2.38: T = Ct * hn^m. hn is building height in metres from the
    foundation or top of rigid basement (excludes non-rigidly-connected
    basement storeys). structure_type keys into PERIOD_COEFFICIENTS.

    Per Sec 2.5.7.2(a): a period computed by structural dynamics (Rayleigh,
    modal eigenvalue) is allowed instead, but must not exceed this
    approximate value by more than 40% -- that computed-period path needs an
    actual stiffness model (structural-analysis's job), so it isn't
    implemented here; this function is the approximate/default path only."""
    if structure_type not in PERIOD_COEFFICIENTS:
        raise KeyError(f"'{structure_type}' not in PERIOD_COEFFICIENTS -- use one of "
                        f"{list(PERIOD_COEFFICIENTS)}. Masonry/shear-wall structures "
                        f"have their own formula (Eq 6.2.39/40) not implemented here "
                        f"-- see the module docstring's KNOWN GAPS.")
    c = PERIOD_COEFFICIENTS[structure_type]
    return c["Ct"] * height_m ** c["m"]


def computed_period_upper_bound(approximate_period_s):
    """Sec 2.5.7.2(a): a computed (Rayleigh/modal) period must not exceed the
    approximate period by more than 40%. Returns that ceiling -- the caller
    (structural-analysis, once it exists) checks its own computed T against
    this before using it for Sa."""
    return 1.40 * approximate_period_s


# ---------------------------------------------------------------------------
# Sec 2.5.7.3 -- Seismic weight
# ---------------------------------------------------------------------------
def seismic_live_load_fraction(live_load_kn_m2):
    """Sec 2.5.7.3: fraction of live load applicable to seismic weight.
    <=3 kN/m2 -> 25%; >3 kN/m2 -> 50%. Permanent heavy equipment/retained
    liquid/sustained imposed load is 100% regardless -- handle that
    separately in the caller, this function is for ordinary occupancy live
    load only."""
    return 0.25 if live_load_kn_m2 <= 3.0 else 0.50


def seismic_weight_kn(dead_load_kn, sdl_kn, live_load_kn, live_load_intensity_kn_m2,
                       permanent_equipment_kn=0.0):
    """Sec 2.5.7.3: W = D + SDL + (fraction * L) + permanent_equipment, where
    the fraction comes from seismic_live_load_fraction() applied to the
    UNREDUCED live load intensity (kN/m2, used only to pick the 25%/50%
    threshold) -- live_load_kn is the actual load total (kN) that fraction
    gets applied to. Partition wall weight is already inside dead_load_kn
    (BNBC 2.2.5 already treats it as dead load) -- don't add it again."""
    fraction = seismic_live_load_fraction(live_load_intensity_kn_m2)
    return dead_load_kn + sdl_kn + fraction * live_load_kn + permanent_equipment_kn


# ---------------------------------------------------------------------------
# Sec 2.5.7.4 -- Vertical distribution of base shear (Eq 6.2.41)
# ---------------------------------------------------------------------------
def vertical_distribution_exponent(period_s):
    """Sec 2.5.7.4: k=1 for T<=0.5s, k=2 for T>=2.5s, linear interpolation
    between."""
    if period_s <= 0.5:
        return 1.0
    if period_s >= 2.5:
        return 2.0
    return 1.0 + (period_s - 0.5) / (2.5 - 0.5)


def vertical_distribution(base_shear_kn, story_weights_kn, story_heights_m, k):
    """Eq 6.2.41: Fx = V * (wx*hx^k) / sum(wi*hi^k). story_weights_kn and
    story_heights_m are parallel lists, one entry per storey (heights
    measured from the base, not storey-to-storey), in any consistent order.
    k is a single scalar for the whole building -- get it from
    vertical_distribution_exponent(period_s) first; kept as a separate
    function so "what period gives what k" and "how k spreads the shear"
    stay independently checkable. Returns a list of Fx (kN), same order as
    the inputs, normalized so it sums exactly to base_shear_kn (guards the
    same floating-point drift skill 2's distribution.py guards for its panel
    loads)."""
    if len(story_weights_kn) != len(story_heights_m):
        raise ValueError("story_weights_kn and story_heights_m must be the same length.")
    numerators = [w * h ** k for w, h in zip(story_weights_kn, story_heights_m)]
    denom = sum(numerators)
    if denom == 0:
        raise ValueError("sum(wi*hi^k) is zero -- check story_heights_m aren't all zero.")
    return [base_shear_kn * n / denom for n in numerators]


# ---------------------------------------------------------------------------
# Sec 2.5.7.5 -- Storey shear (Eq 6.2.42)
# ---------------------------------------------------------------------------
def story_shear(fx_top_to_bottom):
    """Eq 6.2.42: Vx at storey x = sum of Fi for storey x and all storeys
    above it. Input fx_top_to_bottom must be ordered top storey first. Returns
    cumulative story shear in the same top-to-bottom order."""
    cumulative = []
    running = 0.0
    for fx in fx_top_to_bottom:
        running += fx
        cumulative.append(running)
    return cumulative


# ---------------------------------------------------------------------------
# Sec 2.5.7.6 -- Accidental torsional moment (Eq 6.2.43)
# ---------------------------------------------------------------------------
def accidental_torsional_moment(story_force_kn, floor_dimension_perpendicular_m):
    """Eq 6.2.43: Mta = eai * Fi, eai = +-0.05 * Li (Li = floor dimension
    PERPENDICULAR to the direction of the seismic force being considered --
    easy to pass the wrong dimension, double check axis). Returns the
    magnitude (kN*m); apply the sign that produces the more severe effect
    per the code's own instruction, not both simultaneously."""
    return 0.05 * floor_dimension_perpendicular_m * story_force_kn


# ---------------------------------------------------------------------------
# Sec 2.5.7.8 -- Overturning moment (Eq 6.2.47)
# ---------------------------------------------------------------------------
def overturning_moment_at_level(fx_list, heights_m, level_index):
    """Eq 6.2.47: Mx at level x = sum over i>=x of Fi*(hi - hx). fx_list and
    heights_m are parallel, ordered from base (index 0) to roof. level_index
    is the index (into both lists) of the level being checked."""
    hx = heights_m[level_index]
    return sum(fx_list[i] * (heights_m[i] - hx) for i in range(level_index, len(fx_list)))


def foundation_overturning_design_moment(fx_list, heights_m):
    """Sec 2.5.7.8: foundations (except inverted-pendulum structures) may be
    designed for 3/4 of the full foundation overturning moment. Returns that
    reduced value; the full Mo is overturning_moment_at_level(..., 0)."""
    full_mo = overturning_moment_at_level(fx_list, heights_m, 0)
    return 0.75 * full_mo


# ---------------------------------------------------------------------------
# Sec 2.5.7.7 -- Deflection and storey drift (Eq 6.2.45, 6.2.46)
# ---------------------------------------------------------------------------
def design_deflection(elastic_deflection_m, Cd, importance_factor_I):
    """Eq 6.2.45: delta_x = Cd * delta_xe / I. delta_xe (the elastic
    deflection under the REDUCED design forces) has to come from an actual
    stiffness analysis -- structural-analysis's job once it exists. This
    function is the transform step only."""
    return Cd * elastic_deflection_m / importance_factor_I


def story_drift(design_deflection_top_m, design_deflection_bottom_m):
    """Eq 6.2.46: story drift = difference of design deflections (already
    Cd/I-amplified, from design_deflection() above) at the top and bottom of
    the storey. There is currently no allowable drift limit Delta_a
    transcribed to check this against -- see Sec 2.5.14 in KNOWN GAPS."""
    return design_deflection_top_m - design_deflection_bottom_m


# ---------------------------------------------------------------------------
# Sec 2.5.7.9 -- P-delta / stability coefficient (Eq 6.2.48, 6.2.49)
# ---------------------------------------------------------------------------
def stability_coefficient(total_vertical_load_kn, story_shear_kn, design_story_drift_m,
                           story_height_m, Cd):
    """Eq 6.2.48: theta = (Px * delta) / (Vx * hsx * Cd). No individual load
    factor in Px should exceed 1.0 (per the code's own note) -- pass Px as an
    unfactored/service-level total, not a load-combination-factored one."""
    return (total_vertical_load_kn * design_story_drift_m) / (story_shear_kn * story_height_m * Cd)


def stability_coefficient_max(Cd, demand_capacity_ratio_beta=1.0):
    """Eq 6.2.49: theta_max = 0.5 / (beta * Cd). beta is the storey's actual
    shear demand/capacity ratio; the code permits conservatively taking
    beta=1.0 when it isn't otherwise known -- that's this function's
    default, not an invented shortcut."""
    return 0.5 / (demand_capacity_ratio_beta * Cd)


def pdelta_amplification_factor(theta):
    """Sec 2.5.7.9: when 0.10 < theta <= theta_max, the code permits
    multiplying displacements and member forces by 1/(1-theta) as an
    alternative to full rational P-delta analysis. Returns that multiplier;
    the caller is responsible for first checking theta <= theta_max
    (stability_coefficient_max()) -- theta beyond that means the structure
    is potentially unstable and needs redesign, not amplification."""
    if theta <= 0.10:
        return 1.0  # P-delta effects need not be considered at all
    return 1.0 / (1.0 - theta)


# ---------------------------------------------------------------------------
# Sec 2.5.8.1 -- When dynamic analysis is required (not just permitted)
# ---------------------------------------------------------------------------
def dynamic_analysis_required(height_m, zone, is_regular):
    """Sec 2.5.8.1: dynamic analysis (RSA or time history) is REQUIRED, not
    just optional, for:
      (a) regular buildings taller than 40m in zones 2-4, or 90m in zone 1
      (b) irregular buildings taller than 12m in zones 2-4, or 40m in zone 1
    (irregular buildings under 40m in zone 1 don't require it but the code
    recommends it anyway -- that recommendation isn't encoded as a bool
    here, surface it as a note in the caller if zone==1 and is_regular is
    False and height_m<40)."""
    zone = int(zone)
    if is_regular:
        threshold = 90.0 if zone == 1 else 40.0
    else:
        threshold = 40.0 if zone == 1 else 12.0
    return height_m > threshold


def static_analysis_permitted(period_s, TC_s, is_regular_in_elevation):
    """Sec 2.5.6: the equivalent static (ESFP) procedure is valid only when
    BOTH (a) period_s < min(4*TC_s, 2.0) and (b) the building has no
    elevation irregularity (Sec 2.5.5.3's vertical irregularity types).
    is_regular_in_elevation must be supplied by the caller (from skill 1's
    geometry/mass/stiffness-adjacent flags) -- this function doesn't infer
    it."""
    return period_s < min(4 * TC_s, 2.0) and is_regular_in_elevation


# ---------------------------------------------------------------------------
# Sec 2.5.9 -- Response Spectrum Analysis (RSA): the pieces that don't need
# an eigenvalue solve. The modal periods/shapes/participation factors
# themselves need an actual stiffness model -- structural-analysis's job.
# These functions are here so that skill, once it has modal properties, has
# a verified place to plug them into the code's own combination rules
# instead of re-deriving them.
# ---------------------------------------------------------------------------
def modal_force_at_level(spectral_acceleration_g, modal_shape_coefficient,
                          modal_participation_factor, weight_kn):
    """Eq 6.2.50: Fik = Ak * phi_ik * Pk * Wi for mode k at level i. Ak comes
    from design_spectral_acceleration() evaluated at that mode's period Tk."""
    return spectral_acceleration_g * modal_shape_coefficient * modal_participation_factor * weight_kn


def rsa_base_shear_scale_factor(rsa_base_shear_kn, esfp_base_shear_kn):
    """Sec 2.5.9.4: if the RSA base shear Vrc is less than 85% of the ESFP
    base shear V, every RSA-derived FORCE (not drift/displacement) must be
    scaled up by 0.85*V/Vrc. Returns 1.0 (no scaling needed) or the required
    factor."""
    threshold = 0.85 * esfp_base_shear_kn
    if rsa_base_shear_kn >= threshold:
        return 1.0
    return threshold / rsa_base_shear_kn


# Minimum modal mass participation required (Sec 2.5.9.2): 90% of actual mass
# in each of two orthogonal directions. A constant, not a formula.
RSA_MIN_MASS_PARTICIPATION_PCT = 90.0


def requires_3d_model(is_regular, has_independent_orthogonal_systems):
    """Sec 2.5.9.1: independent 2D models (one per orthogonal
    seismic-force-resisting system) are permitted ONLY for regular
    structures with independent orthogonal systems. Everything else --
    irregular structures, or ones without independent orthogonal systems --
    needs a full 3D model with >=3 dynamic DOF/level (2 translation +
    torsion)."""
    return not (is_regular and has_independent_orthogonal_systems)


# ---------------------------------------------------------------------------
# Sec 2.5.4.3 -- Discretized design response spectrum, as portable DATA.
# The closed-form design_spectral_acceleration() above is this module's own
# formula; this samples it into a plain (T, Sa) table that travels inside
# structural_model.json, so a downstream consumer (structural-analysis, once
# it has real modal periods from an eigenvalue solve) can interpolate Sa at
# any period directly from data, without needing its own copy of this
# module's code -- the same reasoning that keeps skills from importing across
# their package boundaries (see references/site_seismic_wind_input_format.md).
# ---------------------------------------------------------------------------
def design_response_spectrum_curve(Z, I, R, site_class, damping_pct=5.0, beta=0.11,
                                    t_max=4.0, t_step=0.02):
    """Returns [{'T_sec':..., 'Sa_g':...}, ...] from T=0 to t_max, at t_step
    resolution, with the site class's own TB/TC/TD breakpoints always
    included exactly (not just landed on by chance) so no consumer ever
    linearly-interpolates across the sharp corner at the top of the plateau.
    At 0.02s steps over 0-4s this is ~200 points -- small, and dense enough
    that linear interpolation between samples introduces negligible error
    (the underlying curve is smooth except at TB/TC/TD, which are exact grid
    points here).

    Note for whoever reads this curve's tail: it goes flat well before
    t_max, at Sa = 0.67*beta*Z*I*S -- that's Eq 6.2.34's own lower-bound
    floor asserting itself (see design_spectral_acceleration()), not a
    sampling artifact. The underlying 1/T^2 branch really would keep
    decreasing; the code just doesn't let Sa fall below that floor."""
    site_class = site_class.strip().upper()
    if site_class not in SITE_CLASS_PARAMETERS:
        raise KeyError(f"'{site_class}' has no entry in SITE_CLASS_PARAMETERS -- "
                        f"S1/S2 need a site-specific spectrum per Sec 2.5.4.3.")
    p = SITE_CLASS_PARAMETERS[site_class]
    grid = {0.0, p["TB_s"], p["TC_s"], p["TD_s"], t_max}
    t = 0.0
    while t <= t_max + 1e-9:
        grid.add(round(t, 6))
        t += t_step
    points = []
    for T in sorted(g for g in grid if g <= t_max):
        Sa = design_spectral_acceleration(T, Z, I, R, site_class, damping_pct, beta)
        points.append({"T_sec": round(T, 4), "Sa_g": round(Sa, 6)})
    return points


# ---------------------------------------------------------------------------
# Sec 2.5.9 -- Response Spectrum Analysis: the complete system a downstream
# eigenvalue solve needs, verified against Sec 2.5.9's full text (not just
# the modal-force formula already implemented above).
# ---------------------------------------------------------------------------
def rsa_system(Z, I, R, Cd, site_class, esfp_base_shear_kn, damping_pct=5.0):
    """Bundles everything Sec 2.5.9 requires of an RSA once real modal
    properties exist, so structural-analysis can run the actual eigenvalue
    solve and combination against a verified, ready-made spec rather than
    re-deriving these rules. Does NOT run the eigenvalue solve itself --
    that needs the real stiffness model this skill doesn't have."""
    return {
        "design_spectrum_g": design_response_spectrum_curve(Z, I, R, site_class, damping_pct),
        "min_mass_participation_pct": RSA_MIN_MASS_PARTICIPATION_PCT,  # Sec 2.5.9.2
        "modal_combination_rule": (
            "SRSS (square root of sum of squares) by default; CQC (complete "
            "quadratic combination) is REQUIRED where closely-spaced "
            "translational/torsional modal periods cross-correlate (Sec "
            "2.5.9.4's own words -- the code names both methods but doesn't "
            "give a numeric closeness threshold for when CQC becomes "
            "mandatory, so treat that determination as an engineering "
            "judgment call once real periods are known, not something this "
            "function decides)."
        ),
        "esfp_base_shear_kn_for_scaling": esfp_base_shear_kn,
        "force_scaling_rule": (
            "if RSA base shear Vrc < 0.85 * esfp_base_shear_kn, multiply "
            "every RSA-derived FORCE (story shear, moment, etc. -- NOT "
            "drift/displacement) by 0.85*esfp_base_shear_kn/Vrc -- Sec "
            "2.5.9.4. Use rsa_base_shear_scale_factor()."
        ),
        "displacement_scaling_rule": (
            "RSA displacements/drifts get multiplied by Cd/I to obtain "
            "design values, exactly as in the ESFP path -- Sec 2.5.9.4 "
            "cross-references Sec 2.5.7.7. Use design_deflection()."
        ),
        "modeling_requirements": [
            "cracked-section stiffness for concrete/masonry elements (Sec 2.5.9.1)",
            "include panel-zone deformation's contribution to storey drift for steel moment frames (Sec 2.5.9.1)",
            "3D model with >=3 DOF/level required unless requires_3d_model() returns False for this building (Sec 2.5.9.1)",
        ],
    }


# ---------------------------------------------------------------------------
# Sec 2.5.10 -- Linear Time History Analysis (LTHA): ground motion selection
# and scaling criteria, verified against Sec 2.5.10.2/2.5.10.3's full text.
# ---------------------------------------------------------------------------
def ltha_ground_motion_criteria(period_s, analysis_dimension="3D"):
    """Sec 2.5.10.2. Returns the verified matching/scaling requirements for
    SELECTING ground motions to match this structure's own period -- does
    NOT select or scale actual records itself (that needs a real record
    library and structural-analysis's own real T, not this skill's
    approximate Ta).
    period_s: the structure's fundamental period T in the direction under
              consideration. Sec 2.5.10.2's matching window (0.2T-1.5T) is
              defined in terms of this real period -- once structural-
              analysis has it from an eigenvalue solve, re-call this with
              that value rather than trusting whatever approximate Ta this
              skill computed."""
    if analysis_dimension not in ("2D", "3D"):
        raise ValueError("analysis_dimension must be '2D' or '3D'")
    criteria = {
        "min_records": 3,
        "period_matching_range_s": [round(0.2 * period_s, 4), round(1.5 * period_s, 4)],
        "record_count_for_design_value": {
            "fewer_than_7": "use the MAXIMUM structural response across all records/pairs as the design value",
            "7_or_more": "use the AVERAGE of the maximum structural responses across all records/pairs as the design value",
        },
    }
    if analysis_dimension == "2D":
        criteria["ground_motion_type"] = (
            "one horizontal acceleration time history per record, from an "
            "actual recorded event with magnitude/fault-distance/source "
            "mechanism consistent with the MCE (simulated records permitted "
            "to make up the count if too few recorded events qualify)"
        )
        criteria["matching_rule"] = (
            "the AVERAGE of the 5%-damped response spectra across all "
            "selected records must not be less than the design response "
            "spectrum ordinate, at every period in period_matching_range_s"
        )
    else:
        criteria["ground_motion_type"] = (
            "pairs of orthogonal horizontal acceleration time histories per "
            "record, both components scaled by the SAME factor"
        )
        criteria["matching_rule"] = (
            "an SRSS spectrum is built per pair (sqrt of sum of squares of "
            "the two components' 5%-damped spectra); the AVERAGE of the SRSS "
            "spectra across all selected pairs must not be less than 1.3x "
            "the design response spectrum ordinate, at every period in "
            "period_matching_range_s"
        )
    return criteria


def ltha_base_shear_scale_factor(ltha_base_shear_kn, esfp_base_shear_kn):
    """Sec 2.5.10.3: if LTHA's maximum base shear Vth is less than the ESFP
    base shear V, every LTHA response quantity (story shear, moments,
    drifts, floor deflections, member forces) gets multiplied by V/Vth.
    Unlike RSA's 85%-of-V threshold (Sec 2.5.9.4), this compares directly
    to V with no allowance."""
    if ltha_base_shear_kn >= esfp_base_shear_kn:
        return 1.0
    return esfp_base_shear_kn / ltha_base_shear_kn


def ltha_design_value_rule(num_records):
    """Sec 2.5.10.3's record-count rule as a callable: <7 records/pairs ->
    take the MAXIMUM response across them as the design value; >=7 -> take
    the AVERAGE of the maximum responses. Returns 'max' or 'average' so the
    caller doesn't have to re-encode the threshold itself."""
    return "max" if num_records < 7 else "average"


# ---------------------------------------------------------------------------
# Sec 2.5.11 -- Nonlinear Time History Analysis (NTHA): the 'real' (fully
# unreduced) design spectrum NTHA is run against, per Sec 2.5.11.2.
# ---------------------------------------------------------------------------
def ntha_real_design_spectrum_curve(Z, site_class, damping_pct=5.0, beta=0.11,
                                     t_max=4.0, t_step=0.02):
    """Sec 2.5.11.2: NTHA uses the 'real' design acceleration response
    spectrum -- Eq 6.2.34 evaluated with R=1 and I=1 (the UNREDUCED
    spectrum). A thin wrapper around design_response_spectrum_curve() with
    those two parameters fixed, since that function already takes R and I
    as arguments rather than assuming the ESFP-reduced case.

    SOURCE TEXT NOTE: the source PDF's OCR rendered the stacked fraction
    '2/3' as a bare '3' in two places in this subsection ("PGA of 3Z" and
    "PGA value of 3ZS"). Read here as (2/3)*Z and (2/3)*Z*S respectively --
    not a guess: this same section states explicitly, in unmangled text
    elsewhere, that "the design basis earthquake ground motion is selected
    at a ground shaking level that is 2/3 of the maximum considered
    earthquake", and Sec 2.5.4.3 gives the analogous reduced design PGA as
    (2/3)(ZI/R) in the identical pattern -- a bare '3Z' would be larger than
    the MCE-level PGA itself (which Z already represents), which doesn't fit
    the section's own definition of what a "design basis" motion is. Flagged
    here for the same reason the response spectrum equations were flagged:
    confirm against a clean copy of the code before treating it as beyond
    doubt, even though the reconstruction is well-grounded."""
    return design_response_spectrum_curve(Z, I=1.0, R=1.0, site_class=site_class,
                                           damping_pct=damping_pct, beta=beta,
                                           t_max=t_max, t_step=t_step)


def ntha_ground_motion_criteria(period_s, analysis_dimension="3D"):
    """Sec 2.5.11.2 cross-references Sec 2.5.10.2 for ground motion
    selection -- NTHA uses the same criteria as LTHA. Thin alias so the
    cross-reference is visible in code, not just in a comment."""
    return ltha_ground_motion_criteria(period_s, analysis_dimension)
