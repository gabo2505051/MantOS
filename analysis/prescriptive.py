"""
prescriptive.py  — F6: Análisis Prescriptivo
--------------------------------------------
Responde: ¿qué hacer?

Subtareas:
  6.1  Motor de recomendaciones basado en umbrales de KPIs
  6.2  Priorización de intervenciones (URGENTE / PLANIFICADO / MONITOREO)
  6.3  Motor de alertas con severidades (CRITICA / ALTA / MEDIA / BAJA)
"""

from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd

from analysis.base import AnalysisBase
from analysis.kpis import KPICalculator
from analysis.predictive import PredictiveAnalysis

# ------------------------------------------------------------------
# Umbrales de KPIs para reglas prescriptivas
# ------------------------------------------------------------------
THRESHOLDS = {
    "risk_score_critical":   70.0,    # score >= 70 → acción urgente
    "risk_score_high":       45.0,    # score 45-70 → planificar PM02
    "mtbf_drop_pct":         0.30,    # caída > 30% → revisar causa raíz
    "ghost_pct_warning":     0.20,    # > 20% ghost stops → revisar registro
    "weekly_spike_zscore":   2.0,     # Z-score > 2 → semana anómala
    "mttr_high_min":         60.0,    # MTTR > 60 min → intervención compleja
    "availability_critical":  0.95,   # < 95% → equipo en estado crítico
}

# Severidades de alerta
SEVERITIES = ("CRITICA", "ALTA", "MEDIA", "BAJA")


class PrescriptiveAnalysis(AnalysisBase):
    """Motor de análisis prescriptivo para MantOS."""

    def __init__(self, db_path=None):
        super().__init__(db_path)
        self._kpi  = KPICalculator(db_path or self.db_path)
        self._pred = PredictiveAnalysis(db_path or self.db_path)

    # ------------------------------------------------------------------
    # 6.1 — Motor de recomendaciones
    # ------------------------------------------------------------------

    def get_recommendations(
        self,
        equnr:      str,
        start_date: Optional[str] = None,
        end_date:   Optional[str] = None,
    ) -> List[Dict]:
        """
        Genera una lista de recomendaciones para un equipo basadas en KPIs.

        Returns:
            Lista de dicts con {tipo, prioridad, mensaje, justificacion}
            ordenada por prioridad (1=más urgente)
        """
        start, end = self.clamp_dates(start_date, end_date)
        recs: List[Dict] = []

        # Obtener datos necesarios
        risk    = self._pred.calc_risk_score(equnr=equnr, start_date=start, end_date=end)
        mttr    = self._kpi.calc_mttr(equnr=equnr, start_date=start, end_date=end)
        avail   = self._kpi.calc_availability(equnr=equnr, start_date=start, end_date=end)
        trend   = self._kpi.get_failure_trend(equnr=equnr, start_date=start, end_date=end)

        risk_score     = risk["risk_score"]
        availability   = avail["availability_pct"] / 100.0
        ghost_total    = self.scalar(
            "SELECT COUNT(*) FROM maintenance_orders WHERE equnr = ? AND is_ghost_stop = 1 AND start_datetime >= ? AND start_datetime <= ?",
            (equnr, start, end)
        ) or 0
        total_events = self.scalar(
            "SELECT COUNT(*) FROM maintenance_orders WHERE equnr = ? AND start_datetime >= ? AND start_datetime <= ?",
            (equnr, start, end)
        ) or 0
        ghost_pct = ghost_total / total_events if total_events > 0 else 0.0

        # Regla 1: Risk score crítico
        if risk_score >= THRESHOLDS["risk_score_critical"]:
            recs.append({
                "tipo":          "INSPECCION_CORRECTIVA",
                "prioridad":     1,
                "urgencia":      "URGENTE (< 48 horas)",
                "mensaje":       f"Inspección correctiva urgente requerida. Score de riesgo: {risk_score:.0f}/100.",
                "justificacion": f"El equipo supera el umbral crítico de riesgo ({THRESHOLDS['risk_score_critical']:.0f}). "
                                  f"Componentes: {risk['components']}",
            })

        # Regla 2: Risk score alto
        elif risk_score >= THRESHOLDS["risk_score_high"]:
            recs.append({
                "tipo":          "MANTENIMIENTO_PREVENTIVO",
                "prioridad":     2,
                "urgencia":      "PLANIFICADO (< 2 semanas)",
                "mensaje":       f"Programar PM02 preventivo en las próximas 2 semanas. Score de riesgo: {risk_score:.0f}/100.",
                "justificacion": f"Risk score elevado. Tendencia: {risk['trend_direction']}.",
            })

        # Regla 3: Tendencia deteriorando
        if trend.get("direction") == "deteriorating" and (trend.get("r_squared") or 0) > 0.2:
            recs.append({
                "tipo":          "ANALISIS_CAUSA_RAIZ",
                "prioridad":     2,
                "urgencia":      "PLANIFICADO (< 1 semana)",
                "mensaje":       "Realizar análisis de causa raíz. La frecuencia de fallas muestra tendencia ascendente estadísticamente significativa.",
                "justificacion": f"Pendiente de regresión: {trend.get('slope', 0):.3f} fallas/semana. R²={trend.get('r_squared', 0):.2f}.",
            })

        # Regla 4: Disponibilidad baja
        if availability < THRESHOLDS["availability_critical"]:
            recs.append({
                "tipo":          "REVISION_DISPONIBILIDAD",
                "prioridad":     1,
                "urgencia":      "URGENTE (< 24 horas)",
                "mensaje":       f"Disponibilidad del equipo en {availability*100:.1f}% — por debajo del umbral mínimo ({THRESHOLDS['availability_critical']*100:.0f}%).",
                "justificacion": f"Downtime acumulado: {avail['downtime_min']:.0f} min en el período.",
            })

        # Regla 5: MTTR alto
        if mttr and mttr > THRESHOLDS["mttr_high_min"]:
            recs.append({
                "tipo":          "REVISION_PROCESO_REPARACION",
                "prioridad":     3,
                "urgencia":      "MONITOREO (próximo mes)",
                "mensaje":       f"MTTR elevado ({mttr:.0f} min). Revisar proceso y recursos de reparación.",
                "justificacion": f"El tiempo medio de reparación supera {THRESHOLDS['mttr_high_min']:.0f} min.",
            })

        # Regla 6: Ghost stops excesivos
        if ghost_pct > THRESHOLDS["ghost_pct_warning"]:
            recs.append({
                "tipo":          "REVISION_REGISTRO_OTS",
                "prioridad":     4,
                "urgencia":      "MONITOREO (próximo mes)",
                "mensaje":       f"Alto porcentaje de paros fantasma ({ghost_pct*100:.1f}%). Revisar proceso de registro de OTs.",
                "justificacion": f"{ghost_total} de {total_events} órdenes tienen start_datetime = end_datetime.",
            })

        # Sin recomendaciones: equipo en buen estado
        if not recs:
            recs.append({
                "tipo":          "SIN_ACCION_REQUERIDA",
                "prioridad":     5,
                "urgencia":      "MONITOREO RUTINARIO",
                "mensaje":       f"Equipo en condición normal. Score de riesgo: {risk_score:.0f}/100.",
                "justificacion": "Todos los indicadores están dentro de los rangos aceptables.",
            })

        return sorted(recs, key=lambda x: x["prioridad"])

    # ------------------------------------------------------------------
    # 6.2 — Priorización de intervenciones
    # ------------------------------------------------------------------

    def get_action_plan(
        self,
        linea:        Optional[str] = None,
        horizon_days: int = 14,
        start_date:   Optional[str] = None,
        end_date:     Optional[str] = None,
    ) -> Dict:
        """
        Genera un plan de acción priorizado para todos los equipos
        (o los de una línea), clasificados en URGENTE / PLANIFICADO / MONITOREO.

        Returns:
            dict con {urgente: [...], planificado: [...], monitoreo: [...]}
        """
        start, end = self.clamp_dates(start_date, end_date)

        # Obtener ranking de riesgo
        df_risk = self._pred.get_risk_ranking(linea=linea, start_date=start, end_date=end)

        if df_risk.empty:
            return {"urgente": [], "planificado": [], "monitoreo": []}

        plan: Dict = {"urgente": [], "planificado": [], "monitoreo": []}

        for _, row in df_risk.iterrows():
            equnr      = row["equnr"]
            risk_score = row["risk_score"]
            risk_level = row["risk_level"]

            entry = {
                "equnr":          equnr,
                "nombre_equipo":  row.get("nombre_equipo", ""),
                "tag_equipo":     row.get("tag_equipo", equnr),
                "linea":          row.get("linea", ""),
                "risk_score":     risk_score,
                "risk_level":     risk_level,
                "trend":          row.get("trend_direction", ""),
                "top_recommendation": None,
            }

            # Obtener la recomendación más urgente
            try:
                recs = self.get_recommendations(equnr=equnr, start_date=start, end_date=end)
                if recs:
                    entry["top_recommendation"] = recs[0]["mensaje"]
            except Exception:
                pass

            if risk_score >= THRESHOLDS["risk_score_critical"]:
                plan["urgente"].append(entry)
            elif risk_score >= THRESHOLDS["risk_score_high"]:
                plan["planificado"].append(entry)
            else:
                plan["monitoreo"].append(entry)

        return plan

    # ------------------------------------------------------------------
    # 6.3 — Motor de alertas
    # ------------------------------------------------------------------

    def check_alerts(
        self,
        equnr:      Optional[str] = None,
        linea:      Optional[str] = None,
        start_date: Optional[str] = None,
        end_date:   Optional[str] = None,
    ) -> List[Dict]:
        """
        Verifica si hay alertas activas para un equipo o línea.
        Cada alerta tiene: severidad, tipo, mensaje, equnr, timestamp.

        Returns:
            Lista de alertas ordenadas por severidad (CRITICA primero)
        """
        start, end = self.clamp_dates(start_date, end_date)
        now_str    = datetime.now(timezone.utc).isoformat(timespec="seconds")
        alerts: List[Dict] = []

        # Obtener equipos a verificar
        if equnr:
            equipos = [equnr]
        elif linea:
            df_eq  = self.query("SELECT equnr FROM equipment WHERE linea = ?", (linea,))
            equipos = df_eq["equnr"].tolist()
        else:
            df_eq  = self.query(
                "SELECT DISTINCT equnr FROM maintenance_orders WHERE start_datetime >= ? AND start_datetime <= ?",
                (start, end)
            )
            equipos = df_eq["equnr"].tolist()

        for eq in equipos:
            try:
                risk  = self._pred.calc_risk_score(equnr=eq, start_date=start, end_date=end)
                avail = self._kpi.calc_availability(equnr=eq, start_date=start, end_date=end)
                anom  = self._pred.detect_anomalies(equnr=eq, start_date=start, end_date=end)

                # Alerta 1: Risk score crítico
                if risk["risk_score"] >= THRESHOLDS["risk_score_critical"]:
                    alerts.append({
                        "severidad": "CRITICA",
                        "tipo":      "RIESGO_CRITICO",
                        "equnr":     eq,
                        "mensaje":   f"Score de riesgo crítico: {risk['risk_score']:.0f}/100 (umbral: {THRESHOLDS['risk_score_critical']:.0f})",
                        "timestamp": now_str,
                    })
                # Alerta 2: Risk score alto
                elif risk["risk_score"] >= THRESHOLDS["risk_score_high"]:
                    alerts.append({
                        "severidad": "ALTA",
                        "tipo":      "RIESGO_ALTO",
                        "equnr":     eq,
                        "mensaje":   f"Score de riesgo elevado: {risk['risk_score']:.0f}/100",
                        "timestamp": now_str,
                    })

                # Alerta 3: Disponibilidad baja
                avail_pct = avail["availability_pct"] / 100.0
                if avail_pct < THRESHOLDS["availability_critical"]:
                    alerts.append({
                        "severidad": "ALTA",
                        "tipo":      "BAJA_DISPONIBILIDAD",
                        "equnr":     eq,
                        "mensaje":   f"Disponibilidad {avail_pct*100:.1f}% < umbral {THRESHOLDS['availability_critical']*100:.0f}%",
                        "timestamp": now_str,
                    })

                # Alerta 4: Semana anómala reciente
                if not anom.empty:
                    recent_anomalies = anom[anom["is_anomaly"] == True]
                    if not recent_anomalies.empty:
                        worst = recent_anomalies.loc[recent_anomalies["z_score"].abs().idxmax()]
                        alerts.append({
                            "severidad": "MEDIA",
                            "tipo":      "ANOMALIA_TEMPORAL",
                            "equnr":     eq,
                            "mensaje":   f"Semana {worst['period']} con {worst['event_count']:.0f} eventos (Z={worst['z_score']:.2f})",
                            "timestamp": now_str,
                        })

            except Exception:
                continue

        # Ordenar por severidad
        sev_order = {"CRITICA": 0, "ALTA": 1, "MEDIA": 2, "BAJA": 3}
        alerts.sort(key=lambda a: sev_order.get(a["severidad"], 9))
        return alerts
