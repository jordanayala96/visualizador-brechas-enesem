import unittest

import pandas as pd

from quality_validations import evaluate_quality_validations


def calendars():
    field = pd.DataFrame({"date": pd.to_datetime(["2026-05-15", "2026-05-25"]), "week": [1, 2]})
    critique = pd.DataFrame({"date": pd.to_datetime(["2026-06-01"]), "week": [3]})
    return field, critique


class QualityValidationTests(unittest.TestCase):
    def test_preserves_rules_two_and_forty_nine(self):
        raw = pd.DataFrame({
            "Nro. orden": [1, 2],
            "Identificador Empresa": ["100", "200"],
            "RUC": ["1790000000001", "1790000000002"],
            "Razón social": ["Empresa uno", "Empresa dos"],
            "CZ_FINAL": ["CENTRO", "CENTRO"],
            "LEVANTADA": [1, 0],
            "DILIGENCIADA": [2, 1],
            "SOCIALIZACIÓN": [2, 2],
        })
        field, critique = calendars()
        summary, details, _ = evaluate_quality_validations(raw, field, critique)
        cases = summary.set_index("Código")["Casos"].to_dict()
        self.assertEqual(cases["2"], 1)
        self.assertEqual(cases["49"], 1)
        self.assertEqual({"2", "49"}, set(details["Código"]))

    def test_calendar_mismatch_is_detected(self):
        raw = pd.DataFrame({
            "Nro. orden": [1],
            "Identificador Empresa": ["100"],
            "RUC": ["1790000000001"],
            "Razón social": ["Empresa prueba"],
            "CZ_FINAL": ["CENTRO"],
            "FCH_LEVANTAMIENTO": [pd.Timestamp("2026-05-25")],
            "COB_CAMP": [1],
        })
        field, critique = calendars()
        summary, details, _ = evaluate_quality_validations(raw, field, critique)
        rule = summary.loc[summary["Código"].eq("8")].iloc[0]
        self.assertEqual(rule["Estado"], "Ejecutada")
        self.assertEqual(rule["Casos"], 1)
        self.assertIn("8", set(details["Código"]))

    def test_missing_columns_are_not_reported_as_zero_quality_issues(self):
        raw = pd.DataFrame({
            "Nro. orden": [1],
            "Identificador Empresa": ["100"],
            "RUC": ["1790000000001"],
            "Razón social": ["Empresa prueba"],
            "CZ_FINAL": ["CENTRO"],
        })
        field, critique = calendars()
        summary, _, _ = evaluate_quality_validations(raw, field, critique)
        rule = summary.loc[summary["Código"].eq("8")].iloc[0]
        self.assertEqual(rule["Estado"], "No evaluada")
        self.assertIn("lift_date", rule["Variables faltantes"])


if __name__ == "__main__":
    unittest.main()
