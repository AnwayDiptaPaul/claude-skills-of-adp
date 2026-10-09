#!/usr/bin/env python3
"""
apply_dynamic_loads.py — the entry point for this skill. Reads a
structural_model.json (from revit-structure-recognition, already carrying
revit-load-application's `loads` section) and a site_seismic_wind_input.json
(see references/site_seismic_wind_input_format.md), computes BNBC 2020
equivalent-static seismic story forces per orthogonal direction and MWFRS
wind pressures per story, and writes an enriched structural_model.json with
the `dynamic_loads` section populated.

Usage:
    python3 apply_dynamic_loads.py --structural-model structural_model.json \
        --site-input site_seismic_wind_input.json --out output_dir/

SCOPE: the equivalent-static force procedure (ESFP) for seismic, and the
MWFRS analytical procedure (Method 2) for wind, for regular-enough buildings
where those procedures are code-permitted. Response spectrum modal analysis,
linear/nonlinear time history, and nonlinear static (pushover) all need an
actual stiffness model (an eigenvalue solve, at minimum) that this
load-application-stage skill doesn't have — see SKILL.md's Known
Limitations. When dynamic analysis is REQUIRED (not just permitted) per Sec
2.5.8.1, this script still produces the ESFP numbers (RSA's own base shear
gets checked against 85% of them per Sec 2.5.9.4, so they're needed either
way) but flags the result into needs_review rather than presenting ESFP
alone as sufficient.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "codes" / "bnbc2020"))
import seismic as sm   # noqa: E402
import wind as wd      # noqa: E402


def _stories_sorted(structural_model):
    return sorted(structural_model.get("stories", []), key=lambda s: s["elevation_mm"])


# ---------------------------------------------------------------------------
# Seismic
# ---------------------------------------------------------------------------
def compute_seismic(structural_model, site_input, needs_review):
    stories = _stories_sorted(structural_model)
    if not stories:
        needs_review.append({"reason": "no stories found in structural_model -- seismic not computed"})
        return None

    heights_m = [s["elevation_mm"] / 1000.0 for s in stories]
    building_height_m = heights_m[-1]

    # --- shared (building-wide) inputs ---
    location = site_input.get("location")
    Z = site_input.get("zone_coefficient_Z_override")
    if Z is None:
        if not location:
            needs_review.append({"reason": "no location or zone_coefficient_Z_override -- seismic not computed"})
            return None
        try:
            Z = sm.get_zone_coefficient(location)
        except KeyError as e:
            needs_review.append({"reason": f"seismic zone lookup failed: {e}"})
            return None

    zone = next((z for z, d in sm.ZONE_DESCRIPTIONS.items() if d["coefficient_Z"] == Z), None)
    if zone is None:
        needs_review.append({"reason": f"Z={Z} doesn't match any of the four standard zone coefficients "
                                        f"(0.12/0.20/0.28/0.36) -- seismic design category and the dynamic-"
                                        f"analysis-required threshold both need a zone NUMBER (1-4), not just Z. "
                                        f"Seismic not computed."})
        return None

    site_class = site_input.get("site_class")
    if not site_class and site_input.get("site_class_inputs"):
        site_class = sm.classify_site_class(**site_input["site_class_inputs"])
    if not site_class or site_class not in sm.SITE_CLASS_PARAMETERS:
        needs_review.append({"reason": f"no usable site_class (got {site_class!r}) -- SE/S1/S2 need a "
                                        f"site-specific spectrum per Sec 2.5.4.3, not this module's table "
                                        f"lookup. Seismic not computed."})
        return None

    occupancy_category = site_input.get("occupancy_category")
    if not occupancy_category:
        needs_review.append({"reason": "no occupancy_category -- seismic not computed"})
        return None
    I = sm.get_seismic_importance_factor(occupancy_category)
    sdc = sm.seismic_design_category(site_class, zone, occupancy_category)
    damping_pct = site_input.get("damping_pct", 5.0)

    is_regular = site_input.get("is_regular")
    if is_regular is None:
        needs_review.append({"reason": "is_regular not supplied -- defaulted to True for the "
                                        "dynamic-analysis-required check; verify against Sec 2.5.5.3's "
                                        "irregularity types before trusting that check"})
        is_regular = True

    has_independent_orthogonal_systems = site_input.get("has_independent_orthogonal_systems")
    if has_independent_orthogonal_systems is None:
        needs_review.append({"reason": "has_independent_orthogonal_systems not supplied -- defaulted "
                                        "to False (conservative: requires a 3D RSA/LTHA/NTHA model) "
                                        "per Sec 2.5.9.1; confirm before assuming independent 2D "
                                        "models per direction are permitted instead"})
        has_independent_orthogonal_systems = False
    needs_3d_model = sm.requires_3d_model(is_regular, has_independent_orthogonal_systems)

    # --- seismic weight, per story ---
    weight_lookup = {w["story_index"]: w for w in site_input.get("story_seismic_weights", [])}
    story_weights_kn = []
    for s in stories:
        w_in = weight_lookup.get(s["index"])
        if not w_in:
            needs_review.append({"story": s["name"], "reason": "no story_seismic_weights entry -- "
                                                                 "contributes 0 to seismic weight"})
            story_weights_kn.append(0.0)
            continue
        story_weights_kn.append(sm.seismic_weight_kn(
            w_in.get("dead_load_kn", 0.0), w_in.get("sdl_kn", 0.0),
            w_in.get("live_load_kn", 0.0), w_in.get("live_load_intensity_kn_m2", 0.0)))
    total_weight_kn = sum(story_weights_kn)
    if total_weight_kn <= 0:
        needs_review.append({"reason": "total seismic weight is zero -- story_seismic_weights is "
                                        "missing or empty. Seismic not computed."})
        return None

    shared_inputs = {
        "location": location, "zone": zone, "zone_coefficient_Z": Z,
        "site_class": site_class, "site_class_source": site_input.get("site_class_source"),
        "occupancy_category": occupancy_category, "importance_factor_I": I,
        "seismic_design_category": sdc, "damping_pct": damping_pct,
        "seismic_weight_kn": round(total_weight_kn, 1),
        "is_regular": is_regular,
        "has_independent_orthogonal_systems": has_independent_orthogonal_systems,
        "requires_3d_dynamic_model": needs_3d_model,
    }

    # --- per-direction results ---
    result = {"method": site_input.get("analysis_method", "equivalent_static"),
              "shared_inputs": shared_inputs}
    structural_systems_in = site_input.get("structural_system") or {}
    period_types_in = site_input.get("period_structure_type") or {}

    for direction in ("x_direction", "y_direction"):
        system_key = structural_systems_in.get(direction)
        if not system_key:
            needs_review.append({"reason": f"no structural_system.{direction} -- that direction's "
                                            f"seismic forces not computed"})
            result[direction] = None
            continue
        try:
            sys_props = sm.get_structural_system(system_key, sdc)
        except (KeyError, ValueError) as e:
            needs_review.append({"reason": f"{direction}: {e}"})
            result[direction] = None
            continue

        R, Cd, Omega0 = sys_props["R"], sys_props["Cd"], sys_props["Omega0"]
        if R < I:
            needs_review.append({"reason": f"{direction}: R={R} < I={I} for '{system_key}' -- the code "
                                            f"states R/I must not exceed 1 (i.e. R must be >= I)"})

        period_type = period_types_in.get(direction, "concrete_moment_resisting_frame")
        Ta = sm.approximate_period(building_height_m, period_type)
        T_ceiling = sm.computed_period_upper_bound(Ta)
        Sa = sm.design_spectral_acceleration(Ta, Z, I, R, site_class, damping_pct)
        V = sm.base_shear(Sa, total_weight_kn)
        k = sm.vertical_distribution_exponent(Ta)
        Fx = sm.vertical_distribution(V, story_weights_kn, heights_m, k)
        Vx_base_to_top = list(reversed(sm.story_shear(list(reversed(Fx)))))

        story_forces = []
        for i, s in enumerate(stories):
            perp_dim = s.get("perpendicular_dimension_m")
            mta = sm.accidental_torsional_moment(Fx[i], perp_dim) if perp_dim else None
            if mta is None:
                needs_review.append({"story": s["name"], "reason": f"{direction}: no "
                                      f"perpendicular_dimension_m on this story -- accidental "
                                      f"torsional moment not computed"})
            story_forces.append({
                "story_index": s["index"], "elevation_m": round(heights_m[i], 3),
                "weight_kn": round(story_weights_kn[i], 1), "Fx_kn": round(Fx[i], 2),
                "story_shear_Vx_kn": round(Vx_base_to_top[i], 2),
                "accidental_torsion_kn_m": round(mta, 2) if mta is not None else None,
                "overturning_moment_kn_m": round(sm.overturning_moment_at_level(Fx, heights_m, i), 2),
            })

        dyn_required = sm.dynamic_analysis_required(building_height_m, zone, is_regular)
        static_ok = sm.static_analysis_permitted(Ta, sm.SITE_CLASS_PARAMETERS[site_class]["TC_s"], is_regular)
        if dyn_required:
            needs_review.append({"reason": f"{direction}: dynamic_analysis_required=True "
                                  f"(height={building_height_m:.1f}m, zone={zone}, regular={is_regular}) "
                                  f"-- ESFP alone is not sufficient per Sec 2.5.8.1; RSA or time-history "
                                  f"is needed once structural-analysis exists to provide modal properties"})
        elif not static_ok:
            needs_review.append({"reason": f"{direction}: static_analysis_permitted=False "
                                  f"(T={Ta:.3f}s vs the Sec 2.5.6 limit, or elevation irregularity) -- "
                                  f"ESFP results here are for reference only, not code-compliant on "
                                  f"their own"})

        # The advanced-analysis "system": everything Sec 2.5.9-2.5.11 need
        # once structural-analysis has a real modal solve, built from
        # verified formulas/criteria (codes/bnbc2020/seismic.py) -- not the
        # eigenvalue/time-stepping solve itself, which needs the stiffness
        # model this skill doesn't build. Ta (approximate) stands in for the
        # real period here; structural-analysis should re-derive
        # ltha_ground_motion_criteria()/ntha_ground_motion_criteria() against
        # its own computed T once available, not treat this Ta-based window
        # as final.
        rsa = sm.rsa_system(Z, I, R, Cd, site_class, esfp_base_shear_kn=V, damping_pct=damping_pct)
        dimension = "3D" if needs_3d_model else "2D"
        ltha_criteria = sm.ltha_ground_motion_criteria(Ta, analysis_dimension=dimension)
        ntha_curve = sm.ntha_real_design_spectrum_curve(Z, site_class, damping_pct)
        ntha_criteria = sm.ntha_ground_motion_criteria(Ta, analysis_dimension=dimension)

        result[direction] = {
            "structural_system": system_key, "R": R, "Omega0": Omega0, "Cd": Cd,
            "period": {"structure_type": period_type, "approximate_Ta_sec": round(Ta, 4),
                       "computed_period_ceiling_sec": round(T_ceiling, 4),
                       "used_T_sec": round(Ta, 4), "source": "approximate"},
            "design_spectral_acceleration_Sa_g": round(Sa, 5),
            "base_shear_kn": round(V, 2),
            "vertical_distribution_exponent_k": round(k, 4),
            "story_forces": story_forces,
            "dynamic_analysis_required": dyn_required,
            "static_analysis_permitted": static_ok,
            "rsa": rsa,
            "ltha": {"ground_motion_criteria": ltha_criteria,
                     "note": "target spectrum is rsa.design_spectrum_g (same Sa(T) curve, "
                              "not recomputed) -- Sec 2.5.10.2 matches records against the "
                              "same design response spectrum RSA uses"},
            "ntha": {"real_design_spectrum_g": ntha_curve, "ground_motion_criteria": ntha_criteria},
        }

    return result


# ---------------------------------------------------------------------------
# Wind
# ---------------------------------------------------------------------------
def compute_wind(structural_model, site_input, needs_review):
    stories = _stories_sorted(structural_model)
    if not stories:
        needs_review.append({"reason": "no stories found in structural_model -- wind not computed"})
        return None
    heights_m = [s["elevation_mm"] / 1000.0 for s in stories]
    mean_roof_height_m = heights_m[-1]

    wind_in = site_input.get("wind") or {}
    exposure = wind_in.get("exposure_category")
    V_ms = wind_in.get("basic_wind_speed_v_ms_override")
    I_wind = wind_in.get("importance_factor_I_override")
    Kd = wind_in.get("directionality_factor_Kd_override")
    kz_lookup = {e["story_index"]: e["Kz"] for e in (wind_in.get("kz_by_story_override") or [])}

    missing = [name for name, val in (("basic_wind_speed_v_ms_override", V_ms),
                                       ("importance_factor_I_override", I_wind),
                                       ("directionality_factor_Kd_override", Kd)) if val is None]
    if missing:
        needs_review.append({"reason": f"wind.{', wind.'.join(missing)} not supplied -- these tables "
                                        f"(2.4.1/2.4.2/2.4.5) aren't populated in codes/bnbc2020/wind.py "
                                        f"(see its KNOWN GAPS); wind pressures cannot be computed until "
                                        f"an engineer supplies verified values"})
    if not kz_lookup:
        needs_review.append({"reason": "wind.kz_by_story_override not supplied -- Table 2.4.4 isn't "
                                        "populated in codes/bnbc2020/wind.py; wind pressures cannot be "
                                        "computed until an engineer supplies Kz per story height"})

    enclosure = wind_in.get("enclosure_classification")
    if not enclosure:
        openings = wind_in.get("opening_areas_m2") or {}
        if all(k in openings for k in ("windward_wall", "rest_of_envelope")) and \
           all(openings.get(k) is not None for k in ("windward_wall", "rest_of_envelope")):
            needs_review.append({"reason": "enclosure classification needs gross wall areas too "
                                            "(wind.classify_enclosure()'s full signature) -- only "
                                            "opening areas were supplied; enclosure not classified"})
        else:
            needs_review.append({"reason": "no wind.enclosure_classification and insufficient opening "
                                            "area data -- defaulting to 'enclosed' for the formula "
                                            "structure below, but this is a real classification an "
                                            "engineer needs to confirm"})
        enclosure = "enclosed"
    GCpi = wd.get_internal_pressure_coefficient(enclosure)

    plan = wind_in.get("plan_dimensions_m") or {}
    L, B = plan.get("L_along_wind"), plan.get("B_across_wind")
    if L and B:
        cp_leeward = wd.leeward_wall_cp(L / B)
    else:
        cp_leeward = None
        needs_review.append({"reason": "wind.plan_dimensions_m not supplied -- leeward wall Cp "
                                        "(depends on L/B) not computed"})

    G = wd.gust_effect_factor_rigid()
    Kzt = 1.0  # Sec 2.4.9.1's hill/ridge/escarpment conditions assumed not applicable -- flag if they are
    if wind_in.get("topographic_conditions_apply"):
        needs_review.append({"reason": "topographic_conditions_apply=True but topographic_factor() "
                                        "needs Fig 2.4.4's K1/K2/K3 hill-shape tables (not transcribed) "
                                        "-- Kzt left at 1.0, which is NOT conservative here"})

    can_compute = not missing and kz_lookup
    story_pressures = []
    for s in stories:
        idx = s["index"]
        entry = {"story_index": idx, "elevation_m": round(s["elevation_mm"] / 1000.0, 3),
                  "qz_kn_m2": None, "p_windward_kn_m2": None, "p_leeward_kn_m2": None,
                  "p_side_kn_m2": None}
        if can_compute and idx in kz_lookup:
            qz = wd.velocity_pressure(kz_lookup[idx], Kzt, Kd, V_ms, I_wind)
            qh = wd.velocity_pressure(kz_lookup.get(stories[-1]["index"], kz_lookup[idx]), Kzt, Kd, V_ms, I_wind)
            entry["qz_kn_m2"] = round(qz, 4)
            entry["p_windward_kn_m2"] = round(
                wd.design_pressure_mwfrs_rigid(qz, qh, G, wd.WALL_CP["windward"], GCpi), 4)
            if cp_leeward is not None:
                entry["p_leeward_kn_m2"] = round(
                    wd.design_pressure_mwfrs_rigid(qh, qh, G, cp_leeward, -GCpi), 4)
            entry["p_side_kn_m2"] = round(
                wd.design_pressure_mwfrs_rigid(qh, qh, G, wd.WALL_CP["side"], -GCpi), 4)
        story_pressures.append(entry)

    return {
        "method": "mwfrs_method_2_analytical",
        "inputs": {
            "basic_wind_speed_v_ms": V_ms, "exposure_category": exposure,
            "wind_importance_factor_I": I_wind, "topographic_factor_Kzt": Kzt,
            "directionality_factor_Kd": Kd, "enclosure_classification": enclosure,
            "internal_pressure_coefficient_GCpi": GCpi, "gust_effect_factor_G": G,
            "is_rigid": True,
        },
        "wall_pressures_by_story": story_pressures,
    }


# ---------------------------------------------------------------------------
def run(structural_model, site_input, out_dir):
    seismic_needs_review, wind_needs_review = [], []
    seismic_result = compute_seismic(structural_model, site_input, seismic_needs_review)
    wind_result = compute_wind(structural_model, site_input, wind_needs_review)

    dynamic_loads = {}
    if seismic_result is not None:
        seismic_result["needs_review"] = seismic_needs_review
        dynamic_loads["seismic"] = seismic_result
    else:
        dynamic_loads["seismic"] = {"needs_review": seismic_needs_review}
    if wind_result is not None:
        wind_result["needs_review"] = wind_needs_review
        dynamic_loads["wind"] = wind_result
    else:
        dynamic_loads["wind"] = {"needs_review": wind_needs_review}

    structural_model["dynamic_loads"] = dynamic_loads

    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    (out_path / "structural_model.json").write_text(json.dumps(structural_model, indent=2))

    total_flags = len(seismic_needs_review) + len(wind_needs_review)
    computed_dirs = [d for d in ("x_direction", "y_direction")
                      if dynamic_loads["seismic"].get(d)]
    print(f"Seismic: {len(computed_dirs)}/2 direction(s) computed. "
          f"Wind: {'computed' if wind_result and wind_result['wall_pressures_by_story'][0]['qz_kn_m2'] is not None else 'formula-ready, awaiting verified table values'}. "
          f"{total_flags} item(s) flagged for review -> {out_path}/structural_model.json")
    return structural_model


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--structural-model", required=True)
    ap.add_argument("--site-input", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    structural_model = json.loads(Path(args.structural_model).read_text())
    site_input = json.loads(Path(args.site_input).read_text())
    run(structural_model, site_input, args.out)


if __name__ == "__main__":
    main()
