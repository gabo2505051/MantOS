# MantOS 🏭

**Sistema de Análisis de Mantenimiento Industrial — MVP v1.0**

MantOS procesa órdenes de trabajo históricas de SAP PM para detectar patrones de falla, calcular KPIs operacionales (MTTR, MTBF, disponibilidad) y presentar insights accionables al equipo de mantenimiento a través de un dashboard interactivo.

> Desarrollado sobre datos sintéticos que simulan la estructura real de SAP Plant Maintenance (tablas AUFK, QMIH, ILOA, EQUI).

---

## ¿Qué hace MantOS?

| Capacidad | Descripción |
|---|---|
| **Ingesta de datos** | Lee exports SAP PM (CSV/XLS/XLSX) y los normaliza en una base de datos SQLite |
| **KPIs automáticos** | Calcula MTTR, MTBF, disponibilidad y tasa de falla por equipo y línea |
| **Análisis descriptivo** | Distribución de eventos, Pareto de fallas, tendencias temporales |
| **Análisis diagnóstico** | Detección de equipos críticos, análisis de recurrencia, correlaciones |
| **Análisis predictivo** | Proyección de fallas y estimación de próximas intervenciones |
| **Análisis prescriptivo** | Recomendaciones priorizadas de acción por equipo |
| **Reportes exportables** | Generación de reportes ejecutivos y por equipo en PDF y Markdown |
| **Dashboard Streamlit** | Interfaz web interactiva con filtros por línea, equipo y período |

---

## Estructura del Proyecto

```
MantOS/
├── 📄 README.md
├── 📄 requirements.txt
├── 📄 streamlit_app.py          ← Entry point del dashboard web
├── 📄 demo.py                   ← Demo CLI con análisis completo
│
├── 📁 ingestion/                ← Pipeline de datos
│   ├── ingest.py                ← CSV/XLS → SQLite (con detección de encoding)
│   ├── catalog_loader.py        ← Tablas de referencia (equipos, usuarios, tipos OT)
│   └── schema.sql               ← DDL SQLite con índices y vistas
│
├── 📁 analysis/                 ← Motor de análisis
│   ├── base.py                  ← Clase base y conexión a DB
│   ├── kpis.py                  ← MTTR, MTBF, disponibilidad, tasa de falla
│   ├── descriptive.py           ← Estadísticas descriptivas y distribuciones
│   ├── diagnostic.py            ← Diagnóstico de equipos críticos
│   ├── predictive.py            ← Proyecciones y estimación de próximas fallas
│   ├── prescriptive.py          ← Recomendaciones priorizadas
│   ├── reports.py               ← Generación de reportes MD y PDF
│   ├── visualizations.py        ← Gráficos Plotly/Matplotlib
│   └── pdf_export.py            ← Exportación a PDF con fpdf
│
├── 📁 data/
│   ├── sap_raw_export.csv       ← Dataset principal (2,149 OTs simuladas)
│   ├── sap_synthetic_data.csv   ← Dataset alternativo
│   ├── mantos.db                ← SQLite generada localmente (no versionada)
│   ├── assets/                  ← Gráficos generados por la app
│   └── reports/                 ← Reportes generados por la app
│
├── 📁 docs/
│   ├── arquitectura_mantos_v2.md       ← Diseño técnico del sistema
│   ├── catalogo_tecnico_planta.md      ← Diccionario de datos y equipos
│   └── assets/                         ← Diagramas de arquitectura
│
└── 📁 tests/
    ├── test_ingestion.py        ← Tests de pipeline de ingesta
    └── test_analysis.py         ← Tests de módulos de análisis
```

---

## Quickstart

### 1. Instalar dependencias

```bash
pip install -r requirements.txt
```

### 2. Cargar los datos

```bash
python ingestion/ingest.py --file data/sap_raw_export.csv --db data/mantos.db
```

Salida esperada:
```
=======================================================
  MantOS -- Ingesta completada OK
=======================================================
  Total órdenes : 2,149
  Ghost stops   : 312 (14.5%)
  Duración media: 87.3 min (excl. fantasmas)

  Desglose por tipo:
    PM01:   743 (34.6%)   ← Correctivos
    PM02:   589 (27.4%)   ← Preventivos
    PM03:   817 (38.0%)   ← Operacionales
=======================================================
```

### 3. Lanzar el dashboard

```bash
streamlit run streamlit_app.py
```

Abre tu navegador en **http://localhost:8501**

### 4. (Opcional) Ejecutar demo por consola

```bash
python demo.py
```

### 5. Correr tests

```bash
python -m pytest tests/ -v
```

---

## Datos de Demostración

El dataset incluido (`data/sap_raw_export.csv`) simula 2 años de operación de la **Planta Galletera Sur (PGS)**:

| Campo | Detalle |
|---|---|
| **Período** | Abril 2024 — Marzo 2026 |
| **Líneas** | LA1 (Soda), LA2 (Oblea), LA3, LA4 (Alfajores ⭐), LA5 (Export) |
| **Equipos** | 26 equipos distribuidos en 5 líneas de producción |
| **Órdenes** | 2,149 OTs (PM01 correctivo / PM02 preventivo / PM03 operacional) |
| **Formato** | Compatible con exports SAP PM reales (AUFK + QMIH + ILOA) |

Ver [`docs/catalogo_tecnico_planta.md`](docs/catalogo_tecnico_planta.md) para el diccionario completo de datos.

---

## Schema de la Base de Datos

### Tabla principal: `maintenance_orders`

| Columna | Tipo | Descripción |
|---|---|---|
| `aufnr` | TEXT | Número de OT — clave natural única |
| `qmnum` | TEXT | Número de aviso de mantenimiento |
| `start_datetime` | TEXT | Inicio en ISO 8601 UTC |
| `end_datetime` | TEXT | Fin en ISO 8601 UTC |
| `duration_min` | REAL | Duración calculada en minutos |
| `is_ghost_stop` | INTEGER | `1` si start == end (paro fantasma) |
| `tplnr` | TEXT | Ubicación técnica funcional |
| `equnr` | TEXT | ID de equipo |
| `qmtxt` | TEXT | Descripción corta de falla |
| `ltxtaufk` | TEXT | Texto técnico largo |
| `auart` | TEXT | Clase de orden: PM01 / PM02 / PM03 |
| `arbpl` | TEXT | Centro de trabajo |
| `ernam` | TEXT | Usuario creador |

### Tablas de referencia
- **`equipment`** — Catálogo de equipos con ubicación técnica y línea
- **`users`** — Usuarios clasificados (humano / sistema / operador)
- **`order_types`** — Tipos de orden PM01/PM02/PM03 con descripción

### Vistas útiles
- **`v_orders_enriched`** — Órdenes enriquecidas con datos de equipo y usuario
- **`v_kpi_by_equipment`** — KPIs pre-calculados por equipo

---

## Roadmap

| Fase | Módulo | Estado |
|---|---|---|
| 1 — Ingesta de datos | `ingestion/` | ✅ Completo |
| 2 — Motor de análisis | `analysis/` | ✅ Completo |
| 3 — Dashboard MVP | `streamlit_app.py` | ✅ Completo |
| 4 — Agente LLM | `agent/` | 🔜 Próxima versión |
| 5 — Integración SAP real | OData API | 🔜 Próxima versión |

---

## Stack Tecnológico

| Capa | Tecnología |
|---|---|
| Datos | SQLite + Pandas |
| Análisis | NumPy · SciPy · scikit-learn |
| Visualización | Plotly · Matplotlib |
| Dashboard | Streamlit |
| Reportes | fpdf · Markdown |
| Tests | pytest |
