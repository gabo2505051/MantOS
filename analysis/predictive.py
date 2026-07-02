"""
predictive.py  — F5: Análisis Predictivo
-----------------------------------------
Responde: ¿qué va a pasar?

Subtareas:
  5.1  Pronóstico de tendencia de fallas (regresión lineal)
  5.2  Score de riesgo compuesto por equipo (0-100)
  5.3  Detección de anomalías temporales (Z-score)
"""

from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd
from scipy.stats import linregress

from analysis.base import AnalysisBase
from analysis.kpis import KPICalculator
from analysis.diagnostic import DiagnosticAnalysis


class PredictiveAnalysis(AnalysisBase):
    """Motor de análisis predictivo para MantOS."""

    def __init__(self, db_path=None):
        super().__init__(db_path)
        self._kpi  = KPICalculator(db_path or self.db_path)
        self._diag = DiagnosticAnalysis(db_path or self.db_path)

    # ------------------------------------------------------------------
    # 5.1 — Pronóstico de tendencia
    # ------------------------------------------------------------------

    def forecast_failure_rate(
        self,
        equnr:        str,
        horizon_days: int = 30,
        training_days: int = 90,
        auart:        str = "W",   # frecuencia de la serie: 'W' semana, 'M' mes
        start_date:   Optional[str] = None,
        end_date:     Optional[str] = None,
    ) -> Dict:
        """
        Proyecta la tasa de fallas a futuro usando regresión lineal
        sobre los últimos `training_days`.

        Returns:
            dict con {predicted_events_next_period, confidence_r2, trend,
                      slope, intercept, training_points}
        """
        start, end = self.clamp_dates(start_date, end_date)

        df = self._kpi.calc_failure_rate(
            equnr=equnr, freq="W", start_date=start, end_date=end
        )

        if len(df) < 4:
            return {
                "equnr":                     equnr,
                "predicted_events_next_period": None,
                "confidence_r2":              None,
                "trend":                      "insufficient_data",
                "slope":                      None,
                "training_points":            len(df),
            }

        x = np.arange(len(df), dtype=float)
        y = df["failure_count"].to_numpy(dtype=float)

        slope, intercept, r_value, p_value, _ = linregress(x, y)
        r_sq = r_value ** 2

        # Predecir el próximo punto
        next_x            = len(df)
        predicted         = intercept + slope * next_x
        predicted_clipped = max(0.0, predicted)  # no puede ser negativo

        # Tendencia
        if abs(slope) < 0.05 or r_sq < 0.15:
            trend = "stable"
        elif slope > 0:
            trend = "deteriorating"
        else:
            trend = "improving"

        return {
            "equnr":                        equnr,
            "predicted_events_next_period": round(predicted_clipped, 2),
            "confidence_r2":                round(r_sq, 4),
            "trend":                        trend,
            "slope":                        round(float(slope), 4),
            "intercept":                    round(float(intercept), 4),
            "training_points":              int(len(df)),
            "last_observed_count":          int(y[-1]),
        }

    # ------------------------------------------------------------------
    # 5.2 — Score de riesgo por equipo
    # ------------------------------------------------------------------

    def calc_risk_score(
        self,
        equnr:      str,
        start_date: Optional[str] = None,
        end_date:   Optional[str] = None,
    ) -> Dict:
        """
        Calcula un score de riesgo compuesto (0-100) para un equipo.

        Componentes y pesos:
          - Frecuencia reciente (últimas 4 semanas vs media histórica): 40%
          - Tendencia de MTBF (deteriorating/stable/improving):         30%
          - Score de recurrencia (gaps cortos entre fallas):            20%
          - % de ghost stops (calidad de datos / operación caótica):    10%

        Returns:
            dict con {equnr, risk_score, components, risk_level}
        """
        start, end = self.clamp_dates(start_date, end_date)

        # --- Componente 1: Frecuencia reciente (40%) ---
        df_rate = self._kpi.calc_failure_rate(
            equnr=equnr, freq="W", start_date=start, end_date=end
        )
        if len(df_rate) >= 4:
            hist_mean  = df_rate["failure_count"].iloc[:-4].mean() if len(df_rate) > 4 else df_rate["failure_count"].mean()
            recent_mean = df_rate["failure_count"].iloc[-4:].mean()
            # Score: 0 si reciente <= histórico, 100 si reciente es 3x el histórico
            if hist_mean > 0:
                ratio = recent_mean / hist_mean
                freq_score = min(100.0, max(0.0, (ratio - 1.0) / 2.0 * 100.0))
            else:
                freq_score = min(100.0, recent_mean * 10.0)
        else:
            freq_score = 50.0  # sin datos suficientes → riesgo medio

        # --- Componente 2: Tendencia de MTBF (30%) ---
        trend_data  = self._kpi.get_failure_trend(equnr=equnr, start_date=start, end_date=end)
        trend       = trend_data.get("direction", "stable")
        trend_score = {"deteriorating": 100.0, "stable": 40.0, "improving": 10.0,
                       "insufficient_data": 50.0}.get(trend, 50.0)

        # --- Componente 3: Score de recurrencia (20%) ---
        rec_score = self._diag.get_recurrence_score(
            equnr=equnr, window_days=7, start_date=start, end_date=end
        ) * 100.0

        # --- Componente 4: % ghost stops (10%) ---
        total = self.scalar(
            "SELECT COUNT(*) FROM maintenance_orders WHERE equnr = ? AND start_datetime >= ? AND start_datetime <= ?",
            (equnr, start, end),
        ) or 0
        ghosts = self.scalar(
            "SELECT COUNT(*) FROM maintenance_orders WHERE equnr = ? AND is_ghost_stop = 1 AND start_datetime >= ? AND start_datetime <= ?",
            (equnr, start, end),
        ) or 0
        ghost_pct   = (ghosts / total * 100) if total > 0 else 0
        ghost_score = min(100.0, ghost_pct * 2.0)  # 50% ghost → score 100

        # Score compuesto ponderado
        risk_score = (
            freq_score  * 0.40 +
            trend_score * 0.30 +
            rec_score   * 0.20 +
            ghost_score * 0.10
        )
        risk_score = round(min(100.0, max(0.0, risk_score)), 1)

        # Nivel de riesgo
        if risk_score >= 70:
            risk_level = "CRITICO"
        elif risk_score >= 45:
            risk_level = "ALTO"
        elif risk_score >= 25:
            risk_level = "MEDIO"
        else:
            risk_level = "BAJO"

        return {
            "equnr":      equnr,
            "risk_score": risk_score,
            "risk_level": risk_level,
            "components": {
                "frecuencia_reciente":  round(freq_score, 1),
                "tendencia_fallas":     round(trend_score, 1),
                "recurrencia":          round(rec_score, 1),
                "ghost_stops_pct":      round(ghost_score, 1),
            },
            "trend_direction": trend,
        }

    def get_risk_ranking(
        self,
        linea:      Optional[str] = None,
        start_date: Optional[str] = None,
        end_date:   Optional[str] = None,
    ) -> pd.DataFrame:
        """
        Calcula el riesgo para todos los equipos y los ordena de mayor a menor.

        Returns:
            DataFrame con [equnr, nombre_equipo, linea, risk_score, risk_level, trend_direction]
        """
        start, end = self.clamp_dates(start_date, end_date)

        if linea:
            df_eq = self.query("SELECT equnr FROM equipment WHERE linea = ?", (linea,))
        else:
            df_eq = self.query(
                "SELECT DISTINCT equnr FROM maintenance_orders "
                "WHERE start_datetime >= ? AND start_datetime <= ?",
                (start, end),
            )

        rows = []
        for equnr in df_eq["equnr"]:
            try:
                risk = self.calc_risk_score(equnr=equnr, start_date=start, end_date=end)
                rows.append({
                    "equnr":          risk["equnr"],
                    "risk_score":     risk["risk_score"],
                    "risk_level":     risk["risk_level"],
                    "trend_direction": risk["trend_direction"],
                })
            except Exception:
                pass

        if not rows:
            return pd.DataFrame()

        df_risk = pd.DataFrame(rows)

        # Enriquecer con nombre
        df_names = self.query("SELECT equnr, nombre_equipo, linea, tplnr FROM equipment")
        df_risk  = df_risk.merge(df_names, on="equnr", how="left")
        
        def extract_tag(t):
            if not t: return ""
            parts = str(t).split("-")
            return f"{parts[-2]}_{parts[-1]}" if len(parts) >= 2 else t
            
        if not df_risk.empty and "tplnr" in df_risk.columns:
            df_risk["tag_equipo"] = df_risk["tplnr"].apply(extract_tag)
        else:
            df_risk["tag_equipo"] = df_risk["equnr"]

        return df_risk.sort_values("risk_score", ascending=False).reset_index(drop=True)

    # ------------------------------------------------------------------
    # 5.3 — Detección de anomalías temporales
    # ------------------------------------------------------------------

    def detect_anomalies(
        self,
        equnr:        Optional[str] = None,
        linea:        Optional[str] = None,
        window_weeks: int = 4,
        z_threshold:  float = 2.0,
        start_date:   Optional[str] = None,
        end_date:     Optional[str] = None,
    ) -> pd.DataFrame:
        """
        Detecta semanas con frecuencia de eventos fuera de la banda normal
        (media ± z_threshold * σ).

        Returns:
            DataFrame con [week, event_count, mean, std, z_score, is_anomaly]
        """
        start, end = self.clamp_dates(start_date, end_date)

        df_rate = self._kpi.calc_failure_rate(
            equnr=equnr, linea=linea, auart="PM01",
            freq="W", start_date=start, end_date=end,
        )

        # También incluir PM03 para el análisis de anomalías operacionales
        df_rate_pm3 = self._kpi.calc_failure_rate(
            equnr=equnr, linea=linea, auart="PM03",
            freq="W", start_date=start, end_date=end,
        )

        # Combinar PM01 + PM03
        if not df_rate.empty and not df_rate_pm3.empty:
            df_rate = df_rate.merge(
                df_rate_pm3[["period", "failure_count"]],
                on="period", how="outer", suffixes=("_pm01", "_pm03")
            ).fillna(0)
            df_rate["failure_count"] = (
                df_rate.get("failure_count_pm01", 0) +
                df_rate.get("failure_count_pm03", 0)
            )
            df_rate = df_rate[["period", "failure_count"]]

        if len(df_rate) < 4:
            return pd.DataFrame(columns=["period", "event_count", "mean", "std", "z_score", "is_anomaly"])

        counts = df_rate["failure_count"].to_numpy(dtype=float)
        mean   = counts.mean()
        std    = counts.std()

        if std < 0.01:
            # Sin varianza: no hay anomalías
            df_rate["mean"]       = mean
            df_rate["std"]        = 0.0
            df_rate["z_score"]    = 0.0
            df_rate["is_anomaly"] = False
        else:
            df_rate["mean"]       = round(mean, 2)
            df_rate["std"]        = round(std, 2)
            df_rate["z_score"]    = ((df_rate["failure_count"] - mean) / std).round(3)
            df_rate["is_anomaly"] = df_rate["z_score"].abs() >= z_threshold

        df_rate = df_rate.rename(columns={"failure_count": "event_count"})
        return df_rate.reset_index(drop=True)
