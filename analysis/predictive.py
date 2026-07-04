"""
predictive.py  — F5: Análisis Predictivo
-----------------------------------------
Responde: ¿qué va a pasar?

Subtareas:
  5.1  Pronóstico de tendencia de fallas (regresión lineal)
  5.2  Score de riesgo compuesto por equipo (0-100)
  5.3  Detección de anomalías temporales (Z-score)
  5.4  [ML] Clasificador Random Forest — probabilidad de falla en 7d y 14d
"""

import json
import pickle
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from scipy.stats import linregress

from analysis.base import AnalysisBase
from analysis.kpis import KPICalculator
from analysis.diagnostic import DiagnosticAnalysis

# ──────────────────────────────────────────────────────────────
# Paths para persistir el modelo entrenado
# ──────────────────────────────────────────────────────────────
_MODEL_DIR  = Path(__file__).resolve().parent.parent / "data" / "models"
_MODEL_PATH = _MODEL_DIR / "failure_classifier.pkl"
_META_PATH  = _MODEL_DIR / "feature_metadata.json"


class PredictiveAnalysis(AnalysisBase):
    """Motor de análisis predictivo para MantOS."""

    def __init__(self, db_path=None):
        super().__init__(db_path)
        self._kpi  = KPICalculator(db_path or self.db_path)
        self._diag = DiagnosticAnalysis(db_path or self.db_path)
        self._clf  = None   # modelo cargado lazily
        self._meta = {}

    # ──────────────────────────────────────────────────────────
    # 5.1 — Pronóstico de tendencia
    # ──────────────────────────────────────────────────────────

    def forecast_failure_rate(
        self,
        equnr:        str,
        horizon_days: int = 30,
        training_days: int = 90,
        auart:        str = "W",
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

        next_x            = len(df)
        predicted         = intercept + slope * next_x
        predicted_clipped = max(0.0, predicted)

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

    # ──────────────────────────────────────────────────────────
    # 5.2 — Score de riesgo por equipo
    # ──────────────────────────────────────────────────────────

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
            if hist_mean > 0:
                ratio = recent_mean / hist_mean
                freq_score = min(100.0, max(0.0, (ratio - 1.0) / 2.0 * 100.0))
            else:
                freq_score = min(100.0, recent_mean * 10.0)
        else:
            freq_score = 50.0

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
        ghost_score = min(100.0, ghost_pct * 2.0)

        risk_score = (
            freq_score  * 0.40 +
            trend_score * 0.30 +
            rec_score   * 0.20 +
            ghost_score * 0.10
        )
        risk_score = round(min(100.0, max(0.0, risk_score)), 1)

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

    # ──────────────────────────────────────────────────────────
    # 5.3 — Detección de anomalías temporales
    # ──────────────────────────────────────────────────────────

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

        df_rate_pm3 = self._kpi.calc_failure_rate(
            equnr=equnr, linea=linea, auart="PM03",
            freq="W", start_date=start, end_date=end,
        )

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

    # ──────────────────────────────────────────────────────────
    # 5.4 — [ML] Random Forest Classifier (7d y 14d)
    # ──────────────────────────────────────────────────────────

    def _build_feature_row(
        self,
        equnr: str,
        window_end: datetime,
        lookback_days: int = 60,
    ) -> Optional[Dict]:
        """
        Construye un vector de features para un equipo en un punto de tiempo dado.
        Lookback: `lookback_days` días antes de `window_end`.
        """
        w_start = (window_end - timedelta(days=lookback_days)).strftime("%Y-%m-%dT%H:%M:%SZ")
        w_end   = window_end.strftime("%Y-%m-%dT%H:%M:%SZ")

        # Todos los eventos en la ventana
        df_ev = self.query(
            """SELECT mo.auart, mo.duration_min, mo.start_datetime, mo.is_ghost_stop
               FROM maintenance_orders mo
               WHERE mo.equnr = ? AND mo.start_datetime >= ? AND mo.start_datetime <= ?""",
            (equnr, w_start, w_end),
        )

        total = len(df_ev)
        if total == 0:
            return None

        df_ev["start_dt"] = pd.to_datetime(df_ev["start_datetime"], utc=True, errors="coerce")
        now_utc = window_end.replace(tzinfo=timezone.utc)

        events_7d  = int((df_ev["start_dt"] >= now_utc - timedelta(days=7)).sum())
        events_30d = int((df_ev["start_dt"] >= now_utc - timedelta(days=30)).sum())
        events_60d = total

        pm01_df = df_ev[df_ev["auart"] == "PM01"]
        pct_pm01 = len(pm01_df) / total if total > 0 else 0.0

        avg_duration = df_ev["duration_min"].clip(lower=0).mean()

        # Días desde la última falla PM01
        if not pm01_df.empty:
            last_fail = pm01_df["start_dt"].max()
            days_since = max(0.0, (now_utc - last_fail).total_seconds() / 86400)
        else:
            days_since = float(lookback_days)  # sin falla reciente → máximo

        # Recurrencia: % de eventos ocurridos en menos de 7 días del anterior
        if len(pm01_df) >= 2:
            gaps = pm01_df["start_dt"].sort_values().diff().dt.total_seconds().dropna() / 3600
            rec_score = float((gaps < 7 * 24).mean())
        else:
            rec_score = 0.0

        # Ghost stops %
        ghost_pct = float(df_ev["is_ghost_stop"].mean()) if total > 0 else 0.0

        # Día de la semana más frecuente de fallas
        if not pm01_df.empty and not pm01_df["start_dt"].isna().all():
            dow_mode = int(pm01_df["start_dt"].dt.dayofweek.mode().iloc[0])
        else:
            dow_mode = 0

        return {
            "events_7d":             events_7d,
            "events_30d":            events_30d,
            "events_60d":            events_60d,
            "avg_duration_min":      round(float(avg_duration), 2),
            "pct_pm01":              round(pct_pm01, 4),
            "days_since_last_failure": round(days_since, 2),
            "recurrence_score":      round(rec_score, 4),
            "ghost_pct":             round(ghost_pct, 4),
            "dayofweek_mode":        dow_mode,
        }

    def _build_training_dataset(
        self,
        horizon_7d:  int = 7,
        horizon_14d: int = 14,
        step_days:   int = 14,
    ) -> pd.DataFrame:
        """
        Genera el dataset de entrenamiento con ventana deslizante sobre el histórico.
        Etiqueta: 1 si hubo falla PM01 en los próximos N días, 0 si no.
        """
        # Rango global de datos
        bounds = self.query(
            "SELECT MIN(start_datetime) as mn, MAX(start_datetime) as mx FROM maintenance_orders"
        )
        if bounds.empty or pd.isna(bounds["mn"].iloc[0]):
            return pd.DataFrame()

        global_start = pd.to_datetime(bounds["mn"].iloc[0], utc=True)
        global_end   = pd.to_datetime(bounds["mx"].iloc[0], utc=True)

        # Todos los equipos con al menos 5 eventos
        df_equip = self.query(
            """SELECT equnr, COUNT(*) as cnt FROM maintenance_orders
               GROUP BY equnr HAVING cnt >= 5"""
        )

        rows = []
        window_start = global_start + timedelta(days=60)  # primeros 60 días son lookback
        current = window_start

        while current < global_end - timedelta(days=max(horizon_7d, horizon_14d)):
            for equnr in df_equip["equnr"]:
                feat = self._build_feature_row(equnr, current, lookback_days=60)
                if feat is None:
                    continue

                # Etiquetas: ¿hubo falla en los próximos N días?
                for horizon, col in [(horizon_7d, "label_7d"), (horizon_14d, "label_14d")]:
                    h_start = current.strftime("%Y-%m-%dT%H:%M:%SZ")
                    h_end   = (current + timedelta(days=horizon)).strftime("%Y-%m-%dT%H:%M:%SZ")
                    count = self.scalar(
                        "SELECT COUNT(*) FROM maintenance_orders WHERE equnr = ? AND auart = 'PM01' AND start_datetime > ? AND start_datetime <= ?",
                        (equnr, h_start, h_end),
                    ) or 0
                    feat[col] = int(count > 0)

                feat["equnr"]  = equnr
                feat["window"] = current.date().isoformat()
                rows.append(feat)

            current += timedelta(days=step_days)

        if not rows:
            return pd.DataFrame()

        return pd.DataFrame(rows)

    def train_failure_classifier(self, force: bool = False) -> Dict:
        """
        Entrena un Random Forest para predecir probabilidad de falla en 7d y 14d.
        Guarda el modelo en disco. Si ya existe y force=False, lo omite.

        Returns:
            dict con {trained_at, accuracy_7d, accuracy_14d, n_samples, features}
        """
        from sklearn.ensemble import RandomForestClassifier
        from sklearn.model_selection import cross_val_score
        from sklearn.preprocessing import LabelEncoder

        _MODEL_DIR.mkdir(parents=True, exist_ok=True)

        if _MODEL_PATH.exists() and not force:
            # Cargar modelo existente
            with open(_MODEL_PATH, "rb") as f:
                self._clf = pickle.load(f)
            if _META_PATH.exists():
                with open(_META_PATH) as f:
                    self._meta = json.load(f)
            return self._meta

        df = self._build_training_dataset()
        if df.empty or len(df) < 20:
            return {"error": "Datos insuficientes para entrenar el modelo", "n_samples": len(df)}

        feature_cols = [
            "events_7d", "events_30d", "events_60d", "avg_duration_min",
            "pct_pm01", "days_since_last_failure", "recurrence_score",
            "ghost_pct", "dayofweek_mode",
        ]

        X = df[feature_cols].fillna(0).values
        y7  = df["label_7d"].values
        y14 = df["label_14d"].values

        clf7  = RandomForestClassifier(n_estimators=150, max_depth=8, random_state=42, class_weight="balanced")
        clf14 = RandomForestClassifier(n_estimators=150, max_depth=8, random_state=42, class_weight="balanced")

        # Cross-validation accuracy
        acc7  = cross_val_score(clf7,  X, y7,  cv=min(5, len(df) // 4), scoring="roc_auc").mean()
        acc14 = cross_val_score(clf14, X, y14, cv=min(5, len(df) // 4), scoring="roc_auc").mean()

        # Entrenamiento final en todo el dataset
        clf7.fit(X, y7)
        clf14.fit(X, y14)

        feature_importance_7d = dict(zip(feature_cols, clf7.feature_importances_.round(4).tolist()))
        feature_importance_14d = dict(zip(feature_cols, clf14.feature_importances_.round(4).tolist()))

        self._clf = {"clf7": clf7, "clf14": clf14, "feature_cols": feature_cols}

        with open(_MODEL_PATH, "wb") as f:
            pickle.dump(self._clf, f)

        self._meta = {
            "trained_at":       datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "n_samples":        int(len(df)),
            "auc_roc_7d":       round(float(acc7),  4),
            "auc_roc_14d":      round(float(acc14), 4),
            "features":         feature_cols,
            "importance_7d":    feature_importance_7d,
            "importance_14d":   feature_importance_14d,
        }

        with open(_META_PATH, "w") as f:
            json.dump(self._meta, f, indent=2)

        return self._meta

    def _load_model(self):
        """Carga el modelo desde disco si no está en memoria."""
        if self._clf is not None:
            return True
        if _MODEL_PATH.exists():
            with open(_MODEL_PATH, "rb") as f:
                self._clf = pickle.load(f)
            if _META_PATH.exists():
                with open(_META_PATH) as f:
                    self._meta = json.load(f)
            return True
        return False

    def predict_next_failure_probability(
        self,
        equnr: str,
        start_date: Optional[str] = None,
        end_date:   Optional[str] = None,
    ) -> Dict:
        """
        Predice la probabilidad de que el equipo tenga una falla
        en los próximos 7 y 14 días.

        Returns:
            dict con {equnr, prob_7d, prob_14d, risk_label_7d, risk_label_14d,
                      top_features, model_available}
        """
        # Asegurar que el modelo está entrenado/cargado
        if not self._load_model():
            self.train_failure_classifier()

        if self._clf is None:
            return {
                "equnr":           equnr,
                "prob_7d":         None,
                "prob_14d":        None,
                "risk_label_7d":   "N/A",
                "risk_label_14d":  "N/A",
                "model_available": False,
            }

        _, end = self.clamp_dates(start_date, end_date)
        window_end = pd.to_datetime(end, utc=True).to_pydatetime()
        feat = self._build_feature_row(equnr, window_end, lookback_days=60)

        if feat is None:
            return {
                "equnr":           equnr,
                "prob_7d":         None,
                "prob_14d":        None,
                "risk_label_7d":   "Sin datos",
                "risk_label_14d":  "Sin datos",
                "model_available": True,
            }

        feature_cols = self._clf["feature_cols"]
        X = np.array([[feat.get(c, 0) for c in feature_cols]])

        prob_7d  = float(self._clf["clf7"].predict_proba(X)[0, 1])
        prob_14d = float(self._clf["clf14"].predict_proba(X)[0, 1])

        def _label(p: float) -> str:
            if p >= 0.75:  return "CRITICO"
            if p >= 0.50:  return "ALTO"
            if p >= 0.25:  return "MEDIO"
            return "BAJO"

        # Top 3 features más influyentes
        imp = self._meta.get("importance_14d", {})
        top_feats = sorted(imp.items(), key=lambda x: -x[1])[:3]

        return {
            "equnr":           equnr,
            "prob_7d":         round(prob_7d, 4),
            "prob_14d":        round(prob_14d, 4),
            "risk_label_7d":   _label(prob_7d),
            "risk_label_14d":  _label(prob_14d),
            "top_features":    top_feats,
            "model_available": True,
        }

    def get_all_predictions(
        self,
        linea:      Optional[str] = None,
        start_date: Optional[str] = None,
        end_date:   Optional[str] = None,
    ) -> pd.DataFrame:
        """
        Devuelve predicciones ML para todos los equipos de una línea o toda la planta.

        Returns:
            DataFrame con [equnr, tag_equipo, linea, prob_7d, prob_14d,
                           risk_label_7d, risk_label_14d]
        """
        start, end = self.clamp_dates(start_date, end_date)

        if linea:
            df_eq = self.query(
                "SELECT equnr, nombre_equipo, linea, tplnr FROM equipment WHERE linea = ?",
                (linea,)
            )
        else:
            df_eq = self.query(
                """SELECT e.equnr, e.nombre_equipo, e.linea, e.tplnr
                   FROM equipment e
                   JOIN (SELECT DISTINCT equnr FROM maintenance_orders
                         WHERE start_datetime >= ? AND start_datetime <= ?) mo
                   ON e.equnr = mo.equnr""",
                (start, end),
            )

        def extract_tag(t):
            if not t: return ""
            parts = str(t).split("-")
            return f"{parts[-2]}_{parts[-1]}" if len(parts) >= 2 else t

        rows = []
        for _, row in df_eq.iterrows():
            try:
                pred = self.predict_next_failure_probability(
                    equnr=row["equnr"], start_date=start, end_date=end
                )
                rows.append({
                    "equnr":           row["equnr"],
                    "tag_equipo":      extract_tag(row.get("tplnr", "")),
                    "nombre_equipo":   row.get("nombre_equipo", ""),
                    "linea":           row.get("linea", ""),
                    "prob_7d":         pred["prob_7d"],
                    "prob_14d":        pred["prob_14d"],
                    "risk_label_7d":   pred["risk_label_7d"],
                    "risk_label_14d":  pred["risk_label_14d"],
                })
            except Exception:
                pass

        if not rows:
            return pd.DataFrame()

        return pd.DataFrame(rows).sort_values("prob_14d", ascending=False).reset_index(drop=True)
