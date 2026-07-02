"""
diagnostic.py  — F3: Análisis de Diagnóstico
---------------------------------------------
Responde: ¿por qué pasó?

Subtareas:
  3.1  Pareto de fallas (80/20 por eventos y downtime)
  3.2  Auditoría de paros fantasma
  3.3  Detección de patrones de recurrencia
  3.4  Agrupamiento y taxonomía de fallas por texto
"""

import re
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from analysis.base import AnalysisBase
from analysis.descriptive import DescriptiveAnalysis

# Taxonomía canónica de categorías de falla
# Formato: {categoria: [patrones_regex]}
FAILURE_TAXONOMY = {
    "SENSOR_FALLA": [
        r"\bsensor\b", r"\bsens\b", r"\boptico\b", r"\bproximidad\b",
        r"\btemp\b", r"\bfallo\b", r"\bfalla\b",
    ],
    "ATASCO_PRODUCTO": [
        r"\batasco\b", r"\batsc\b", r"\bproducto\b", r"\batasque\b",
    ],
    "REINICIO_HMI": [
        r"\breinicio\b", r"\breset\b", r"\brst\b", r"\bciclo\b", r"\bhmi\b",
    ],
    "MICRO_PARO": [
        r"\bmicro.?paro\b", r"\bm\.paro\b", r"\bmicroparo\b",
        r"\bparo.?menor\b", r"\bparo.?operativo\b",
    ],
    "INSPECCION_RUTINA": [
        r"\binsp\b", r"\binspeccion\b", r"\brutina\b", r"\brutinaria\b",
    ],
    "CAMBIO_CONSUMIBLE": [
        r"\bcambio\b", r"\bconsum\b", r"\brepuesto\b",
    ],
    "CALIBRACION_AJUSTE": [
        r"\bcalib\b", r"\bajuste\b", r"\baj\b",
    ],
    "MANTENIMIENTO_PREVENTIVO": [
        r"\bpreventivo\b", r"\bprev\b", r"\bprogramado\b", r"\bmto\b",
        r"\bmtto\b", r"\bmantt\b",
    ],
}


class DiagnosticAnalysis(AnalysisBase):
    """Motor de análisis de diagnóstico de órdenes de mantenimiento."""

    def __init__(self, db_path=None):
        super().__init__(db_path)
        self._desc = DescriptiveAnalysis(db_path or self.db_path)

    # ------------------------------------------------------------------
    # 3.1 — Pareto de fallas
    # ------------------------------------------------------------------

    def get_pareto(
        self,
        metric:     str = "events",   # 'events' | 'downtime'
        group_by:   str = "equnr",    # 'equnr' | 'linea'
        auart:      Optional[str] = None,
        linea:      Optional[str] = None,
        start_date: Optional[str] = None,
        end_date:   Optional[str] = None,
        top_n:      int = 20,
    ) -> pd.DataFrame:
        """
        Calcula el análisis de Pareto: identifica los equipos/líneas que
        concentran el 80% de los eventos o del downtime.

        Returns:
            DataFrame con [group_key, value, pct, cumulative_pct, is_vital_few]
            is_vital_few = True si el equipo está dentro del 80% acumulado
        """
        start, end = self.clamp_dates(start_date, end_date)
        auart_filt = "AND mo.auart = ?" if auart else ""
        linea_filt = "AND e.linea = ?" if linea else ""
        params     = [start, end]
        if auart:
            params.append(auart)
        if linea:
            params.append(linea)

        group_col = "mo.equnr" if group_by == "equnr" else "e.linea"

        if metric == "events":
            value_expr = "COUNT(*)"
            value_col  = "event_count"
        else:
            value_expr = "ROUND(SUM(CASE WHEN mo.duration_min > 0 THEN mo.duration_min ELSE 0 END), 2)"
            value_col  = "downtime_min"

        sql = f"""
            SELECT
                {group_col} AS group_key,
                {value_expr} AS value
            FROM maintenance_orders mo
            LEFT JOIN equipment e ON mo.equnr = e.equnr
            WHERE mo.start_datetime >= ? AND mo.start_datetime <= ?
              {auart_filt}
              {linea_filt}
            GROUP BY group_key
            HAVING group_key IS NOT NULL
            ORDER BY value DESC
            LIMIT ?
        """
        params.append(top_n)
        df = self.query(sql, tuple(params))
        df = df.rename(columns={"value": value_col})

        if df.empty:
            return df

        total = df[value_col].sum()
        df["pct"]            = (df[value_col] / total * 100).round(2)
        df["cumulative_pct"] = df["pct"].cumsum().round(2)
        df["is_vital_few"]   = df["cumulative_pct"] <= 80.0

        return df.reset_index(drop=True)

    # ------------------------------------------------------------------
    # 3.2 — Auditoría de ghost stops
    # ------------------------------------------------------------------

    def audit_ghost_stops(
        self,
        start_date: Optional[str] = None,
        end_date:   Optional[str] = None,
    ) -> Dict:
        """
        Analiza los paros fantasma (is_ghost_stop = 1):
        - Distribución por equipo, usuario, hora del día y día de semana
        - Identifica los principales generadores

        Returns:
            dict con sub-DataFrames y resumen
        """
        start, end = self.clamp_dates(start_date, end_date)
        params     = (start, end)

        base_filter = (
            "WHERE mo.is_ghost_stop = 1 "
            "AND mo.start_datetime >= ? AND mo.start_datetime <= ?"
        )

        total_ghost = self.scalar(
            f"SELECT COUNT(*) FROM maintenance_orders mo {base_filter}", params
        )

        # Por equipo
        by_equip = self.query(
            f"""SELECT mo.equnr, e.nombre_equipo, e.linea, COUNT(*) AS ghost_count
                FROM maintenance_orders mo
                LEFT JOIN equipment e ON mo.equnr = e.equnr
                {base_filter}
                GROUP BY mo.equnr ORDER BY ghost_count DESC""",
            params,
        )

        # Por usuario creador
        by_user = self.query(
            f"""SELECT mo.ernam, u.tipo, COUNT(*) AS ghost_count,
                       ROUND(COUNT(*) * 100.0 / ?, 1) AS pct
                FROM maintenance_orders mo
                LEFT JOIN users u ON mo.ernam = u.ernam
                {base_filter}
                GROUP BY mo.ernam ORDER BY ghost_count DESC""",
            (total_ghost, *params),
        )

        # Por hora del día
        by_hour = self.query(
            f"""SELECT
                    CAST(strftime('%H', mo.start_datetime) AS INTEGER) AS hora,
                    COUNT(*) AS ghost_count
                FROM maintenance_orders mo
                {base_filter}
                GROUP BY hora ORDER BY hora""",
            params,
        )

        # Por tipo de orden
        by_auart = self.query(
            f"""SELECT mo.auart, COUNT(*) AS ghost_count
                FROM maintenance_orders mo
                {base_filter}
                GROUP BY mo.auart ORDER BY ghost_count DESC""",
            params,
        )

        return {
            "total_ghost_stops": total_ghost,
            "period":            {"start": start, "end": end},
            "by_equipment":      by_equip,
            "by_user":           by_user,
            "by_hour":           by_hour,
            "by_order_type":     by_auart,
            "top_generator_user":   by_user.iloc[0]["ernam"] if not by_user.empty else None,
            "top_generator_equip":  by_equip.iloc[0]["equnr"] if not by_equip.empty else None,
        }

    # ------------------------------------------------------------------
    # 3.3 — Patrones de recurrencia
    # ------------------------------------------------------------------

    def get_recurrence_score(
        self,
        equnr:       str,
        window_days: int = 7,
        start_date:  Optional[str] = None,
        end_date:    Optional[str] = None,
    ) -> float:
        """
        Calcula un score de recurrencia para un equipo (0=sin recurrencia, 1=alta).

        El score mide qué proporción de días en el período tiene más de un evento
        en la ventana de `window_days` consecutivos.

        Returns:
            float ∈ [0, 1]
        """
        start, end = self.clamp_dates(start_date, end_date)

        df = self.query(
            """SELECT start_datetime FROM maintenance_orders
               WHERE equnr = ? AND start_datetime >= ? AND start_datetime <= ?
               AND is_ghost_stop = 0
               ORDER BY start_datetime""",
            (equnr, start, end),
        )

        if len(df) < 2:
            return 0.0

        timestamps = pd.to_datetime(df["start_datetime"], utc=True)
        # Calcular gaps entre eventos consecutivos (en días)
        gaps = timestamps.diff().dt.total_seconds().dropna() / 86400.0

        # Proporción de gaps menores a window_days
        score = float((gaps < window_days).mean())
        return round(score, 4)

    def get_recurring_failures(
        self,
        threshold:   float = 0.5,
        window_days: int   = 7,
        start_date:  Optional[str] = None,
        end_date:    Optional[str] = None,
    ) -> pd.DataFrame:
        """
        Retorna la lista de equipos con recurrencia alta (score >= threshold).

        Returns:
            DataFrame con [equnr, nombre_equipo, linea, recurrence_score, total_events]
            ordenado por score descendente
        """
        start, end = self.clamp_dates(start_date, end_date)
        equipment  = self.get_all_equipment()

        rows = []
        for equnr in equipment:
            score = self.get_recurrence_score(
                equnr, window_days=window_days, start_date=start, end_date=end
            )
            if score >= threshold:
                rows.append({"equnr": equnr, "recurrence_score": score})

        if not rows:
            return pd.DataFrame(columns=["equnr", "nombre_equipo", "linea",
                                          "recurrence_score", "total_events"])

        df_scores = pd.DataFrame(rows)

        # Enriquecer con nombre y línea
        equnr_list = ", ".join(f"'{e}'" for e in df_scores["equnr"])
        df_info = self.query(
            f"""SELECT mo.equnr,
                       e.nombre_equipo,
                       e.linea,
                       COUNT(*) AS total_events
                FROM maintenance_orders mo
                LEFT JOIN equipment e ON mo.equnr = e.equnr
                WHERE mo.equnr IN ({equnr_list})
                  AND mo.start_datetime >= ? AND mo.start_datetime <= ?
                  AND mo.is_ghost_stop = 0
                GROUP BY mo.equnr""",
            (start, end),
        )

        result = df_scores.merge(df_info, on="equnr", how="left")
        return result.sort_values("recurrence_score", ascending=False).reset_index(drop=True)

    # ------------------------------------------------------------------
    # 3.4 — Agrupamiento y taxonomía de fallas
    # ------------------------------------------------------------------

    @staticmethod
    def classify_failure_text(text: str) -> str:
        """
        Clasifica un texto de falla en una categoría canónica de la taxonomía.

        Returns:
            nombre de la categoría, o 'OTRO' si no encaja en ninguna
        """
        if not text or not isinstance(text, str):
            return "OTRO"

        t = text.lower()
        for category, patterns in FAILURE_TAXONOMY.items():
            for pat in patterns:
                if re.search(pat, t):
                    return category
        return "OTRO"

    def build_failure_taxonomy(
        self,
        start_date: Optional[str] = None,
        end_date:   Optional[str] = None,
    ) -> pd.DataFrame:
        """
        Clasifica todas las órdenes según la taxonomía canónica.

        Returns:
            DataFrame con [aufnr, equnr, auart, qmtxt, categoria,
                           categoria_count, pct_of_total]
        """
        start, end = self.clamp_dates(start_date, end_date)

        df = self.query(
            """SELECT aufnr, equnr, auart, qmtxt
               FROM maintenance_orders
               WHERE start_datetime >= ? AND start_datetime <= ?""",
            (start, end),
        )

        df["categoria"] = df["qmtxt"].apply(self.classify_failure_text)

        # Contar por categoría
        cat_counts = df["categoria"].value_counts().rename("categoria_count")
        total      = len(df)
        df = df.merge(cat_counts.reset_index().rename(columns={"index": "categoria"}),
                      on="categoria", how="left")
        df["pct_of_total"] = (df["categoria_count"] / total * 100).round(2)

        return df

    def get_taxonomy_summary(
        self,
        start_date: Optional[str] = None,
        end_date:   Optional[str] = None,
    ) -> pd.DataFrame:
        """
        Resumen de la taxonomía: cuántos eventos hay por categoría.

        Returns:
            DataFrame con [categoria, event_count, pct, downtime_min]
            ordenado por event_count desc
        """
        start, end = self.clamp_dates(start_date, end_date)

        df = self.query(
            """SELECT qmtxt, duration_min
               FROM maintenance_orders
               WHERE start_datetime >= ? AND start_datetime <= ?""",
            (start, end),
        )
        df["categoria"] = df["qmtxt"].apply(self.classify_failure_text)
        df["downtime"]  = df["duration_min"].where(df["duration_min"] > 0, 0)

        summary = (
            df.groupby("categoria")
            .agg(event_count=("categoria", "size"), downtime_min=("downtime", "sum"))
            .reset_index()
            .sort_values("event_count", ascending=False)
        )
        total = summary["event_count"].sum()
        summary["pct"] = (summary["event_count"] / total * 100).round(2)
        summary["downtime_min"] = summary["downtime_min"].round(2)

        return summary.reset_index(drop=True)
