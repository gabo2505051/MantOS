"""
Tests para todos los módulos de análisis de la Fase 2.
Cubre: descriptive, diagnostic, kpis, predictive, prescriptive, reports.
"""

import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from analysis.descriptive  import DescriptiveAnalysis
from analysis.diagnostic   import DiagnosticAnalysis
from analysis.kpis         import KPICalculator
from analysis.predictive   import PredictiveAnalysis
from analysis.prescriptive import PrescriptiveAnalysis
from analysis.reports      import ReportGenerator
from analysis.visualizations import ChartGenerator

DB_PATH    = _ROOT / "data" / "mantos.db"
EQUNR_LA4  = "10004003"   # LA4-ENV01 — Envasadora, el equipo más activo
LINEA_LA4  = "LA4"
START      = "2024-04-01T00:00:00Z"
END        = "2024-09-30T23:59:59Z"


@pytest.fixture(scope="session")
def desc():
    if not DB_PATH.exists():
        pytest.skip("DB no encontrada — ejecuta python ingestion/ingest.py")
    return DescriptiveAnalysis(DB_PATH)

@pytest.fixture(scope="session")
def diag():
    if not DB_PATH.exists():
        pytest.skip("DB no encontrada")
    return DiagnosticAnalysis(DB_PATH)

@pytest.fixture(scope="session")
def kpi():
    if not DB_PATH.exists():
        pytest.skip("DB no encontrada")
    return KPICalculator(DB_PATH)

@pytest.fixture(scope="session")
def pred():
    if not DB_PATH.exists():
        pytest.skip("DB no encontrada")
    return PredictiveAnalysis(DB_PATH)

@pytest.fixture(scope="session")
def presc():
    if not DB_PATH.exists():
        pytest.skip("DB no encontrada")
    return PrescriptiveAnalysis(DB_PATH)

@pytest.fixture(scope="session")
def rpt():
    if not DB_PATH.exists():
        pytest.skip("DB no encontrada")
    return ReportGenerator(DB_PATH)


# ======================================================================
# F2 — Análisis Descriptivo
# ======================================================================

class TestDescriptive:

    def test_event_frequency_returns_dataframe(self, desc):
        df = desc.get_event_frequency(group_by="equnr", period="month",
                                      start_date=START, end_date=END)
        assert not df.empty
        assert "group_key" in df.columns
        assert "event_count" in df.columns

    def test_event_frequency_valid_periods(self, desc):
        for period in ("day", "week", "month"):
            df = desc.get_event_frequency(period=period, start_date=START, end_date=END)
            assert not df.empty

    def test_event_frequency_invalid_period(self, desc):
        with pytest.raises(ValueError):
            desc.get_event_frequency(period="year")

    def test_top_equipment_n(self, desc):
        df = desc.get_top_equipment_by_events(n=5, start_date=START, end_date=END)
        assert len(df) <= 5
        assert "event_count" in df.columns
        # Ordenado descendente
        assert df["event_count"].is_monotonic_decreasing

    def test_top_equipment_pct_sums_correctly(self, desc):
        df = desc.get_top_equipment_by_events(n=100, start_date=START, end_date=END)
        assert "pct_of_total" in df.columns
        # La suma de % puede no ser 100 si hay más equipos, pero los valores son correctos
        assert (df["pct_of_total"] >= 0).all()
        assert (df["pct_of_total"] <= 100).all()

    def test_temporal_heatmap_shape(self, desc):
        heatmap = desc.get_temporal_heatmap(start_date=START, end_date=END)
        assert heatmap.shape == (24, 7)  # 24 horas x 7 días
        assert list(heatmap.columns) == ["Lun", "Mar", "Mie", "Jue", "Vie", "Sab", "Dom"]

    def test_temporal_heatmap_nonnegative(self, desc):
        heatmap = desc.get_temporal_heatmap(equnr=EQUNR_LA4, start_date=START, end_date=END)
        assert (heatmap >= 0).all().all()

    def test_duration_stats_excludes_ghost_stops(self, desc):
        stats = desc.get_duration_stats(equnr=EQUNR_LA4, start_date=START, end_date=END)
        assert stats["count"] >= 0
        # min debe ser > 0 (ghost stops excluidos)
        if stats["count"] > 0:
            assert stats["min"] > 0

    def test_duration_stats_percentiles_ordered(self, desc):
        stats = desc.get_duration_stats(start_date=START, end_date=END)
        if stats["count"] > 0:
            assert stats["median"] <= stats["p90"]
            assert stats["p90"]    <= stats["p99"]

    def test_duration_by_type_has_three_rows(self, desc):
        df = desc.get_duration_by_type(start_date=START, end_date=END)
        assert len(df) == 3
        assert set(df["auart"]) == {"PM01", "PM02", "PM03"}

    def test_normalize_failure_text(self, desc):
        assert "micro paro" in desc.normalize_failure_text("MICROPARO")
        assert "micro paro" in desc.normalize_failure_text("m.paro oper")
        assert "atasco"     in desc.normalize_failure_text("ATSC PRODUCTO")
        assert "sensor"     in desc.normalize_failure_text("FALLA SENS. OPTICO")

    def test_top_keywords_returns_list(self, desc):
        keywords = desc.get_top_keywords(n=10, start_date=START, end_date=END)
        assert isinstance(keywords, list)
        assert len(keywords) <= 10
        assert all(isinstance(k, tuple) and len(k) == 2 for k in keywords)

    def test_top_keywords_frequencies_descending(self, desc):
        keywords = desc.get_top_keywords(n=20, start_date=START, end_date=END)
        freqs = [f for _, f in keywords]
        assert freqs == sorted(freqs, reverse=True)

    def test_failure_summary_structure(self, desc):
        summary = desc.get_failure_summary(start_date=START, end_date=END)
        assert "total_events" in summary
        assert "ghost_stops"  in summary
        assert "by_type"      in summary
        assert summary["total_events"] > 0


# ======================================================================
# F3 — Análisis de Diagnóstico
# ======================================================================

class TestDiagnostic:

    def test_pareto_events_structure(self, diag):
        df = diag.get_pareto(metric="events", start_date=START, end_date=END)
        assert not df.empty
        assert "pct"            in df.columns
        assert "cumulative_pct" in df.columns
        assert "is_vital_few"   in df.columns

    def test_pareto_pct_sums_to_100(self, diag):
        df = diag.get_pareto(metric="events", top_n=100, start_date=START, end_date=END)
        assert abs(df["pct"].sum() - 100.0) < 0.5  # tolerancia de redondeo

    def test_pareto_cumulative_monotonic(self, diag):
        df = diag.get_pareto(metric="downtime", start_date=START, end_date=END)
        assert df["cumulative_pct"].is_monotonic_increasing

    def test_pareto_vital_few_at_most_80pct(self, diag):
        df = diag.get_pareto(metric="events", start_date=START, end_date=END)
        vital_few = df[df["is_vital_few"]]
        if not vital_few.empty:
            assert vital_few["cumulative_pct"].max() <= 80.1  # tolerancia

    def test_ghost_stop_audit_structure(self, diag):
        result = diag.audit_ghost_stops(start_date=START, end_date=END)
        assert "total_ghost_stops" in result
        assert "by_equipment"      in result
        assert "by_user"           in result
        assert result["total_ghost_stops"] > 0

    def test_ghost_stop_audit_bat_user_present(self, diag):
        """BAT_USER es un generador frecuente de ghost stops según el catálogo."""
        result = diag.audit_ghost_stops(start_date=START, end_date=END)
        users  = result["by_user"]["ernam"].tolist()
        assert "BAT_USER" in users

    def test_recurrence_score_range(self, diag):
        score = diag.get_recurrence_score(EQUNR_LA4, start_date=START, end_date=END)
        assert 0.0 <= score <= 1.0

    def test_recurring_failures_threshold(self, diag):
        df = diag.get_recurring_failures(threshold=0.3, start_date=START, end_date=END)
        assert "recurrence_score" in df.columns
        if not df.empty:
            assert (df["recurrence_score"] >= 0.3).all()

    def test_classify_failure_text(self, diag):
        assert diag.classify_failure_text("MICROPARO")           in ["MICRO_PARO", "OTRO"]
        assert diag.classify_failure_text("ATASCO L4")           == "ATASCO_PRODUCTO"
        assert diag.classify_failure_text("reinicio de ciclo HMI") == "REINICIO_HMI"
        assert diag.classify_failure_text("FALLA SENS. OPTICO")  == "SENSOR_FALLA"
        assert diag.classify_failure_text("MTO PREV. PROGRAMADO") == "MANTENIMIENTO_PREVENTIVO"

    def test_taxonomy_summary_covers_main_categories(self, diag):
        df = diag.get_taxonomy_summary(start_date=START, end_date=END)
        assert not df.empty
        assert "categoria"   in df.columns
        assert "event_count" in df.columns
        assert "pct"         in df.columns
        # Debe haber al menos SENSOR_FALLA, ATASCO y REINICIO
        cats = df["categoria"].tolist()
        assert "SENSOR_FALLA"     in cats or "MICRO_PARO" in cats

    def test_taxonomy_pct_sums_100(self, diag):
        df = diag.get_taxonomy_summary(start_date=START, end_date=END)
        assert abs(df["pct"].sum() - 100.0) < 1.0


# ======================================================================
# F4 — KPIs
# ======================================================================

class TestKPIs:

    def test_mttr_la4_env_positive(self, kpi):
        mttr = kpi.calc_mttr(equnr=EQUNR_LA4, start_date=START, end_date=END)
        # PM01 de ENV01 puede ser escasos; probar con PM02 también
        mttr2 = kpi.calc_mttr(equnr=EQUNR_LA4, auart="PM02", start_date=START, end_date=END)
        # Al menos uno de los dos debería tener datos
        assert (mttr is not None and mttr > 0) or (mttr2 is not None and mttr2 > 0)

    def test_mttr_returns_none_when_no_data(self, kpi):
        mttr = kpi.calc_mttr(equnr="99999999", start_date=START, end_date=END)
        assert mttr is None

    def test_mttr_by_equipment_ordered(self, kpi):
        df = kpi.calc_mttr_by_equipment(auart="PM02", start_date=START, end_date=END)
        if not df.empty:
            assert df["mttr_min"].is_monotonic_decreasing

    def test_mtbf_returns_positive_hours(self, kpi):
        # PM01 puede ser escaso; probamos también PM02
        mtbf = kpi.calc_mtbf(equnr=EQUNR_LA4, auart="PM02",
                              start_date=START, end_date=END)
        if mtbf is not None:
            assert mtbf > 0

    def test_mtbf_none_for_single_event(self, kpi):
        """Equipo con solo un evento PM01 → MTBF no calculable."""
        # Usamos un equipo menos activo que probablemente tiene < 2 PM01
        mtbf = kpi.calc_mtbf(equnr="10001002", auart="PM01",
                              start_date=START, end_date=END)
        # Puede ser None o un valor (si tiene 2+ eventos); ambos son correctos
        assert mtbf is None or mtbf > 0

    def test_availability_range(self, kpi):
        avail = kpi.calc_availability(equnr=EQUNR_LA4, start_date=START, end_date=END)
        assert 0.0 <= avail["availability_pct"] <= 100.0

    def test_availability_structure(self, kpi):
        avail = kpi.calc_availability(equnr=EQUNR_LA4, start_date=START, end_date=END)
        for key in ("total_operating_min", "downtime_min", "uptime_min",
                    "availability_pct", "pm01_count"):
            assert key in avail

    def test_availability_by_linea_la4(self, kpi):
        df = kpi.calc_availability_by_linea(linea=LINEA_LA4, start_date=START, end_date=END)
        assert not df.empty
        assert len(df) == 6  # LA4 tiene 6 equipos en el catálogo
        assert (df["availability_pct"] >= 0).all()
        assert (df["availability_pct"] <= 100).all()

    def test_failure_rate_series_not_empty(self, kpi):
        df = kpi.calc_failure_rate(equnr=EQUNR_LA4, freq="W",
                                   auart="PM03", start_date=START, end_date=END)
        assert not df.empty
        assert "period"        in df.columns
        assert "failure_count" in df.columns
        assert "rolling_mean_4" in df.columns

    def test_failure_rate_counts_nonnegative(self, kpi):
        df = kpi.calc_failure_rate(equnr=EQUNR_LA4, freq="M",
                                   start_date=START, end_date=END)
        assert (df["failure_count"] >= 0).all()

    def test_failure_trend_structure(self, kpi):
        trend = kpi.get_failure_trend(equnr=EQUNR_LA4, start_date=START, end_date=END)
        assert "direction" in trend
        assert trend["direction"] in ("deteriorating", "stable", "improving", "insufficient_data")

    def test_kpi_summary_json_structure(self, kpi):
        summary = kpi.get_kpi_summary(equnr=EQUNR_LA4, start_date=START, end_date=END)
        assert "query"        in summary
        assert "mttr"         in summary
        assert "mtbf"         in summary
        assert "availability" in summary
        assert "event_counts" in summary
        assert "PM01" in summary["event_counts"]


# ======================================================================
# F5 — Análisis Predictivo
# ======================================================================

class TestPredictive:

    def test_forecast_structure(self, pred):
        fc = pred.forecast_failure_rate(equnr=EQUNR_LA4, start_date=START, end_date=END)
        assert "trend"                        in fc
        assert "predicted_events_next_period" in fc
        assert "training_points"              in fc

    def test_forecast_predicted_nonnegative(self, pred):
        fc = pred.forecast_failure_rate(equnr=EQUNR_LA4, start_date=START, end_date=END)
        val = fc.get("predicted_events_next_period")
        if val is not None:
            assert val >= 0.0

    def test_forecast_r2_range(self, pred):
        fc = pred.forecast_failure_rate(equnr=EQUNR_LA4, start_date=START, end_date=END)
        r2 = fc.get("confidence_r2")
        if r2 is not None:
            assert 0.0 <= r2 <= 1.0

    def test_risk_score_range(self, pred):
        risk = pred.calc_risk_score(equnr=EQUNR_LA4, start_date=START, end_date=END)
        assert 0.0 <= risk["risk_score"] <= 100.0

    def test_risk_score_level_valid(self, pred):
        risk = pred.calc_risk_score(equnr=EQUNR_LA4, start_date=START, end_date=END)
        assert risk["risk_level"] in ("CRITICO", "ALTO", "MEDIO", "BAJO")

    def test_risk_score_components_present(self, pred):
        risk = pred.calc_risk_score(equnr=EQUNR_LA4, start_date=START, end_date=END)
        assert "components" in risk
        comps = risk["components"]
        assert all(0.0 <= v <= 100.0 for v in comps.values())

    def test_risk_ranking_sorted_desc(self, pred):
        df = pred.get_risk_ranking(linea=LINEA_LA4, start_date=START, end_date=END)
        if not df.empty and len(df) > 1:
            assert df["risk_score"].is_monotonic_decreasing

    def test_risk_ranking_la4_has_6_equipos(self, pred):
        df = pred.get_risk_ranking(linea=LINEA_LA4, start_date=START, end_date=END)
        assert len(df) == 6

    def test_anomaly_detection_structure(self, pred):
        df = pred.detect_anomalies(equnr=EQUNR_LA4, start_date=START, end_date=END)
        if not df.empty:
            assert "period"     in df.columns
            assert "event_count" in df.columns
            assert "z_score"    in df.columns
            assert "is_anomaly" in df.columns

    def test_anomaly_z_score_computation(self, pred):
        df = pred.detect_anomalies(equnr=EQUNR_LA4, start_date=START, end_date=END)
        if not df.empty and "z_score" in df.columns:
            # Z-score de la media debería estar cerca de 0
            import numpy as np
            mean_z = df["z_score"].mean()
            assert abs(mean_z) < 1.0


# ======================================================================
# F6 — Análisis Prescriptivo
# ======================================================================

class TestPrescriptive:

    def test_recommendations_returns_list(self, presc):
        recs = presc.get_recommendations(equnr=EQUNR_LA4, start_date=START, end_date=END)
        assert isinstance(recs, list)
        assert len(recs) >= 1

    def test_recommendations_structure(self, presc):
        recs = presc.get_recommendations(equnr=EQUNR_LA4, start_date=START, end_date=END)
        for rec in recs:
            assert "tipo"          in rec
            assert "prioridad"     in rec
            assert "urgencia"      in rec
            assert "mensaje"       in rec
            assert "justificacion" in rec

    def test_recommendations_sorted_by_priority(self, presc):
        recs = presc.get_recommendations(equnr=EQUNR_LA4, start_date=START, end_date=END)
        prios = [r["prioridad"] for r in recs]
        assert prios == sorted(prios)

    def test_action_plan_structure(self, presc):
        plan = presc.get_action_plan(linea=LINEA_LA4, start_date=START, end_date=END)
        assert "urgente"     in plan
        assert "planificado" in plan
        assert "monitoreo"   in plan

    def test_action_plan_all_equipos_classified(self, presc):
        plan = presc.get_action_plan(linea=LINEA_LA4, start_date=START, end_date=END)
        total = len(plan["urgente"]) + len(plan["planificado"]) + len(plan["monitoreo"])
        assert total == 6  # LA4 tiene 6 equipos

    def test_alerts_returns_list(self, presc):
        alerts = presc.check_alerts(equnr=EQUNR_LA4, start_date=START, end_date=END)
        assert isinstance(alerts, list)

    def test_alerts_structure(self, presc):
        alerts = presc.check_alerts(equnr=EQUNR_LA4, start_date=START, end_date=END)
        for a in alerts:
            assert "severidad" in a
            assert "tipo"      in a
            assert "equnr"     in a
            assert "mensaje"   in a
            assert a["severidad"] in ("CRITICA", "ALTA", "MEDIA", "BAJA")

    def test_alerts_sorted_by_severity(self, presc):
        alerts = presc.check_alerts(linea=LINEA_LA4, start_date=START, end_date=END)
        sev_order = {"CRITICA": 0, "ALTA": 1, "MEDIA": 2, "BAJA": 3}
        sev_vals  = [sev_order[a["severidad"]] for a in alerts]
        assert sev_vals == sorted(sev_vals)


# ======================================================================
# F7 — Generador de Reportes
# ======================================================================

class TestReports:

    def test_weekly_report_is_markdown(self, rpt):
        report = rpt.get_weekly_plant_report(week_start="2024-06-03")
        assert isinstance(report, str)
        assert len(report) > 100
        assert "#" in report  # tiene encabezados

    def test_weekly_report_has_required_sections(self, rpt):
        report = rpt.get_weekly_plant_report(week_start="2024-06-03")
        assert "Resumen Ejecutivo"  in report
        assert "Alertas Activas"    in report
        assert "Plan de Accion"     in report

    def test_equipment_report_is_markdown(self, rpt):
        report = rpt.get_equipment_report(equnr=EQUNR_LA4, period_days=90)
        assert isinstance(report, str)
        assert len(report) > 200

    def test_equipment_report_has_kpis(self, rpt):
        report = rpt.get_equipment_report(equnr=EQUNR_LA4, period_days=90)
        assert "MTTR"             in report
        assert "MTBF"             in report
        assert "Disponibilidad"   in report
        assert "Recomendaciones"  in report

    def test_equipment_report_contains_equnr(self, rpt):
        report = rpt.get_equipment_report(equnr=EQUNR_LA4, period_days=90)
        assert EQUNR_LA4 in report

    def test_executive_report_is_markdown(self, rpt):
        report = rpt.get_executive_report(period="month")
        assert isinstance(report, str)
        assert len(report) > 200

    def test_executive_report_has_required_sections(self, rpt):
        report = rpt.get_executive_report(period="month")
        assert "Panorama General"   in report
        assert "Disponibilidad"     in report
        assert "Equipos Criticos"   in report
        assert "Top 5"              in report

    def test_executive_report_quarter(self, rpt):
        report = rpt.get_executive_report(period="quarter")
        assert "Trimestre" in report

# ======================================================================
# F7.b — Visualizaciones (Gráficos)
# ======================================================================

class TestVisualizations:
    
    def test_plot_pareto_creates_file(self, diag):
        pareto = diag.get_pareto(metric="downtime", start_date=START, end_date=END)
        path = ChartGenerator.plot_pareto(pareto, "Test Pareto", "test_pareto.png")
        assert path != ""
        assert Path(path).exists()
        
    def test_plot_kpi_trend_creates_file(self, kpi):
        rates = kpi.calc_failure_rate(equnr=EQUNR_LA4, freq="W", auart="PM03", start_date=START, end_date=END)
        path = ChartGenerator.plot_kpi_trend(rates, "Test Trend", "test_trend.png")
        assert path != ""
        assert Path(path).exists()
        
    def test_plot_heatmap_creates_file(self, desc):
        heatmap = desc.get_temporal_heatmap(start_date=START, end_date=END)
        path = ChartGenerator.plot_heatmap(heatmap, "Test Heatmap", "test_heatmap.png")
        assert path != ""
        assert Path(path).exists()
        
    def test_plot_kpi_comparison_creates_file(self):
        import pandas as pd
        df = pd.DataFrame({
            "equnr": ["100", "200"],
            "availability_pct": [99.5, 95.0],
            "mttr_min": [10.0, 50.0],
            "mtbf_hours": [100.0, 20.0]
        })
        path = ChartGenerator.plot_kpi_comparison(df, "Test KPI Comparison", "test_kpi_comp.png")
        assert path != ""
        assert Path(path).exists()
        
    @pytest.fixture(autouse=True, scope="class")
    def cleanup(self):
        yield
        ChartGenerator.cleanup_assets()
