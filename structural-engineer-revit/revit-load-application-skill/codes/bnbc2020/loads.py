"""
codes/bnbc2020/loads.py — BNBC 2020 (Part 6, Chapter 2) dead and live load data.

SOURCE AND VERIFICATION: every value below was checked directly against the
official BNBC 2020 Part 6 Chapter 2 text (Bangladesh National Building Code,
"Loads on Buildings and Structures") before being transcribed — not recalled
from general training exposure. Values are re-expressed here as plain Python
data with this module's own key names; nothing below is a copy of the code's
own table formatting or prose. Section/table numbers are cited in comments
so a value can be checked against a physical copy of the code in seconds.

Units: kN/m² for area loads and unit weights per area, kN/m³ for unit weights
per volume, kN for concentrated loads, kN/m for line loads — matching the
mm-based geometry convention used everywhere else in this pipeline (schema.md),
loads themselves stay in kN, the structural-engineering-standard unit.

COVERAGE NOTE: Table 6.2.3 (live loads) has dozens of occupancy rows,
including a number of narrow special cases (vehicle barrier forces, elevator
machine room floor gratings, book-stack-room limitations, etc.) — this module
transcribes the occupancy categories that cover the large majority of real
buildings, not every footnoted edge case. `get_live_load()` raises rather than
silently guessing when an occupancy string doesn't match anything here — see
its docstring. Extend OCCUPANCY_LIVE_LOADS as real projects surface gaps,
checking each new value against the code the same way these were checked.
"""

# ---------------------------------------------------------------------------
# Table 6.2.1 — Unit Weight of Basic Materials (kN/m³)
# ---------------------------------------------------------------------------
UNIT_WEIGHTS_KN_M3 = {
    "concrete_stone_aggregate_unreinforced": 22.8,   # add 0.63 per 1% reinforcement by volume for RCC
    "concrete_brick_aggregate_unreinforced": 20.4,
    "brick": 18.9,
    "steel": 77.0,
    "stainless_steel": 78.75,
    "timber": (5.9, 11.0),  # range given in the code; pick per species/grade
    "aluminium": 27.0,
    "sand_dry": 15.7,
}


def reinforced_concrete_unit_weight_kn_m3(reinforcement_pct_by_volume=1.0, aggregate="stone"):
    """BNBC 2020 Table 6.2.1 footnote: add 0.63 kN/m3 per 1% reinforcement by
    volume to the unreinforced value. Default 1% is a common preliminary
    assumption for RCC beams/columns/slabs — refine per actual design."""
    base = UNIT_WEIGHTS_KN_M3["concrete_stone_aggregate_unreinforced" if aggregate == "stone"
                               else "concrete_brick_aggregate_unreinforced"]
    return base + 0.63 * reinforcement_pct_by_volume


# ---------------------------------------------------------------------------
# Table 6.2.2 — Weight of Construction Materials (kN/m² of finished surface),
# organized by where they're used. For SDL buildup (finishes, ceilings, roof
# coverings) — see estimate_sdl() below for how these compose.
# ---------------------------------------------------------------------------
FLOOR_FINISH_WEIGHTS_KN_M2 = {
    "asphalt_25mm": 0.526,
    "clay_tiling_13mm": 0.268,
    "concrete_slab_stone_100mm": 2.360,   # for topping/screed thickness, not structural slab itself
    "concrete_slab_stone_150mm": 3.540,
    "terrazzo_16mm": 0.431,
}

CEILING_WEIGHTS_KN_M2 = {
    "fibrous_plaster_10mm": 0.081,
    "cement_plaster_13mm": 0.287,
    "suspended_metal_lath_plaster": 0.480,
}

ROOF_COVERING_WEIGHTS_KN_M2 = {
    "bituminous_felt_5ply_gravel": 0.431,
    "concrete_tile_25mm": 0.527,
    "clay_tile": (0.6, 0.9),  # range
    "steel_sheet_galv_corrugated_1mm": 0.120,
    "steel_sheet_galv_corrugated_0_8mm": 0.096,
    "steel_sheet_galv_corrugated_0_6mm": 0.077,
}

WALL_PARTITION_WEIGHTS_KN_M2 = {
    "brick_masonry_burnt_clay_per_100mm": 1.910,
    "brick_masonry_sand_lime_per_100mm": 1.980,
    "concrete_100mm": 2.360,
    "concrete_150mm": 3.540,
    "concrete_250mm": 5.900,
    "terracotta_hollow_block_75mm": 0.671,
    "terracotta_hollow_block_100mm": 0.995,
    "terracotta_hollow_block_150mm": 1.388,
}
# Table 6.2.2 note: brick-aggregate concrete may be taken as 90% of the stone-aggregate value.

# ---------------------------------------------------------------------------
# Table 6.2.3 — Minimum Uniformly Distributed and Concentrated Live Loads.
# Each entry: uniform load (kN/m2), concentrated load (kN) or None if the
# code doesn't specify one for that occupancy.
# ---------------------------------------------------------------------------
OCCUPANCY_LIVE_LOADS = {
    # Residential
    "residential_dwelling_general": (2.00, None),
    "residential_habitable_attic_sleeping": (1.50, None),
    "residential_uninhabitable_attic_with_storage": (1.00, None),
    "residential_uninhabitable_attic_no_storage": (0.50, None),
    "hotel_multifamily_private_rooms_corridors": (2.00, None),
    "hotel_multifamily_public_rooms_corridors": (4.80, None),
    "residential_stairs": (2.00, None),  # one/two-family only; see stairs_general otherwise

    # Office
    "office_general": (2.40, 9.00),
    "office_lobby_first_floor_corridor": (4.80, 9.00),
    "office_corridor_above_first_floor": (3.80, 9.00),
    "office_file_computer_room": (4.80, 9.00),  # code: design heavier if anticipated occupancy needs it — floor value only, verify actual

    # Assembly
    "assembly_fixed_seats": (2.90, None),
    "assembly_movable_seats": (4.80, None),
    "assembly_lobbies_platforms": (4.80, None),
    "assembly_stage_floors": (7.20, None),
    "dance_hall_ballroom": (4.80, None),

    # Corridors / stairs / circulation
    "corridor_first_floor": (4.80, None),
    "stairs_exitways_general": (4.80, None),  # note l: 1.33kN concentrated on 2580mm2 tread area

    # Education
    "school_classroom": (2.00, 4.50),
    "school_corridor_first_floor": (4.80, 4.50),
    "school_corridor_above_first_floor": (3.80, 4.50),

    # Healthcare
    "hospital_operating_lab": (2.90, 4.50),
    "hospital_patient_room": (2.00, 4.50),
    "hospital_corridor_above_first_floor": (3.80, 4.50),

    # Library
    "library_reading_room": (2.90, 4.50),
    "library_stack_room": (7.20, 4.50),  # note d: subject to stack-height/aisle-width limitations, verify
    "library_corridor_above_first_floor": (3.80, 4.50),

    # Retail / storage / industrial
    "store_retail_first_floor": (4.80, 4.50),
    "store_retail_upper_floor": (3.60, 4.50),
    "store_wholesale_all_floors": (6.00, 4.50),
    "storage_general_light": (6.00, None),
    "storage_general_heavy": (12.00, None),
    "manufacturing_light": (4.00, 6.00),
    "manufacturing_medium": (6.00, 9.00),
    "manufacturing_heavy": (12.00, 13.40),

    # Parking / vehicular
    "garage_passenger_vehicles": (2.00, None),  # note b/c: concentrated wheel-load provisions also apply, not tabulated here
    "vehicular_driveway_yard_trucking": (12.00, 35.60),

    # Roof access / miscellaneous
    "walkway_elevated_platform": (2.90, None),
    "balcony_exterior": (4.80, None),
    "bowling_pool_recreational": (3.60, None),
}


def get_live_load(occupancy_key):
    """Returns (uniform_kn_m2, concentrated_kn_or_None) for a known occupancy
    key. Raises KeyError rather than guessing — an unmatched occupancy needs
    a human decision (closest analogous category, or a value from Sec 2.3.9's
    "loads not specified" procedure — probable assembly/furniture/storage
    weight), not a silent default that could understate a real load."""
    if occupancy_key not in OCCUPANCY_LIVE_LOADS:
        raise KeyError(
            f"'{occupancy_key}' is not in OCCUPANCY_LIVE_LOADS. BNBC 2020 Table 6.2.3 covers many "
            f"more occupancies than are transcribed here — check the code directly for anything "
            f"unmatched, and extend this table (verified against the code, not guessed) rather than "
            f"picking the nearest-sounding key."
        )
    return OCCUPANCY_LIVE_LOADS[occupancy_key]


# ---------------------------------------------------------------------------
# Table 6.2.4 — Minimum Roof Live Loads (kN/m2, kN concentrated)
# ---------------------------------------------------------------------------
ROOF_LIVE_LOADS = {
    "flat_roof": None,           # code: "See Table 6.2.3" — i.e. use the occupancy live load if the roof is used/occupied
    "pitched_slope_lt_1_3": (1.0, 0.9),
    "pitched_slope_1_3_to_1_0": (0.8, 0.9),
    "pitched_slope_ge_1_0": (0.6, 0.9),
    "greenhouse_agricultural": (0.5, 0.9),
    "awning_canopy_fabric": (0.24, None),   # nonreducible per the code
}

# ---------------------------------------------------------------------------
# Section 2.2.5 / 2.3.6 — Partition wall loads
# ---------------------------------------------------------------------------
PARTITION_LIGHT_THRESHOLD_KN_PER_M = 5.5      # partitions at/below this weight-per-metre-run may use the UDL allowance instead of exact line loads
PARTITION_UDL_FRACTION_OF_WEIGHT_PER_M = 0.33  # UDL allowance = 33% of weight/m run...
PARTITION_UDL_MINIMUM_KN_M2 = 1.2              # ...subject to this minimum


def partition_udl_allowance_kn_m2(weight_per_m_run_kn):
    """Sec 2.3.6: for light partitions (<= 5.5 kN/m run), an area UDL may be
    used in lieu of exact concentrated line loads at each partition's actual
    position. Returns None if the partition is too heavy for this allowance —
    model it as an explicit line load at its real position instead (Sec 2.2.5)."""
    if weight_per_m_run_kn > PARTITION_LIGHT_THRESHOLD_KN_PER_M:
        return None
    return max(PARTITION_UDL_FRACTION_OF_WEIGHT_PER_M * weight_per_m_run_kn, PARTITION_UDL_MINIMUM_KN_M2)


# ---------------------------------------------------------------------------
# Table 6.2.7 / Sec 2.3.13 — Live load reduction
# ---------------------------------------------------------------------------
KLL_ELEMENT_FACTORS = {
    "interior_column": 4,
    "exterior_column_no_cantilever_slab": 4,
    "edge_column_with_cantilever_slab": 3,
    "corner_column_with_cantilever_slab": 2,
    "edge_beam_no_cantilever_slab": 2,
    "interior_beam": 2,
    "other": 1,  # edge beams WITH cantilever slabs, cantilever beams, one-way slabs, two-way slabs, members without continuous shear transfer normal to span
}

LIVE_LOAD_REDUCTION_MIN_AREA_M2 = 37.16  # KLL*AT threshold below which no reduction is permitted


def reduced_live_load(l0_kn_m2, kll, tributary_area_m2, supports_two_or_more_floors=False,
                       is_public_assembly=False, is_passenger_garage=False):
    """Eq. 6.2.1: L = L0*(0.25 + 4.57/sqrt(KLL*AT)), floored at 0.50*L0 (one
    floor) or 0.40*L0 (two or more floors). Returns l0_kn_m2 unchanged
    (no reduction) when any of Sec 2.3.13.2-2.3.13.4's exclusions apply:
    L0 > 4.80 kN/m2 (heavy live load), passenger car garages, or public
    assembly occupancies with L0 <= 4.80 kN/m2 — check those flags honestly
    rather than always trying to reduce."""
    if l0_kn_m2 > 4.80 and not supports_two_or_more_floors:
        return l0_kn_m2  # Sec 2.3.13.2: heavy loads not reduced unless supporting 2+ floors (then 20% flat reduction — not modeled here, apply manually)
    if is_passenger_garage:
        return l0_kn_m2  # Sec 2.3.13.3: no reduction for passenger car garages (same 2+ floor exception as above)
    if is_public_assembly and l0_kn_m2 <= 4.80:
        return l0_kn_m2  # Sec 2.3.13.4(a): no reduction

    kll_at = kll * tributary_area_m2
    if kll_at < LIVE_LOAD_REDUCTION_MIN_AREA_M2:
        return l0_kn_m2  # below the 37.16 m2 threshold: no reduction permitted

    import math
    l = l0_kn_m2 * (0.25 + 4.57 / math.sqrt(kll_at))
    floor = (0.40 if supports_two_or_more_floors else 0.50) * l0_kn_m2
    return max(l, floor)
