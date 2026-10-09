"""
occupancy_mapping.py — classify a Room/Space's occupancy from whatever the
model actually gives you: an explicit Revit Occupancy/Department parameter
if the office filled one in (strong signal), or the room name (medium
signal, pattern-matched) if not. Same philosophy as
revit-structure-recognition's classifiers: multi-signal, confidence-scored,
flag rather than force a guess when nothing matches.

Room naming conventions vary a lot by office and by project language —
ROOM_NAME_PATTERNS below covers common English-language conventions and is
explicitly meant to be extended per-project, not treated as exhaustive.
"""
import re

# Ordered: first matching pattern wins. Keys match codes/bnbc2020/loads.py's
# OCCUPANCY_LIVE_LOADS keys exactly, so a successful match is immediately
# usable there with no further translation step.
ROOM_NAME_PATTERNS = [
    (r"\b(bedroom|living|dining|family\s*room|kitchen)\b", "residential_dwelling_general"),
    (r"\b(apartment|flat|unit)\b", "residential_dwelling_general"),
    (r"\b(attic)\b.*\b(storage|store)\b", "residential_uninhabitable_attic_with_storage"),
    (r"\battic\b", "residential_uninhabitable_attic_no_storage"),
    (r"\bhotel\s*room\b|\bguest\s*room\b", "hotel_multifamily_private_rooms_corridors"),

    (r"\boffice\b(?!.*(lobby|corridor))", "office_general"),
    (r"\b(server|it|computer)\s*room\b", "office_file_computer_room"),
    (r"\blobby\b", "office_lobby_first_floor_corridor"),
    (r"\bcorridor\b|\bhallway\b|\bpassage\b", "office_corridor_above_first_floor"),  # first-floor vs upper needs the story context, not just the name — see classify_room_occupancy()

    (r"\b(auditorium|hall|assembly)\b", "assembly_movable_seats"),
    (r"\btheat(er|re)\b|\bcinema\b", "assembly_fixed_seats"),
    (r"\bstage\b", "assembly_stage_floors"),
    (r"\b(ballroom|dance)\b", "dance_hall_ballroom"),

    (r"\b(class\s*room|classroom)\b", "school_classroom"),
    (r"\b(lab|laboratory)\b", "hospital_operating_lab"),  # generic lab defaults to the higher hospital-lab value pending a more specific category — flag for review, see classify_room_occupancy
    (r"\b(operat(ing|ion)\s*room|OT\b)\b", "hospital_operating_lab"),
    (r"\bpatient\b|\bward\b", "hospital_patient_room"),

    (r"\b(library|reading\s*room)\b", "library_reading_room"),
    (r"\bstack\s*room\b|\bbook\s*stack\b", "library_stack_room"),

    (r"\b(retail|shop)\b", "store_retail_first_floor"),
    (r"\bwarehouse\b|\bgodown\b", "storage_general_heavy"),
    (r"\bstorage\b|\bstore\s*room\b", "storage_general_light"),

    (r"\b(factory|manufactur\w*)\b", "manufacturing_medium"),  # can't infer light/medium/heavy from a name alone — flag for review, see classify_room_occupancy

    (r"\b(parking|garage|car\s*park)\b", "garage_passenger_vehicles"),

    (r"\bstair\b|\bstaircase\b", "stairs_exitways_general"),
    (r"\b(balcony|veranda)\b", "balcony_exterior"),
    (r"\bgym\b|\bbowling\b|\bpool\s*room\b", "bowling_pool_recreational"),
]

# Occupancy keys that are a coarse guess even on a name match — the pattern
# matched something real, but the code has finer-grained categories this
# module can't distinguish from the name alone. Always flag these for review
# regardless of match confidence otherwise.
INHERENTLY_AMBIGUOUS_KEYS = {
    "hospital_operating_lab",         # "lab" alone doesn't distinguish a school/research lab from a hospital OT
    "manufacturing_medium",           # light/medium/heavy needs actual process info, not just "factory"
    "office_corridor_above_first_floor",  # BNBC's corridor value depends on which storey — name alone can't tell
}


def classify_room_occupancy(room_name, explicit_occupancy_param=None, story_index=None):
    """Returns {"value": <occupancy key or None>, "confidence": "high"|"medium"|"low",
    "signals": [...]}. `value` is a key into codes.bnbc2020.loads.OCCUPANCY_LIVE_LOADS
    when matched — pass it straight to get_live_load()."""
    signals = []

    if explicit_occupancy_param:
        # The office's own stated intent — closest thing to ground truth here,
        # but still needs mapping onto an actual OCCUPANCY_LIVE_LOADS key,
        # which this function doesn't attempt to guess at from an arbitrary
        # free-text parameter value — that mapping is a one-time per-office
        # lookup table worth building once real parameter values are seen.
        signals.append(f"explicit occupancy parameter = '{explicit_occupancy_param}' (not auto-mapped to a load-table key yet — see docstring)")

    name = (room_name or "").lower()
    for pattern, key in ROOM_NAME_PATTERNS:
        if re.search(pattern, name, re.I):
            signals.append(f"room name '{room_name}' matches pattern for '{key}'")
            confidence = "medium"
            if key == "office_corridor_above_first_floor" and story_index == 0:
                key = "corridor_first_floor"
                signals.append("story_index=0 -> using first-floor corridor value instead")
            elif key in INHERENTLY_AMBIGUOUS_KEYS:
                confidence = "low"
                signals.append(f"'{key}' is inherently ambiguous from a name alone — see INHERENTLY_AMBIGUOUS_KEYS")
            return {"value": key, "confidence": confidence, "signals": signals}

    signals.append(f"no pattern matched room name '{room_name}'" if room_name else "no room name or occupancy parameter available")
    return {"value": None, "confidence": "low", "signals": signals}
