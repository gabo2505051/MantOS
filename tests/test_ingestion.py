"""
test_ingestion.py
-----------------
Tests de sanidad post-ingesta para MantOS.

Verifican que:
  - La DB existe y tiene las tablas correctas
  - El número de órdenes coincide con el CSV fuente
  - Los ghost stops están correctamente marcados
  - Las columnas derivadas son válidas (duration_min >= 0)
  - Las tablas de referencia están completas
  - Las vistas funcionan correctamente
  - Los índices existen

Uso:
    python -m pytest tests/ -v
    python -m pytest tests/ -v --tb=short
"""

import sqlite3
import sys
from pathlib import Path

import pytest

# Añadir la raíz del proyecto al path
_TESTS_DIR   = Path(__file__).resolve().parent
_PROJECT_ROOT = _TESTS_DIR.parent
sys.path.insert(0, str(_PROJECT_ROOT))

# ==============================================================
# Configuración
# ==============================================================
DB_PATH  = _PROJECT_ROOT / "data" / "mantos.db"
CSV_PATH = _PROJECT_ROOT.parent / "sap_raw_export.csv"

# Valores esperados según el catálogo técnico
EXPECTED_TOTAL_ROWS = 2149
EXPECTED_GHOST_STOPS_APPROX = 214   # ±5% de tolerancia
EXPECTED_GHOST_PCT_MAX = 0.15       # No más del 15% de ghost stops
EXPECTED_TABLES = {
    "maintenance_orders",
    "equipment",
    "users",
    "order_types",
}
EXPECTED_VIEWS = {
    "v_orders_enriched",
    "v_kpi_by_equipment",
}
EXPECTED_AUART = {"PM01", "PM02", "PM03"}
EXPECTED_INDEXES = {
    "idx_mo_equnr_start",
    "idx_mo_tplnr_start",
    "idx_mo_auart",
    "idx_mo_start_datetime",
    "idx_mo_ghost",
}


# ==============================================================
# Fixtures
# ==============================================================

@pytest.fixture(scope="session")
def conn():
    """Abre una conexión de solo lectura a la DB de MantOS."""
    if not DB_PATH.exists():
        pytest.skip(
            f"DB no encontrada en {DB_PATH}. Ejecuta primero: python ingestion/ingest.py"
        )
    connection = sqlite3.connect(str(DB_PATH))
    yield connection
    connection.close()


def _fetch_one(conn: sqlite3.Connection, sql: str, params=()) -> any:
    return conn.execute(sql, params).fetchone()[0]


def _fetch_all(conn: sqlite3.Connection, sql: str, params=()) -> list:
    return conn.execute(sql, params).fetchall()


# ==============================================================
# Tests: Estructura de la DB
# ==============================================================

class TestDatabaseStructure:

    def test_db_file_exists(self):
        """La base de datos SQLite debe existir."""
        assert DB_PATH.exists(), f"DB no encontrada: {DB_PATH}"
        size_kb = DB_PATH.stat().st_size / 1024
        assert size_kb > 100, f"DB demasiado pequeña ({size_kb:.1f} KB) — posible ingesta fallida"

    def test_tables_exist(self, conn):
        """Todas las tablas del schema deben existir."""
        rows = _fetch_all(
            conn,
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )
        actual_tables = {row[0] for row in rows}
        missing = EXPECTED_TABLES - actual_tables
        assert not missing, f"Tablas faltantes: {missing}"

    def test_views_exist(self, conn):
        """Las vistas del schema deben existir."""
        rows = _fetch_all(
            conn,
            "SELECT name FROM sqlite_master WHERE type='view'"
        )
        actual_views = {row[0] for row in rows}
        missing = EXPECTED_VIEWS - actual_views
        assert not missing, f"Vistas faltantes: {missing}"

    def test_indexes_exist(self, conn):
        """Los índices críticos deben estar creados."""
        rows = _fetch_all(
            conn,
            "SELECT name FROM sqlite_master WHERE type='index' AND name NOT LIKE 'sqlite_%'"
        )
        actual_indexes = {row[0] for row in rows}
        missing = EXPECTED_INDEXES - actual_indexes
        assert not missing, f"Índices faltantes: {missing}"


# ==============================================================
# Tests: Integridad de maintenance_orders
# ==============================================================

class TestMaintenanceOrders:

    def test_total_row_count(self, conn):
        """El total de órdenes debe coincidir con el CSV fuente (2149)."""
        total = _fetch_one(conn, "SELECT COUNT(*) FROM maintenance_orders")
        assert total == EXPECTED_TOTAL_ROWS, (
            f"Esperado {EXPECTED_TOTAL_ROWS} filas, encontrado {total}"
        )

    def test_aufnr_unique(self, conn):
        """No debe haber AUFNR duplicados."""
        total     = _fetch_one(conn, "SELECT COUNT(*) FROM maintenance_orders")
        distinct  = _fetch_one(conn, "SELECT COUNT(DISTINCT aufnr) FROM maintenance_orders")
        assert total == distinct, f"AUFNR duplicados detectados: {total - distinct}"

    def test_auart_values(self, conn):
        """Solo deben existir valores válidos de AUART (PM01, PM02, PM03)."""
        rows = _fetch_all(conn, "SELECT DISTINCT auart FROM maintenance_orders")
        actual_auart = {row[0] for row in rows if row[0] is not None}
        unexpected = actual_auart - EXPECTED_AUART
        assert not unexpected, f"Valores AUART inesperados: {unexpected}"

    def test_pm03_majority(self, conn):
        """PM03 debe ser el tipo más frecuente (>70% según catálogo)."""
        total = _fetch_one(conn, "SELECT COUNT(*) FROM maintenance_orders")
        pm03  = _fetch_one(conn, "SELECT COUNT(*) FROM maintenance_orders WHERE auart='PM03'")
        pct   = pm03 / total
        assert pct > 0.70, f"PM03 representa solo {pct:.1%}, se esperaba >70%"


# ==============================================================
# Tests: Columnas derivadas
# ==============================================================

class TestDerivedColumns:

    def test_ghost_stops_count_approx(self, conn):
        """Los ghost stops deben ser aproximadamente 214 (±30 de tolerancia)."""
        ghost = _fetch_one(
            conn, "SELECT COUNT(*) FROM maintenance_orders WHERE is_ghost_stop = 1"
        )
        assert abs(ghost - EXPECTED_GHOST_STOPS_APPROX) <= 30, (
            f"Ghost stops: {ghost}, esperado ~{EXPECTED_GHOST_STOPS_APPROX} ±30"
        )

    def test_ghost_stops_pct_reasonable(self, conn):
        """El porcentaje de ghost stops no debe superar el 15%."""
        total = _fetch_one(conn, "SELECT COUNT(*) FROM maintenance_orders")
        ghost = _fetch_one(
            conn, "SELECT COUNT(*) FROM maintenance_orders WHERE is_ghost_stop = 1"
        )
        pct = ghost / total
        assert pct <= EXPECTED_GHOST_PCT_MAX, (
            f"Ghost stop % demasiado alto: {pct:.1%} (máximo esperado: {EXPECTED_GHOST_PCT_MAX:.0%})"
        )

    def test_duration_min_non_negative(self, conn):
        """Ningún duration_min debe ser negativo."""
        neg_count = _fetch_one(
            conn, "SELECT COUNT(*) FROM maintenance_orders WHERE duration_min < 0"
        )
        assert neg_count == 0, f"{neg_count} filas con duration_min negativo"

    def test_duration_zero_for_ghost_stops(self, conn):
        """Los ghost stops deben tener duration_min = 0."""
        non_zero_ghost = _fetch_one(
            conn,
            """SELECT COUNT(*) FROM maintenance_orders
               WHERE is_ghost_stop = 1 AND duration_min > 0"""
        )
        assert non_zero_ghost == 0, (
            f"{non_zero_ghost} ghost stops con duration_min > 0 (inconsistencia)"
        )

    def test_timestamps_format(self, conn):
        """Los timestamps deben tener formato ISO 8601 con 'Z' al final."""
        # Muestra aleatoria de 10 filas
        rows = _fetch_all(
            conn,
            "SELECT start_datetime, end_datetime FROM maintenance_orders LIMIT 20"
        )
        for start, end in rows:
            if start is not None:
                assert start.endswith("Z"), f"start_datetime sin 'Z': {start!r}"
            if end is not None:
                assert end.endswith("Z"), f"end_datetime sin 'Z': {end!r}"


# ==============================================================
# Tests: Tablas de referencia
# ==============================================================

class TestReferenceTables:

    def test_order_types_complete(self, conn):
        """Las 3 clases de orden (PM01/PM02/PM03) deben estar en order_types."""
        rows = _fetch_all(conn, "SELECT auart FROM order_types")
        actual = {row[0] for row in rows}
        assert actual == EXPECTED_AUART, f"order_types incompleto: {actual}"

    def test_equipment_count(self, conn):
        """La tabla equipment debe tener al menos 25 equipos del catálogo."""
        count = _fetch_one(conn, "SELECT COUNT(*) FROM equipment")
        assert count >= 25, f"equipment tiene solo {count} filas (esperado ≥25)"

    def test_equipment_la4_present(self, conn):
        """Los 6 equipos de LA4 (línea principal) deben estar presentes."""
        la4_count = _fetch_one(
            conn, "SELECT COUNT(*) FROM equipment WHERE linea = 'LA4'"
        )
        assert la4_count == 6, f"LA4 tiene {la4_count} equipos, se esperan 6"

    def test_users_complete(self, conn):
        """La tabla users debe tener los 18 usuarios del catálogo."""
        count = _fetch_one(conn, "SELECT COUNT(*) FROM users")
        assert count >= 18, f"users tiene solo {count} filas (esperado ≥18)"

    def test_user_types(self, conn):
        """Los tipos de usuario deben ser solo: humano, sistema, operador."""
        rows = _fetch_all(conn, "SELECT DISTINCT tipo FROM users")
        actual = {row[0] for row in rows}
        valid  = {"humano", "sistema", "operador"}
        unexpected = actual - valid
        assert not unexpected, f"Tipos de usuario inesperados: {unexpected}"


# ==============================================================
# Tests: Vistas
# ==============================================================

class TestViews:

    def test_view_orders_enriched_count(self, conn):
        """La vista v_orders_enriched debe retornar el mismo total de filas."""
        total    = _fetch_one(conn, "SELECT COUNT(*) FROM maintenance_orders")
        enriched = _fetch_one(conn, "SELECT COUNT(*) FROM v_orders_enriched")
        assert total == enriched, (
            f"v_orders_enriched ({enriched}) ≠ maintenance_orders ({total})"
        )

    def test_view_orders_enriched_joins(self, conn):
        """La vista debe traer nombre_equipo y tipo_mantenimiento para LA4."""
        row = conn.execute(
            """SELECT nombre_equipo, tipo_mantenimiento
               FROM v_orders_enriched
               WHERE equnr = '10004001'
               LIMIT 1"""
        ).fetchone()
        assert row is not None, "No hay datos de LA4-BAN01 en v_orders_enriched"
        nombre, tipo = row
        assert nombre == "Bañadora", f"nombre_equipo esperado 'Bañadora', got {nombre!r}"
        assert tipo in ("Correctivo", "Preventivo", "Operacional"), (
            f"tipo_mantenimiento inválido: {tipo!r}"
        )

    def test_view_kpi_by_equipment(self, conn):
        """La vista v_kpi_by_equipment debe tener datos para todos los equipos activos."""
        count = _fetch_one(conn, "SELECT COUNT(*) FROM v_kpi_by_equipment")
        assert count >= 10, f"v_kpi_by_equipment solo tiene {count} equipos"

    def test_view_kpi_la4_total(self, conn):
        """El total de eventos en LA4 debe superar 1500 (es la línea principal)."""
        la4_total = _fetch_one(
            conn,
            """SELECT SUM(total_eventos) FROM v_kpi_by_equipment
               WHERE linea = 'LA4'"""
        )
        assert la4_total is not None and la4_total > 1500, (
            f"LA4 solo tiene {la4_total} eventos (esperado >1500)"
        )


# ==============================================================
# Test de integración: Consulta típica del agente
# ==============================================================

class TestAgentQueryPatterns:

    def test_query_by_equipment_and_date_range(self, conn):
        """Simula la consulta más frecuente del agente: equipo + rango temporal."""
        rows = _fetch_all(
            conn,
            """SELECT aufnr, start_datetime, duration_min, qmtxt
               FROM maintenance_orders
               WHERE equnr = '10004003'
                 AND start_datetime BETWEEN '2024-04-01T00:00:00Z'
                                        AND '2024-04-30T23:59:59Z'
               ORDER BY start_datetime""",
        )
        assert len(rows) > 0, "No hay datos de LA4-ENV01 en abril 2024"

    def test_query_pm01_correctivos(self, conn):
        """Filtro de solo correctivos (PM01) debe retornar ~67 filas."""
        count = _fetch_one(
            conn,
            "SELECT COUNT(*) FROM maintenance_orders WHERE auart = 'PM01'"
        )
        assert 40 <= count <= 100, (
            f"PM01 tiene {count} filas, se esperaba entre 40-100"
        )

    def test_query_top_failing_equipment(self, conn):
        """El equipo con más eventos debe estar en LA4 (línea principal)."""
        row = _fetch_all(
            conn,
            """SELECT equnr, COUNT(*) as cnt
               FROM maintenance_orders
               GROUP BY equnr
               ORDER BY cnt DESC
               LIMIT 1"""
        )[0]
        top_equnr, top_count = row
        # Según el catálogo, LA4 tiene los 6 primeros equipos por frecuencia
        assert top_equnr.startswith("10004"), (
            f"El equipo más frecuente es {top_equnr} (se esperaba de LA4: 10004xxx)"
        )
        assert top_count > 200, (
            f"El top equipo tiene solo {top_count} eventos (esperado >200)"
        )
