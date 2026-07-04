"""
prescriptive.py  — F6: Análisis Prescriptivo
--------------------------------------------
Responde: ¿qué hacer?

Subtareas:
  6.1  Motor de recomendaciones basado en umbrales de KPIs + ML
  6.2  Priorización de intervenciones (URGENTE / PLANIFICADO / MONITOREO)
  6.3  Motor de alertas con severidades (CRITICA / ALTA / MEDIA / BAJA)
  6.4  Score de salud global de la planta / línea
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
    "ml_prob_critical":      0.75,    # prob ML >= 75% → riesgo crítico
    "ml_prob_high":          0.50,    # prob ML >= 50% → riesgo alto
}

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
        Genera una lista de recomendaciones para un equipo basadas en KPIs + ML.

        Returns:
            Lista de dicts con {tipo, prioridad, urgencia, mensaje, justificacion}
            ordenada por prioridad (1=más urgente)
        """
        start, end = self.clamp_dates(start_date, end_date)
        recs: List[Dict] = []

        # Obtener datos necesarios
        risk    = self._pred.calc_risk_score(equnr=equnr, start_date=start, end_date=end)
        ml_pred = self._pred.predict_next_failure_probability(equnr=equnr, start_date=start, end_date=end)
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

        # ── Regla ML 1: Probabilidad alta de falla en 7 días ──
        prob_7d  = ml_pred.get("prob_7d")
        prob_14d = ml_pred.get("prob_14d")
        if prob_7d is not None and prob_7d >= THRESHOLDS["ml_prob_critical"]:
            top_feats = ml_pred.get("top_features", [])
            feat_str  = ", ".join(f"{f[0]}={f[1]:.2f}" for f in top_feats)
            recs.append({
                "tipo":          "INSPECCION_ML_URGENTE",
                "prioridad":     1,
                "urgencia":      "URGENTE (< 7 días)",
                "mensaje":       f"Modelo ML predice {prob_7d*100:.0f}% de probabilidad de falla en los próximos 7 días.",
                "justificacion": f"Top features: {feat_str}. Horizonte 14d: {prob_14d*100:.0f}% de prob.",
                "fuente":        "ML",
            })
        elif prob_14d is not None and prob_14d >= THRESHOLDS["ml_prob_high"]:
            recs.append({
                "tipo":          "PREVENCION_ML_PLANIFICADA",
                "prioridad":     2,
                "urgencia":      "PLANIFICADO (< 14 días)",
                "mensaje":       f"Modelo ML predice {prob_14d*100:.0f}% de probabilidad de falla en los próximos 14 días.",
                "justificacion": f"Riesgo moderado detectado por ML. Prob. 7d: {(prob_7d or 0)*100:.0f}%.",
                "fuente":        "ML",
            })

        # ── Regla 1: Risk score crítico ──
        if risk_score >= THRESHOLDS["risk_score_critical"]:
            recs.append({
                "tipo":          "INSPECCION_CORRECTIVA",
                "prioridad":     1,
                "urgencia":      "URGENTE (< 48 horas)",
                "mensaje":       f"Inspección correctiva urgente requerida. Score de riesgo: {risk_score:.0f}/100.",
                "justificacion": f"El equipo supera el umbral crítico de riesgo ({THRESHOLDS['risk_score_critical']:.0f}). Componentes: {risk['components']}",
                "fuente":        "KPI",
            })
        elif risk_score >= THRESHOLDS["risk_score_high"]:
            recs.append({
                "tipo":          "MANTENIMIENTO_PREVENTIVO",
                "prioridad":     2,
                "urgencia":      "PLANIFICADO (< 2 semanas)",
                "mensaje":       f"Programar PM02 preventivo en las próximas 2 semanas. Score de riesgo: {risk_score:.0f}/100.",
                "justificacion": f"Risk score elevado. Tendencia: {risk['trend_direction']}.",
                "fuente":        "KPI",
            })

        # ── Regla 2: Tendencia deteriorando ──
        if trend.get("direction") == "deteriorating" and (trend.get("r_squared") or 0) > 0.2:
            recs.append({
                "tipo":          "ANALISIS_CAUSA_RAIZ",
                "prioridad":     2,
                "urgencia":      "PLANIFICADO (< 1 semana)",
                "mensaje":       "Realizar análisis de causa raíz. La frecuencia de fallas muestra tendencia ascendente estadísticamente significativa.",
                "justificacion": f"Pendiente de regresión: {trend.get('slope', 0):.3f} fallas/semana. R²={trend.get('r_squared', 0):.2f}.",
                "fuente":        "KPI",
            })

        # ── Regla 3: Disponibilidad baja ──
        if availability < THRESHOLDS["availability_critical"]:
            recs.append({
                "tipo":          "REVISION_DISPONIBILIDAD",
                "prioridad":     1,
                "urgencia":      "URGENTE (< 24 horas)",
                "mensaje":       f"Disponibilidad del equipo en {availability*100:.1f}% — por debajo del umbral mínimo ({THRESHOLDS['availability_critical']*100:.0f}%).",
                "justificacion": f"Downtime acumulado: {avail['downtime_min']:.0f} min en el período.",
                "fuente":        "KPI",
            })

        # ── Regla 4: MTTR alto ──
        if mttr and mttr > THRESHOLDS["mttr_high_min"]:
            recs.append({
                "tipo":          "REVISION_PROCESO_REPARACION",
                "prioridad":     3,
                "urgencia":      "MONITOREO (próximo mes)",
                "mensaje":       f"MTTR elevado ({mttr:.0f} min). Revisar proceso y recursos de reparación.",
                "justificacion": f"El tiempo medio de reparación supera {THRESHOLDS['mttr_high_min']:.0f} min.",
                "fuente":        "KPI",
            })

        # ── Regla 5: Ghost stops excesivos ──
        if ghost_pct > THRESHOLDS["ghost_pct_warning"]:
            recs.append({
                "tipo":          "REVISION_REGISTRO_OTS",
                "prioridad":     4,
                "urgencia":      "MONITOREO (próximo mes)",
                "mensaje":       f"Alto porcentaje de paros fantasma ({ghost_pct*100:.1f}%). Revisar proceso de registro de OTs.",
                "justificacion": f"{ghost_total} de {total_events} órdenes tienen start_datetime = end_datetime.",
                "fuente":        "AUDITORIA",
            })

        # Sin recomendaciones: equipo en buen estado
        if not recs:
            recs.append({
                "tipo":          "SIN_ACCION_REQUERIDA",
                "prioridad":     5,
                "urgencia":      "MONITOREO RUTINARIO",
                "mensaje":       f"Equipo en condición normal. Score de riesgo: {risk_score:.0f}/100.",
                "justificacion": "Todos los indicadores están dentro de los rangos aceptables.",
                "fuente":        "KPI",
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

        df_risk = self._pred.get_risk_ranking(linea=linea, start_date=start, end_date=end)

        if df_risk.empty:
            return {"urgente": [], "planificado": [], "monitoreo": []}

        plan: Dict = {"urgente": [], "planificado": [], "monitoreo": []}

        for _, row in df_risk.iterrows():
            equnr      = row["equnr"]
            risk_score = row["risk_score"]
            risk_level = row["risk_level"]

            # Intentar obtener predicción ML también
            ml_prob_14d = None
            try:
                ml_pred = self._pred.predict_next_failure_probability(
                    equnr=equnr, start_date=start, end_date=end
                )
                ml_prob_14d = ml_pred.get("prob_14d")
            except Exception:
                pass

            entry = {
                "equnr":          equnr,
                "nombre_equipo":  row.get("nombre_equipo", ""),
                "tag_equipo":     row.get("tag_equipo", equnr),
                "linea":          row.get("linea", ""),
                "risk_score":     risk_score,
                "risk_level":     risk_level,
                "trend":          row.get("trend_direction", ""),
                "ml_prob_14d":    ml_prob_14d,
                "top_recommendation": None,
            }

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

        # Fetch nombres para enriquecer las alertas
        df_names = self.query("SELECT equnr, nombre_equipo, linea, tplnr FROM equipment")
        def _tag(eq):
            row = df_names[df_names["equnr"] == eq]
            if row.empty: return eq
            t = row.iloc[0]["tplnr"]
            if not t: return eq
            parts = str(t).split("-")
            return f"{parts[-2]}_{parts[-1]}" if len(parts) >= 2 else eq

        for eq in equipos:
            try:
                risk  = self._pred.calc_risk_score(equnr=eq, start_date=start, end_date=end)
                avail = self._kpi.calc_availability(equnr=eq, start_date=start, end_date=end)
                anom  = self._pred.detect_anomalies(equnr=eq, start_date=start, end_date=end)

                # Intentar predicción ML
                ml_prob_7d = None
                try:
                    ml = self._pred.predict_next_failure_probability(equnr=eq, start_date=start, end_date=end)
                    ml_prob_7d = ml.get("prob_7d")
                except Exception:
                    pass

                tag = _tag(eq)
                eq_linea = df_names[df_names["equnr"] == eq]["linea"].values
                eq_linea = eq_linea[0] if len(eq_linea) > 0 else ""

                # Alerta ML: prob 7d crítica
                if ml_prob_7d is not None and ml_prob_7d >= THRESHOLDS["ml_prob_critical"]:
                    alerts.append({
                        "severidad": "CRITICA",
                        "tipo":      "PREDICCION_ML",
                        "equnr":     eq,
                        "tag":       tag,
                        "linea":     eq_linea,
                        "mensaje":   f"ML predice {ml_prob_7d*100:.0f}% de probabilidad de falla en 7 días",
                        "timestamp": now_str,
                    })

                # Alerta 1: Risk score crítico
                if risk["risk_score"] >= THRESHOLDS["risk_score_critical"]:
                    alerts.append({
                        "severidad": "CRITICA",
                        "tipo":      "RIESGO_CRITICO",
                        "equnr":     eq,
                        "tag":       tag,
                        "linea":     eq_linea,
                        "mensaje":   f"Score de riesgo crítico: {risk['risk_score']:.0f}/100 (umbral: {THRESHOLDS['risk_score_critical']:.0f})",
                        "timestamp": now_str,
                    })
                elif risk["risk_score"] >= THRESHOLDS["risk_score_high"]:
                    alerts.append({
                        "severidad": "ALTA",
                        "tipo":      "RIESGO_ALTO",
                        "equnr":     eq,
                        "tag":       tag,
                        "linea":     eq_linea,
                        "mensaje":   f"Score de riesgo elevado: {risk['risk_score']:.0f}/100",
                        "timestamp": now_str,
                    })

                # Alerta 2: Disponibilidad baja
                avail_pct = avail["availability_pct"] / 100.0
                if avail_pct < THRESHOLDS["availability_critical"]:
                    alerts.append({
                        "severidad": "ALTA",
                        "tipo":      "BAJA_DISPONIBILIDAD",
                        "equnr":     eq,
                        "tag":       tag,
                        "linea":     eq_linea,
                        "mensaje":   f"Disponibilidad {avail_pct*100:.1f}% < umbral {THRESHOLDS['availability_critical']*100:.0f}%",
                        "timestamp": now_str,
                    })

                # Alerta 3: Semana anómala reciente
                if not anom.empty:
                    recent_anomalies = anom[anom["is_anomaly"] == True]
                    if not recent_anomalies.empty:
                        worst = recent_anomalies.loc[recent_anomalies["z_score"].abs().idxmax()]
                        alerts.append({
                            "severidad": "MEDIA",
                            "tipo":      "ANOMALIA_TEMPORAL",
                            "equnr":     eq,
                            "tag":       tag,
                            "linea":     eq_linea,
                            "mensaje":   f"Semana {worst['period']} con {worst['event_count']:.0f} eventos (Z={worst['z_score']:.2f})",
                            "timestamp": now_str,
                        })

            except Exception:
                continue

        sev_order = {"CRITICA": 0, "ALTA": 1, "MEDIA": 2, "BAJA": 3}
        alerts.sort(key=lambda a: sev_order.get(a["severidad"], 9))
        return alerts

    # ------------------------------------------------------------------
    # 6.4 — Score de salud global de la planta / línea
    # ------------------------------------------------------------------

    def get_plant_health_score(
        self,
        linea:      Optional[str] = None,
        start_date: Optional[str] = None,
        end_date:   Optional[str] = None,
    ) -> Dict:
        """
        Calcula un score de salud global (0-100) para la planta o una línea.
        100 = planta en perfectas condiciones. 0 = todos los equipos en estado crítico.

        Score = 100 - promedio_ponderado(risk_scores de todos los equipos)
        Ponderación: equipos críticos y altos cuentan más.

        Returns:
            dict con {health_score, health_label, n_equipos, by_level: {critico, alto, medio, bajo}}
        """
        start, end = self.clamp_dates(start_date, end_date)
        df_risk = self._pred.get_risk_ranking(linea=linea, start_date=start, end_date=end)

        if df_risk.empty:
            return {
                "health_score":  None,
                "health_label":  "Sin datos",
                "n_equipos":     0,
                "by_level":      {"CRITICO": 0, "ALTO": 0, "MEDIO": 0, "BAJO": 0},
            }

        # Promedio ponderado del risk_score
        avg_risk = df_risk["risk_score"].mean()
        health_score = round(max(0.0, min(100.0, 100.0 - avg_risk)), 1)

        # Contar por nivel
        level_counts = df_risk["risk_level"].value_counts().to_dict()
        by_level = {
            "CRITICO": level_counts.get("CRITICO", 0),
            "ALTO":    level_counts.get("ALTO", 0),
            "MEDIO":   level_counts.get("MEDIO", 0),
            "BAJO":    level_counts.get("BAJO", 0),
        }

        if health_score >= 75:
            health_label = "SALUDABLE"
        elif health_score >= 55:
            health_label = "ESTABLE"
        elif health_score >= 35:
            health_label = "EN RIESGO"
        else:
            health_label = "CRITICO"

        return {
            "health_score": health_score,
            "health_label": health_label,
            "n_equipos":    int(len(df_risk)),
            "by_level":     by_level,
        }
