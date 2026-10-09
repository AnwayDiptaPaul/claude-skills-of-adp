"""
codes/bnbc2020/wind.py — BNBC 2020 (Part 6, Chapter 2, Section 2.4) wind load
data and formulas.

SOURCE: Section 2.4 "Wind Loads" is entirely absent from the IISEE-hosted PDF
that revit-load-application's loads.py and this module's own seismic.py were
verified against (that document jumps straight from Sec 2.3 Live Loads to
Sec 2.5 Earthquake Loads -- confirmed by fetching it directly rather than
assuming the earlier session's "not yet researched" note was right without
checking). Section 2.4 was instead read in full from a second, independent
source: https://law.resource.org/pub/bd/bnbc.2012/gov.bd.bnbc.2012.06.02.pdf
(law.resource.org's hosted copy of the same Part 6 Chapter 2, under a
"bnbc.2012" path -- likely an earlier numbered draft cycle; treated here with
the same "verify before stamped use" caution as seismic.py's "2017" header
note). Both documents' shared Sec 2.2 (Dead Loads) and Sec 2.3 (Live Loads)
text matched revit-load-application's own already-verified numbers exactly
(same Table 6.2.1-6.2.7 values, allowing for this source's slightly
different rounding on a handful of live load entries -- e.g. 2.87 vs 2.90 --
consistent with drafting-cycle rounding differences, not a different code).

This chapter is a close structural relative of ASCE 7-05 (BNBC's own Table
6.2.19 footnote elsewhere in Sec 2.5 explicitly cross-references "Table
12.2-1 of ASCE 7-05" as a fallback, and the wind chapter's own equation
numbering, symbol set, and method structure -- Method 1 Simplified, Method 2
Analytical, Method 3 Wind Tunnel -- mirror ASCE 7-05 almost exactly), but
every formula and coefficient below was read from BNBC's own text, not
carried over from ASCE 7 by assumption.

UNITS: kN, m, m/s, kN/m2 throughout, matching this pipeline's convention
(BNBC's own qz formula (Eq 2.4.15) is written for these exact units: the
0.000613 coefficient is unit-specific, not a generic constant).

KNOWN GAPS -- IMPORTANT, READ BEFORE USE: several standard-form numeric
tables that Method 2 depends on are referenced repeatedly in Sec 2.4's own
text but rendered as image tables in the source PDF (not machine-readable
text) and were not independently found in a second, reliable source before
this skill's build time ran out. Without these, this module computes the
FORMULA STRUCTURE correctly but cannot produce a trustworthy final pressure
number. Do not fill these in from ASCE 7 by assumption -- BNBC's own text
explicitly gives Kd "in Table 2.4.5" etc. as its own table, not as "see
ASCE 7". Get the actual BNBC numbers before this module is load-bearing:
  - Table 2.4.1 / Fig 6.2.1 -- basic wind speed V (m/s) by location. A
    secondary academia.edu source (a 2022 comparison paper) gives DIVISION-
    level approximate figures (Dhaka division ~65.7 m/s, Chattogram division
    ~80 m/s, etc. -- see BASIC_WIND_SPEED_APPROX_UNVERIFIED below) but BNBC's
    own zone contours do not follow administrative division lines any more
    than the seismic zone map does (Chandpur's seismic Z=0.20 differs from
    neighbouring Chittagong's Z=0.28 despite being in the same division) --
    so a division-level figure must NOT be used as a stand-in for Chandpur's
    or Cumilla's actual value without checking the real zone map/table.
  - Table 2.4.2 -- wind importance factor I by occupancy category.
  - Table 2.4.3 -- turbulence-intensity constants (c, l-bar, epsilon-bar,
    zg, zmin, b-bar, alpha-bar) by exposure category A/B/C, needed for the
    full computed gust factor (Eq 2.4.4-2.4.14) and for flexible-structure
    analysis. gust_effect_factor_rigid() below (the G=0.85 shortcut) doesn't
    need this table; the full computed-G path does.
  - Table 2.4.4 -- velocity pressure exposure coefficient Kz by exposure
    category and height z.
  - Table 2.4.5 -- wind directionality factor Kd (by structure type).
This mirrors revit-load-application's own "only BNBC 2020 populated, others
stubbed" honesty pattern -- these are flagged gaps to fill from a verified
source, not values to guess at.
"""
import math

# ---------------------------------------------------------------------------
# Sec 2.4.1.1 -- Minimum design wind loading (applies regardless of the
# computed pressure -- a floor, not a fallback default)
# ---------------------------------------------------------------------------
MINIMUM_MWFRS_PRESSURE_KN_M2 = 0.5
MINIMUM_COMPONENTS_CLADDING_PRESSURE_KN_M2 = 0.5  # net, either direction


# ---------------------------------------------------------------------------
# NOT VERIFIED -- see KNOWN GAPS above. Division-level approximate figures
# from a secondary source (Md Lixon et al., "Comparison of Wind Load among
# BNBC and Other International Codes", 2022), included only as a rough
# planning number -- never pass these to velocity_pressure() for anything
# that reaches a client or a stamped drawing without checking the real
# BNBC zone map/table first.
# ---------------------------------------------------------------------------
BASIC_WIND_SPEED_APPROX_UNVERIFIED_M_S = {
    "dhaka_division": 65.7, "chattogram_division": 80.0, "khulna_division": 73.3,
    "barishal_division": 78.7, "rajshahi_division": 49.2, "rangpur_division": 65.3,
    "mymensingh_division": 67.4, "sylhet_division": 61.1,
}
# The BNBC wind-speed zone map (via an independent Dlubal engineering-software
# lookup tool, "Basic Wind Velocity for Bangladesh According to BNBC:2015")
# uses this discrete set of zone speeds -- confirms the code works in bands
# like the seismic Z-zones do, not a continuous field, but without giving a
# location->value table this project can extract as text:
BASIC_WIND_SPEED_ZONE_VALUES_M_S_UNVERIFIED = [
    41.4, 44.7, 50.6, 56.7, 62.5, 65.6, 68.1, 73.9, 80.0,
]  # some zones (coastal/cyclone-prone) carry a starred variant per that tool;
   # variant meaning not confirmed here either.


# ---------------------------------------------------------------------------
# Sec 2.4.10.1 -- Gust effect factor, rigid structures
# ---------------------------------------------------------------------------
def gust_effect_factor_rigid():
    """Sec 2.4.10.1: for rigid structures (fundamental frequency >= 1 Hz --
    true for essentially all ordinary low/mid-rise RCC or steel frame
    buildings), the gust effect factor G may simply be taken as 0.85,
    instead of the full computed formula (Eq 2.4.4-2.4.9), which needs
    Table 2.4.3's turbulence constants (not verified -- see module
    docstring) and is really only necessary for flexible/dynamically
    sensitive structures (natural frequency < 1 Hz -- tall/slender towers,
    not this project's stated RCC frame practice)."""
    return 0.85


def is_rigid(natural_frequency_hz):
    """Sec 2.1.3 BUILDING OR OTHER STRUCTURES, RIGID: fundamental frequency
    >= 1 Hz. (The inverse -- FLEXIBLE -- is frequency < 1 Hz.)"""
    return natural_frequency_hz >= 1.0


# ---------------------------------------------------------------------------
# Sec 2.4.11.5 -- Velocity pressure (Eq 2.4.15)
# ---------------------------------------------------------------------------
def velocity_pressure(Kz, Kzt, Kd, V_m_s, I):
    """Eq 2.4.15: qz = 0.000613 * Kz * Kzt * Kd * V^2 * I, in kN/m2, with V
    in m/s. The 0.000613 coefficient is unit-specific to (kN/m2, m/s) -- do
    not reuse this function's numeric constant if V or the return value is
    ever expressed in different units.
    Kz: velocity pressure exposure coefficient at height z -- Table 2.4.4,
        NOT VERIFIED (see module docstring).
    Kzt: topographic factor -- 1.0 unless Sec 2.4.9.1's hill/ridge/escarpment
        conditions apply (topographic_factor() below handles that case).
    Kd: wind directionality factor -- Table 2.4.5, NOT VERIFIED.
    V_m_s: basic wind speed for the site -- Table 2.4.1/Fig 6.2.1, NOT
        VERIFIED for specific locations (see BASIC_WIND_SPEED_* above).
    I: importance factor -- Table 2.4.2, NOT VERIFIED."""
    return 0.000613 * Kz * Kzt * Kd * V_m_s ** 2 * I


def topographic_factor(K1, K2, K3):
    """Eq 2.4.3: Kzt = (1 + K1*K2*K3)^2. K1/K2/K3 come from Fig 2.4.4's
    hill-shape tables based on H/Lh, x/Lh, z/Lh -- not transcribed here (a
    graphical figure with several hill-shape variants); return 1.0 directly
    instead of calling this function when Sec 2.4.9.1's applicability
    conditions (isolated hill/ridge/escarpment, H/Lh>=0.2, etc.) aren't met,
    which is the common case for typical building sites."""
    return (1 + K1 * K2 * K3) ** 2


# ---------------------------------------------------------------------------
# Sec 2.4.12.1 / Fig 2.4.5 -- Internal pressure coefficient GCpi
# ---------------------------------------------------------------------------
INTERNAL_PRESSURE_COEFFICIENTS = {
    "open": 0.00,
    "partially_enclosed": 0.55,   # applied as +/-0.55 -- both signs checked
    "enclosed": 0.18,             # applied as +/-0.18 -- both signs checked
}


def get_internal_pressure_coefficient(enclosure_classification):
    """Fig 2.4.5. Returns the MAGNITUDE; Sec 2.4.12.1 requires checking both
    +GCpi and -GCpi as separate load cases, not just using the signed value
    once."""
    key = enclosure_classification.strip().lower()
    if key not in INTERNAL_PRESSURE_COEFFICIENTS:
        raise KeyError(f"'{enclosure_classification}' must be one of "
                        f"{list(INTERNAL_PRESSURE_COEFFICIENTS)}.")
    return INTERNAL_PRESSURE_COEFFICIENTS[key]


def classify_enclosure(opening_area_windward_m2, opening_area_rest_envelope_m2,
                        gross_area_windward_wall_m2, gross_area_rest_envelope_m2):
    """Sec 2.1.3 (definitions) / Sec 2.4.11: classify a building as open,
    partially enclosed, or enclosed from its openings, per the exact
    inequalities BNBC states (mirrored from ASCE 7's own definitions):
      OPEN: Ao >= 0.8 * Ag (at least 80% of any one wall is open)
      PARTIALLY ENCLOSED: Ao > 1.10*Aoi, AND
                           Ao > min(0.37 m2, 0.01*Ag), AND Aoi/Agi <= 0.20
      ENCLOSED: neither of the above
    Ao/Ag are for the wall receiving positive external pressure; Aoi/Agi are
    the sums for the rest of the envelope. If a building satisfies both
    "open" and "partially enclosed" by the letter of the inequalities, Sec
    2.4.11.4 says classify it as OPEN."""
    Ao, Ag = opening_area_windward_m2, gross_area_windward_wall_m2
    Aoi, Agi = opening_area_rest_envelope_m2, gross_area_rest_envelope_m2
    is_open = Ao >= 0.8 * Ag
    is_partially_enclosed = (Ao > 1.10 * Aoi) and (Ao > min(0.37, 0.01 * Ag)) and \
                             (Agi == 0 or Aoi / Agi <= 0.20)
    if is_open:
        return "open"
    if is_partially_enclosed:
        return "partially_enclosed"
    return "enclosed"


# ---------------------------------------------------------------------------
# Sec 2.4.12.2 / Fig 2.4.6 -- External pressure coefficients Cp, MWFRS walls
# ---------------------------------------------------------------------------
WALL_CP = {
    "windward": 0.8,  # all L/B, use with qz (varies with height up the wall)
    # leeward: depends on L/B (building depth / breadth, both normal to wind)
    "side": -0.7,      # use with qh
}


def leeward_wall_cp(L_over_B):
    """Fig 2.4.6 table: leeward wall Cp by L/B (L = along-wind plan
    dimension, B = across-wind plan dimension). 0<=L/B<=1: -0.5;
    L/B=2: -0.3; L/B>=4: -0.2. Linearly interpolated between 1 and 2, and
    between 2 and 4 (the code permits linear interpolation for L/B values
    other than those tabulated)."""
    if L_over_B <= 1:
        return -0.5
    if L_over_B <= 2:
        return -0.5 + (L_over_B - 1) * (-0.3 - -0.5) / (2 - 1)
    if L_over_B <= 4:
        return -0.3 + (L_over_B - 2) * (-0.2 - -0.3) / (4 - 2)
    return -0.2


# Roof Cp (Fig 2.4.6 table), normal-to-ridge case, windward slope -- keyed by
# h/L bracket and roof angle theta (degrees). Two values at some cells mean
# the windward roof slope can see either sign; design for both. This is the
# NORMAL-TO-RIDGE table only (parallel-to-ridge and theta<10 use a separate,
# simpler row in the source table not transcribed here -- flagged, not
# guessed).
ROOF_CP_WINDWARD_NORMAL_TO_RIDGE = {
    # h/L bracket -> {theta_degrees: (Cp_a, Cp_b_or_None)}
    "<0.25": {10: (-0.7, -0.18), 15: (-0.5, 0.0), 20: (-0.3, 0.2), 25: (-0.2, 0.3),
              30: (-0.2, 0.3), 35: (0.0, 0.4), 45: (0.4, None)},
    "0.25-1.0": {10: (-0.9, -0.18), 15: (-0.7, -0.18), 20: (-0.4, 0.0), 25: (-0.3, 0.2),
                 30: (-0.2, 0.2), 35: (-0.2, 0.3), 45: (0.0, 0.4)},
    ">1.0": {10: (-1.3, -0.18), 15: (-1.0, -0.18), 20: (-0.7, -0.18), 25: (-0.5, 0.0),
             30: (-0.3, 0.2), 35: (-0.2, 0.2), 45: (0.0, 0.3)},
}
ROOF_CP_LEEWARD_NORMAL_TO_RIDGE = {
    # h/L bracket -> {theta_degrees_over_10: Cp}  (leeward side, theta>10)
    "<0.25": -0.3, "0.25-1.0": -0.5, ">1.0": -0.6,
}


def roof_h_over_l_bracket(h_over_l):
    if h_over_l < 0.25:
        return "<0.25"
    if h_over_l <= 1.0:
        return "0.25-1.0"
    return ">1.0"


# ---------------------------------------------------------------------------
# Sec 2.4.13.2 -- Design wind pressure, MWFRS, rigid buildings of all heights
# (Eq 2.4.17)
# ---------------------------------------------------------------------------
def design_pressure_mwfrs_rigid(q, qi, G, Cp, GCpi):
    """Eq 2.4.17: p = q*G*Cp - qi*(GCpi), kN/m2. For windward walls, q=qz
    (evaluated at the height in question, varies up the wall); for leeward
    walls/side walls/roof, q=qh (evaluated once at mean roof height h). qi is
    qh for enclosed buildings (both positive and negative internal pressure
    cases); for partially enclosed buildings qi=qz at the highest opening for
    the positive-internal-pressure case specifically (conservatively qi=qh
    is permitted there too, per the code's own text) -- get q and qi from
    velocity_pressure() at the right height for the surface being designed,
    this function just combines them. Apply GCpi (from
    get_internal_pressure_coefficient(), signed) as its own +/- pair of load
    cases, not baked into this call."""
    return q * G * Cp - qi * GCpi


def design_pressure_mwfrs_low_rise(qh, GCpf, GCpi):
    """Eq 2.4.18: the low-rise-building alternative to Eq 2.4.17 -- p =
    qh*(GCpf - GCpi). GCpf (the combined gust-and-pressure coefficient for
    low-rise buildings) comes from Fig 2.4.10's 8-zone/8-load-pattern table,
    which IS fully transcribed below (ROOF_ZONE_GCPF_LOW_RISE) for the
    common flat/near-flat-roof case."""
    return qh * (GCpf - GCpi)


# Fig 2.4.10 -- combined external pressure coefficient GCpf for low-rise
# (h<=18.3m) buildings, by roof angle and the 8 named building-surface zones
# (1,2,3,4,5,6 plus the 1E-4E "end zone" variants used near building
# corners). Transcribed for the flat/near-flat 0-5 degree row, the common
# case for RCC frame buildings with a flat roof; other angle rows exist in
# the source but aren't transcribed here.
ROOF_ZONE_GCPF_LOW_RISE_0_TO_5_DEG = {
    "1": 0.40, "2": -0.69, "3": -0.37, "4": -0.29, "5": -0.45, "6": -0.45,
    "1E": 0.61, "2E": -1.07, "3E": -0.53, "4E": -0.43,
}


# ---------------------------------------------------------------------------
# Sec 2.4.15/2.4.16 -- Other structures and freestanding elements
# (Eq 2.4.27, 2.4.28) -- formula only; Cf force-coefficient figures
# (2.4.20-2.4.23) not transcribed (signs/towers/lattice structures -- outside
# this project's stated RCC-building practice).
# ---------------------------------------------------------------------------
def design_force_freestanding_wall_or_sign(qh, G, Cf, gross_area_m2):
    """Eq 2.4.27: F = qh * G * Cf * As, kN."""
    return qh * G * Cf * gross_area_m2


def design_force_other_structures(qz, G, Cf, projected_area_m2):
    """Eq 2.4.28: F = qz * G * Cf * Af, kN."""
    return qz * G * Cf * projected_area_m2
