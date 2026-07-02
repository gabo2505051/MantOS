# 🏭 MantOS — Mapa Arquitectónico

> **Planta Galletera Sur** · Sistema de Análisis de Mantenimiento  
> Alcance: Ingesta → Análisis (Descriptivo, Diagnóstico, KPIs) → Presentación

---

## Diagrama Principal (C4 — Nivel Contenedor)

```mermaid
flowchart TD
    %% ─────────────────────────────────────────
    %% FUENTES EXTERNAS
    %% ─────────────────────────────────────────
    subgraph EXT["🌐 Fuentes Externas"]
        SAP["📋 SAP PM\nReporte AUFNR/QMNUM\n.csv / .xlsx / .xls"]
        IIOT["⚙️ Sistema IIoT\nSYS_IIOT · SYS_SCADA\nPM03 / PM02"]
        OPR["👷 Operadores &amp; Mecánicos\nPM01 · PM02 · PM03"]
    end

    %% ─────────────────────────────────────────
    %% CAPA DE INGESTA
    %% ─────────────────────────────────────────
    subgraph ING["📥 Ingesta  ·  ingestion/"]
        INGEST["ingest.py\n─────────────\n① load_data()\n   • Detecta encoding\n   • Soporta CSV/XLS/XLSX\n   • Normaliza timestamps ISO8601\n   • Calcula duration_min\n   • Detecta ghost_stops\n② init_db()\n③ insert_orders()"]
        CAT["catalog_loader.py\n─────────────\n• ORDER_TYPES  (PM01/02/03)\n• EQUIPMENT    (25 equipos)\n• USERS        (18 actores)\n→ load_reference_tables()"]
        SCHEMA["schema.sql\n─────────────\n• maintenance_orders\n• equipment\n• order_types\n• users"]
    end

    %% ─────────────────────────────────────────
    %% BASE DE DATOS
    %% ─────────────────────────────────────────
    subgraph DB["🗄️ Persistencia  ·  data/"]
        SQLITE[("mantos.db\nSQLite\n─────────────\n📦 maintenance_orders\n📦 equipment\n📦 order_types\n📦 users")]
    end

    %% ─────────────────────────────────────────
    %% CAPA DE ANÁLISIS
    %% ─────────────────────────────────────────
    subgraph ANAL["🔬 Análisis  ·  analysis/"]
        BASE["base.py — AnalysisBase\n─────────────────────\n• Conexión lazy SQLite\n• query() / scalar()\n• clamp_dates()\n• build_filter_clause()\n• equipment_exists()"]

        DESC["descriptive.py\nDescriptiveAnalysis\n─────────────────\n• get_top_equipment_by_events()\n• get_temporal_heatmap()\n• get_top_keywords()\n• get_event_series()"]

        DIAG["diagnostic.py\nDiagnosticAnalysis\n─────────────────\n• get_pareto()\n• audit_ghost_stops()\n• get_downtime_by_period()"]

        KPI["kpis.py\nKPICalculator\n─────────────────\n• calc_mttr()\n• calc_mtbf() / calc_mttf()\n• calc_availability()\n• calc_failure_rate()\n• get_failure_trend()\n• get_kpi_summary() ← API"]
    end

    %% ─────────────────────────────────────────
    %% EXPORTACIÓN
    %% ─────────────────────────────────────────
    subgraph EXP["📤 Exportación  ·  analysis/"]
        VIZ["visualizations.py\n• Gráficos Plotly\n• Heatmaps"]
        REP["reports.py\n• Generación de reportes\n• Consolidación de datos"]
        PDF["pdf_export.py\n• Export a PDF"]
    end

    %% ─────────────────────────────────────────
    %% CAPA DE PRESENTACIÓN
    %% ─────────────────────────────────────────
    subgraph UI["🖥️ Presentación"]
        STREAM["streamlit_app.py\n─────────────────────────\n📊 Tab 1: Resumen General &amp; KPIs\n   • Métricas: MTTR · MTBF · Disponibilidad\n   • Comparativa equipos / líneas\n📈 Tab 2: Análisis Descriptivo\n   • Top equipos por fallas\n   • Keywords frecuentes\n   • Heatmap temporal\n🛠️ Tab 3: Diagnóstico\n   • Pareto de downtime (80/20)\n   • Auditoría ghost stops\n─────────────────────────\nFiltros: Línea · Equipo · Fechas · AUART"]
        DEMO["demo.py\n(consola / script)"]
    end

    %% ─────────────────────────────────────────
    %% TESTING
    %% ─────────────────────────────────────────
    subgraph TEST["🧪 Testing  ·  tests/"]
        TKPI["test_kpis.py\nPyTest"]
    end

    %% ─────────────────────────────────────────
    %% FLUJO DE DATOS
    %% ─────────────────────────────────────────
    SAP  -->|"CSV / XLS / XLSX"| INGEST
    IIOT -->|"PM03 / PM02"| SAP
    OPR  -->|"PM01 / PM02 / PM03"| SAP

    INGEST -->|"usa"| CAT
    INGEST -->|"aplica"| SCHEMA
    CAT    -->|"INSERT OR IGNORE"| SQLITE
    SCHEMA -->|"DDL → CREATE TABLE"| SQLITE
    INGEST -->|"INSERT OR REPLACE\nmaintenance_orders"| SQLITE

    SQLITE -->|"SELECT"| BASE
    BASE   -->|"hereda"| DESC
    BASE   -->|"hereda"| DIAG
    BASE   -->|"hereda"| KPI

    DESC -->|"DataFrames"| STREAM
    DIAG -->|"DataFrames"| STREAM
    KPI  -->|"JSON / dict"| STREAM

    DESC -->|"datos"| VIZ
    KPI  -->|"datos"| REP
    VIZ  -->|"gráficos"| REP
    REP  -->|"contenido"| PDF

    STREAM -->|"@st.cache_data"| DESC
    STREAM -->|"@st.cache_data"| DIAG
    STREAM -->|"@st.cache_data"| KPI

    TKPI -->|"testa"| KPI
    DEMO -->|"usa"| DESC
    DEMO -->|"usa"| DIAG
    DEMO -->|"usa"| KPI

    %% ─────────────────────────────────────────
    %% ESTILOS
    %% ─────────────────────────────────────────
    classDef external  fill:#1a1a2e,stroke:#e94560,color:#fff,stroke-width:2px
    classDef ingesta   fill:#16213e,stroke:#0f3460,color:#a8dadc,stroke-width:2px
    classDef db        fill:#0f3460,stroke:#533483,color:#fff,stroke-width:3px
    classDef base      fill:#533483,stroke:#e94560,color:#fff,stroke-width:2px
    classDef analisis  fill:#1a1a2e,stroke:#4cc9f0,color:#4cc9f0,stroke-width:2px
    classDef export    fill:#162032,stroke:#48cae4,color:#90e0ef,stroke-width:2px
    classDef ui        fill:#0d1b2a,stroke:#f72585,color:#fff,stroke-width:3px
    classDef test      fill:#1b1b2f,stroke:#7209b7,color:#c77dff,stroke-width:1px

    class SAP,IIOT,OPR external
    class INGEST,CAT,SCHEMA ingesta
    class SQLITE db
    class BASE base
    class DESC,DIAG,KPI analisis
    class VIZ,REP,PDF export
    class STREAM,DEMO ui
    class TKPI test
```

---

## Flujo de Datos Simplificado

```mermaid
flowchart LR
    A(["📋 Reporte SAP - Archivo de órdenes de mantenimiento"])
    B["📥 Procesamiento - El sistema lee, ordena y valida la información"]
    C[("🗄️ Base de Datos - Almacenamiento interno del sistema")]
    D["🔬 Análisis - El sistema calcula indicadores y tendencias"]
    E["🖥️ Panel de Control - Visualización para el equipo de gestión"]
    F["📤 Informes - Reportes y PDFs bajo demanda"]

    A -->|"Lee el archivo y detecta errores"| B
    B -->|"Guarda los datos en el sistema"| C
    C -->|"Consulta y procesa la información"| D
    D -->|"Muestra gráficos e indicadores"| E
    D -->|"Genera informes"| F

    style A fill:#1a1a2e,stroke:#e94560,color:#fff
    style B fill:#16213e,stroke:#0f3460,color:#a8dadc
    style C fill:#0f3460,stroke:#533483,color:#fff
    style D fill:#1a1a2e,stroke:#4cc9f0,color:#4cc9f0
    style E fill:#0d1b2a,stroke:#f72585,color:#fff
    style F fill:#162032,stroke:#48cae4,color:#90e0ef
```

### ¿Qué ocurre en cada paso?

| Paso | ¿Qué es? | ¿Qué hace el sistema? |
|:---:|---|---|
| 1 | **Reporte SAP** | El área de mantenimiento exporta el historial de órdenes de trabajo desde SAP |
| 2 | **Procesamiento** | El sistema lee el archivo, detecta fechas incorrectas, calcula tiempos de parada y filtra registros duplicados o vacíos |
| 3 | **Base de Datos** | Toda la información queda almacenada de forma ordenada: equipos, usuarios, tipos de orden y eventos de mantenimiento |
| 4 | **Análisis** | El sistema calcula automáticamente los indicadores clave: tiempo promedio de reparación, disponibilidad de equipos, equipos con más fallas, etc. |
| 5 | **Panel de Control** | El jefe o supervisor accede a un tablero web con gráficos interactivos, filtros por línea, equipo y fechas |
| 6 | **Informes** | Bajo demanda, el sistema genera reportes y documentos PDF con los resultados del período |

---

## Estructura de Tablas SQLite

```mermaid
erDiagram
    MAINTENANCE_ORDERS {
        string aufnr PK "Orden SAP"
        string qmnum "Notificación"
        string start_datetime "ISO 8601 UTC"
        string end_datetime "ISO 8601 UTC"
        float  duration_min "Calculado"
        int    is_ghost_stop "0|1"
        string tplnr FK "Ubic. Técnica"
        string equnr FK "Equipo"
        string auart FK "PM01|PM02|PM03"
        string ernam FK "Usuario SAP"
        string ingestion_src "csv|excel"
        string ingested_at "Metadato ingesta"
    }

    EQUIPMENT {
        string equnr PK
        string tplnr "PGS-PR-LAx-EQPxx"
        string linea "LA1..LA5, LAX"
        string nombre_equipo
        string descripcion
    }

    ORDER_TYPES {
        string auart PK
        string nombre "Correctivo|Preventivo|Operacional"
        string descripcion
    }

    USERS {
        string ernam PK
        string tipo "humano|sistema|operador"
        string descripcion
    }

    MAINTENANCE_ORDERS ||--o{ EQUIPMENT : "equnr"
    MAINTENANCE_ORDERS ||--o{ ORDER_TYPES : "auart"
    MAINTENANCE_ORDERS ||--o{ USERS : "ernam"
```

---

## Resumen de Responsabilidades

| Módulo | Clase Principal | Responsabilidad |
|---|---|---|
| `ingestion/ingest.py` | — (funciones) | Leer SAP export → limpiar → cargar SQLite |
| `ingestion/catalog_loader.py` | — (constantes) | Datos de referencia: equipos, usuarios, tipos |
| `ingestion/schema.sql` | — (DDL) | Definición de todas las tablas |
| `analysis/base.py` | `AnalysisBase` | Conexión DB, helpers SQL/fecha, filtros comunes |
| `analysis/descriptive.py` | `DescriptiveAnalysis` | Top equipos, heatmaps, keywords |
| `analysis/diagnostic.py` | `DiagnosticAnalysis` | Pareto 80/20, auditoría ghost stops |
| `analysis/kpis.py` | `KPICalculator` | MTTR, MTBF, Disponibilidad, Tasa de fallas |
| `analysis/reports.py` | — | Consolidación de reportes |
| `analysis/pdf_export.py` | — | Export a PDF |
| `analysis/visualizations.py` | — | Gráficos Plotly reutilizables |
| `streamlit_app.py` | — (UI) | Dashboard web: 3 tabs, filtros interactivos |

> **Excluido del alcance:** `analysis/predictive.py` · `analysis/prescriptive.py`
