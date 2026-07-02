"""
descriptive.py  — F2: Análisis Descriptivo
------------------------------------------
Responde: ¿qué pasó?

Subtareas:
  2.1  Frecuencia de fallas por equipo/línea/tipo y período
  2.2  Mapa de calor temporal (hora × día de semana)
  2.3  Distribución de duración de eventos
  2.4  Análisis básico de texto de fallas (keywords, normalización)
"""

import re
from collections import Counter
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from analysis.base import AnalysisBase


# Abreviaciones conocidas en el dataset → término canónico
_ABBREV_MAP = {
    r"\bm\.paro\b":       "micro paro",
    r"\bmparo\b":         "micro paro",
    r"\bmicroparo\b":     "micro paro",
    r"\batsc\b":          "atasco",
    r"\batasco\b":        "atasco",
    r"\brst\b":           "reinicio",
    r"\breset\b":         "reinicio",
    r"\brst\b":           "reinicio",
    r"\bfallo\b":         "falla",
    r"\bfalllo\b":        "falla",
    r"\bsens\b":          "sensor",
    r"\bsensor\b":        "sensor",
    r"\btemp\b":          "temperatura",
    r"\bprox\b":          "proximidad",
    r"\boptico\b":        "optico",
    r"\binsp\b":          "inspeccion",
    r"\binspeccion\b":    "inspeccion",
    r"\bmto\b":           "mantenimiento",
    r"\bmtto\b":          "mantenimiento",
    r"\bmantt\b":         "mantenimiento",
    r"\bcalib\b":         "calibracion",
    r"\bcmb\b":           "cambio",
    r"\bconsum\b":        "consumibles",
    r"\baj\b":            "ajuste",
    r"\bprev\b":          "preventivo",
    r"\bcorr\b":          "correctivo",
    r"\bHMI\b":           "hmi",
    r"\bL4\b":            "linea4",
}

# Stopwords de dominio industrial (no aportan a la semántica de falla)
_STOPWORDS = {
    "de", "en", "el", "la", "los", "las", "por", "con", "sin",
    "se", "y", "a", "un", "una", "al", "del", "o", "es", "no",
    "ok", "idem", "anterior", "ver", "ot", "novedad", "resuelto",
    "sin", "sin observaciones", "normalizado", "equipo",
}

DAYS_ES = ["Lun", "Mar", "Mie", "Jue", "Vie", "Sab", "Dom"]


# ======================================================================
class DescriptiveAnalysis(AnalysisBase):
    """Motor de análisis descriptivo de órdenes de mantenimiento."""

    # ------------------------------------------------------------------
    # 2.1 — Frecuencia de fallas
    # ------------------------------------------------------------------

    def get_event_frequency(
        self,
        group_by:   str = "equnr",     # 'equnr' | 'tplnr' | 'linea' | 'auart'
        period:     str = "month",     # 'day' | 'week' | 'month'
        auart:      Optional[str] = None,
        start_date: Optional[str] = None,
        end_date:   Optional[str] = None,
        top_n:      Optional[int] = None,
    ) -> pd.DataFrame:
        """
        Cuenta eventos agrupados por una dimensión y un período temporal.

        Returns:
            DataFrame con columnas [group_key, period_label, event_count, downtime_min]
        """
        start, end = self.clamp_dates(start_date, end_date)

        # Mapa de formato SQLite para strftime según período
        period_fmt = {"day": "%Y-%m-%d", "week": "%Y-%W", "month": "%Y-%m"}
        if period not in period_fmt:
            raise ValueError(f"period debe ser 'day', 'week' o 'month'. Got: {period!r}")

        # Dimensión de agrupado
        group_col_map = {
            "equnr": "mo.equnr",
            "tplnr": "mo.tplnr",
            "linea": "e.linea",
            "auart": "mo.auart",
        }
        if group_by not in group_col_map:
            raise ValueError(f"group_by debe ser uno de: {list(group_col_map)}. Got: {group_by!r}")

        group_col  = group_col_map[group_by]
        strfmt     = period_fmt[period]
        auart_filt = "AND mo.auart = ?" if auart else ""
        params     = [start, end]
        if auart:
            params.append(auart)

        sql = f"""
            SELECT
                {group_col}                               AS group_key,
                strftime('{strfmt}', mo.start_datetime)  AS period_label,
                COUNT(*)                                   AS event_count,
                ROUND(SUM(CASE WHEN mo.duration_min > 0
                               THEN mo.duration_min ELSE 0 END), 2) AS downtime_min
            FROM maintenance_orders mo
            LEFT JOIN equipment e ON mo.equnr = e.equnr
            WHERE mo.start_datetime >= ?
              AND mo.start_datetime <= ?
              {auart_filt}
            GROUP BY group_key, period_label
            ORDER BY group_key, period_label
        """
        df = self.query(sql, tuple(params))

        if top_n:
            # Filtrar por los top_n grupos con más eventos totales
            top_keys = (
                df.groupby("group_key")["event_count"]
                .sum()
                .nlargest(top_n)
                .index
            )
            df = df[df["group_key"].isin(top_keys)]

        return df.reset_index(drop=True)

    def get_top_equipment_by_events(
        self,
        n: int = 10,
        auart: Optional[str] = None,
        linea: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date:   Optional[str] = None,
    ) -> pd.DataFrame:
        """
        Top-N equipos ordenados por cantidad total de eventos.

        Returns:
            DataFrame con [equnr, nombre_equipo, linea, event_count, downtime_min, pct_of_total]
        """
        start, end = self.clamp_dates(start_date, end_date)
        auart_filt = "AND mo.auart = ?" if auart else ""
        linea_filt = "AND e.linea = ?" if linea else ""
        params     = [start, end]
        if auart:
            params.append(auart)
        if linea:
            params.append(linea)

        sql = f"""
            SELECT
                mo.equnr,
                e.nombre_equipo,
                e.linea,
                COUNT(*) AS event_count,
                ROUND(SUM(CASE WHEN mo.duration_min > 0
                               THEN mo.duration_min ELSE 0 END), 2) AS downtime_min
            FROM maintenance_orders mo
            LEFT JOIN equipment e ON mo.equnr = e.equnr
            WHERE mo.start_datetime >= ?
              AND mo.start_datetime <= ?
              {auart_filt}
              {linea_filt}
            GROUP BY mo.equnr
            ORDER BY event_count DESC
            LIMIT ?
        """
        params.append(n)
        df = self.query(sql, tuple(params))

        if not df.empty:
            total = df["event_count"].sum()
            df["pct_of_total"] = (df["event_count"] / total * 100).round(1)
            # Acumulado para análisis de Bad Actors
            df["pct_acumulado"] = df["pct_of_total"].cumsum().round(1)

        return df

    # ------------------------------------------------------------------
    # 2.2 — Mapa de calor temporal
    # ------------------------------------------------------------------

    def get_temporal_heatmap(
        self,
        equnr:      Optional[str] = None,
        linea:      Optional[str] = None,
        start_date: Optional[str] = None,
        end_date:   Optional[str] = None,
    ) -> pd.DataFrame:
        """
        Genera una matriz hora (0-23) × día de semana (0=Lun, 6=Dom)
        con el conteo de eventos.

        Returns:
            DataFrame pivotado: índices=horas (0-23), columnas=días (Lun..Dom)
        """
        start, end = self.clamp_dates(start_date, end_date)
        filt_equnr = "AND mo.equnr = ?" if equnr else ""
        filt_linea = "AND e.linea = ?"  if linea  else ""
        params     = [start, end]
        if equnr:
            params.append(equnr)
        if linea:
            params.append(linea)

        sql = f"""
            SELECT
                CAST(strftime('%H', mo.start_datetime) AS INTEGER) AS hora,
                CAST(strftime('%w', mo.start_datetime) AS INTEGER) AS dia_semana_raw,
                COUNT(*) AS event_count
            FROM maintenance_orders mo
            LEFT JOIN equipment e ON mo.equnr = e.equnr
            WHERE mo.start_datetime >= ?
              AND mo.start_datetime <= ?
              {filt_equnr}
              {filt_linea}
            GROUP BY hora, dia_semana_raw
            ORDER BY hora, dia_semana_raw
        """
        df = self.query(sql, tuple(params))

        if df.empty:
            # Retornar matriz vacía con estructura correcta
            return pd.DataFrame(
                0, index=range(24), columns=DAYS_ES
            )

        # SQLite devuelve 0=Domingo, 1=Lunes … 6=Sábado
        # Reordenar a Lunes=0 … Domingo=6 (estilo ISO)
        day_map = {1: 0, 2: 1, 3: 2, 4: 3, 5: 4, 6: 5, 0: 6}
        df["dia_semana"] = df["dia_semana_raw"].map(day_map)

        # Pivotear
        pivot = df.pivot_table(
            index="hora", columns="dia_semana",
            values="event_count", aggfunc="sum", fill_value=0
        )
        # Asegurar todas las horas y días
        pivot = pivot.reindex(index=range(24), columns=range(7), fill_value=0)
        pivot.columns = DAYS_ES
        pivot.index.name = "Hora"

        return pivot

    # ------------------------------------------------------------------
    # 2.3 — Distribución de duración
    # ------------------------------------------------------------------

    def get_duration_stats(
        self,
        equnr:      Optional[str] = None,
        linea:      Optional[str] = None,
        auart:      Optional[str] = None,
        start_date: Optional[str] = None,
        end_date:   Optional[str] = None,
    ) -> Dict:
        """
        Calcula estadísticas de duración (en minutos) excluyendo ghost stops.

        Returns:
            dict con: count, mean, median, std, min, max, p90, p99,
                      ghost_stops_excluded, total_downtime_min
        """
        start, end = self.clamp_dates(start_date, end_date)
        filt_equnr = "AND mo.equnr = ?" if equnr else ""
        filt_linea = "AND e.linea = ?"  if linea  else ""
        filt_auart = "AND mo.auart = ?" if auart  else ""
        params     = [start, end]
        if equnr:
            params.append(equnr)
        if linea:
            params.append(linea)
        if auart:
            params.append(auart)

        # Cargar solo los duration_min válidos (> 0)
        sql = f"""
            SELECT mo.duration_min, mo.is_ghost_stop
            FROM maintenance_orders mo
            LEFT JOIN equipment e ON mo.equnr = e.equnr
            WHERE mo.start_datetime >= ?
              AND mo.start_datetime <= ?
              {filt_equnr}
              {filt_linea}
              {filt_auart}
        """
        df = self.query(sql, tuple(params))

        total_events    = len(df)
        ghost_excluded  = int(df["is_ghost_stop"].sum())
        valid           = df[df["duration_min"] > 0]["duration_min"].dropna()

        if valid.empty:
            return {
                "count": 0, "mean": None, "median": None, "std": None,
                "min": None, "max": None, "p90": None, "p99": None,
                "ghost_stops_excluded": ghost_excluded,
                "total_events": total_events,
                "total_downtime_min": 0.0,
            }

        arr = valid.to_numpy()
        return {
            "count":                  int(len(arr)),
            "mean":                   round(float(np.mean(arr)), 2),
            "median":                 round(float(np.median(arr)), 2),
            "std":                    round(float(np.std(arr)), 2),
            "min":                    round(float(np.min(arr)), 2),
            "max":                    round(float(np.max(arr)), 2),
            "p90":                    round(float(np.percentile(arr, 90)), 2),
            "p99":                    round(float(np.percentile(arr, 99)), 2),
            "ghost_stops_excluded":   ghost_excluded,
            "total_events":           total_events,
            "total_downtime_min":     round(float(np.sum(arr)), 2),
        }

    def get_duration_by_type(
        self,
        start_date: Optional[str] = None,
        end_date:   Optional[str] = None,
    ) -> pd.DataFrame:
        """
        Estadísticas de duración separadas por tipo de orden (PM01/PM02/PM03).

        Returns:
            DataFrame con [auart, count, mean, median, p90, total_downtime_min]
        """
        start, end = self.clamp_dates(start_date, end_date)
        results = []
        for auart in ("PM01", "PM02", "PM03"):
            stats = self.get_duration_stats(auart=auart, start_date=start, end_date=end)
            stats["auart"] = auart
            results.append(stats)
        return pd.DataFrame(results)[
            ["auart", "count", "mean", "median", "p90", "max", "total_downtime_min"]
        ]

    # ------------------------------------------------------------------
    # 2.4 — Análisis de texto
    # ------------------------------------------------------------------

    @staticmethod
    def normalize_failure_text(text: str) -> str:
        """
        Normaliza texto de falla:
        1. Lowercase
        2. Reemplaza abreviaciones por términos canónicos
        3. Elimina puntuación y caracteres especiales
        4. Elimina stopwords de dominio
        """
        if not text or not isinstance(text, str):
            return ""

        t = text.lower().strip()

        # Reemplazar abreviaciones
        for pattern, replacement in _ABBREV_MAP.items():
            t = re.sub(pattern, replacement, t, flags=re.IGNORECASE)

        # Eliminar puntuación y caracteres no alfanuméricos
        t = re.sub(r"[^\w\s]", " ", t)
        t = re.sub(r"\s+", " ", t).strip()

        # Filtrar stopwords
        tokens = [w for w in t.split() if w not in _STOPWORDS and len(w) > 2]
        return " ".join(tokens)

    def get_top_keywords(
        self,
        equnr:      Optional[str] = None,
        linea:      Optional[str] = None,
        auart:      Optional[str] = None,
        n:          int = 20,
        start_date: Optional[str] = None,
        end_date:   Optional[str] = None,
        field:      str = "qmtxt",   # 'qmtxt' | 'ltxtaufk' | 'both'
    ) -> List[Tuple[str, int]]:
        """
        Extrae las N palabras clave más frecuentes en los textos de falla.

        Returns:
            lista de (keyword, frecuencia) ordenada por frecuencia desc
        """
        start, end = self.clamp_dates(start_date, end_date)
        filt_equnr = "AND mo.equnr = ?" if equnr else ""
        filt_linea = "AND e.linea = ?"  if linea  else ""
        filt_auart = "AND mo.auart = ?" if auart  else ""
        params     = [start, end]
        if equnr:
            params.append(equnr)
        if linea:
            params.append(linea)
        if auart:
            params.append(auart)

        if field == "both":
            select_field = "mo.qmtxt || ' ' || COALESCE(mo.ltxtaufk, '')"
        elif field in ("qmtxt", "ltxtaufk"):
            select_field = f"mo.{field}"
        else:
            raise ValueError(f"field debe ser 'qmtxt', 'ltxtaufk' o 'both'. Got: {field!r}")

        sql = f"""
            SELECT {select_field} AS raw_text
            FROM maintenance_orders mo
            LEFT JOIN equipment e ON mo.equnr = e.equnr
            WHERE mo.start_datetime >= ?
              AND mo.start_datetime <= ?
              {filt_equnr}
              {filt_linea}
              {filt_auart}
        """
        df = self.query(sql, tuple(params))

        counter: Counter = Counter()
        for text in df["raw_text"].dropna():
            normalized = self.normalize_failure_text(str(text))
            counter.update(normalized.split())

        return counter.most_common(n)

    def get_failure_summary(
        self,
        start_date: Optional[str] = None,
        end_date:   Optional[str] = None,
    ) -> Dict:
        """
        Resumen general descriptivo de todo el dataset en un rango temporal.

        Returns:
            dict con estadísticas de alto nivel para el generador de reportes.
        """
        start, end = self.clamp_dates(start_date, end_date)
        params = (start, end)

        total = self.scalar(
            "SELECT COUNT(*) FROM maintenance_orders WHERE start_datetime >= ? AND start_datetime <= ?",
            params,
        )
        by_type = self.query(
            """SELECT auart, COUNT(*) AS cnt, ROUND(SUM(CASE WHEN duration_min > 0 THEN duration_min ELSE 0 END),2) AS dt
               FROM maintenance_orders
               WHERE start_datetime >= ? AND start_datetime <= ?
               GROUP BY auart""",
            params,
        )
        ghost = self.scalar(
            """SELECT COUNT(*) FROM maintenance_orders
               WHERE start_datetime >= ? AND start_datetime <= ? AND is_ghost_stop = 1""",
            params,
        )
        top3 = self.get_top_equipment_by_events(n=3, start_date=start, end_date=end)

        result = {
            "period":       {"start": start, "end": end},
            "total_events": total,
            "ghost_stops":  ghost,
            "ghost_pct":    round(ghost / total * 100, 1) if total else 0,
            "by_type":      by_type.set_index("auart").to_dict("index"),
            "top3_equipment": top3[["equnr", "nombre_equipo", "event_count", "downtime_min"]].to_dict("records"),
        }
        return result
