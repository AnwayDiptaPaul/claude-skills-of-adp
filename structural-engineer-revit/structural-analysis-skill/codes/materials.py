"""
codes/materials.py — parses revit-structure-recognition's section_hint and
material.names strings into numeric section/material properties usable by
an actual FE model (openseespy).

WHY THIS IS NEEDED, AND WHY IT'S AN EXCEPTION TO THIS PIPELINE'S USUAL RULE:
structural_model.json carries section_hint ("300x300") and material.names
("Concrete C30/37") as plain strings -- Revit family-type labels passed
through, not validated numeric fields. Every other skill in this suite
treats a string like this as something to flag rather than parse (matching
revit-load-application's own occupancy_mapping.py caveat about name-pattern
matching being fragile). This module is the one deliberate exception:
building any FE model at all requires SOME numeric section/material
properties, and BNBC's own section_hint convention (WIDTHxDEPTH in mm,
confirmed by revit-structure-recognition's own classification signal --
"object_type matches '\\d+x\\d+.*Column'" -- in its own schema.md) is
specific and narrow enough to parse reliably for the common rectangular
case. Anything that doesn't match the expected pattern is flagged, never
silently defaulted.

CONCRETE ELASTIC MODULUS -- NOT YET VERIFIED AGAINST BNBC'S OWN TEXT: BNBC
2020's concrete design chapter (Part 6, likely a "Concrete Structures"
chapter distinct from Chapter 2) has not been researched by this pipeline
-- everything verified so far is Chapter 2 (loads: dead/live/wind/
earthquake). Ec below uses the ACI 318 formula (Ec = 4700*sqrt(fck) MPa,
normal-weight concrete), which is extremely widely used and BNBC's
concrete chapter is very likely ACI-based given the rest of Part 6's clear
ACI/ASCE lineage (already confirmed for the load chapter) -- but this is a
reasonable, commonly-used default, not a value checked against BNBC's own
text the way every load-code number elsewhere in this pipeline has been.
Flagged via resolve_material()'s own "source" field; confirm against BNBC
Part 6's actual concrete chapter before this matters for a stamped drawing.
"""
import re

STEEL_E_MPA = 200_000.0    # universal physical constant, not code-specific
STEEL_G_MPA = 77_000.0     # ~E/(2*(1+0.3)), nu=0.3 for standard structural steel
STEEL_UNIT_WEIGHT_KN_M3 = 78.5
CONCRETE_POISSON_RATIO = 0.20         # commonly used for normal-weight concrete; not yet BNBC-verified
CONCRETE_UNIT_WEIGHT_KN_M3 = 24.0     # BNBC Table 6.2.1 -- already verified in revit-load-application's loads.py


def parse_rectangular_section(section_hint):
    """Parses a 'WIDTHxDEPTH' style section_hint (mm) into
    {'width_mm':, 'depth_mm':, 'shape': 'rectangular'}. Returns None --
    never a guessed default -- for anything that doesn't cleanly match:
    circular sections ('D400'/'400dia'), steel designations that reuse an
    'NxM'-shaped look but mean something else entirely (e.g. 'W12X26' is
    nominal depth in inches / weight in lb-per-ft, NOT width x depth in mm
    -- silently parsing that as a rectangular RC section would be a real,
    dangerous error, not a harmless approximation), or a hint that's
    missing, blank, or outside a sane size range."""
    if not section_hint:
        return None
    m = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*[xX\u00d7]\s*(\d+(?:\.\d+)?)\s*(?:mm)?\s*", section_hint)
    if not m:
        return None
    width, depth = float(m.group(1)), float(m.group(2))
    # A 'section' under 50mm or over 3000mm on either side is far more
    # likely a misparsed non-rectangular designation than a real RC
    # section -- flag rather than accept silently.
    if not (50 <= width <= 3000 and 50 <= depth <= 3000):
        return None
    return {"width_mm": width, "depth_mm": depth, "shape": "rectangular"}


def rectangular_section_properties(width_mm, depth_mm):
    """Pure geometry -- area and both principal moments of inertia for a
    solid rectangle. Not code data (no 'verify against BNBC' caveat needed
    -- closed-form mechanics of materials, the same for every code)."""
    A = width_mm * depth_mm
    Iz = width_mm * depth_mm ** 3 / 12.0   # strong axis (bending about z, in-plane of depth)
    Iy = depth_mm * width_mm ** 3 / 12.0   # weak axis
    # Saint-Venant torsional constant, standard rectangular-section
    # engineering approximation (exact only for a square; the accepted
    # practice approximation otherwise):
    a, b = max(width_mm, depth_mm), min(width_mm, depth_mm)
    beta = 1.0 / 3.0 - 0.21 * (b / a) * (1.0 - (b / a) ** 4 / 12.0)
    J = beta * a * b ** 3
    return {"A_mm2": A, "Iz_mm4": Iz, "Iy_mm4": Iy, "J_mm4": J}


def parse_concrete_grade(material_names):
    """Parses Eurocode-style 'C30/37' concrete grade notation (cylinder/
    cube characteristic strength, MPa) from a material.names list. Returns
    {'fck_mpa':, 'notation': 'C30/37'} or None. This is the exact notation
    revit-structure-recognition's own documented example uses; a project
    using a different convention (bare "fc'=21 MPa", ACI-style "4000 psi")
    needs its own parse path, not a force-fit into this one -- returning
    None rather than guessing keeps that honest."""
    if not material_names:
        return None
    for name in material_names:
        m = re.search(r"C\s*(\d+)\s*/\s*(\d+)", name)
        if m:
            return {"fck_mpa": float(m.group(1)), "notation": m.group(0)}
    return None


def concrete_elastic_modulus_mpa(fck_mpa):
    """Ec = 4700*sqrt(fck) MPa (ACI 318, normal-weight concrete). See
    module docstring: a widely-used default, not yet checked against BNBC
    Part 6's own concrete chapter."""
    return 4700.0 * fck_mpa ** 0.5


def resolve_material(material_block, frame_type_value):
    """Given an element's material dict and frame_type.value ('RCC',
    'Steel', ...), returns {'E_mpa':, 'G_mpa':, 'unit_weight_kn_m3':,
    'source':...} on success. On failure, returns {'reason': ...} instead
    -- callers must check for that key, not assume every element resolves."""
    names = (material_block or {}).get("names", [])
    ft = (frame_type_value or "").strip().lower()
    if ft in ("rcc", "concrete", "reinforced concrete"):
        grade = parse_concrete_grade(names)
        if grade is None:
            return {"reason": f"material.names={names} has no parseable Cxx/yy grade -- "
                               f"cannot derive Ec without a characteristic strength"}
        E = concrete_elastic_modulus_mpa(grade["fck_mpa"])
        G = E / (2 * (1 + CONCRETE_POISSON_RATIO))
        return {"E_mpa": E, "G_mpa": G, "unit_weight_kn_m3": CONCRETE_UNIT_WEIGHT_KN_M3,
                "fck_mpa": grade["fck_mpa"],
                "source": f"parsed:{grade['notation']}, Ec=4700*sqrt(fck) (ACI 318, not yet BNBC-verified)"}
    if ft == "steel":
        return {"E_mpa": STEEL_E_MPA, "G_mpa": STEEL_G_MPA, "unit_weight_kn_m3": STEEL_UNIT_WEIGHT_KN_M3,
                "source": "steel default (universal physical constant, not code-specific)"}
    return {"reason": f"frame_type '{frame_type_value}' is not 'RCC'/'Concrete' or 'Steel' -- "
                       f"no material resolution path implemented for this type"}
