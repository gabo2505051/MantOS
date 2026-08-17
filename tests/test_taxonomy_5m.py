"""
test_taxonomy_5m.py — Unit Tests para el Módulo 5M y Filtros Prescriptivos
"""

import pytest
import pandas as pd
from pathlib import Path
from analysis.taxonomy_5m import classify_cause_5m, TAXONOMY_5M
from analysis.descriptive import DescriptiveAnalysis
from analysis.prescriptive import PrescriptiveAnalysis

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "mantos.db"


class TestTaxonomy5M:

    def test_classify_descalibracion_maquina(self):
        res = classify_cause_5m(qmtxt="Descalibracion de sensor de temperatura", auart="PM01")
        assert res["categoria_5m"] == "MAQUINA"
        assert res["causa_simplificada"] == "Des-calibración de instrumento"

    def test_classify_averia_valvula(self):
        res = classify_cause_5m(qmtxt="Fallo en valvula solenoide de aspiracion", auart="PM01")
        assert res["categoria_5m"] == "MAQUINA"
        assert res["causa_simplificada"] == "Avería de válvula / actuador"

    def test_classify_mal_acople_mano_obra(self):
        res = classify_cause_5m(qmtxt="Mal acople de hoja en rodillo de laminador", auart="PM01")
        assert res["categoria_5m"] in ("MANO DE OBRA", "MANO_DE_OBRA")
        assert res["causa_simplificada"] == "Mal acople de hoja / rodillo"

    def test_classify_preventivo_programado_na(self):
        res = classify_cause_5m(qmtxt="Mantenimiento preventivo rutinario", auart="PM02")
        assert res["categoria_5m"] in ("N/A", "N_A")
        assert res["causa_simplificada"] == "N/A (Mantenimiento Programado)"

    def test_top_causes_excludes_na_by_default(self):
        desc = DescriptiveAnalysis(DB_PATH)
        df_causes = desc.get_top_failure_causes(exclude_na=True, top_n=10)
        if not df_causes.empty:
            assert "N/A" not in df_causes["categoria_5m"].values
            assert "N_A" not in df_causes["categoria_5m"].values


    def test_top_causes_includes_na_when_requested(self):
        desc = DescriptiveAnalysis(DB_PATH)
        df_causes = desc.get_top_failure_causes(exclude_na=False, top_n=20)
        assert not df_causes.empty
        assert "causa_simplificada" in df_causes.columns

    def test_prescriptive_recommendations_have_5m_sources(self):
        presc = PrescriptiveAnalysis(DB_PATH)
        # Test con equipo de envasadora
        recs = presc.get_recommendations(equnr="10004003")
        assert isinstance(recs, list)
        assert len(recs) > 0
        fuentes = [r.get("fuente") for r in recs]
        assert any(f in ("KPI_MECANICO", "5M_MANO_DE_OBRA", "ML", "KPI", "AUDITORIA") for f in fuentes)
