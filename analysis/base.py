"""
base.py
-------
Clase base y helpers compartidos para todos los módulos de análisis de MantOS.
Proporciona: conexión a la DB, helpers de fecha, y funciones SQL comunes.
"""

import sqlite3
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional, List, Tuple

import pandas as pd

# Ruta por defecto de la DB (relativa a la raíz del proyecto)
_MODULE_DIR  = Path(__file__).resolve().parent
_PROJECT_ROOT = _MODULE_DIR.parent
DEFAULT_DB   = _PROJECT_ROOT / "data" / "mantos.db"

# Rango completo de datos disponibles
DATA_START = "2024-04-01T00:00:00Z"
DATA_END   = "2026-03-31T23:59:59Z"

# Horas de operación diarias (asumimos 24/7 — ajustable)
OPERATING_HOURS_PER_DAY = 24

# Equipos de LA4 (línea principal de alfajores)
LA4_EQUIPMENT = [
    "10004001",  # BAN01 - Bañadora
    "10004002",  # BUF01 - Buffer
    "10004003",  # ENV01 - Envasadora
    "10004004",  # INY01 - Inyectora-Formadora
    "10004005",  # TDF01 - Túnel de frío
    "10004006",  # RPL01 - Robot paletizador
]


class AnalysisBase:
    """
    Clase base para todos los módulos de análisis de MantOS.
    Gestiona la conexión a SQLite y expone helpers de consulta y fecha.
    """

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = Path(db_path) if db_path else DEFAULT_DB
        if not self.db_path.exists():
            raise FileNotFoundError(
                f"Base de datos no encontrada: {self.db_path}\n"
                "Ejecuta primero: python ingestion/ingest.py"
            )
        self._conn: Optional[sqlite3.Connection] = None

    # ------------------------------------------------------------------
    # Gestión de conexión
    # ------------------------------------------------------------------

    @property
    def conn(self) -> sqlite3.Connection:
        """Conexión lazy a SQLite (se abre al primer uso)."""
        if self._conn is None:
            self._conn = sqlite3.connect(str(self.db_path))
            self._conn.row_factory = sqlite3.Row
            # Optimizaciones de lectura
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA synchronous=NORMAL")
        return self._conn

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    # ------------------------------------------------------------------
    # Helpers de consulta
    # ------------------------------------------------------------------

    def query(self, sql: str, params: tuple = ()) -> pd.DataFrame:
        """Ejecuta una consulta SQL y retorna un DataFrame de pandas."""
        return pd.read_sql_query(sql, self.conn, params=params)

    def scalar(self, sql: str, params: tuple = ()) -> any:
        """Ejecuta una consulta y retorna el primer valor escalar."""
        cur = self.conn.execute(sql, params)
        row = cur.fetchone()
        return row[0] if row else None

    # ------------------------------------------------------------------
    # Helpers de fecha
    # ------------------------------------------------------------------

    @staticmethod
    def iso_to_dt(iso_str: str) -> datetime:
        """Convierte un string ISO 8601 UTC a datetime aware."""
        return datetime.fromisoformat(iso_str.replace("Z", "+00:00"))

    @staticmethod
    def dt_to_iso(dt: datetime) -> str:
        """Convierte un datetime a string ISO 8601 UTC."""
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")

    @staticmethod
    def days_between(start_iso: str, end_iso: str) -> float:
        """Calcula los días entre dos timestamps ISO 8601."""
        t0 = AnalysisBase.iso_to_dt(start_iso)
        t1 = AnalysisBase.iso_to_dt(end_iso)
        return (t1 - t0).total_seconds() / 86400.0

    @staticmethod
    def clamp_dates(start: Optional[str], end: Optional[str]) -> Tuple[str, str]:
        """
        Retorna el rango de fechas, usando los extremos del dataset si no se
        especifican. Valida que start <= end.
        """
        s = start or DATA_START
        e = end   or DATA_END
        if AnalysisBase.iso_to_dt(s) > AnalysisBase.iso_to_dt(e):
            raise ValueError(f"start_date ({s}) debe ser <= end_date ({e})")
        return s, e

    # ------------------------------------------------------------------
    # Helpers de validación
    # ------------------------------------------------------------------

    def equipment_exists(self, equnr: str) -> bool:
        """Verifica que el equipo existe en maintenance_orders."""
        count = self.scalar(
            "SELECT COUNT(*) FROM maintenance_orders WHERE equnr = ?", (equnr,)
        )
        return (count or 0) > 0

    def get_all_equipment(self) -> List[str]:
        """Retorna la lista de todos los equnr con eventos registrados."""
        df = self.query("SELECT DISTINCT equnr FROM maintenance_orders ORDER BY equnr")
        return df["equnr"].tolist()

    def get_all_lineas(self) -> List[str]:
        """Retorna la lista de todas las líneas de producción con datos."""
        df = self.query(
            "SELECT DISTINCT linea FROM equipment WHERE linea IS NOT NULL ORDER BY linea"
        )
        return df["linea"].tolist()

    # ------------------------------------------------------------------
    # Helpers de filtrado estándar
    # ------------------------------------------------------------------

    def build_filter_clause(
        self,
        equnr: Optional[str] = None,
        linea: Optional[str] = None,
        auart: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date:   Optional[str] = None,
        exclude_ghost_stops: bool = False,
    ) -> Tuple[str, list]:
        """
        Construye una cláusula WHERE parametrizada para filtros comunes.

        Returns:
            (where_clause: str, params: list)
        """
        clauses = ["1=1"]
        params  = []

        if equnr:
            clauses.append("mo.equnr = ?")
            params.append(equnr)

        if linea:
            clauses.append("e.linea = ?")
            params.append(linea)

        if auart:
            clauses.append("mo.auart = ?")
            params.append(auart)

        if start_date:
            clauses.append("mo.start_datetime >= ?")
            params.append(start_date)

        if end_date:
            clauses.append("mo.start_datetime <= ?")
            params.append(end_date)

        if exclude_ghost_stops:
            clauses.append("mo.is_ghost_stop = 0")

        return " AND ".join(clauses), params
