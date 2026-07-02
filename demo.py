"""
demo.py
-------
Demo interactivo de MantOS — Motor de Analisis.
Muestra outputs reales de cada modulo con los datos de la Planta Galletera Sur.

Uso:
    python demo.py                    # demo completo
    python demo.py --modulo kpis      # solo un modulo
    python demo.py --equipo 10004003  # enfocado en un equipo
    python demo.py --reporte equipo   # genera reporte Markdown y lo guarda

Modulos disponibles: descriptivo, diagnostico, kpis, predictivo, prescriptivo, reportes
"""

import argparse
import sys
import subprocess
from pathlib import Path

# Asegurar que el proyecto raiz esta en el path
_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(_ROOT))

from analysis.descriptive  import DescriptiveAnalysis
from analysis.diagnostic   import DiagnosticAnalysis
from analysis.kpis         import KPICalculator
from analysis.predictive   import PredictiveAnalysis
from analysis.prescriptive import PrescriptiveAnalysis
from analysis.reports      import ReportGenerator

DB_PATH = _ROOT / "data" / "mantos.db"

# Período de demo: 1 año del dataset
DEMO_START = "2023-10-01T00:00:00Z"
DEMO_END   = "2024-09-30T23:59:59Z"

# Equipo principal de demo: LA4-ENV01 (Envasadora — más activo del dataset)
DEMO_EQUNR = "10004003"
DEMO_LINEA = "LA1"

SEP  = "=" * 60
SEP2 = "-" * 60


def header(title: str):
    print()
    print(SEP)
    print(f"  {title}")
    print(SEP)


def subheader(title: str):
    print()
    print(SEP2)
    print(f"  {title}")
    print(SEP2)


# ======================================================================
# Demo 1 — Análisis Descriptivo
# ======================================================================

def demo_descriptivo():
    header("F2 — ANALISIS DESCRIPTIVO")
    desc = DescriptiveAnalysis(DB_PATH)

    # 2.1 — Top 5 equipos por eventos
    subheader("2.1  Top 5 Equipos por Eventos (Apr-Sep 2024)")
    top = desc.get_top_equipment_by_events(n=5, start_date=DEMO_START, end_date=DEMO_END)
    print(f"{'Equipo':<12} {'Nombre':<25} {'Linea':<6} {'Eventos':>8} {'Downtime(min)':>14} {'%Total':>8}")
    print("-" * 80)
    for _, r in top.iterrows():
        print(f"{r['equnr']:<12} {str(r.get('nombre_equipo','')):<25} "
              f"{str(r.get('linea','')):<6} {r['event_count']:>8,} "
              f"{r['downtime_min']:>14.1f} {r['pct_of_total']:>7.1f}%")

    # 2.2 — Mapa de calor: pico de actividad
    subheader("2.2  Mapa de Calor Temporal — LA4-ENV01 (hora pico por dia)")
    heatmap = desc.get_temporal_heatmap(
        equnr=DEMO_EQUNR, start_date=DEMO_START, end_date=DEMO_END
    )
    print(f"Hora con mas eventos por dia de semana:")
    for col in heatmap.columns:
        hora_pico = heatmap[col].idxmax()
        max_val   = heatmap[col].max()
        print(f"  {col}: hora {hora_pico:02d}h  ({max_val} eventos)")

    # 2.3 — Estadísticas de duración
    subheader("2.3  Distribucion de Duracion de Eventos")
    stats = desc.get_duration_stats(start_date=DEMO_START, end_date=DEMO_END)
    print(f"  Eventos con duracion > 0 : {stats['count']:,}")
    print(f"  Media                    : {stats['mean']} min")
    print(f"  Mediana                  : {stats['median']} min")
    print(f"  Percentil 90             : {stats['p90']} min")
    print(f"  Maximo                   : {stats['max']} min")
    print(f"  Downtime total acumulado : {stats['total_downtime_min']:,.1f} min ({stats['total_downtime_min']/60:.1f} h)")
    print(f"  Ghost stops excluidos    : {stats['ghost_stops_excluded']}")

    # 2.4 — Top keywords
    subheader("2.4  Top 10 Keywords en Textos de Falla (LA4)")
    kws = desc.get_top_keywords(linea=DEMO_LINEA, n=10,
                                 start_date=DEMO_START, end_date=DEMO_END)
    for rank, (word, freq) in enumerate(kws, 1):
        bar = "#" * min(40, freq // 2)
        print(f"  {rank:2}. {word:<20} {freq:4} {bar}")

    desc.close()


# ======================================================================
# Demo 2 — Análisis de Diagnóstico
# ======================================================================

def demo_diagnostico():
    header("F3 — ANALISIS DE DIAGNOSTICO")
    diag = DiagnosticAnalysis(DB_PATH)

    # 3.1 — Pareto
    subheader("3.1  Pareto de Downtime — Top 10 equipos")
    pareto = diag.get_pareto(metric="downtime", top_n=10,
                              start_date=DEMO_START, end_date=DEMO_END)
    print(f"{'#':<3} {'Equipo':<12} {'Downtime(min)':>14} {'%':>6} {'Cum%':>7} {'Vital?':>7}")
    print("-" * 55)
    for i, (_, r) in enumerate(pareto.iterrows(), 1):
        vital = "SI" if r["is_vital_few"] else ""
        print(f"{i:<3} {r['group_key']:<12} {r['downtime_min']:>14.1f} "
              f"{r['pct']:>5.1f}% {r['cumulative_pct']:>6.1f}%  {vital:>6}")
    vital_count = pareto["is_vital_few"].sum()
    print(f"\n  --> {vital_count} equipos concentran el 80% del downtime (Regla 80/20)")

    # 3.2 — Ghost stops
    subheader("3.2  Auditoria de Paros Fantasma")
    audit = diag.audit_ghost_stops(start_date=DEMO_START, end_date=DEMO_END)
    print(f"  Total ghost stops en el periodo : {audit['total_ghost_stops']}")
    print(f"  Principal generador (equipo)    : {audit['top_generator_equip']}")
    print(f"  Principal generador (usuario)   : {audit['top_generator_user']}")
    print()
    print("  Top 5 usuarios que generan ghost stops:")
    print(f"  {'Usuario':<15} {'Tipo':<12} {'Ghost Stops':>12} {'%Total':>8}")
    print("  " + "-" * 50)
    for _, r in audit["by_user"].head(5).iterrows():
        print(f"  {r['ernam']:<15} {str(r.get('tipo','')):<12} "
              f"{r['ghost_count']:>12} {r.get('pct', 0.0):>7.1f}%")

    # 3.3 — Recurrencia
    subheader("3.3  Patrones de Recurrencia (ventana 7 dias)")
    rec = diag.get_recurring_failures(threshold=0.4,
                                       start_date=DEMO_START, end_date=DEMO_END)
    if rec.empty:
        print("  Sin equipos con recurrencia alta en el periodo.")
    else:
        print(f"  Equipos con recurrencia >= 40%:")
        for _, r in rec.iterrows():
            bar = "#" * int(r["recurrence_score"] * 20)
            print(f"  {r['equnr']} ({r.get('nombre_equipo',''):<22}) "
                  f"score={r['recurrence_score']:.2f}  {bar}")

    # 3.4 — Taxonomía
    subheader("3.4  Taxonomia de Fallas (categorias canonicas)")
    tax = diag.get_taxonomy_summary(start_date=DEMO_START, end_date=DEMO_END)
    print(f"  {'Categoria':<30} {'Eventos':>8} {'%':>6} {'Downtime(min)':>14}")
    print("  " + "-" * 65)
    for _, r in tax.iterrows():
        print(f"  {r['categoria']:<30} {r['event_count']:>8,} {r['pct']:>5.1f}%  {r['downtime_min']:>12.1f}")

    diag.close()


# ======================================================================
# Demo 3 — KPIs
# ======================================================================

def demo_kpis():
    header("F4 — CALCULADORA DE KPIs")
    kpi = KPICalculator(DB_PATH)

    # KPIs por equipo LA4
    subheader(f"4.1-4.3  KPIs Individuales — {DEMO_LINEA}")
    print(f"  {'Equipo':<12} {'Nombre':<22} {'MTTR(min)':>10} {'MTBF(h)':>9} {'Disp%':>7} {'Downtime':>10}")
    print("  " + "-" * 75)

    df_eq = kpi.query("SELECT equnr, nombre_equipo, tplnr FROM equipment WHERE linea = ?", (DEMO_LINEA,))
    
    def extract_tag(t):
        if not t: return ""
        parts = str(t).split("-")
        return f"{parts[-2]}_{parts[-1]}" if len(parts) >= 2 else t
        
    equipos_linea = list(zip(df_eq["equnr"], df_eq["nombre_equipo"], df_eq["tplnr"].apply(extract_tag)))

    # Si el DEMO_EQUNR no está en la línea, usamos el primero
    global DEMO_EQUNR
    if not any(eq[0] == DEMO_EQUNR for eq in equipos_linea) and equipos_linea:
        DEMO_EQUNR = equipos_linea[0][0]

    for equnr, nombre, tag in equipos_linea:
        mttr = kpi.calc_mttr(equnr=equnr, auart=None,
                              start_date=DEMO_START, end_date=DEMO_END)
        mtbf = kpi.calc_mtbf(equnr=equnr, auart=None,
                              start_date=DEMO_START, end_date=DEMO_END)
        avail = kpi.calc_availability(equnr=equnr,
                                       start_date=DEMO_START, end_date=DEMO_END)
        print(f"  {tag:<12} {nombre:<22} "
              f"{f'{mttr:.1f}' if mttr else 'N/A':>10} "
              f"{f'{mtbf:.1f}' if mtbf else 'N/A':>9} "
              f"{avail['availability_pct']:>6.2f}%"
              f"{avail['downtime_min']:>10.0f}m")

    # Tasa de fallas mensual para ENV01
    # Tasa de fallas mensual para equipo
    subheader(f"4.4  Tasa de Fallas Mensual — {DEMO_EQUNR} (PM03)")
    rates = kpi.calc_failure_rate(equnr=DEMO_EQUNR, auart="PM03",
                                   freq="M", start_date=DEMO_START, end_date=DEMO_END)
    print(f"  {'Mes':<12} {'Eventos':>8} {'Media Movil(4)':>15}")
    print("  " + "-" * 40)
    for _, r in rates.iterrows():
        bar = "#" * int(r["failure_count"])
        print(f"  {r['period'][:7]:<12} {r['failure_count']:>8}   "
              f"{r['rolling_mean_4']:>8.1f}    {bar}")

    # Tendencia
    trend = kpi.get_failure_trend(equnr=DEMO_EQUNR,
                                   start_date=DEMO_START, end_date=DEMO_END)
    print()
    trend_str = {
        "deteriorating": "EMPEORANDO (pendiente positiva)",
        "stable":        "ESTABLE",
        "improving":     "MEJORANDO (pendiente negativa)",
    }.get(trend["direction"], trend["direction"])
    print(f"  Tendencia detectada: {trend_str}")
    slope = trend.get('slope')
    r_sq  = trend.get('r_squared')
    print(f"  Pendiente          : {slope:.4f} eventos/semana" if slope is not None else "  Pendiente          : N/A")
    print(f"  R²                 : {r_sq:.4f}" if r_sq is not None else "  R²                 : N/A")

    kpi.close()


# ======================================================================
# Demo 4 — Análisis Predictivo
# ======================================================================

def demo_predictivo():
    header("F5 — ANALISIS PREDICTIVO")
    pred = PredictiveAnalysis(DB_PATH)

    # Ranking de riesgo LA4
    subheader(f"5.2  Ranking de Riesgo — {DEMO_LINEA}")
    ranking = pred.get_risk_ranking(linea=DEMO_LINEA,
                                     start_date=DEMO_START, end_date=DEMO_END)
    print(f"  {'#':<3} {'Equipo':<12} {'Nombre':<22} {'Score':>7} {'Nivel':<10} {'Tendencia'}")
    print("  " + "-" * 75)
    for i, (_, r) in enumerate(ranking.iterrows(), 1):
        icon = {"CRITICO": "[!!]", "ALTO": "[! ]", "MEDIO": "[ .]", "BAJO": "[  ]"}.get(r["risk_level"], "    ")
        tag = r.get("tag_equipo", r["equnr"])
        print(f"  {i:<3} {tag:<12} {str(r.get('nombre_equipo','')):<22} "
              f"{r['risk_score']:>6.1f}  {icon} {r['risk_level']:<8}  {r.get('trend_direction','')}")

    # Forecast para el equipo más activo
    subheader(f"5.1  Pronostico de Fallas — {DEMO_EQUNR} (proxima semana)")
    forecast = pred.forecast_failure_rate(equnr=DEMO_EQUNR,
                                           start_date=DEMO_START, end_date=DEMO_END)
    print(f"  Eventos estimados (proxima semana) : {forecast.get('predicted_events_next_period', 'N/A')}")
    print(f"  Ultimo valor observado             : {forecast.get('last_observed_count', 'N/A')}")
    print(f"  Confianza del modelo (R²)          : {forecast.get('confidence_r2', 'N/A')}")
    print(f"  Tendencia                          : {forecast.get('trend', 'N/A')}")
    print(f"  Pendiente                          : {forecast.get('slope', 'N/A')} eventos/semana")

    # Anomalías
    subheader(f"5.3  Semanas Anomalas — {DEMO_EQUNR}")
    anom = pred.detect_anomalies(equnr=DEMO_EQUNR,
                                  start_date=DEMO_START, end_date=DEMO_END)
    anomalias = anom[anom["is_anomaly"] == True] if "is_anomaly" in anom.columns else anom
    if anomalias.empty:
        print("  No se detectaron semanas anomalas en el periodo.")
    else:
        print(f"  {len(anomalias)} semanas con actividad fuera de lo normal (Z-score > 2):")
        print(f"  {'Semana':<15} {'Eventos':>8} {'Media':>8} {'Z-Score':>9}")
        print("  " + "-" * 45)
        for _, r in anomalias.head(5).iterrows():
            print(f"  {str(r['period'])[:10]:<15} {r['event_count']:>8.0f} "
                  f"{r['mean']:>8.1f} {r['z_score']:>9.2f}")

    pred.close()


# ======================================================================
# Demo 5 — Prescriptivo
# ======================================================================

def demo_prescriptivo():
    header("F6 — ANALISIS PRESCRIPTIVO")
    presc = PrescriptiveAnalysis(DB_PATH)

    # Plan de acción para LA4
    subheader(f"6.2  Plan de Accion — {DEMO_LINEA}")
    plan = presc.get_action_plan(linea=DEMO_LINEA,
                                  start_date=DEMO_START, end_date=DEMO_END)

    print(f"\n  [URGENTE] — {len(plan['urgente'])} equipos")
    for e in plan["urgente"]:
        tag = e.get("tag_equipo", e["equnr"])
        print(f"    >> {tag} ({e.get('nombre_equipo','')}) — Score: {e['risk_score']:.0f}")
        if e.get("top_recommendation"):
            print(f"       {e['top_recommendation']}")

    print(f"\n  [PLANIFICADO] — {len(plan['planificado'])} equipos")
    for e in plan["planificado"]:
        tag = e.get("tag_equipo", e["equnr"])
        print(f"    -> {tag} ({e.get('nombre_equipo','')}) — Score: {e['risk_score']:.0f}")

    print(f"\n  [MONITOREO] — {len(plan['monitoreo'])} equipos")
    for e in plan["monitoreo"]:
        tag = e.get("tag_equipo", e["equnr"])
        print(f"     . {tag} ({e.get('nombre_equipo','')}) — Score: {e['risk_score']:.0f}")

    # Recomendaciones detalladas para ENV01
    subheader(f"6.1  Recomendaciones — {DEMO_EQUNR}")
    recs = presc.get_recommendations(equnr=DEMO_EQUNR,
                                      start_date=DEMO_START, end_date=DEMO_END)
    for r in recs:
        print(f"\n  [{r['prioridad']}] {r['urgencia']}")
        print(f"  Tipo    : {r['tipo']}")
        print(f"  Mensaje : {r['mensaje']}")
        print(f"  Razon   : {r['justificacion']}")

    # Alertas
    subheader(f"6.3  Alertas Activas — {DEMO_LINEA}")
    alerts = presc.check_alerts(linea=DEMO_LINEA,
                                 start_date=DEMO_START, end_date=DEMO_END)
    if not alerts:
        print("  Sin alertas activas.")
    else:
        for a in alerts:
            print(f"  [{a['severidad']:<8}] {a['equnr']} — {a['mensaje']}")

    presc.close()


# ======================================================================
# Demo 6 — Reportes
# ======================================================================

def demo_reportes(save_to_disk: bool = True, export_pdf: bool = False):
    header("F7 — GENERADOR DE REPORTES")
    rpt = ReportGenerator(DB_PATH)
    output_dir = _ROOT / "data" / "reports"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    generated_files = []

    # Reporte por equipo
    subheader(f"7.2  Reporte por Equipo — {DEMO_EQUNR}")
    eq_report = rpt.get_equipment_report(equnr=DEMO_EQUNR, period_days=90,
                                          end_date=DEMO_END)
    if save_to_disk:
        out = output_dir / f"reporte_{DEMO_EQUNR}.md"
        out.write_text(eq_report, encoding="utf-8")
        generated_files.append(out)
        print(f"  Guardado en: {out}")
    print()
    # Mostrar primeras 30 líneas del reporte
    lines = eq_report.split("\n")[:30]
    for line in lines:
        print(f"  {line}")
    print("  [... reporte completo guardado en disco ...]")

    # Reporte ejecutivo
    subheader("7.3  Reporte Ejecutivo (ultimo año)")
    exec_report = rpt.get_executive_report(period="year", end_date=DEMO_END, linea=DEMO_LINEA)
    if save_to_disk:
        out = output_dir / "reporte_ejecutivo.md"
        out.write_text(exec_report, encoding="utf-8")
        generated_files.append(out)
        print(f"  Guardado en: {out}")
    print()
    lines = exec_report.split("\n")[:25]
    for line in lines:
        print(f"  {line}")
    print("  [... reporte completo guardado en disco ...]")

    # Reporte semanal
    subheader("7.1  Reporte Semanal de Planta")
    weekly = rpt.get_weekly_plant_report(week_start="2024-09-02")
    if save_to_disk:
        out = output_dir / "reporte_semanal_2024-09-02.md"
        out.write_text(weekly, encoding="utf-8")
        generated_files.append(out)
        print(f"  Guardado en: {out}")

    rpt.close()

    # Reporte ejecutivo en PDF
    subheader("7.4  Generar Reporte PDF (fpdf)")
    if export_pdf:
        pdf_out = output_dir / "reporte_ejecutivo_directo.pdf"
        print(f"  Generando PDF directo en: {pdf_out}")
        success = rpt.export_executive_report_pdf(str(pdf_out), period="year", end_date=DEMO_END, linea=DEMO_LINEA)
        if success:
            print("  -> OK: PDF generado exitosamente.")
        else:
            print("  -> ERROR al generar PDF (verifica dependencias de fpdf).")


# ======================================================================
# Entrypoint
# ======================================================================

def main():
    parser = argparse.ArgumentParser(
        description="MantOS — Demo del Motor de Analisis"
    )
    parser.add_argument(
        "--modulo",
        choices=["descriptivo", "diagnostico", "kpis", "predictivo", "prescriptivo", "reportes", "todos"],
        default="todos",
        help="Modulo a demostrar (default: todos)",
    )
    parser.add_argument(
        "--equipo",
        default=DEMO_EQUNR,
        help=f"Equipo a analizar (default: {DEMO_EQUNR})",
    )
    parser.add_argument(
        "--no-guardar",
        action="store_true",
        help="No guardar reportes en disco",
    )
    parser.add_argument(
        "--pdf",
        action="store_true",
        help="Exportar los reportes a PDF automaticamente (usando fpdf)",
    )
    args = parser.parse_args()

    if not DB_PATH.exists():
        print(f"ERROR: Base de datos no encontrada en {DB_PATH}")
        print("Ejecuta primero: python ingestion/ingest.py")
        sys.exit(1)

    print()
    print(SEP)
    print("  MantOS v0.2 — Demo del Motor de Analisis")
    print(f"  Planta Galletera Sur | Periodo: {DEMO_START[:10]} -> {DEMO_END[:10]}")
    print(SEP)

    modulo = args.modulo
    save   = not args.no_guardar

    run_all = modulo == "todos"

    if run_all or modulo == "descriptivo":
        demo_descriptivo()
    if run_all or modulo == "diagnostico":
        demo_diagnostico()
    if run_all or modulo == "kpis":
        demo_kpis()
    if run_all or modulo == "predictivo":
        demo_predictivo()
    if run_all or modulo == "prescriptivo":
        demo_prescriptivo()
    if run_all or modulo == "reportes":
        demo_reportes(save_to_disk=save, export_pdf=args.pdf)

    print()
    print(SEP)
    print("  Demo completado.")
    if save and (run_all or modulo == "reportes"):
        print(f"  Reportes guardados en: {_ROOT / 'data' / 'reports'}")
    print(SEP)
    print()


if __name__ == "__main__":
    main()
