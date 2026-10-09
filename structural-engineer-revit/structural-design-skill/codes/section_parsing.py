"""
codes/section_parsing.py — parses section_hint/material.names strings into
numeric properties. A deliberately-duplicated, minimal copy of
structural-analysis's own codes/materials.py (same two functions:
parse_rectangular_section, parse_concrete_grade) -- not imported across
the skill-package boundary, for the same reason documented throughout
this pipeline since dynamic-load. See structural-analysis's materials.py
for the fuller version (including steel material resolution, section
geometric properties, elastic modulus) this skill doesn't need, and for
the original reasoning on why parsing a Revit label string is done at all
in this pipeline (an exception to the usual "flag, don't parse names"
rule) and why a steel designation like 'W12X26' must never be parsed the
way a '300x300' RC section is.
"""
import re


def parse_rectangular_section(section_hint):
    """Identical logic to structural-analysis/codes/materials.py's own
    function of the same name -- see that module for the full reasoning
    and test cases (including the steel-W-shape rejection test)."""
    if not section_hint:
        return None
    m = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*[xX\u00d7]\s*(\d+(?:\.\d+)?)\s*(?:mm)?\s*", section_hint)
    if not m:
        return None
    width, depth = float(m.group(1)), float(m.group(2))
    if not (50 <= width <= 3000 and 50 <= depth <= 3000):
        return None
    return {"width_mm": width, "depth_mm": depth, "shape": "rectangular"}


def parse_concrete_grade(material_names):
    """Identical logic to structural-analysis/codes/materials.py's own
    function of the same name."""
    if not material_names:
        return None
    for name in material_names:
        m = re.search(r"C\s*(\d+)\s*/\s*(\d+)", name)
        if m:
            return {"fck_mpa": float(m.group(1)), "notation": m.group(0)}
    return None
