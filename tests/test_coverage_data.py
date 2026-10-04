from __future__ import annotations

from io import BytesIO
import unittest

import pandas as pd

from coverage_data import (
    EXCLUDED_COMPANY_ID,
    load_coverage_directory,
    progress_summaries,
    socialization_summary,
)


class CoverageDataTests(unittest.TestCase):
    def test_excludes_special_company_id(self):
        raw = pd.DataFrame({
            "Identificador Empresa": [EXCLUDED_COMPANY_ID, "100"],
            "COORD. Z": ["LITORAL", "LITORAL"],
            "CZ_FINAL": ["LITORAL", "LITORAL"],
            "SOCIALIZACIÓN": [1, 1],
            "DILIGENCIADA": [1, 1],
            "LEVANTADA": [1, 1],
            "CRITICADA": [1, 1],
            "EFECT_CAMPO": [1, 1],
            "EFECT_CRIT": [1, 1],
            "DESGLO_EFECT": ["Efectiva (sin novedad)", "Efectiva (sin novedad)"],
        })
        buffer = BytesIO()
        raw.to_excel(buffer, index=False)
        directory, _, controls = load_coverage_directory(
            buffer.getvalue(), filename="directorio.xlsx"
        )
        self.assertEqual(len(directory), 1)
        self.assertEqual(controls["excluded_special_id"], 1)

    def test_transfer_balance(self):
        directory = pd.DataFrame({
            "company_id": ["1", "2", "3"],
            "zone_initial": ["LITORAL", "LITORAL", "SUR"],
            "zone_final": ["LITORAL", "SUR", "LITORAL"],
            "socialized": [True, True, True],
            "diligenced": [True, False, True],
        })
        table, _ = socialization_summary(directory, ["LITORAL", "SUR"])
        self.assertEqual(int(table.loc[0, "Enviadas"]), 2)
        self.assertEqual(int(table.loc[0, "Recibidas"]), 2)

    def test_progress_boundary_includes_exactly_50_percent(self):
        directory = pd.DataFrame({
            "company_id": ["1", "2"],
            "zone_final": ["LITORAL", "LITORAL"],
            "lifted": [False, False],
        })
        progress = pd.DataFrame({
            "company_id": ["1", "2"],
            "progress": [0.50, 0.75],
            "chapters_v": [11, 16],
            "chapters_g": [0, 0],
            "chapters_complete": [11, 16],
        })
        _, bands, _ = progress_summaries(directory, progress, ["LITORAL"])
        litoral = bands.loc[bands["Coordinación Zonal"].eq("LITORAL")].iloc[0]
        self.assertEqual(int(litoral["Hasta 50%"]), 1)
        self.assertEqual(int(litoral["Entre 51% y 75%"]), 1)


if __name__ == "__main__":
    unittest.main()
