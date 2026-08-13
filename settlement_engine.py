"""Auditable Terzaghi one-dimensional consolidation calculation engine.

All calculations use SI base engineering units internally:
length = m, stress = kPa, time = day, Cv = m²/day, settlement = m.
The module has no UI or third-party dependencies and can be tested independently.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import exp, isfinite, log10, pi, sqrt
from typing import Any


class EngineeringValidationError(ValueError):
    """Raised when one or more mandatory engineering inputs are invalid."""

    def __init__(self, errors: dict[str, str]):
        self.errors = errors
        super().__init__("; ".join(errors.values()))


@dataclass(frozen=True)
class UnitSystem:
    length: str = "m"
    stress: str = "kPa"
    cv: str = "m2/year"
    time: str = "years"


LENGTH_TO_M = {"m": 1.0, "mm": 0.001}
STRESS_TO_KPA = {"kPa": 1.0, "MPa": 1000.0}
CV_TO_M2_DAY = {"m2/day": 1.0, "m2/year": 1.0 / 365.25}
TIME_TO_DAY = {"days": 1.0, "months": 365.25 / 12.0, "years": 365.25}


def _number(value: Any, path: str, label: str, errors: dict[str, str], *,
            minimum: float | None = None, strict: bool = False) -> float | None:
    if value is None or isinstance(value, bool) or (isinstance(value, str) and not value.strip()):
        errors[path] = f"{label} is required."
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        errors[path] = f"{label} must be numeric."
        return None
    if not isfinite(number):
        errors[path] = f"{label} must be a finite numeric value."
        return None
    if minimum is not None and ((strict and number <= minimum) or (not strict and number < minimum)):
        comparator = "greater than" if strict else "at least"
        errors[path] = f"{label} must be {comparator} {minimum:g}."
        return None
    return number


def _text(value: Any, path: str, label: str, errors: dict[str, str]) -> str | None:
    if value is None or not str(value).strip():
        errors[path] = f"{label} is required."
        return None
    return str(value).strip()


def convert_length(value: float, unit: str) -> float:
    if unit not in LENGTH_TO_M:
        raise EngineeringValidationError({"units.length": "Length unit must be m or mm."})
    return value * LENGTH_TO_M[unit]


def convert_stress(value: float, unit: str) -> float:
    if unit not in STRESS_TO_KPA:
        raise EngineeringValidationError({"units.stress": "Stress unit must be kPa or MPa."})
    return value * STRESS_TO_KPA[unit]


def convert_cv(value: float, unit: str) -> float:
    if unit not in CV_TO_M2_DAY:
        raise EngineeringValidationError({"units.cv": "Cv unit must be m2/day or m2/year."})
    return value * CV_TO_M2_DAY[unit]


def convert_time(value: float, unit: str) -> float:
    if unit not in TIME_TO_DAY:
        raise EngineeringValidationError({"units.time": "Time unit must be days, months, or years."})
    return value * TIME_TO_DAY[unit]


def days_to(value: float, unit: str) -> float:
    if unit not in TIME_TO_DAY:
        raise EngineeringValidationError({"units.time": "Time unit must be days, months, or years."})
    return value / TIME_TO_DAY[unit]


def calculate_pore_pressure(depth_m: float, groundwater_depth_m: float,
                            gamma_water: float = 9.81) -> float:
    """Hydrostatic pore pressure below the groundwater table, in kPa."""
    return gamma_water * max(0.0, depth_m - groundwater_depth_m)


def calculate_total_stress(depth_m: float, layers: list[dict[str, float]],
                           groundwater_depth_m: float) -> float:
    """Integrate total/saturated unit weights from ground level to depth."""
    stress = 0.0
    top = 0.0
    for layer in layers:
        bottom = top + layer["thickness"]
        segment_bottom = min(depth_m, bottom)
        if segment_bottom > top:
            above_bottom = min(segment_bottom, groundwater_depth_m)
            above = max(0.0, above_bottom - top)
            below_top = max(top, groundwater_depth_m)
            below = max(0.0, segment_bottom - below_top)
            stress += above * layer["unitWeight"] + below * layer["saturatedUnitWeight"]
        if depth_m <= bottom:
            break
        top = bottom
    return stress


def calculate_effective_stress(total_stress: float, pore_pressure: float) -> float:
    return total_stress - pore_pressure


def calculate_stress_increase(load: dict[str, float | str], depth_m: float) -> float:
    """Stress increase at depth; foundation mode uses the specified 2:1 equation."""
    if load["type"] == "uniform":
        return float(load["q"])
    z = max(0.0, depth_m - float(load["embedmentDepth"]))
    width = float(load["width"])
    length = float(load["length"])
    return float(load["q"]) * width * length / ((width + z) * (length + z))


def calculate_nc_settlement(cc: float, thickness_m: float, e0: float,
                            sigma0: float, delta_sigma: float) -> float:
    if sigma0 <= 0 or thickness_m <= 0 or 1 + e0 <= 0 or cc <= 0:
        raise EngineeringValidationError({"settlement": "NC settlement requires σ'0, H, Cc, and (1 + e₀) greater than zero."})
    return cc * thickness_m / (1 + e0) * log10((sigma0 + delta_sigma) / sigma0)


def calculate_oc_settlement(cc: float, cr: float, thickness_m: float, e0: float,
                            sigma0: float, delta_sigma: float,
                            preconsolidation_pressure: float) -> dict[str, float]:
    if sigma0 <= 0 or thickness_m <= 0 or 1 + e0 <= 0 or cc <= 0 or cr <= 0:
        raise EngineeringValidationError({"settlement": "OC settlement requires σ'0, H, Cc, Cr, and (1 + e₀) greater than zero."})
    if preconsolidation_pressure < sigma0:
        raise EngineeringValidationError({"preconsolidationPressure": "Preconsolidation pressure σ'p must be at least the initial effective stress σ'0."})
    if cc <= cr:
        raise EngineeringValidationError({"compressionIndex": "Compression index Cc must be greater than recompression index Cr for OC soil."})
    final_stress = sigma0 + delta_sigma
    if final_stress <= preconsolidation_pressure:
        recompression = cr * thickness_m / (1 + e0) * log10(final_stress / sigma0)
        virgin = 0.0
    else:
        recompression = cr * thickness_m / (1 + e0) * log10(preconsolidation_pressure / sigma0)
        virgin = cc * thickness_m / (1 + e0) * log10(final_stress / preconsolidation_pressure)
    return {"recompression": recompression, "virgin": virgin, "total": recompression + virgin}


def calculate_time_factor(cv_m2_day: float, time_days: float, drainage_path_m: float) -> float:
    if cv_m2_day <= 0 or drainage_path_m <= 0 or time_days < 0:
        raise EngineeringValidationError({"timeFactor": "Tv requires Cv and Hdr greater than zero and time at least zero."})
    return cv_m2_day * time_days / drainage_path_m**2


def calculate_degree_of_consolidation(tv: float) -> float:
    """Average U using the standard early-time relation then Terzaghi series."""
    if tv < 0:
        raise EngineeringValidationError({"timeFactor": "Time factor Tv cannot be negative."})
    if tv == 0:
        return 0.0
    transition_tv = pi * 0.60**2 / 4.0
    if tv <= transition_tv:
        return 2.0 * sqrt(tv / pi)
    remaining = 0.0
    for m in range(200):
        odd = 2 * m + 1
        term = 8.0 / (pi**2 * odd**2) * exp(-(odd**2) * pi**2 * tv / 4.0)
        remaining += term
        if term < 1e-14:
            break
    return min(1.0, max(0.0, 1.0 - remaining))


def time_factor_for_degree(target_u: float) -> float:
    """Invert U–Tv: standard early-time expression to 60%, series thereafter."""
    if target_u <= 0 or target_u >= 1:
        raise EngineeringValidationError({"targetDegree": "Target degree of consolidation must be greater than 0% and less than 100%."})
    if target_u <= 0.60:
        return pi * target_u**2 / 4.0
    low, high = 0.0, 5.0
    for _ in range(100):
        mid = (low + high) / 2.0
        if calculate_degree_of_consolidation(mid) < target_u:
            low = mid
        else:
            high = mid
    return (low + high) / 2.0


def calculate_consolidation_time(target_u: float, drainage_path_m: float,
                                 cv_m2_day: float) -> float:
    if cv_m2_day <= 0 or drainage_path_m <= 0:
        raise EngineeringValidationError({"consolidationTime": "Consolidation time requires Cv and Hdr greater than zero."})
    return time_factor_for_degree(target_u) * drainage_path_m**2 / cv_m2_day


def calculate_settlement_at_time(primary_settlement_m: float, cv_m2_day: float,
                                 time_days: float, drainage_path_m: float) -> dict[str, float]:
    tv = calculate_time_factor(cv_m2_day, time_days, drainage_path_m)
    degree = calculate_degree_of_consolidation(tv)
    return {"tv": tv, "degree": degree, "settlement": degree * primary_settlement_m}


def _units(payload: dict[str, Any], errors: dict[str, str]) -> UnitSystem:
    raw = payload.get("units") or {}
    units = UnitSystem(raw.get("length", "m"), raw.get("stress", "kPa"),
                       raw.get("cv", "m2/year"), raw.get("time", "years"))
    for field, allowed in (("length", LENGTH_TO_M), ("stress", STRESS_TO_KPA),
                           ("cv", CV_TO_M2_DAY), ("time", TIME_TO_DAY)):
        if getattr(units, field) not in allowed:
            errors[f"units.{field}"] = f"Unsupported {field} unit."
    return units


def _validate_and_normalize(payload: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    errors: dict[str, str] = {}
    warnings: list[str] = []
    units = _units(payload, errors)
    project = payload.get("project") or {}
    _text(project.get("name"), "project.name", "Project Name", errors)

    groundwater = payload.get("groundwater") or {}
    gwt = _number(groundwater.get("depth"), "groundwater.depth", "Groundwater table depth", errors, minimum=0)
    gamma_w = _number(groundwater.get("gammaWater"), "groundwater.gammaWater", "Unit weight of water γw", errors, minimum=0, strict=True)

    raw_layers = payload.get("layers")
    if not isinstance(raw_layers, list) or not raw_layers:
        errors["layers"] = "At least one soil layer is required."
        raw_layers = []
    layers: list[dict[str, Any]] = []
    for index, raw in enumerate(raw_layers):
        prefix = f"layers.{index}"
        condition = raw.get("condition")
        drainage = raw.get("drainage")
        name = _text(raw.get("name"), f"{prefix}.name", "Layer Name", errors)
        description = _text(raw.get("description"), f"{prefix}.description", "Soil Description", errors)
        h = _number(raw.get("thickness"), f"{prefix}.thickness", "Compressible layer thickness H", errors, minimum=0, strict=True)
        gamma = _number(raw.get("unitWeight"), f"{prefix}.unitWeight", "Total unit weight γ", errors, minimum=0, strict=True)
        gamma_sat = _number(raw.get("saturatedUnitWeight"), f"{prefix}.saturatedUnitWeight", "Saturated unit weight γsat", errors, minimum=0, strict=True)
        e0 = _number(raw.get("voidRatio"), f"{prefix}.voidRatio", "Initial void ratio e₀", errors, minimum=0)
        cc = _number(raw.get("compressionIndex"), f"{prefix}.compressionIndex", "Compression index Cc", errors, minimum=0, strict=True)
        cv = _number(raw.get("cv"), f"{prefix}.cv", "Coefficient of consolidation Cv", errors, minimum=0, strict=True)
        if condition not in ("NC", "OC"):
            errors[f"{prefix}.condition"] = "Soil condition NC or OC is required."
        if drainage not in ("single", "double"):
            errors[f"{prefix}.drainage"] = "Drainage condition is required."
        sigma_p = cr = None
        if condition == "OC":
            sigma_p = _number(raw.get("preconsolidationPressure"), f"{prefix}.preconsolidationPressure", "Preconsolidation pressure σ'p", errors, minimum=0, strict=True)
            cr = _number(raw.get("recompressionIndex"), f"{prefix}.recompressionIndex", "Recompression index Cr", errors, minimum=0, strict=True)
            if cc is not None and cr is not None and cc <= cr:
                errors[f"{prefix}.compressionIndex"] = "Compression index Cc must be greater than recompression index Cr for OC soil."
        layers.append({
            "name": name, "description": description,
            "thickness": convert_length(h, units.length) if h is not None and units.length in LENGTH_TO_M else None,
            "unitWeight": gamma, "saturatedUnitWeight": gamma_sat, "voidRatio": e0,
            "compressionIndex": cc,
            "cv": convert_cv(cv, units.cv) if cv is not None and units.cv in CV_TO_M2_DAY else None,
            "condition": condition, "drainage": drainage,
            "preconsolidationPressure": convert_stress(sigma_p, units.stress) if sigma_p is not None and units.stress in STRESS_TO_KPA else None,
            "recompressionIndex": cr,
        })

    loading = payload.get("loading") or {}
    load_type = loading.get("type")
    if load_type not in ("uniform", "foundation"):
        errors["loading.type"] = "Loading type is required."
    q = _number(loading.get("q"), "loading.q", "Applied pressure q", errors, minimum=0, strict=True)
    load: dict[str, Any] = {"type": load_type, "q": convert_stress(q, units.stress) if q is not None and units.stress in STRESS_TO_KPA else None}
    if load_type == "foundation":
        if loading.get("method") != "2:1":
            errors["loading.method"] = "Stress distribution method 2:1 is required."
        for field, label in (("width", "Foundation width B"), ("length", "Foundation length L")):
            value = _number(loading.get(field), f"loading.{field}", label, errors, minimum=0, strict=True)
            load[field] = convert_length(value, units.length) if value is not None and units.length in LENGTH_TO_M else None
        embedment = _number(loading.get("embedmentDepth"), "loading.embedmentDepth", "Foundation embedment depth Df", errors, minimum=0)
        load["embedmentDepth"] = convert_length(embedment, units.length) if embedment is not None and units.length in LENGTH_TO_M else None
        load["method"] = "2:1"

    analysis = payload.get("analysis") or {}
    selected_time = _number(analysis.get("selectedTime"), "analysis.selectedTime", "Specified consolidation time", errors, minimum=0)
    target_degree = _number(analysis.get("targetDegree"), "analysis.targetDegree", "Target degree of consolidation", errors, minimum=0, strict=True)
    if target_degree is not None and target_degree >= 100:
        errors["analysis.targetDegree"] = "Target degree of consolidation must be less than 100%."

    if errors:
        raise EngineeringValidationError(errors)
    assert gwt is not None and gamma_w is not None and q is not None and selected_time is not None and target_degree is not None
    return ({
        "units": units, "project": project, "layers": layers,
        "groundwaterDepth": convert_length(gwt, units.length), "gammaWater": gamma_w,
        "loading": load, "selectedTimeDays": convert_time(selected_time, units.time),
        "targetDegree": target_degree / 100.0,
    }, warnings)


def _detail(category: str, layer: str, parameter: str, formula: str,
            substitution: str, result: float, unit: str) -> dict[str, Any]:
    return {"category": category, "layer": layer, "parameter": parameter,
            "formula": formula, "substitution": substitution,
            "result": result, "unit": unit}


def _aggregate_degree(layer_results: list[dict[str, Any]], time_days: float) -> tuple[float, float, list[float]]:
    total_primary = sum(layer["primarySettlementM"] for layer in layer_results)
    settlements, tvs = [], []
    for layer in layer_results:
        timed = calculate_settlement_at_time(layer["primarySettlementM"], layer["cvM2Day"], time_days, layer["drainagePathM"])
        settlements.append(timed["settlement"])
        tvs.append(timed["tv"])
    total_at_time = sum(settlements)
    degree = total_at_time / total_primary if total_primary > 0 else 0.0
    return degree, total_at_time, tvs


def _aggregate_time(layer_results: list[dict[str, Any]], target: float) -> float:
    high = max(calculate_consolidation_time(target, layer["drainagePathM"], layer["cvM2Day"])
               for layer in layer_results)
    while _aggregate_degree(layer_results, high)[0] < target:
        high *= 2
    low = 0.0
    for _ in range(80):
        mid = (low + high) / 2
        if _aggregate_degree(layer_results, mid)[0] < target:
            low = mid
        else:
            high = mid
    return (low + high) / 2


def calculate_layer_settlement(layer: dict[str, Any], sigma0: float,
                               delta_sigma: float) -> dict[str, float]:
    if layer["condition"] == "NC":
        total = calculate_nc_settlement(layer["compressionIndex"], layer["thickness"],
                                        layer["voidRatio"], sigma0, delta_sigma)
        return {"recompression": 0.0, "virgin": total, "total": total}
    return calculate_oc_settlement(layer["compressionIndex"], layer["recompressionIndex"],
                                   layer["thickness"], layer["voidRatio"], sigma0,
                                   delta_sigma, layer["preconsolidationPressure"])


def calculate_total_settlement(layer_results: list[dict[str, Any]]) -> float:
    return sum(layer["primarySettlementM"] for layer in layer_results)


def analyze_settlement(payload: dict[str, Any]) -> dict[str, Any]:
    """Validate a complete analysis and return auditable layer/time results."""
    data, warnings = _validate_and_normalize(payload)
    layers = data["layers"]
    load = data["loading"]
    gwt = data["groundwaterDepth"]
    gamma_w = data["gammaWater"]
    layer_results: list[dict[str, Any]] = []
    details: list[dict[str, Any]] = []
    top = 0.0

    for index, layer in enumerate(layers):
        midpoint = top + layer["thickness"] / 2.0
        total_stress = calculate_total_stress(midpoint, layers, gwt)
        pore = calculate_pore_pressure(midpoint, gwt, gamma_w)
        effective = calculate_effective_stress(total_stress, pore)
        path = f"layers.{index}"
        if effective <= 0:
            raise EngineeringValidationError({f"{path}.effectiveStress": "Initial effective stress is zero or negative. Check groundwater level and soil unit weights."})
        delta = calculate_stress_increase(load, midpoint)
        if delta <= 0:
            raise EngineeringValidationError({"loading.q": "Calculated stress increase must be greater than zero."})
        final = effective + delta
        if layer["condition"] == "OC" and layer["preconsolidationPressure"] < effective:
            raise EngineeringValidationError({f"{path}.preconsolidationPressure": "Preconsolidation pressure is lower than initial effective stress. Check input data."})
        if load["type"] == "foundation" and midpoint < load["embedmentDepth"]:
            warnings.append(f"{layer['name']}: midpoint is above foundation base; z was limited to 0 m and Δσz = q at that point.")
        components = calculate_layer_settlement(layer, effective, delta)
        hdr = layer["thickness"] if layer["drainage"] == "single" else layer["thickness"] / 2.0
        selected = calculate_settlement_at_time(components["total"], layer["cv"], data["selectedTimeDays"], hdr)
        times = {str(percent): calculate_consolidation_time(percent / 100.0, hdr, layer["cv"])
                 for percent in (50, 90, 95)}
        target_time = calculate_consolidation_time(data["targetDegree"], hdr, layer["cv"])

        result = {
            "index": index, "name": layer["name"], "description": layer["description"],
            "condition": layer["condition"], "drainage": layer["drainage"],
            "topDepthM": top, "bottomDepthM": top + layer["thickness"], "midDepthM": midpoint,
            "totalStressKPa": total_stress, "porePressureKPa": pore,
            "initialEffectiveStressKPa": effective, "stressIncreaseKPa": delta,
            "finalEffectiveStressKPa": final,
            "recompressionSettlementM": components["recompression"],
            "virginSettlementM": components["virgin"], "primarySettlementM": components["total"],
            "drainagePathM": hdr, "cvM2Day": layer["cv"],
            "selectedTv": selected["tv"], "selectedDegree": selected["degree"],
            "selectedSettlementM": selected["settlement"], "timesDays": times,
            "targetTimeDays": target_time,
        }
        layer_results.append(result)
        details.extend([
            _detail("Effective stress", layer["name"], "Initial total vertical stress σv0", "σv0 = Σ(γ × h)", f"Integrated to z = {midpoint:.3f} m using γ above GWT and γsat below GWT", total_stress, "kPa"),
            _detail("Effective stress", layer["name"], "Initial pore-water pressure u0", "u0 = γw × max(0, z − zw)", f"{gamma_w:.3f} × max(0, {midpoint:.3f} − {gwt:.3f})", pore, "kPa"),
            _detail("Effective stress", layer["name"], "Initial effective stress σ'0", "σ'0 = σv0 − u0", f"{total_stress:.3f} − {pore:.3f}", effective, "kPa"),
        ])
        if load["type"] == "uniform":
            load_sub = f"Δσz = q = {load['q']:.3f}"
            load_formula = "Δσz = q"
        else:
            z = max(0.0, midpoint - load["embedmentDepth"])
            load_formula = "Δσz = q(BL)/[(B+z)(L+z)]"
            load_sub = f"{load['q']:.3f}({load['width']:.3f}×{load['length']:.3f})/[({load['width']:.3f}+{z:.3f})({load['length']:.3f}+{z:.3f})]"
        details.extend([
            _detail("Loading", layer["name"], "Stress increase Δσz", load_formula, load_sub, delta, "kPa"),
            _detail("Effective stress", layer["name"], "Final effective stress σ'f", "σ'f = σ'0 + Δσz", f"{effective:.3f} + {delta:.3f}", final, "kPa"),
        ])
        factor = layer["thickness"] / (1 + layer["voidRatio"])
        if layer["condition"] == "NC":
            formula = "Sc = [CcH/(1+e₀)] log₁₀(σ'f/σ'0)"
            sub = f"[{layer['compressionIndex']:.4f}×{layer['thickness']:.3f}/(1+{layer['voidRatio']:.3f})] log₁₀({final:.3f}/{effective:.3f})"
        elif final <= layer["preconsolidationPressure"]:
            formula = "Sc = [CrH/(1+e₀)] log₁₀(σ'f/σ'0)"
            sub = f"[{layer['recompressionIndex']:.4f}×{factor:.4f}] log₁₀({final:.3f}/{effective:.3f})"
        else:
            formula = "Sc = [CrH/(1+e₀)]log₁₀(σ'p/σ'0) + [CcH/(1+e₀)]log₁₀(σ'f/σ'p)"
            sub = f"[{layer['recompressionIndex']:.4f}×{factor:.4f}]log₁₀({layer['preconsolidationPressure']:.3f}/{effective:.3f}) + [{layer['compressionIndex']:.4f}×{factor:.4f}]log₁₀({final:.3f}/{layer['preconsolidationPressure']:.3f})"
        details.extend([
            _detail("Settlement", layer["name"], "Primary consolidation settlement Sc", formula, sub, components["total"] * 1000, "mm"),
            _detail("Consolidation time", layer["name"], "Drainage path Hdr", "Hdr = H (single) or H/2 (double)", f"{layer['thickness']:.3f} m; {layer['drainage']} drainage", hdr, "m"),
            _detail("Consolidation time", layer["name"], "Degree at selected time U", "Tv = Cv·t/Hdr²; U = Terzaghi series", f"Tv = {layer['cv']:.6g}×{data['selectedTimeDays']:.3f}/{hdr:.3f}² = {selected['tv']:.5f}", selected["degree"] * 100, "%"),
            _detail("Consolidation time", layer["name"], "Settlement at selected time St", "St = U × Sc", f"{selected['degree']:.5f} × {components['total'] * 1000:.3f}", selected["settlement"] * 1000, "mm"),
        ])
        top += layer["thickness"]

    total_primary = calculate_total_settlement(layer_results)
    selected_degree, selected_settlement, _ = _aggregate_degree(layer_results, data["selectedTimeDays"])
    overall_times = {str(percent): _aggregate_time(layer_results, percent / 100.0) for percent in (50, 90, 95)}
    overall_target_time = _aggregate_time(layer_results, data["targetDegree"])
    horizon = max(overall_times["95"] * 1.25, data["selectedTimeDays"], overall_target_time)
    time_points = []
    for i in range(26):
        day = horizon * (i / 25.0) ** 2
        degree, settlement, tvs = _aggregate_degree(layer_results, day)
        time_points.append({
            "timeDays": day, "timeDisplay": days_to(day, data["units"].time),
            "timeUnit": data["units"].time, "tvMin": min(tvs), "tvMax": max(tvs),
            "degree": degree, "settlementMm": settlement * 1000,
        })

    details.append(_detail("Settlement", "All layers", "Total primary consolidation settlement", "Sc,total = ΣSc,i",
                           " + ".join(f"{layer['primarySettlementM'] * 1000:.3f}" for layer in layer_results),
                           total_primary * 1000, "mm"))
    return {
        "project": data["project"], "units": {"length": "m", "stress": "kPa", "settlement": "mm", "time": data["units"].time},
        "assumptions": [
            "Terzaghi one-dimensional primary consolidation theory applies; strain and drainage are vertical.",
            "Layer stresses are evaluated at each layer midpoint; layers are horizontal and contiguous from ground level.",
            "Total unit weight γ is used above the groundwater table and γsat below it; hydrostatic pore pressure is assumed.",
            "Uniform surcharge is constant with depth. Foundation loading uses Δσz = qBL/[(B+z)(L+z)] with z below the foundation base.",
            "Cv is constant within each layer. Overall multilayer degree of consolidation is settlement-weighted.",
            "Immediate settlement: Not included in this analysis. Secondary settlement: Not included in this analysis.",
            "Results require review by a qualified geotechnical engineer and are not automatically suitable for construction.",
        ],
        "warnings": warnings, "layers": layer_results,
        "summary": {
            "totalPrimarySettlementMm": total_primary * 1000,
            "immediateSettlement": None, "secondarySettlement": None,
            "totalSettlementMm": total_primary * 1000,
            "selectedTimeDays": data["selectedTimeDays"],
            "selectedTimeDisplay": days_to(data["selectedTimeDays"], data["units"].time),
            "selectedDegree": selected_degree, "selectedSettlementMm": selected_settlement * 1000,
            "timesDays": overall_times,
            "timesDisplay": {key: days_to(value, data["units"].time) for key, value in overall_times.items()},
            "targetDegree": data["targetDegree"], "targetTimeDays": overall_target_time,
            "targetTimeDisplay": days_to(overall_target_time, data["units"].time),
        },
        "timeSeries": time_points, "calculationDetails": details,
    }
