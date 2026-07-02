"""
kpis.py  — F4: Calculadora de KPIs de Mantenimiento
----------------------------------------------------
Calcula los indicadores estándar de mantenimiento industrial:

  4.1  MTTR (Mean Time To Repair)
  4.2  MTBF (Mean Time Between Failures)
  4.3  Disponibilidad y Uptime %
  4.4  Tasa de fallas por período
  4.5  Endpoint JSON consolidado para agente y reportes
"""

from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from analysis.base import AnalysisBase, OPERATING_HOURS_PER_DAY

# Pandas >= 2.2 deprecó los alias M, Q, Y — usar ME, QE, YE
_FREQ_ALIASES = {"M": "ME", "Q": "QE", "Y": "YE", "A": "YE"}

def _norm_freq(freq: str) -> str:
    """Normaliza aliases de frecuencia de pandas para compatibilidad >= 2.2."""
    return _FREQ_ALIASES.get(freq.upper(), freq)


class KPICalculator(AnalysisBase):
    """Motor de cálculo de KPIs de mantenimiento para MantOS."""

    # ------------------------------------------------------------------
    # 4.1 — MTTR (Mean Time To Repair)
    # ------------------------------------------------------------------

    def calc_mttr(
        self,
        equnr:      Optional[str] = None,
        linea:      Optional[str] = None,
        auart:      str = "PM01",          # Solo correctivos por default
        start_date: Optional[str] = None,
        end_date:   Optional[str] = None,
    ) -> Optional[float]:
        """
        Calcula el MTTR en minutos:
        MTTR = Suma(duration_min) / Cantidad_de_intervenciones

        Solo considera eventos con duration_min > 0 (excluye ghost stops).

        Args:
            equnr:      filtrar por equipo específico
            linea:      filtrar por línea de producción
            auart:      tipo de orden (default PM01 = correctivos)
            start_date: inicio del período ISO 8601
            end_date:   fin del período ISO 8601

        Returns:
            MTTR en minutos, o None si no hay datos suficientes
        """
        start, end = self.clamp_dates(start_date, end_date)
        filt_equnr = "AND mo.equnr = ?" if equnr else ""
        filt_linea = "AND e.linea = ?"  if linea  else ""
        filt_auart = "AND mo.auart = ?" if auart  else ""
        
        params     = [start, end]
        if auart:
            params.append(auart)
        if equnr:
            params.append(equnr)
        if linea:
            params.append(linea)

        sql = f"""
            SELECT AVG(mo.duration_min) AS mttr
            FROM maintenance_orders mo
            LEFT JOIN equipment e ON mo.equnr = e.equnr
            WHERE mo.start_datetime >= ?
              AND mo.start_datetime <= ?
              AND mo.duration_min > 0
              AND mo.is_ghost_stop = 0
              {filt_auart}
              {filt_equnr}
              {filt_linea}
        """
        result = self.scalar(sql, tuple(params))
        return round(float(result), 2) if result is not None else None

    def calc_mttr_by_equipment(
        self,
        linea:      Optional[str] = None,
        auart:      str = "PM01",
        start_date: Optional[str] = None,
        end_date:   Optional[str] = None,
    ) -> pd.DataFrame:
        """
        Calcula el MTTR para todos los equipos, ordenados de mayor a menor.

        Returns:
            DataFrame con [equnr, nombre_equipo, linea, mttr_min, event_count]
        """
        start, end = self.clamp_dates(start_date, end_date)
        filt_linea = "AND e.linea = ?" if linea else ""
        params     = [start, end, auart]
        if linea:
            params.append(linea)

        sql = f"""
            SELECT
                mo.equnr,
                e.nombre_equipo,
                e.linea,
                ROUND(AVG(mo.duration_min), 2)  AS mttr_min,
                COUNT(*)                         AS event_count
            FROM maintenance_orders mo
            LEFT JOIN equipment e ON mo.equnr = e.equnr
            WHERE mo.start_datetime >= ?
              AND mo.start_datetime <= ?
              AND mo.auart = ?
              AND mo.duration_min > 0
              AND mo.is_ghost_stop = 0
              {filt_linea}
            GROUP BY mo.equnr
            HAVING event_count >= 2
            ORDER BY mttr_min DESC
        """
        return self.query(sql, tuple(params))

    # ------------------------------------------------------------------
    # 4.2 — MTBF (Mean Time Between Failures)
    # ------------------------------------------------------------------

    def calc_mtbf(
        self,
        equnr:      str,
        auart:      str = "PM01",
        start_date: Optional[str] = None,
        end_date:   Optional[str] = None,
    ) -> Optional[float]:
        """
        Calcula el MTBF en horas para un equipo específico:
        MTBF = Media de gaps entre fallas correctivas consecutivas

        Args:
            equnr:      ID del equipo (requerido)
            auart:      tipo de orden de falla (default PM01)

        Returns:
            MTBF en horas, o None si hay < 2 eventos
        """
        start, end = self.clamp_dates(start_date, end_date)

        df = self.query(
            """SELECT start_datetime FROM maintenance_orders
               WHERE equnr = ? AND auart = ?
                 AND start_datetime >= ? AND start_datetime <= ?
                 AND is_ghost_stop = 0
               ORDER BY start_datetime""",
            (equnr, auart, start, end),
        )

        if len(df) < 2:
            return None

        timestamps = pd.to_datetime(df["start_datetime"], utc=True)
        # Gaps entre eventos consecutivos en horas
        gaps_hours = timestamps.diff().dt.total_seconds().dropna() / 3600.0
        # Filtrar gaps negativos (data sucia) y cero
        gaps_hours = gaps_hours[gaps_hours > 0]

        if gaps_hours.empty:
            return None

        return round(float(gaps_hours.mean()), 2)

    def calc_mttf(
        self,
        equnr:      str,
        auart:      str = "PM01",
        start_date: Optional[str] = None,
        end_date:   Optional[str] = None,
    ) -> Optional[float]:
        """
        Calcula el MTTF (Mean Time To Failure) en horas para un equipo específico.
        En activos reparables, se aproxima como MTBF - MTTR.
        """
        mtbf = self.calc_mtbf(equnr, auart, start_date, end_date)
        mttr_min = self.calc_mttr(equnr=equnr, auart=auart, start_date=start_date, end_date=end_date)
        
        if mtbf is None:
            return None
            
        mttr_hours = (mttr_min / 60.0) if mttr_min else 0.0
        mttf = max(0.0, mtbf - mttr_hours)
        return round(mttf, 2)

    def calc_mtbf_series(
        self,
        equnr:      str,
        freq:       str = "M",    # 'W'=semana, 'M'=mes, 'Q'=trimestre
        auart:      str = "PM01",
        start_date: Optional[str] = None,
        end_date:   Optional[str] = None,
    ) -> pd.DataFrame:
        """
        Calcula el MTBF mes a mes (o semana/trimestre) para ver tendencia.

        Returns:
            DataFrame con [period, mtbf_hours, event_count]
        """
        start, end = self.clamp_dates(start_date, end_date)

        df = self.query(
            """SELECT start_datetime FROM maintenance_orders
               WHERE equnr = ? AND auart = ?
                 AND start_datetime >= ? AND start_datetime <= ?
                 AND is_ghost_stop = 0
               ORDER BY start_datetime""",
            (equnr, auart, start, end),
        )

        if df.empty:
            return pd.DataFrame(columns=["period", "mtbf_hours", "event_count"])

        df["ts"] = pd.to_datetime(df["start_datetime"], utc=True)
        df = df.set_index("ts").sort_index()

        rows = []
        for period_label, group in df.resample(_norm_freq(freq)):
            events = len(group)
            if events >= 2:
                gaps  = group.index.to_series().diff().dt.total_seconds().dropna() / 3600.0
                mtbf  = float(gaps[gaps > 0].mean()) if (gaps > 0).any() else None
            else:
                mtbf  = None
            rows.append({"period": str(period_label.date()), "mtbf_hours": round(mtbf, 2) if mtbf else None, "event_count": events})

        return pd.DataFrame(rows)

    # ------------------------------------------------------------------
    # 4.3 — Disponibilidad y Uptime %
    # ------------------------------------------------------------------

    def calc_availability(
        self,
        equnr:                  str,
        start_date:             Optional[str] = None,
        end_date:               Optional[str] = None,
        operating_hours_per_day: float = OPERATING_HOURS_PER_DAY,
        include_pm02:           bool = False,
    ) -> Dict:
        """
        Calcula la disponibilidad de un equipo en el período:
        Disponibilidad = (Tiempo_operativo - Downtime_total) / Tiempo_operativo

        El downtime considera PM01 (correctivos). Opcionalmente incluye PM02.

        Returns:
            dict con {availability_pct, uptime_min, downtime_min, total_operating_min,
                      pm01_count, pm01_downtime_min, pm02_count, pm02_downtime_min}
        """
        start, end = self.clamp_dates(start_date, end_date)
        period_days = self.days_between(start, end)
        total_operating_min = period_days * operating_hours_per_day * 60.0

        auart_filter = "('PM01', 'PM02')" if include_pm02 else "('PM01')"

        df = self.query(
            f"""SELECT auart, duration_min FROM maintenance_orders
               WHERE equnr = ?
                 AND start_datetime >= ? AND start_datetime <= ?
                 AND is_ghost_stop = 0
                 AND duration_min > 0""",
            (equnr, start, end),
        )

        pm01_rows = df[df["auart"] == "PM01"]
        pm02_rows = df[df["auart"] == "PM02"]

        pm01_downtime = float(pm01_rows["duration_min"].sum())
        pm02_downtime = float(pm02_rows["duration_min"].sum())
        total_downtime = float(df["duration_min"].sum())

        uptime_min        = max(0.0, total_operating_min - total_downtime)
        availability_pct  = (uptime_min / total_operating_min * 100) if total_operating_min > 0 else 100.0

        return {
            "equnr":                equnr,
            "period_days":          round(period_days, 1),
            "total_operating_min":  round(total_operating_min, 1),
            "downtime_min":         round(total_downtime, 2),
            "uptime_min":           round(uptime_min, 2),
            "availability_pct":     round(availability_pct, 4),
            "pm01_count":           len(pm01_rows),
            "pm01_downtime_min":    round(pm01_downtime, 2),
            "pm02_count":           len(pm02_rows),
            "pm02_downtime_min":    round(pm02_downtime, 2),
        }

    def calc_availability_by_linea(
        self,
        linea:      Optional[str] = None,
        start_date: Optional[str] = None,
        end_date:   Optional[str] = None,
    ) -> pd.DataFrame:
        """
        Calcula disponibilidad para todos los equipos (opcionalmente de una línea).

        Returns:
            DataFrame con [equnr, nombre_equipo, linea, availability_pct, downtime_min]
            ordenado por availability_pct asc (los peores primero)
        """
        start, end = self.clamp_dates(start_date, end_date)

        if linea:
            df_eq = self.query(
                "SELECT equnr FROM equipment WHERE linea = ?", (linea,)
            )
        else:
            df_eq = self.query("SELECT equnr FROM equipment")

        rows = []
        for equnr in df_eq["equnr"]:
            avail = self.calc_availability(equnr, start_date=start, end_date=end)
            avail["mttr_min"] = self.calc_mttr(equnr=equnr, start_date=start, end_date=end)
            avail["mtbf_hours"] = self.calc_mtbf(equnr=equnr, start_date=start, end_date=end)
            rows.append(avail)

        df = pd.DataFrame(rows)
        if df.empty:
            return df

        # Enriquecer con nombre de equipo
        df_names = self.query(
            "SELECT equnr, nombre_equipo, linea, tplnr FROM equipment"
        )
        df = df.merge(df_names, on="equnr", how="left")
        
        # Parse tag from tplnr: "PGS-PR-LA1-HRN01" -> "LA1_HRN01"
        def extract_tag(t):
            if pd.isna(t): return ""
            parts = str(t).split("-")
            if len(parts) >= 2:
                return f"{parts[-2]}_{parts[-1]}"
            return t
            
        df["tag_equipo"] = df["tplnr"].apply(extract_tag)
        
        return df.sort_values("availability_pct").reset_index(drop=True)

    # ------------------------------------------------------------------
    # 4.4 — Tasa de fallas por período
    # ------------------------------------------------------------------

    def calc_failure_rate(
        self,
        equnr:      Optional[str] = None,
        linea:      Optional[str] = None,
        auart:      str = "PM01",
        freq:       str = "W",     # 'D'=día, 'W'=semana, 'M'=mes
        start_date: Optional[str] = None,
        end_date:   Optional[str] = None,
    ) -> pd.DataFrame:
        """
        Calcula la tasa de fallas por período (serie temporal).

        Returns:
            DataFrame con [period, failure_count, rolling_mean_4]
            rolling_mean_4 = media móvil de 4 períodos
        """
        start, end = self.clamp_dates(start_date, end_date)
        filt_equnr = "AND mo.equnr = ?" if equnr else ""
        filt_linea = "AND e.linea = ?"  if linea  else ""
        params     = [start, end, auart]
        if equnr:
            params.append(equnr)
        if linea:
            params.append(linea)

        sql = f"""
            SELECT mo.start_datetime
            FROM maintenance_orders mo
            LEFT JOIN equipment e ON mo.equnr = e.equnr
            WHERE mo.start_datetime >= ?
              AND mo.start_datetime <= ?
              AND mo.auart = ?
              AND mo.is_ghost_stop = 0
              {filt_equnr}
              {filt_linea}
            ORDER BY mo.start_datetime
        """
        df = self.query(sql, tuple(params))

        if df.empty:
            return pd.DataFrame(columns=["period", "failure_count", "rolling_mean_4"])

        df["ts"] = pd.to_datetime(df["start_datetime"], utc=True)
        series   = df.set_index("ts").resample(_norm_freq(freq)).size()
        result   = series.rename("failure_count").reset_index()
        result   = result.rename(columns={"ts": "period"})
        result["period"]        = result["period"].dt.strftime("%Y-%m-%d")
        result["rolling_mean_4"] = result["failure_count"].rolling(4, min_periods=1).mean().round(2)

        return result

    def get_failure_trend(
        self,
        equnr:      str,
        auart:      str = "PM01",
        start_date: Optional[str] = None,
        end_date:   Optional[str] = None,
        freq:       str = "W",
    ) -> Dict:
        """
        Calcula si la tasa de fallas de un equipo está subiendo o bajando.

        Returns:
            dict con {slope, r_squared, direction: 'improving'|'deteriorating'|'stable'}
        """
        from scipy.stats import linregress

        df = self.calc_failure_rate(
            equnr=equnr, auart=auart, freq=freq,
            start_date=start_date, end_date=end_date
        )

        if len(df) < 4:
            return {"slope": None, "r_squared": None, "direction": "insufficient_data"}

        x = np.arange(len(df))
        y = df["failure_count"].to_numpy()

        slope, intercept, r_value, p_value, std_err = linregress(x, y)
        r_sq = r_value ** 2

        if abs(slope) < 0.05 or r_sq < 0.15:
            direction = "stable"
        elif slope > 0:
            direction = "deteriorating"
        else:
            direction = "improving"

        return {
            "slope":       round(float(slope), 4),
            "r_squared":   round(float(r_sq), 4),
            "p_value":     round(float(p_value), 4),
            "direction":   direction,
            "data_points": len(df),
        }

    # ------------------------------------------------------------------
    # 4.5 — Endpoint JSON consolidado para agente
    # ------------------------------------------------------------------

    def get_kpi_summary(
        self,
        equnr:      Optional[str] = None,
        linea:      Optional[str] = None,
        start_date: Optional[str] = None,
        end_date:   Optional[str] = None,
    ) -> Dict:
        """
        Retorna un dict JSON con todos los KPIs para un equipo o línea.
        Este es el endpoint principal que consume el agente y los reportes.

        Returns:
            dict estructurado con mttr, mtbf, availability, failure_rate, trend
        """
        start, end = self.clamp_dates(start_date, end_date)

        kpis: Dict = {
            "query": {
                "equnr":      equnr,
                "linea":      linea,
                "start_date": start,
                "end_date":   end,
            },
            "mttr":         None,
            "mtbf":         None,
            "mttf":         None,
            "availability": None,
            "failure_trend": None,
            "event_counts": {},
        }

        # Conteos por tipo
        for auart in ("PM01", "PM02", "PM03"):
            filt_equnr = "AND equnr = ?" if equnr else ""
            filt_linea = ""  # linea requiere JOIN, simplificamos
            params = [start, end, auart]
            if equnr:
                params.append(equnr)
            count = self.scalar(
                f"SELECT COUNT(*) FROM maintenance_orders "
                f"WHERE start_datetime >= ? AND start_datetime <= ? AND auart = ? {filt_equnr}",
                tuple(params)
            )
            kpis["event_counts"][auart] = count or 0

        # Si hay equipo específico: calcular todos los KPIs
        if equnr:
            kpis["mttr"]          = self.calc_mttr(equnr=equnr, start_date=start, end_date=end)
            kpis["mtbf"]          = self.calc_mtbf(equnr=equnr, start_date=start, end_date=end)
            kpis["mttf"]          = self.calc_mttf(equnr=equnr, start_date=start, end_date=end)
            kpis["availability"]  = self.calc_availability(equnr=equnr, start_date=start, end_date=end)
            kpis["failure_trend"] = self.get_failure_trend(equnr=equnr, start_date=start, end_date=end)
        else:
            kpis["mttr"] = self.calc_mttr(linea=linea, start_date=start, end_date=end)
            avail_df = self.calc_availability_by_linea(linea=linea, start_date=start, end_date=end)
            kpis["availability"] = avail_df.to_dict("records") if not avail_df.empty else []
            
            # Promedio de MTBFs individuales
            params = [linea] if linea else []
            filt = "WHERE linea = ?" if linea else ""
            df_eq = self.query(f"SELECT equnr FROM equipment {filt}", tuple(params))
            mtbfs = []
            for eq in df_eq["equnr"]:
                m = self.calc_mtbf(equnr=eq, start_date=start, end_date=end)
                if m is not None:
                    mtbfs.append(m)
            kpis["mtbf"] = round(sum(mtbfs)/len(mtbfs), 2) if mtbfs else None

        return kpis
