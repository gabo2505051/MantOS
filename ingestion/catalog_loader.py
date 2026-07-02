"""
catalog_loader.py
-----------------
Carga las tablas de referencia del catálogo técnico de la Planta Galletera Sur
en la base de datos SQLite de MantOS.

Fuente: catalogo_tecnico_planta.md (codificado aquí como constantes para
        no depender del archivo markdown en runtime).
"""

import sqlite3
from typing import List, Tuple


# ==============================================================
# Tipos de Orden (AUART)
# ==============================================================
ORDER_TYPES: List[Tuple[str, str, str]] = [
    ("PM01", "Correctivo",   "Fallas no planificadas que requieren intervención inmediata"),
    ("PM02", "Preventivo",   "Mantenimiento programado: inspecciones, cambios, calibraciones"),
    ("PM03", "Operacional",  "Micro-paros, atascos, reinicios resueltos por operador o sistema"),
]

# ==============================================================
# Equipos y Ubicaciones Técnicas (EQUI + ILOA)
# Fuente: sección 2 del catálogo técnico
# ==============================================================
EQUIPMENT: List[Tuple[str, str, str, str, str]] = [
    # (equnr, tplnr, linea, nombre_equipo, descripcion)
    ("10001001", "PGS-PR-LA1-HRN01", "LA1", "Horno",                   "Línea 1 - Galletas soda"),
    ("10001002", "PGS-PR-LA1-SFR01", "LA1", "Sala de fermentado",      "Línea 1 - Galletas soda"),
    ("10001003", "PGS-PR-LA1-LAM01", "LA1", "Laminador - Cortador",    "Línea 1 - Galletas soda"),
    ("10001004", "PGS-PR-LA1-MES01", "LA1", "Mesa de trabajo",         "Línea 1 - Galletas soda"),
    ("10002001", "PGS-PR-LA2-HRL01", "LA2", "Horno tipo Libro",        "Línea 2 - Galleta tipo oblea"),
    ("10002002", "PGS-PR-LA2-CRM01", "LA2", "Cremadora",               "Línea 2 - Galleta tipo oblea"),
    ("10002003", "PGS-PR-LA2-CRT01", "LA2", "Cortadora",               "Línea 2 - Galleta tipo oblea"),
    ("10002004", "PGS-PR-LA2-CKC01", "LA2", "Cookie Capper",           "Línea 2 - Galleta tipo oblea"),
    ("10002005", "PGS-PR-LA2-TF101", "LA2", "Túnel de frío N°1",       "Línea 2 - Galleta tipo oblea"),
    ("10002006", "PGS-PR-LA2-TF201", "LA2", "Túnel de frío N°2",       "Línea 2 - Galleta tipo oblea"),
    ("10002007", "PGS-PR-LA2-ARC01", "LA2", "Arcoenfriador",           "Línea 2 - Galleta tipo oblea"),
    ("10003001", "PGS-PR-LA3-EXT01", "LA3", "Extrusores",              "Línea 3"),
    ("10003002", "PGS-PR-LA3-ELB01", "LA3", "Elaboración",             "Línea 3"),
    ("10003003", "PGS-PR-LA3-MZC01", "LA3", "Mezclador 1 - 2",        "Línea 3"),
    ("10004001", "PGS-PR-LA4-BAN01", "LA4", "Bañadora",                "Línea 4 - Alfajores (principal)"),
    ("10004002", "PGS-PR-LA4-BUF01", "LA4", "Buffer",                  "Línea 4 - Alfajores (principal)"),
    ("10004003", "PGS-PR-LA4-ENV01", "LA4", "Envasadora",              "Línea 4 - Alfajores (principal)"),
    ("10004004", "PGS-PR-LA4-INY01", "LA4", "Inyectora - Formadora",   "Línea 4 - Alfajores (principal)"),
    ("10004005", "PGS-PR-LA4-TDF01", "LA4", "Túnel de frío",           "Línea 4 - Alfajores (principal)"),
    ("10004006", "PGS-PR-LA4-RPL01", "LA4", "Robot paletizador",       "Línea 4 - Alfajores (principal)"),
    ("10005001", "PGS-PR-LA5-PRE01", "LA5", "Preparación",             "Línea 5 - Galleta exportada"),
    ("10005002", "PGS-PR-LA5-ENV01", "LA5", "Envasado",                "Línea 5 - Galleta exportada"),
    ("10005003", "PGS-PR-LA5-REM01", "LA5", "Robot empaquetador",      "Línea 5 - Galleta exportada"),
    ("10005004", "PGS-PR-LA5-ELV01", "LA5", "Elevador",                "Línea 5 - Galleta exportada"),
    ("10009001", "PGS-PR-LAX-DST01", "LAX", "Distribuidora",           "Compartido - múltiples líneas"),
    ("10009002", "PGS-PR-LAX-CEN01", "LAX", "Cintas de enfriamiento",  "Compartido - múltiples líneas"),
    ("10009003", "PGS-PR-LA5-AGR01", "LA5", "Agrupado",               "Línea 5 - Galleta exportada"),
]

# ==============================================================
# Usuarios del Sistema (ERNAM)
# Fuente: sección 5 del catálogo técnico
# ==============================================================
USERS: List[Tuple[str, str, str]] = [
    # (ernam, tipo, descripcion)
    # Humanos - Mecánicos
    ("JCASTRO",   "humano",   "Mecánico — PM01, PM02"),
    ("MEC_01",    "humano",   "Mecánico — PM01, PM02"),
    ("MEC_02",    "humano",   "Mecánico — PM01, PM02"),
    ("MEC_03",    "humano",   "Mecánico — PM01, PM02"),
    ("LGOMEZ",    "humano",   "Mecánico — PM01, PM02"),
    ("RPEREZ",    "humano",   "Mecánico — PM01, PM02"),
    ("AMARTINEZ", "humano",   "Mecánico — PM01, PM02"),
    ("FDIAZ",     "humano",   "Mecánico — PM01, PM02"),
    ("MRODRIG",   "humano",   "Mecánico — PM01, PM02"),
    ("PLOPEZ",    "humano",   "Mecánico — PM01, PM02"),
    # Sistemas
    ("SYS_IIOT",  "sistema",  "Sistema IIoT (sensores/PLC) — PM03, PM02"),
    ("BAT_USER",  "sistema",  "Usuario batch/programado — PM03, PM02"),
    ("SYS_SCADA", "sistema",  "Sistema SCADA — PM03"),
    ("RFC_PM",    "sistema",  "Interfaz RFC de SAP PM — PM03, PM02"),
    # Operadores
    ("OPR_T1",    "operador", "Operador Turno 1 — PM03"),
    ("OPR_T2",    "operador", "Operador Turno 2 — PM03"),
    ("OPR_T3",    "operador", "Operador Turno 3 — PM03"),
    ("SUP_LINEA", "operador", "Supervisor de línea — PM03"),
]


def load_reference_tables(conn: sqlite3.Connection) -> None:
    """
    Inserta (o ignora si ya existen) todos los datos de referencia
    en las tablas correspondientes de la DB.

    Args:
        conn: Conexión sqlite3 activa (con transacción abierta o autocommit).
    """
    cursor = conn.cursor()

    # Tipos de orden
    cursor.executemany(
        "INSERT OR IGNORE INTO order_types (auart, nombre, descripcion) VALUES (?, ?, ?)",
        ORDER_TYPES,
    )

    # Equipos
    cursor.executemany(
        """INSERT OR IGNORE INTO equipment
           (equnr, tplnr, linea, nombre_equipo, descripcion)
           VALUES (?, ?, ?, ?, ?)""",
        EQUIPMENT,
    )

    # Usuarios
    cursor.executemany(
        "INSERT OR IGNORE INTO users (ernam, tipo, descripcion) VALUES (?, ?, ?)",
        USERS,
    )

    n_order_types = cursor.execute("SELECT COUNT(*) FROM order_types").fetchone()[0]
    n_equipment   = cursor.execute("SELECT COUNT(*) FROM equipment").fetchone()[0]
    n_users       = cursor.execute("SELECT COUNT(*) FROM users").fetchone()[0]

    print(f"  -> order_types : {n_order_types} filas")
    print(f"  -> equipment   : {n_equipment} filas")
    print(f"  -> users       : {n_users} filas")
