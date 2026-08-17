# 🏭 MantOS — Project Design & Status Review (PDR)
> **Proyecto:** MantOS (Sistema Inteligente de Análisis de Mantenimiento Industrial — Planta Galletera Sur)  
> **Fecha de Evaluación:** 16 de Agosto de 2026  
> **Versión Actual:** MVP 1.0 (con módulos de Ingesta, Análisis Clásico, Taxonomía 5M, ML Predictivo y Prescriptivo)  
> **Documento Referencia:** `docs/arquitectura_mantos_v2.md` | `README.md` | `feature_list.json`

---

## 1. Resumen Ejecutivo y Estado Actual del Proyecto

**MantOS** es una plataforma analítica integral orientada a optimizar la gestión de mantenimiento industrial a partir de historiales de órdenes de trabajo (OTs) de SAP PM. El sistema procesa datos estructurados y semi-estructurados (simulando las tablas `AUFK`, `QMIH`, `ILOA` y `EQUI`), permitiendo calcular métricas críticas operacionales (**MTTR**, **MTBF**, **Disponibilidad**), diagnosticar fallas recurrentes mediante la regla de Pareto (80/20), detectar anomalías temporales y paros fantasma, categorizar causas por metodología 5M y realizar predicciones de fallas mediante Machine Learning.

### 1.1 Inventario de Componentes y Cobertura
- **Ingesta de Datos (`ingest.py`, `catalog_loader.py`):** ETL funcional con soporte para CSV/XLS, autodetector de encoding (UTF-8, Latin1, CP1252), normalización ISO-8601, tabla de equipos (27 equipos), actores (18 usuarios) y tipos de OT (`PM01` Correctivo, `PM02` Preventivo, `PM03` Operacional).
- **Motor de Persistencia (`data/mantos.db`):** Base de datos relacional SQLite con esquema normalizado e índices optimizados, junto a vistas SQL (`v_orders_enriched`, `v_kpi_by_equipment`).
- **Motor de Análisis (`analysis/`):** 10 submódulos independientes (`base`, `kpis`, `descriptive`, `diagnostic`, `predictive`, `prescriptive`, `taxonomy_5m`, `reports`, `pdf_export`, `visualizations`).
- **Interfaz Gráfica (`streamlit_app.py`):** Dashboard web interactivo de 5 pestañas (📊 KPIs, 📈 Descriptivo, 🛠️ Diagnóstico, 🤖 Predictivo, 💡 Prescriptivo).
- **Suite de Pruebas (`tests/`):** 99 pruebas unitarias construidas en `pytest` cubriendo la ingesta, motores analíticos, categorización 5M y prescriptivos (**99 pasadas al 100%**).

---

## 2. Puntos Fuertes del Proyecto (Strengths)

1. **Jerarquía Analítica Completa (Descriptivo → Diagnóstico → Predictivo → Prescriptivo):**
   - El proyecto no se limita a mostrar gráficos del pasado; avanza progresivamente hacia el cálculo de riesgo futuro (modelos ML de 7 y 14 días) y genera un plan de acción prescriptivo categorizado (**URGENTE / PLANIFICADO / MONITOREO**).

2. **Categorización Causal por Metodología 5M en Memoria (`taxonomy_5m.py`):**
   - Mapeo dinámico de descripciones sucias/largas de SAP PM a causas simplificadas estandarizadas (*Máquina, Mano de Obra, Método, Material, N/A Programado*), eliminando el ruido de palabras sueltas descontextualizadas.

3. **Modelo de Datos Normalizado y Adaptado a SAP PM:**
   - La estructura de base de datos modela de forma precisa la jerarquía real de SAP Plant Maintenance, gestionando adecuadamente las claves naturales (`aufnr`), ubicaciones técnicas (`tplnr`), equipos (`equnr`) y la detección nativa de *ghost stops* (`duration_min` == 0).

4. **Machine Learning Predictivo de Alto Rendimiento:**
   - El módulo predictivo (`predictive.py`) implementa clasificadores `Random Forest` entrenados sobre características de ventanas móviles (frecuencia, tendencia MTBF, recurrencia), alcanzando un **AUC-ROC > 0.93** para horizontes de 7 y 14 días.

5. **Interfaz de Usuario Rica y Balanceada en Streamlit:**
   - Visualizaciones de alto impacto: distribución balanceada de 2 columnas en Tab 2 (Top Equipos + Top Causas 5M lado a lado), gauges de riesgo, matrices de calor temporales, diagramas Pareto con doble eje Y y badges de origen de recomendación (`⚙️ KPI_MECANICO` vs `👷 5M_MANO_DE_OBRA`).

6. **Capacidad de Exportación Ejecutiva:**
   - El sistema integra pipelines de generación de reportes estructurados en Markdown y la exportación automatizada a documentos PDF mediante `fpdf`.

---

## 3. Puntos Débiles y Deuda Técnica (Weaknesses & Risks)

1. **Estado de Pruebas Unitarias (Resuelto — 100% de pasadas):**
   - Los fallos iniciales en auditoría de paros fantasma fueron **completamente subsanados** y se añadieron 7 pruebas unitarias dedicadas en `tests/test_taxonomy_5m.py`, alcanzando un total de **99/99 pruebas pasadas (100% éxito)**.

2. **Ingesta Exclusivamente en Lote (Batch Ingestion):**
   - El pipeline actual depende de ejecuciones manuales CLI (`python ingestion/ingest.py`) o carga de archivos locales. No existe un API REST (FastAPI/Flask) ni soporte para ingesta continua por streaming de eventos.

3. **Limitaciones de Concurrencia en SQLite:**
   - SQLite es excelente para prototipos y funcionamiento local, pero no soporta escrituras concurrentes intensivas ni entornos multi-usuario en producción distribuida.

4. **Parámetros y Umbrales Hardcodeados:**
   - Los pesos de la fórmula del Score de Riesgo (40% frecuencia, 30% MTBF, 20% recurrencia, 10% ghost stops) y las reglas de severidad prescriptivas (ej. Risk > 70 = URGENTE) están grabados directamente en código Python en lugar de estar expuestos en un archivo de configuración (`config.yaml`).

5. **Evolución del Retrenado de Modelos ML:**
   - El modelo ML se entrena automáticamente en el arranque del dashboard mediante `@st.cache_resource`. Carece de versión persistente en disco (`.joblib` / `.pkl`) con MLOps o control de deriva (drift).

6. **Brecha con la Arquitectura Prometida V2.0:**
   - Documentos como `arquitectura_mantos_v2.md` describen módulos de agentes conversacionales LLM (NL2SQL, RAG sobre manuales en PDF, Vector Store Chroma/FAISS), pero **ninguno de estos submódulos existe aún en el código fuente**.

---

## 4. Análisis Específico: "Alarma de Equipo" y Node-RED

### 4.1 Diagnóstico de Situación
- **Estado Actual en Código:** Node-RED **NO está implementado** en el código fuente. Su única mención figura en los diagramas conceptuales de la documentación V2.0 (`docs/arquitectura_mantos_v2.md`).
- **Preocupación del Usuario:** El usuario considera no involucrarse con Node-RED por ahora y trabajar exclusivamente con los datos ya existentes de la Planta.

### 4.2 Viabilidad de Operar 100% con Datos de Planta
**Confirmación Técnica:** MantOS **NO requiere Node-RED ni hardware/telemetría externa** para funcionar a su máxima capacidad analítica actual.

El sistema ya procesa toda la información necesaria a partir de los datos históricos y sintéticos de la Planta Galletera Sur (PGS):
- **Eventos Correctivos (`PM01`):** Permiten calcular paros no planificados, MTTR y MTBF.
- **Eventos Preventivos (`PM02`):** Permiten evaluar el cumplimiento del plan de mantenimiento.
- **Eventos Operacionales (`PM03`):** Registran micro-detenciones y alertas de línea.

### 4.3 Motor de "Alarmas Virtuales" Basado en Datos (Sin Node-RED)
En lugar de depender de sensores físicos que envíen datos vía Node-RED, MantOS genera sus **"Alertas de Equipo" de manera dinámica** dentro de `analysis/prescriptive.py` (`check_alerts()`) analizando los propios datos de planta:
1. **Alerta por Incremento de Frecuencia:** Se dispara cuando un equipo registra un incremento de paros mayor a 2 desviaciones estándar ($Z\text{-score} > 2.0$) respecto a su historial.
2. **Alerta por Caída de MTBF:** Se dispara cuando el tiempo medio entre fallas de un equipo cae más de un 30% en los últimos 30 días.
3. **Alerta por Score de Riesgo Crítico:** Se activa automáticamente cuando el índice de riesgo compuesto supera los 70 puntos.
4. **Alerta por Micro-detenciones Acumuladas:** Detecta secuencias inusuales en eventos `PM03` que anteceden paradas mayores.

### 4.4 Estrategia de Desacoplamiento e Integración Futura
Si en el futuro se desea incorporar Node-RED o señales PLC en tiempo real:
- **Enfoque Desacoplado:** Node-RED debe limitarse a actuar como un emisor de eventos que inserte filas en la tabla `maintenance_orders` o en una tabla auxiliar `equipment_alarms`.
- **Independencia del Core:** El motor analítico de MantOS continuará leyendo la base de datos de manera uniforme, sin importar si los registros provinieron de un export mensual de SAP o de un nodo de Node-RED.

---

## 5. Nueva Incorporación Arquitectónica: Taxonomía 5M y Filtro Prescriptivo

Se incorporó exitosamente la capa de **Clasificación Causal por Metodología 5M** (*Máquina, Mano de Obra, Método, Material, N/A Programado*) calculada dinámicamente en memoria (`analysis/taxonomy_5m.py`):

1. **Simplificación en Análisis Descriptivo (Tab 2 UI):**
   - Agrupamiento de descripciones largas SAP en causas simplificadas (*Des-calibración de instrumento, Avería de válvulas, Mal acople de hoja*).
   - Rediseño del Tab 2 en **2 columnas balanceadas**: *Top Equipos por Fallas* a la izquierda y *Top Causas Simplificadas 5M* a la derecha (reemplazando palabras sueltas sin contexto).
   - Inclusión de filtro dinámico en la UI para **excluir mantenimientos programados (`N/A`)** y selector por categoría 5M.
   - Normalización transparente entre etiquetas con espacio y guion bajo (`MANO DE OBRA` / `MANO_DE_OBRA`, `N/A` / `N_A`).

2. **Restricción Estricta en Motor Prescriptivo (Tab 5 UI):**
   - **Regla de Negocio:** Las recomendaciones de mantenimientos correctivos y preventivos físicos a 2 semanas consideran **exclusivamente las causales de tipo `MAQUINA`**.
   - Los paros atribuidos a `MANO DE OBRA` generan sugerencias de capacitación o revisión de SOP (`👷 5M_MANO_DE_OBRA`) sin inflar erróneamente el score de riesgo mecánico del equipo.

---

## 6. Matriz de Recomendaciones y Plan de Acción

| Prioridad | Área | Acción Recomendada | Estado | Impacto |
| :---: | :---: | :--- | :---: | :--- |
| 🔴 **Alta** | **5M Taxonomy** | Implementar `analysis/taxonomy_5m.py` y restringir el motor prescriptivo a causales de tipo `MAQUINA`. | ✅ **Completado** | Elimina falsos positivos en planes de mantenimiento físico. |
| 🔴 **Alta** | **UI Descriptivo** | Incorporar el selector 5M, checkbox de exclusión `N/A` y layout de 2 columnas en el Tab 2 de Streamlit. | ✅ **Completado** | Visualización ejecutiva limpia del Top 10 de causas de falla. |
| 🔴 **Alta** | **Testing** | Corregir las pruebas unitarias e incorporar `tests/test_taxonomy_5m.py`. | ✅ **Completado** | Garantiza 100% de pasadas en pytest (99/99). |
| 🟡 **Media** | **Configuración** | Extraer umbrales (risk scores, ponderaciones) a un archivo `config.yaml`. | ⏳ Pendiente | Facilita la calibración del sistema sin tocar código. |
| 🟡 **Media** | **MLOps** | Persistir el modelo Random Forest en `.joblib` para optimizar el tiempo de carga de Streamlit. | ⏳ Pendiente | Carga inicial del dashboard en < 2 segundos. |
| 🟢 **Baja** | **Base de Datos** | Evaluar la migración de SQLite a PostgreSQL en caso de requerir acceso multiusuario masivo o API REST. | ⏳ Pendiente | Prepara la plataforma para escala industrial V2.0. |

---

## 7. Conclusión

MantOS presenta un **estado de desarrollo altamente maduro, funcional y sólido en su versión MVP (V1.0)**. El core analítico, las predicciones ML, la taxonomía 5M y el dashboard visual funcionan de forma integrada y ofrecen un valor operativo inmediato para la toma de decisiones de mantenimiento.

La decisión de **omitir la integración con Node-RED en la etapa actual es técnicamente acertada y completamente viable**, complementada con la nueva **Categorización 5M** que garantiza que el Plan de Acción Prescriptivo se concentre únicamente en fallas reales de maquinaria.
