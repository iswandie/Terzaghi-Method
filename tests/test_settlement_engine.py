import math
import unittest

from settlement_engine import (
    EngineeringValidationError,
    analyze_settlement,
    calculate_consolidation_time,
    calculate_degree_of_consolidation,
    calculate_nc_settlement,
    calculate_oc_settlement,
    calculate_time_factor,
    convert_cv,
    convert_length,
    convert_stress,
    time_factor_for_degree,
)


def valid_payload():
    return {
        "project": {"name": "Known example"},
        "units": {"length": "m", "stress": "kPa", "cv": "m2/year", "time": "years"},
        "groundwater": {"depth": 1.0, "gammaWater": 9.81},
        "loading": {"type": "uniform", "q": 100.0},
        "analysis": {"selectedTime": 1.0, "targetDegree": 90.0},
        "layers": [{
            "name": "Clay 1", "description": "Soft clay", "thickness": 4.0,
            "unitWeight": 18.0, "saturatedUnitWeight": 20.0, "voidRatio": 0.9,
            "compressionIndex": 0.30, "cv": 1.2, "condition": "NC",
            "drainage": "double", "preconsolidationPressure": "", "recompressionIndex": "",
        }],
    }


class FormulaTests(unittest.TestCase):
    def test_nc_settlement(self):
        expected = 0.30 * 4.0 / 1.9 * math.log10(200.0 / 100.0)
        self.assertAlmostEqual(calculate_nc_settlement(0.30, 4.0, 0.9, 100.0, 100.0), expected, places=12)

    def test_oc_settlement_below_preconsolidation(self):
        result = calculate_oc_settlement(0.30, 0.05, 5.0, 0.8, 100.0, 40.0, 160.0)
        expected = 0.05 * 5.0 / 1.8 * math.log10(140.0 / 100.0)
        self.assertAlmostEqual(result["recompression"], expected)
        self.assertEqual(result["virgin"], 0.0)

    def test_oc_settlement_crossing_preconsolidation(self):
        result = calculate_oc_settlement(0.30, 0.05, 5.0, 0.8, 100.0, 100.0, 150.0)
        expected_cr = 0.05 * 5.0 / 1.8 * math.log10(150.0 / 100.0)
        expected_cc = 0.30 * 5.0 / 1.8 * math.log10(200.0 / 150.0)
        self.assertAlmostEqual(result["total"], expected_cr + expected_cc)
        self.assertGreater(result["virgin"], 0.0)

    def test_single_and_double_drainage(self):
        single = calculate_consolidation_time(0.90, 4.0, 0.01)
        double = calculate_consolidation_time(0.90, 2.0, 0.01)
        self.assertAlmostEqual(single / double, 4.0)
        self.assertAlmostEqual(calculate_time_factor(0.01, single, 4.0), time_factor_for_degree(0.90))

    def test_50_percent_consolidation(self):
        tv = time_factor_for_degree(0.50)
        self.assertAlmostEqual(tv, math.pi / 16, places=12)
        self.assertAlmostEqual(calculate_degree_of_consolidation(tv), 0.50, places=5)

    def test_90_percent_consolidation(self):
        tv = time_factor_for_degree(0.90)
        self.assertAlmostEqual(tv, 0.848, delta=0.002)
        self.assertAlmostEqual(calculate_degree_of_consolidation(tv), 0.90, places=10)


class WorkflowAndValidationTests(unittest.TestCase):
    def test_multiple_layers_sum(self):
        payload = valid_payload()
        second = dict(payload["layers"][0])
        second.update({"name": "Clay 2", "thickness": 3.0, "voidRatio": 1.0, "compressionIndex": 0.25})
        payload["layers"].append(second)
        result = analyze_settlement(payload)
        layer_sum = sum(item["primarySettlementM"] * 1000 for item in result["layers"])
        self.assertEqual(len(result["layers"]), 2)
        self.assertAlmostEqual(result["summary"]["totalPrimarySettlementMm"], layer_sum)

    def test_missing_mandatory_parameter(self):
        payload = valid_payload()
        payload["layers"][0]["voidRatio"] = ""
        with self.assertRaises(EngineeringValidationError) as context:
            analyze_settlement(payload)
        self.assertIn("layers.0.voidRatio", context.exception.errors)

    def test_invalid_negative_value(self):
        payload = valid_payload()
        payload["layers"][0]["thickness"] = -2
        with self.assertRaises(EngineeringValidationError) as context:
            analyze_settlement(payload)
        self.assertIn("layers.0.thickness", context.exception.errors)

    def test_zero_effective_stress(self):
        payload = valid_payload()
        payload["layers"][0]["unitWeight"] = 9.81
        payload["layers"][0]["saturatedUnitWeight"] = 9.81
        payload["groundwater"]["depth"] = 0
        with self.assertRaises(EngineeringValidationError) as context:
            analyze_settlement(payload)
        self.assertIn("layers.0.effectiveStress", context.exception.errors)

    def test_oc_fields_required_only_for_oc(self):
        payload = valid_payload()
        analyze_settlement(payload)  # blank OC-only fields are valid for NC
        payload["layers"][0]["condition"] = "OC"
        with self.assertRaises(EngineeringValidationError) as context:
            analyze_settlement(payload)
        self.assertIn("layers.0.preconsolidationPressure", context.exception.errors)
        self.assertIn("layers.0.recompressionIndex", context.exception.errors)

    def test_unit_conversion(self):
        self.assertEqual(convert_length(1000, "mm"), 1.0)
        self.assertEqual(convert_stress(0.1, "MPa"), 100.0)
        self.assertAlmostEqual(convert_cv(365.25, "m2/year"), 1.0)
        metric = valid_payload()
        converted = valid_payload()
        converted["units"].update({"length": "mm", "stress": "MPa"})
        converted["groundwater"]["depth"] = 1000
        converted["loading"]["q"] = 0.1
        converted["layers"][0]["thickness"] = 4000
        a = analyze_settlement(metric)
        b = analyze_settlement(converted)
        self.assertAlmostEqual(a["summary"]["totalPrimarySettlementMm"], b["summary"]["totalPrimarySettlementMm"])


if __name__ == "__main__":
    unittest.main()