"""
sdl_estimation.py — compose a slab's super dead load (SDL) from its parts.

IMPORTANT DISTINCTION THIS MODULE IS CAREFUL ABOUT: some of what goes into
SDL is a verified BNBC 2020 value (floor finish weight, ceiling weight,
partition allowance — all traceable to a specific table/section in
codes/bnbc2020/loads.py). Some of it is ordinary engineering practice with
no single code-mandated number (an MEP/services allowance for ducts,
conduit, sprinkler piping distributed as an area load — BNBC Sec 2.2.6 says
to include the *actual* weight of fixed service equipment, but gives no
blanket allowance figure the way it does for partitions). Mixing these two
kinds of number together without labeling which is which is exactly the
kind of thing that causes a design to quietly rely on an assumption nobody
signed off on — so every function here returns its components labeled by
source, not just a combined total.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "codes" / "bnbc2020"))
import loads as bnbc  # noqa: E402

# Common-practice MEP/services allowance range (ducts, conduit, sprinkler
# piping, light fixtures distributed as an area load) — NOT a BNBC table
# value. 0.3-0.5 kN/m2 is a widely used starting assumption for ordinary
# commercial/residential floors pending actual MEP coordination; it is an
# assumption to confirm with the MEP engineer, not a code minimum to cite.
MEP_ALLOWANCE_DEFAULT_KN_M2 = 0.4
MEP_ALLOWANCE_SOURCE = "engineering judgment / common practice — NOT a BNBC 2020 table value, confirm with MEP"


def compose_sdl(floor_finish_key=None, ceiling_key=None, mep_allowance_kn_m2=None,
                 partition_weight_per_m_run_kn=None, waterproofing_kn_m2=None):
    """Every argument is optional — pass only what actually applies to this
    slab. Returns a component breakdown (each tagged with its source) and a
    total, rather than just a number, so a reviewer can see what's actually
    baked into the SDL value without re-deriving it.
    """
    components = []

    if floor_finish_key:
        val = bnbc.FLOOR_FINISH_WEIGHTS_KN_M2.get(floor_finish_key)
        if val is None:
            raise KeyError(f"'{floor_finish_key}' not in FLOOR_FINISH_WEIGHTS_KN_M2 — see that table for valid keys")
        val = val if isinstance(val, (int, float)) else val[1]  # ranges: use the upper (conservative) bound
        components.append({"item": floor_finish_key, "value_kn_m2": val, "source": "BNBC 2020 Table 6.2.2"})

    if ceiling_key:
        val = bnbc.CEILING_WEIGHTS_KN_M2.get(ceiling_key)
        if val is None:
            raise KeyError(f"'{ceiling_key}' not in CEILING_WEIGHTS_KN_M2 — see that table for valid keys")
        components.append({"item": ceiling_key, "value_kn_m2": val, "source": "BNBC 2020 Table 6.2.2"})

    if waterproofing_kn_m2 is not None:
        components.append({"item": "waterproofing", "value_kn_m2": waterproofing_kn_m2,
                            "source": "user-supplied — not a single fixed BNBC table value; membrane/screed buildup varies by system"})

    mep = mep_allowance_kn_m2 if mep_allowance_kn_m2 is not None else MEP_ALLOWANCE_DEFAULT_KN_M2
    components.append({"item": "mep_services_allowance", "value_kn_m2": mep, "source": MEP_ALLOWANCE_SOURCE})

    if partition_weight_per_m_run_kn is not None:
        allowance = bnbc.partition_udl_allowance_kn_m2(partition_weight_per_m_run_kn)
        if allowance is None:
            components.append({
                "item": "partitions", "value_kn_m2": None,
                "source": f"BNBC 2020 Sec 2.2.5 — weight/m run ({partition_weight_per_m_run_kn} kN/m) exceeds the "
                           f"{bnbc.PARTITION_LIGHT_THRESHOLD_KN_PER_M} kN/m light-partition threshold; model as an "
                           f"explicit line load at the partition's actual position instead, not an area allowance",
            })
        else:
            components.append({"item": "partitions", "value_kn_m2": allowance, "source": "BNBC 2020 Sec 2.3.6"})

    total = sum(c["value_kn_m2"] for c in components if c["value_kn_m2"] is not None)
    return {"total_kn_m2": total, "components": components}
