-- ==============================================================
-- MantOS — Schema SQLite
-- Planta Galletera Sur (PGS) — SAP Plant Maintenance Data
-- ==============================================================

PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;
PRAGMA foreign_keys = ON;

-- --------------------------------------------------------------
-- Tabla de referencia: Tipos de orden (PM01/PM02/PM03)
-- --------------------------------------------------------------
CREATE TABLE IF NOT EXISTS order_types (
    auart       TEXT PRIMARY KEY,
    nombre      TEXT NOT NULL,
    descripcion TEXT
);

-- --------------------------------------------------------------
-- Tabla de referencia: Equipos y ubicaciones técnicas
-- --------------------------------------------------------------
CREATE TABLE IF NOT EXISTS equipment (
    equnr           TEXT PRIMARY KEY,   -- ID equipo: 1000xxxx
    tplnr           TEXT NOT NULL,      -- Ubicación técnica: PGS-PR-LAx-YYYnn
    linea           TEXT NOT NULL,      -- LA1, LA2, LA3, LA4, LA5, LAX
    nombre_equipo   TEXT NOT NULL,
    descripcion     TEXT
);

-- --------------------------------------------------------------
-- Tabla de referencia: Usuarios del sistema
-- --------------------------------------------------------------
CREATE TABLE IF NOT EXISTS users (
    ernam       TEXT PRIMARY KEY,
    tipo        TEXT NOT NULL,          -- 'humano', 'sistema', 'operador'
    descripcion TEXT
);

-- --------------------------------------------------------------
-- Tabla principal: Órdenes de mantenimiento
-- --------------------------------------------------------------
CREATE TABLE IF NOT EXISTS maintenance_orders (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    aufnr           TEXT NOT NULL UNIQUE,   -- Nro OT SAP (AUFK.AUFNR)
    qmnum           TEXT,                   -- Nro aviso (QMIH.QMNUM)
    start_datetime  TEXT NOT NULL,          -- ISO 8601 UTC (AUFK.GSTRP)
    end_datetime    TEXT,                   -- ISO 8601 UTC (AUFK.GLTRP)
    duration_min    REAL CHECK (duration_min >= 0), -- Calculado: (end - start) en minutos
    is_ghost_stop   INTEGER NOT NULL DEFAULT 0 CHECK (is_ghost_stop IN (0, 1)), -- 1 si start == end
    tplnr           TEXT,                   -- Ubicación técnica (ILOA.TPLNR)
    equnr           TEXT,                   -- ID equipo (EQUI.EQUNR)
    qmtxt           TEXT,                   -- Título falla corto (QMEL.QMTXT)
    ltxtaufk        TEXT,                   -- Texto largo orden (AUFK.LTXT)
    auart           TEXT NOT NULL,          -- Clase orden: PM01/PM02/PM03
    arbpl           TEXT,                   -- Centro de trabajo (CRHD.ARBPL)
    ernam           TEXT,                   -- Usuario creador (AUFK.ERNAM)
    ingestion_src   TEXT DEFAULT 'csv' NOT NULL, -- Fuente de ingesta: 'csv' | 'json' | 'excel'
    ingested_at     TEXT NOT NULL,          -- Timestamp UTC de cuando se ingestó
    created_at      TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at      TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (equnr) REFERENCES equipment(equnr) ON DELETE SET NULL,
    FOREIGN KEY (auart) REFERENCES order_types(auart) ON DELETE CASCADE,
    FOREIGN KEY (ernam) REFERENCES users(ernam) ON DELETE SET NULL
);

-- Trigger to update updated_at timestamp
CREATE TRIGGER IF NOT EXISTS trg_maintenance_orders_updated_at
AFTER UPDATE ON maintenance_orders
FOR EACH ROW
BEGIN
    UPDATE maintenance_orders SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
END;

-- --------------------------------------------------------------
-- Índices para optimizar consultas del agente
-- --------------------------------------------------------------

-- Consultas por equipo + rango temporal (caso más frecuente)
CREATE INDEX IF NOT EXISTS idx_mo_equnr_start
    ON maintenance_orders (equnr, start_datetime);

-- Consultas por ubicación técnica + rango temporal
CREATE INDEX IF NOT EXISTS idx_mo_tplnr_start
    ON maintenance_orders (tplnr, start_datetime);

-- Filtros por tipo de orden (PM01/PM02/PM03)
CREATE INDEX IF NOT EXISTS idx_mo_auart
    ON maintenance_orders (auart);

-- Ordenamiento / filtros temporales puros
CREATE INDEX IF NOT EXISTS idx_mo_start_datetime
    ON maintenance_orders (start_datetime);

-- Filtro rápido de paros fantasma
CREATE INDEX IF NOT EXISTS idx_mo_ghost
    ON maintenance_orders (is_ghost_stop)
    WHERE is_ghost_stop = 1;

-- ==============================================================
-- Vistas útiles para el agente (no almacenan datos adicionales)
-- ==============================================================

-- Vista: órdenes enriquecidas con info de equipo
CREATE VIEW IF NOT EXISTS v_orders_enriched AS
SELECT
    mo.aufnr,
    mo.qmnum,
    mo.start_datetime,
    mo.end_datetime,
    mo.duration_min,
    mo.is_ghost_stop,
    mo.tplnr,
    e.linea,
    e.nombre_equipo,
    mo.equnr,
    mo.qmtxt,
    mo.ltxtaufk,
    mo.auart,
    ot.nombre            AS tipo_mantenimiento,
    mo.arbpl,
    mo.ernam,
    u.tipo               AS tipo_usuario
FROM maintenance_orders mo
LEFT JOIN equipment   e  ON mo.equnr = e.equnr
LEFT JOIN order_types ot ON mo.auart = ot.auart
LEFT JOIN users       u  ON mo.ernam = u.ernam;

-- Vista: KPIs por equipo (útil para análisis rápido)
CREATE VIEW IF NOT EXISTS v_kpi_by_equipment AS
SELECT
    mo.equnr,
    e.nombre_equipo,
    e.linea,
    COUNT(*)                                                AS total_eventos,
    SUM(CASE WHEN mo.auart = 'PM01' THEN 1 ELSE 0 END)    AS correctivos,
    SUM(CASE WHEN mo.auart = 'PM02' THEN 1 ELSE 0 END)    AS preventivos,
    SUM(CASE WHEN mo.auart = 'PM03' THEN 1 ELSE 0 END)    AS operacionales,
    SUM(CASE WHEN mo.is_ghost_stop = 1 THEN 1 ELSE 0 END) AS paros_fantasma,
    ROUND(AVG(CASE WHEN mo.duration_min > 0 THEN mo.duration_min END), 2) AS avg_duration_min,
    ROUND(SUM(CASE WHEN mo.duration_min > 0 THEN mo.duration_min ELSE 0 END), 2) AS total_downtime_min
FROM maintenance_orders mo
LEFT JOIN equipment e ON mo.equnr = e.equnr
GROUP BY mo.equnr;
