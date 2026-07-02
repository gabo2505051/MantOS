"""
ingest.py
---------
Script principal de ingesta de datos SAP PM para MantOS.

Lee sap_raw_export.csv (fuente primaria), calcula columnas derivadas,
normaliza timestamps y carga todo en la base de datos SQLite mantos.db.

Uso:
    python ingestion/ingest.py
    python ingestion/ingest.py --db data/mantos.db
    python ingestion/ingest.py --csv ../sap_raw_export.csv --db data/mantos.db
"""

import argparse
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

# Importar el cargador de tablas de referencia
# (permite ejecutar el script desde cualquier directorio)
_SCRIPT_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _SCRIPT_DIR.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from ingestion.catalog_loader import load_reference_tables  # noqa: E402


# ==============================================================
# Rutas por defecto
# ==============================================================
DEFAULT_CSV = _PROJECT_ROOT.parent / "sap_raw_export.csv"
DEFAULT_DB  = _PROJECT_ROOT / "data" / "mantos.db"
SCHEMA_SQL  = _SCRIPT_DIR / "schema.sql"


# ==============================================================
# Utilidades
# ==============================================================

def _now_utc() -> str:
    """Retorna el timestamp actual en ISO 8601 UTC."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _normalize_ts(ts_series: pd.Series) -> pd.Series:
    """
    Normaliza una columna de timestamps al formato ISO 8601 UTC.
    Acepta formatos como '2024-04-01T08:36:00Z' o '2024-04-01T08:36:00'.
    Devuelve strings ISO 8601 o None si el valor es inválido.
    """
    parsed = pd.to_datetime(ts_series, errors="coerce", utc=True)
    # Convertir a string ISO sin microsegundos
    return parsed.dt.strftime("%Y-%m-%dT%H:%M:%SZ").where(parsed.notna(), other=None)


def _compute_duration_min(start: pd.Series, end: pd.Series) -> pd.Series:
    """
    Calcula la duración en minutos entre dos columnas de timestamps.
    Retorna NaN si alguno es inválido o la duración es negativa.
    """
    t_start = pd.to_datetime(start, errors="coerce", utc=True)
    t_end   = pd.to_datetime(end,   errors="coerce", utc=True)
    delta = (t_end - t_start).dt.total_seconds() / 60.0
    # Duración negativa → marcamos como NaN (dato sucio)
    delta = delta.where(delta >= 0, other=float("nan"))
    return delta


def _is_ghost_stop(start: pd.Series, end: pd.Series) -> pd.Series:
    """
    Detecta 'paros fantasma': registros donde start_datetime == end_datetime.
    Retorna una serie de 0/1 (int).
    """
    t_start = pd.to_datetime(start, errors="coerce", utc=True)
    t_end   = pd.to_datetime(end,   errors="coerce", utc=True)
    return (t_start == t_end).astype(int)


# ==============================================================
# Paso 1: Leer y transformar el CSV
# ==============================================================

def load_data(file_path: Path) -> pd.DataFrame:
    """
    Lee el archivo (CSV o Excel) de export SAP PM y retorna un DataFrame limpio con
    columnas renombradas y tipadas según el schema de MantOS.

    Columnas originales esperadas:
        AUFNR, QMNUM, GSTRP, GLTRP, TPLNR, EQUNR, QMTXT, LTXTAUFK, AUART, ARBPL, ERNAM
    """
    print(f"[MantOS Ingestion] Leyendo {file_path.name}...")

    ext = file_path.suffix.lower()
    
    if ext == '.csv':
        # Intentar detectar encoding
        try:
            import chardet
            with open(file_path, 'rb') as f:
                encoding = chardet.detect(f.read(10000)).get('encoding', 'utf-8')
        except ImportError:
            encoding = 'utf-8'
        
        try:
            df = pd.read_csv(file_path, dtype=str, encoding=encoding, on_bad_lines="warn")
        except UnicodeDecodeError:
            print(f"[MantOS Ingestion] Fallo con encoding {encoding}, reintentando con latin-1")
            df = pd.read_csv(file_path, dtype=str, encoding='latin-1', on_bad_lines="warn")
        ingestion_src = "csv"
    elif ext in ['.xls', '.xlsx']:
        engine = 'openpyxl' if ext == '.xlsx' else 'xlrd'
        df = pd.read_excel(file_path, engine=engine, dtype=str)
        ingestion_src = "excel"
    else:
        raise ValueError("Formato no soportado. Use .csv, .xls o .xlsx")

    print(f"[MantOS Ingestion] {len(df):,} filas leídas del archivo.")

    # Renombrar columnas a nombres del schema interno.
    # [CAMBIOS AQUI]: Si en el futuro SAP cambia los nombres de las columnas en el reporte,
    # actualiza las llaves (lado izquierdo) de este diccionario con el nuevo nombre.
    df = df.rename(columns={
        "AUFNR":    "aufnr",
        "QMNUM":    "qmnum",
        "GSTRP":    "start_raw",
        "GLTRP":    "end_raw",
        "TPLNR":    "tplnr",
        "EQUNR":    "equnr",
        "QMTXT":    "qmtxt",
        "LTXTAUFK": "ltxtaufk",
        "AUART":    "auart",
        "ARBPL":    "arbpl",
        "ERNAM":    "ernam",
    })

    # Normalizar timestamps
    df["start_datetime"] = _normalize_ts(df["start_raw"])
    df["end_datetime"]   = _normalize_ts(df["end_raw"])

    # Columnas derivadas
    df["duration_min"]  = _compute_duration_min(df["start_raw"], df["end_raw"])
    df["is_ghost_stop"] = _is_ghost_stop(df["start_raw"], df["end_raw"])

    # Metadatos de ingesta
    df["ingestion_src"] = ingestion_src
    df["ingested_at"]   = _now_utc()

    # Limpiar columnas intermedias
    df = df.drop(columns=["start_raw", "end_raw"])

    # Estadísticas de calidad de datos
    ghost_count  = df["is_ghost_stop"].sum()
    ghost_pct    = ghost_count / len(df) * 100
    null_start   = df["start_datetime"].isna().sum()
    null_dur     = df["duration_min"].isna().sum()

    print(f"[MantOS Ingestion] Ghost stops detectados : {ghost_count:,} ({ghost_pct:.1f}%)")
    if null_start > 0:
        print(f"[MantOS Ingestion] WARN Timestamps inicio invalidos: {null_start}")
    if null_dur > 0:
        print(f"[MantOS Ingestion] WARN Duraciones no calculables  : {null_dur}")

    return df


# ==============================================================
# Paso 2: Inicializar la base de datos
# ==============================================================

def init_db(db_path: Path) -> sqlite3.Connection:
    """
    Crea (o abre) la base de datos SQLite y aplica el schema DDL.
    """
    db_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"[MantOS Ingestion] Abriendo DB: {db_path}")
    conn = sqlite3.connect(str(db_path))

    # Aplicar schema
    schema_sql = SCHEMA_SQL.read_text(encoding="utf-8")
    conn.executescript(schema_sql)
    conn.commit()

    return conn


# ==============================================================
# Paso 3: Insertar órdenes de mantenimiento
# ==============================================================

def insert_orders(conn: sqlite3.Connection, df: pd.DataFrame) -> int:
    """
    Inserta las filas del DataFrame en la tabla maintenance_orders.
    Usa INSERT OR IGNORE para no duplicar por AUFNR si se re-ejecuta.

    Retorna el número de filas efectivamente insertadas.
    """
    COLUMNS = [
        "aufnr", "qmnum", "start_datetime", "end_datetime",
        "duration_min", "is_ghost_stop", "tplnr", "equnr",
        "qmtxt", "ltxtaufk", "auart", "arbpl", "ernam",
        "ingestion_src", "ingested_at",
    ]

    # Seleccionar y ordenar columnas para la inserción
    df_insert = df[COLUMNS].copy()

    # Reemplazar NaN de pandas por None (→ NULL en SQLite)
    df_insert = df_insert.where(pd.notna(df_insert), other=None)

    rows = list(df_insert.itertuples(index=False, name=None))

    placeholders = ", ".join(["?"] * len(COLUMNS))
    col_names    = ", ".join(COLUMNS)
    sql = f"INSERT OR REPLACE INTO maintenance_orders ({col_names}) VALUES ({placeholders})"

    cursor = conn.cursor()
    cursor.executemany(sql, rows)
    conn.commit()

    inserted = cursor.rowcount
    # cursor.rowcount con executemany puede ser -1 en algunos drivers;
    # usamos un COUNT para obtener el total real.
    total = cursor.execute("SELECT COUNT(*) FROM maintenance_orders").fetchone()[0]
    return total


# ==============================================================
# Paso 4: Resumen final
# ==============================================================

def print_summary(conn: sqlite3.Connection, db_path: Path) -> None:
    """Imprime un resumen de la base de datos post-ingesta."""
    cur = conn.cursor()

    total = cur.execute("SELECT COUNT(*) FROM maintenance_orders").fetchone()[0]
    by_type = cur.execute(
        "SELECT auart, COUNT(*) FROM maintenance_orders GROUP BY auart ORDER BY auart"
    ).fetchall()
    ghost = cur.execute(
        "SELECT COUNT(*) FROM maintenance_orders WHERE is_ghost_stop = 1"
    ).fetchone()[0]
    avg_dur = cur.execute(
        "SELECT ROUND(AVG(duration_min), 2) FROM maintenance_orders WHERE duration_min > 0"
    ).fetchone()[0]
    db_size_kb = db_path.stat().st_size / 1024

    print()
    print("=" * 55)
    print("  MantOS -- Ingesta completada OK")
    print("=" * 55)
    print(f"  DB            : {db_path}")
    print(f"  Tamaño        : {db_size_kb:.1f} KB")
    print(f"  Total órdenes : {total:,}")
    print(f"  Ghost stops   : {ghost:,} ({ghost/total*100:.1f}%)")
    print(f"  Duración media: {avg_dur} min (excl. fantasmas)")
    print()
    print("  Desglose por tipo:")
    for auart, count in by_type:
        pct = count / total * 100
        print(f"    {auart}: {count:>5,} ({pct:.1f}%)")
    print("=" * 55)


# ==============================================================
# Entrypoint principal
# ==============================================================

def main() -> None:
    parser = argparse.ArgumentParser(
        description="MantOS — Ingesta de datos SAP PM a SQLite"
    )
    parser.add_argument(
        "--file",
        type=Path,
        default=DEFAULT_CSV,
        help=f"Ruta al archivo de export SAP (CSV/XLS/XLSX) (default: {DEFAULT_CSV})",
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=DEFAULT_DB,
        help=f"Ruta a la base de datos SQLite de destino (default: {DEFAULT_DB})",
    )
    args = parser.parse_args()

    # Validar que el archivo existe
    if not args.file.exists():
        print(f"[MantOS Ingestion] ERROR Archivo no encontrado: {args.file}")
        sys.exit(1)

    print()
    print("=" * 55)
    print("  MantOS -- Ingesta de Datos SAP PM -> SQLite")
    print("=" * 55)

    # Paso 1: Leer Archivo
    df = load_data(args.file)

    # Paso 2: Inicializar DB
    conn = init_db(args.db)

    try:
        # Paso 3: Cargar tablas de referencia
        print("[MantOS Ingestion] Cargando tablas de referencia...")
        load_reference_tables(conn)

        # Paso 4: Insertar órdenes
        print("[MantOS Ingestion] Insertando órdenes de mantenimiento...")
        total = insert_orders(conn, df)
        print(f"[MantOS Ingestion] {total:,} filas en maintenance_orders.")

        # Paso 5: Resumen
        print_summary(conn, args.db)

    finally:
        conn.close()


if __name__ == "__main__":
    main()
