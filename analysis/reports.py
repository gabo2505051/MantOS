"""
reports.py  — F7: Generador de Reportes
----------------------------------------
Consolida todos los análisis en reportes estructurados en formato Markdown.

  7.1  Reporte semanal de planta
  7.2  Reporte por equipo (deep-dive)
  7.3  Reporte ejecutivo de KPIs
"""

from datetime import datetime, timezone, timedelta
import subprocess
from pathlib import Path
from typing import Optional

import pandas as pd

from analysis.base import AnalysisBase
from analysis.descriptive import DescriptiveAnalysis
from analysis.diagnostic import DiagnosticAnalysis
from analysis.kpis import KPICalculator
from analysis.predictive import PredictiveAnalysis
from analysis.prescriptive import PrescriptiveAnalysis
from analysis.visualizations import ChartGenerator


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def _md_table(headers: list, rows: list) -> str:
    """Genera una tabla Markdown simple."""
    sep = "| " + " | ".join(["---"] * len(headers)) + " |"
    hdr = "| " + " | ".join(str(h) for h in headers) + " |"
    body = "\n".join("| " + " | ".join(str(c) for c in row) + " |" for row in rows)
    return "\n".join([hdr, sep, body])


class ReportGenerator(AnalysisBase):
    """Genera reportes en Markdown consolidando todos los módulos de análisis."""

    def __init__(self, db_path=None):
        super().__init__(db_path)
        _db = db_path or self.db_path
        self._desc  = DescriptiveAnalysis(_db)
        self._diag  = DiagnosticAnalysis(_db)
        self._kpi   = KPICalculator(_db)
        self._pred  = PredictiveAnalysis(_db)
        self._presc = PrescriptiveAnalysis(_db)
        self._charts = ChartGenerator()

    def save_as_pdf(self, markdown_content: str, output_pdf_path: str) -> bool:
        """
        [DEPRECADO] Usado anteriormente con npx markdown-pdf.
        Ahora se prefiere la generación directa con fpdf (ver export_executive_report_pdf).
        """
        print("[MantOS] Nota: save_as_pdf está deprecado. Usar los métodos directos export_*_pdf.")
        return False

    # ------------------------------------------------------------------
    # 7.1 — Reporte semanal de planta
    # ------------------------------------------------------------------

    def get_weekly_plant_report(
        self,
        week_start: Optional[str] = None,
    ) -> str:
        """
        Genera el reporte semanal de la planta completa.

        Args:
            week_start: ISO date del lunes de la semana (ej: '2024-06-03').
                        Si es None, usa la última semana completa.

        Returns:
            String Markdown listo para imprimir o enviar al agente.
        """
        if week_start:
            start = week_start + "T00:00:00Z"
            end   = (datetime.fromisoformat(week_start) + timedelta(days=6)).strftime("%Y-%m-%dT23:59:59Z")
        else:
            # Última semana completa del dataset
            start = "2026-03-24T00:00:00Z"
            end   = "2026-03-30T23:59:59Z"

        # Recopilar datos
        summary  = self._desc.get_failure_summary(start_date=start, end_date=end)
        top_eq   = self._desc.get_top_equipment_by_events(n=5, start_date=start, end_date=end)
        pareto   = self._diag.get_pareto(metric="downtime", start_date=start, end_date=end, top_n=10)
        alerts   = self._presc.check_alerts(start_date=start, end_date=end)
        plan     = self._presc.get_action_plan(start_date=start, end_date=end)
        tax      = self._diag.get_taxonomy_summary(start_date=start, end_date=end)
        
        # Generar gráficos
        pareto_img = self._charts.plot_pareto(pareto, "Pareto de Downtime por Equipo", f"pareto_semanal_{week_start or 'latest'}.png")

        lines = [
            f"# Reporte Semanal de Planta — MantOS",
            f"",
            f"**Planta**: Galletera Sur (PGS)  ",
            f"**Período**: `{start}` -> `{end}`  ",
            f"**Generado**: {_now()}",
            f"",
            f"---",
            f"",
            f"## Resumen Ejecutivo",
            f"",
            f"| Indicador | Valor |",
            f"|---|---|",
            f"| Total eventos | **{summary['total_events']:,}** |",
            f"| Paros fantasma | {summary['ghost_stops']:,} ({summary['ghost_pct']}%) |",
        ]

        # Desglose por tipo
        for auart, data in summary.get("by_type", {}).items():
            lines.append(f"| {auart} ({_auart_label(auart)}) | {data.get('cnt', 0):,} eventos — {data.get('dt', 0):,.1f} min downtime |")

        lines += [
            f"",
            f"---",
            f"",
            f"## Alertas Activas ({len(alerts)})",
            f"",
        ]

        if alerts:
            for a in alerts[:10]:  # máximo 10 alertas
                icon = {"CRITICA": "[X]", "ALTA": "[!]", "MEDIA": "[-]", "BAJA": "[ok]"}.get(a["severidad"], "[?]")
                lines.append(f"- {icon} **[{a['severidad']}]** `{a['equnr']}` — {a['mensaje']}")
        else:
            lines.append("_Sin alertas activas en el período._")

        lines += [
            f"",
            f"---",
            f"",
            f"## Top 5 Equipos por Eventos",
            f"",
        ]

        if not top_eq.empty:
            rows = [
                [r["equnr"], r.get("nombre_equipo", ""), r.get("linea", ""),
                 r["event_count"], f"{r['downtime_min']:.0f} min"]
                for _, r in top_eq.iterrows()
            ]
            lines.append(_md_table(
                ["Equipo", "Nombre", "Linea", "Eventos", "Downtime"],
                rows
            ))
        else:
            lines.append("_Sin datos._")

        lines += [
            f"",
            f"---",
            f"",
            f"## Taxonomia de Fallas (Pareto)",
            f"",
        ]
        
        if pareto_img:
            # Reemplazar barras invertidas de Windows para evitar escape
            img_path = pareto_img.replace('\\', '/')
            lines.append(f"![Pareto Downtime](file:///{img_path})")
            lines.append("")

        if not tax.empty:
            rows = [
                [r["categoria"], r["event_count"], f"{r['pct']}%", f"{r['downtime_min']:.0f} min"]
                for _, r in tax.head(8).iterrows()
            ]
            lines.append(_md_table(["Categoria", "Eventos", "%", "Downtime"], rows))

        lines += [
            f"",
            f"---",
            f"",
            f"## Plan de Accion",
            f"",
            f"### Accion Urgente ({len(plan['urgente'])} equipos)",
            f"",
        ]

        for e in plan["urgente"]:
            lines.append(f"- **`{e['tag_equipo']}`** ({e.get('nombre_equipo', '')}) — Risk Score: {e['risk_score']:.0f}")
            if e.get("top_recommendation"):
                lines.append(f"  - _{e['top_recommendation']}_")

        if not plan["urgente"]:
            lines.append("_Ninguno._")

        lines += [
            f"",
            f"### Planificado ({len(plan['planificado'])} equipos)",
            f"",
        ]
        for e in plan["planificado"][:5]:
            lines.append(f"- **`{e.get('tag_equipo', e['equnr'])}`** ({e.get('nombre_equipo', '')}) — Risk Score: {e['risk_score']:.0f}")

        if not plan["planificado"]:
            lines.append("_Ninguno._")

        lines += ["", "---", "", f"_Reporte generado por MantOS v0.2.0_"]

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # 7.2 — Reporte por equipo
    # ------------------------------------------------------------------

    def get_equipment_report(
        self,
        equnr:       str,
        period_days: int = 90,
        end_date:    Optional[str] = None,
    ) -> str:
        """
        Genera un reporte de profundidad para un equipo específico.

        Returns:
            String Markdown.
        """
        end   = end_date or "2026-03-31T23:59:59Z"
        end_dt = datetime.fromisoformat(end.replace("Z", "+00:00"))
        start_dt = end_dt - timedelta(days=period_days)
        start = start_dt.strftime("%Y-%m-%dT%H:%M:%SZ")

        # Datos del equipo
        eq_info = self.query(
            "SELECT equnr, nombre_equipo, linea, tplnr, descripcion FROM equipment WHERE equnr = ?",
            (equnr,)
        )
        eq_name = eq_info.iloc[0]["nombre_equipo"] if not eq_info.empty else equnr
        eq_linea = eq_info.iloc[0]["linea"] if not eq_info.empty else ""
        eq_tplnr = eq_info.iloc[0]["tplnr"] if not eq_info.empty else ""

        # KPIs
        mttr    = self._kpi.calc_mttr(equnr=equnr, start_date=start, end_date=end)
        mtbf    = self._kpi.calc_mtbf(equnr=equnr, start_date=start, end_date=end)
        avail   = self._kpi.calc_availability(equnr=equnr, start_date=start, end_date=end)
        trend   = self._kpi.get_failure_trend(equnr=equnr, start_date=start, end_date=end)
        risk    = self._pred.calc_risk_score(equnr=equnr, start_date=start, end_date=end)
        forecast= self._pred.forecast_failure_rate(equnr=equnr, start_date=start, end_date=end)
        recs    = self.get_prescriptive_for_report(equnr, start, end)
        stats   = self._desc.get_duration_stats(equnr=equnr, start_date=start, end_date=end)
        tax     = self._diag.get_taxonomy_summary(start_date=start, end_date=end)
        
        # Generar grafico de tendencia
        rates   = self._kpi.calc_failure_rate(equnr=equnr, freq="W", start_date=start, end_date=end)
        trend_img = self._charts.plot_kpi_trend(rates, f"Tendencia de Eventos Semanales - {eq_name}", f"trend_{equnr}.png")

        trend_icon = {"deteriorating": "/\\ Empeorando", "stable": "-- Estable",
                      "improving": "\\/ Mejorando", "insufficient_data": "? Sin datos"}.get(
                        trend.get("direction", ""), "")
        risk_icon = {"CRITICO": "[CRITICO]", "ALTO": "[ALTO]", "MEDIO": "[MEDIO]", "BAJO": "[BAJO]"}.get(
            risk["risk_level"], "[?]")

        lines = [
            f"# Reporte de Equipo: {eq_name}",
            f"",
            f"**ID Equipo**: `{equnr}`  ",
            f"**Ubicacion**: `{eq_tplnr}` ({eq_linea})  ",
            f"**Periodo analizado**: {period_days} dias (`{start[:10]}` -> `{end[:10]}`)  ",
            f"**Generado**: {_now()}",
            f"",
            f"---",
            f"",
            f"## Indicadores Clave (KPIs)",
            f"",
            f"| KPI | Valor |",
            f"|---|---|",
            f"| MTTR (tiempo medio de reparacion) | {f'{mttr:.1f} min' if mttr else 'Sin datos'} |",
            f"| MTBF (tiempo medio entre fallas) | {f'{mtbf:.1f} h' if mtbf else 'Sin datos'} |",
            f"| Disponibilidad | {avail['availability_pct']:.2f}% |",
            f"| Downtime acumulado | {avail['downtime_min']:.0f} min ({avail['pm01_count']} correctivos) |",
            f"| Tendencia de fallas | {trend_icon} |",
            f"| Score de riesgo | {risk_icon} {risk['risk_score']:.0f}/100 ({risk['risk_level']}) |",
            f"",
            f"---",
            f"",
            f"## Estadisticas de Duracion (PM01)",
            f"",
            f"| Estadistica | Valor |",
            f"|---|---|",
            f"| Media | {stats.get('mean', 'N/A')} min |",
            f"| Mediana | {stats.get('median', 'N/A')} min |",
            f"| Percentil 90 | {stats.get('p90', 'N/A')} min |",
            f"| Maximo | {stats.get('max', 'N/A')} min |",
            f"| Total downtime | {stats.get('total_downtime_min', 0):.0f} min |",
            f"",
            f"---",
            f"",
            f"## Prediccion (proximas 4 semanas)",
            f"",
        ]
        
        if trend_img:
            img_path = trend_img.replace('\\', '/')
            lines.append(f"![Tendencia de Fallas](file:///{img_path})")
            lines.append("")
        
        lines += [
            f"| Parametro | Valor |",
            f"|---|---|",
            f"| Eventos estimados (proxima semana) | {forecast.get('predicted_events_next_period', 'N/A')} |",
            f"| Confianza del modelo (R²) | {forecast.get('confidence_r2', 'N/A')} |",
            f"| Tendencia proyectada | {forecast.get('trend', 'N/A')} |",
            f"",
            f"---",
            f"",
            f"## Recomendaciones",
            f"",
        ]

        for rec in recs:
            lines.append(f"### {rec['urgencia']} — {rec['tipo']}")
            lines.append(f"")
            lines.append(f"{rec['mensaje']}")
            lines.append(f"")
            lines.append(f"> **Justificacion**: {rec['justificacion']}")
            lines.append(f"")

        lines += ["---", "", f"_Reporte generado por MantOS v0.2.0_"]
        return "\n".join(lines)

    def get_prescriptive_for_report(self, equnr: str, start: str, end: str):
        """Helper para obtener recomendaciones con manejo de errores."""
        try:
            return self._presc.get_recommendations(equnr=equnr, start_date=start, end_date=end)
        except Exception:
            return []

    # ------------------------------------------------------------------
    # 7.3 — Reporte ejecutivo de KPIs
    # ------------------------------------------------------------------

    def get_executive_report(
        self,
        period: str = "month",   # 'month' | 'quarter' | 'year'
        end_date: Optional[str] = None,
        linea: str = "LA4",
    ) -> str:
        """
        Genera el reporte ejecutivo de KPIs de la planta.

        Returns:
            String Markdown conciso para alta dirección.
        """
        end = end_date or "2026-03-31T23:59:59Z"
        end_dt = datetime.fromisoformat(end.replace("Z", "+00:00"))

        if period == "quarter":
            start_dt = end_dt - timedelta(days=90)
            period_label = "Trimestre"
        elif period == "year":
            start_dt = end_dt - timedelta(days=365)
            period_label = "Año"
        else:
            start_dt = end_dt - timedelta(days=30)
            period_label = "Mes"

        start = start_dt.strftime("%Y-%m-%dT%H:%M:%SZ")

        # Disponibilidad por línea y recoger MTTR/MTBF para el gráfico de KPIs
        avail_la4 = self._kpi.calc_availability_by_linea(linea=linea, start_date=start, end_date=end)
        
        kpi_img = ""
        if not avail_la4.empty:
            # Obtener MTTR y MTBF para cada equipo
            mttrs = []
            mtbfs = []
            for _, row in avail_la4.iterrows():
                mttr = self._kpi.calc_mttr(equnr=row["equnr"], start_date=start, end_date=end, auart=None)
                mtbf = self._kpi.calc_mtbf(equnr=row["equnr"], start_date=start, end_date=end, auart=None)
                mttrs.append(mttr if mttr else 0)
                mtbfs.append(mtbf if mtbf else 0)
            avail_la4["mttr_min"] = mttrs
            avail_la4["mtbf_hours"] = mtbfs
            
            kpi_img = self._charts.plot_kpi_comparison(
                avail_la4, f"KPIs Comparativos (Disponibilidad, MTTR, MTBF) - {period_label}", f"kpi_comp_exec_{period_label}.png"
            )

        # Ranking de riesgo y Pareto
        risk_rank = self._pred.get_risk_ranking(start_date=start, end_date=end)
        pareto = self._diag.get_pareto(metric="downtime", start_date=start, end_date=end, top_n=10)
        pareto_img = self._charts.plot_pareto(pareto, f"Pareto Downtime - {period_label}", f"pareto_exec_{period_label}.png")

        # Resumen descriptivo
        summary = self._desc.get_failure_summary(start_date=start, end_date=end)

        # Plan de acción
        plan = self._presc.get_action_plan(start_date=start, end_date=end)

        criticals = len(plan["urgente"])
        high      = len(plan["planificado"])

        line_avail_str = f"{avail_la4['availability_pct'].mean():.2f}%" if not avail_la4.empty else "N/A"
        
        lines = [
            f"# Reporte Ejecutivo MantOS — 2026",
            f"",
            f"**Planta**: Galletera Sur (PGS)  ",
            f"**Periodo**: `{start[:10]}` -> `{end[:10]}`  ",
            f"**Generado**: {_now()}",
            f"",
            f"---",
            f"",
            f"## Panorama General",
            f"",
            f"| Indicador | Valor |",
            f"|---|---|",
            f"| Total eventos registrados | {summary['total_events']:,} |",
            f"| Equipos en estado CRITICO | **{criticals}** |",
            f"| Equipos con riesgo ALTO | {high} |",
            f"| % Paros fantasma | {summary['ghost_pct']}% |",
            f"| Disponibilidad general ({linea}) | **{line_avail_str}** |",
            f"",
            f"---",
            f"",
            f"## Disponibilidad {linea}",
            f"",
        ]
        
        if kpi_img:
            img_path = kpi_img.replace('\\', '/')
            lines.append(f"![KPIs Comparativos](file:///{img_path})")
            lines.append("")

        if not avail_la4.empty:
            rows = [
                [r.get("tag_equipo", r["equnr"]), r.get("nombre_equipo", ""), f"{r['availability_pct']:.2f}%",
                 f"{r['downtime_min']:.0f} min", r["pm01_count"]]
                for _, r in avail_la4.iterrows()
            ]
            lines.append(_md_table(["Equipo", "Nombre", "Disponibilidad", "Downtime", "Correctivos"], rows))
        else:
            lines.append("_Sin datos de disponibilidad._")

        lines += [
            f"",
            f"---",
            f"",
            f"## Equipos Criticos (Accion Inmediata)",
            f"",
        ]

        if plan["urgente"]:
            for e in plan["urgente"]:
                lines.append(f"- [!] **`{e['equnr']}`** ({e.get('nombre_equipo', '')}, {e.get('linea', '')}) — Risk Score: {e['risk_score']:.0f}/100")
                if e.get("top_recommendation"):
                    lines.append(f"  - {e['top_recommendation']}")
        else:
            lines.append("_No hay equipos en estado critico. ✓_")

        lines += [
            f"",
            f"---",
            f"",
            f"## Top 5 Equipos por Riesgo",
            f"",
        ]
        
        if pareto_img:
            img_path = pareto_img.replace('\\', '/')
            lines.append(f"![Pareto](file:///{img_path})")
            lines.append("")

        if not risk_rank.empty:
            rows = [
                [r["equnr"], r.get("nombre_equipo", ""), r.get("linea", ""),
                 f"{r['risk_score']:.0f}", r["risk_level"], r.get("trend_direction", "")]
                for _, r in risk_rank.head(5).iterrows()
            ]
            lines.append(_md_table(["Equipo", "Nombre", "Linea", "Risk Score", "Nivel", "Tendencia"], rows))

        lines += ["", "---", "", f"_Reporte ejecutivo generado por MantOS v0.2.0_"]
        lines += ["", "---", "", f"_Reporte ejecutivo generado por MantOS v0.2.0_"]
        return "\n".join(lines)

    def export_executive_report_pdf(self, output_pdf_path: str, period: str = "month", end_date: Optional[str] = None, linea: str = "LA4") -> bool:
        """
        Genera el reporte ejecutivo directamente en PDF usando FPDF.
        """
        try:
            from analysis.pdf_export import ReportePDF
        except ImportError:
            print("[MantOS] Error: No se encontró el módulo pdf_export (fpdf no instalado)")
            return False

        end = end_date or "2026-03-31T23:59:59Z"
        end_dt = datetime.fromisoformat(end.replace("Z", "+00:00"))

        if period == "quarter":
            start_dt = end_dt - timedelta(days=90)
            period_title = "Trimestre"
        elif period == "year":
            start_dt = end_dt - timedelta(days=365)
            period_title = "Año"
        else:
            start_dt = end_dt - timedelta(days=30)
            period_title = "Mes"

        start = start_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        period_label = f"[{period_title.upper()}] {start[:10]} al {end[:10]}"

        pdf = ReportePDF(title=f"Reporte Ejecutivo MantOS - {period_title.upper()}")
        pdf.add_page()

        # Resumen descriptivo
        summary = self._desc.get_failure_summary(start_date=start, end_date=end)
        plan = self._presc.get_action_plan(start_date=start, end_date=end)
        criticals = len(plan["urgente"])
        high      = len(plan["planificado"])

        # Disponibilidad Línea
        avail_la4 = self._kpi.calc_availability_by_linea(linea=linea, start_date=start, end_date=end)
        line_avail_str = f"{avail_la4['availability_pct'].mean():.2f}%" if not avail_la4.empty else "N/A"

        pdf.add_section_title("Información del Reporte")
        pdf.add_key_value("Planta:", "Galletera Sur (PGS)")
        pdf.add_key_value("Período analizado:", f"{start[:10]} al {end[:10]}")

        pdf.add_section_title("Panorama General")
        pdf.add_key_value("Total eventos:", f"{summary['total_events']:,}")
        pdf.add_key_value("Equipos en estado CRÍTICO:", str(criticals))
        pdf.add_key_value("Equipos con riesgo ALTO:", str(high))
        pdf.add_key_value("% Paros fantasma:", f"{summary['ghost_pct']}%")
        pdf.add_key_value("Disponibilidad general:", f"{line_avail_str}")

        pdf.add_section_title(f"Disponibilidad {linea}")
        if not avail_la4.empty:
            mttrs = []
            mtbfs = []
            for _, row in avail_la4.iterrows():
                mttr = self._kpi.calc_mttr(equnr=row["equnr"], start_date=start, end_date=end, auart=None)
                mtbf = self._kpi.calc_mtbf(equnr=row["equnr"], start_date=start, end_date=end, auart=None)
                mttrs.append(mttr if mttr else 0)
                mtbfs.append(mtbf if mtbf else 0)
            avail_la4["mttr_min"] = mttrs
            avail_la4["mtbf_hours"] = mtbfs
            
            kpi_img = self._charts.plot_kpi_comparison(
                avail_la4, f"KPIs Comparativos (Disponibilidad, MTTR, MTBF)", f"kpi_comp_exec_{period_label}.png"
            )
            pdf.add_image_if_exists(kpi_img)
            
            df_table = pd.DataFrame()
            df_table["Equipo (Tag)"] = avail_la4["tag_equipo"] if "tag_equipo" in avail_la4.columns else avail_la4["equnr"]
            df_table["Nombre"] = avail_la4["nombre_equipo"]
            df_table["Disp (%)"] = avail_la4["availability_pct"].round(2)
            df_table["Downtime(min)"] = avail_la4["downtime_min"].round(0)
            pdf.tabla_con_paginacion(df_table, [50, 60, 30, 40])
        else:
            pdf.add_bullet_point(f"Sin datos de disponibilidad para {linea}.")

        # Accion inmediata
        pdf.add_section_title("Equipos Críticos (Acción Inmediata)")
        if plan["urgente"]:
            for e in plan["urgente"]:
                msg = f"{e['tag_equipo']} ({e['nombre_equipo']}) - Score: {e['risk_score']:.0f}/100 - {e.get('top_recommendation', 'Revisar')}"
                pdf.add_bullet_point(msg)
        else:
            pdf.add_bullet_point("No hay equipos en estado crítico.")

        # Top 5
        pdf.add_section_title("Top 5 Equipos por Riesgo")
        risk_rank = self._pred.get_risk_ranking(start_date=start, end_date=end)
        pareto = self._diag.get_pareto(metric="downtime", start_date=start, end_date=end, top_n=10)
        pareto_img = self._charts.plot_pareto(pareto, f"Pareto Downtime", f"pareto_exec_{period_label}.png")
        pdf.add_image_if_exists(pareto_img)

        if not risk_rank.empty:
            df_r = risk_rank.head(5)[["nombre_equipo", "risk_score", "risk_level", "trend_direction"]].copy()
            df_r.columns = ["Equipo", "Score de Riesgo", "Nivel de Riesgo", "Tendencia"]
            trad = {"stable": "Estable", "insufficient_data": "Sin datos", "deteriorating": "Empeorando", "improving": "Mejorando"}
            df_r["Tendencia"] = df_r["Tendencia"].map(lambda x: trad.get(x, x))
            pdf.tabla_con_paginacion(df_r, [45, 45, 45, 45])
            
        # Top Fallas
        pdf.add_section_title("Top Fallas Frecuentes (Palabras Clave)")
        kws = self._desc.get_top_keywords(n=10, start_date=start, end_date=end)
        if kws:
            kw_str = ", ".join([f"{w} ({f})" for w, f in kws])
            pdf.add_bullet_point(f"Términos más detectados: {kw_str}")
        pdf.output(output_pdf_path)
        return True


def _auart_label(auart: str) -> str:
    return {"PM01": "Correctivo", "PM02": "Preventivo", "PM03": "Operacional"}.get(auart, auart)
