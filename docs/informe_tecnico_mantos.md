# 📄 MantOS — Informe Técnico de Arquitectura, Modelado y Matemáticas

> **Proyecto:** MantOS (Sistema Inteligente de Análisis de Mantenimiento Industrial — Planta Galletera Sur)  
> **Propósito:** Guía de estudio y referencia técnica completa sobre los modelos matemáticos, pipeline de limpieza, engine prescriptivo y arquitectura del sistema.  
> **Archivos de Referencia Auditados:** `analysis/predictive.py`, `analysis/kpis.py`, `analysis/descriptive.py`, `analysis/prescriptive.py`, `analysis/taxonomy_5m.py`, `ingestion/ingest.py`, `ingestion/schema.sql`.

---

## 📌 BLOQUE A: Modelado Predictivo y Matemáticas

### 1. Algoritmo y Modelo Matemático para 7 y 14 Días

El cálculo de la probabilidad de falla para los horizontes de 7 y 14 días utiliza un **clasificador supervisado de Machine Learning basado en Random Forest con Ventana Temporal Deslizante (*Sliding Window*)** ([predictive.py:L323-L525](file:///d:/01%20Phasor%20Logic/MantOS%20-%20copia%20-%20copia/MantOS/analysis/predictive.py#L323-L525)).

#### A. Algoritmo e Hiperparámetros
* **Modelo Base:** `sklearn.ensemble.RandomForestClassifier`
* **Configuración del Modelo**:
  ```python
  clf7  = RandomForestClassifier(n_estimators=150, max_depth=8, random_state=42, class_weight="balanced")
  clf14 = RandomForestClassifier(n_estimators=150, max_depth=8, random_state=42, class_weight="balanced")
  ```
* **Razón de `class_weight="balanced"`**: En mantenimiento industrial, los días sin fallas superan ampliamente a los días con fallas. El balanceo de pesos de clase ajusta la función de pérdida para evitar falsos negativos en equipos críticos.

#### B. Generación de Dataset (Sliding Window)
* El motor recorre el historial de la planta en pasos de 14 días (`step_days = 14`).
* Para cada punto temporal y cada equipo, calcula un **vector de 9 características (features)** basado en los 60 días de historial previo (`lookback_days = 60`).
* Asigna la etiqueta binaria `label_7d = 1` o `label_14d = 1` si en el intervalo futuro $[t, t + \Delta t]$ ocurrió al menos una falla correctiva (`PM01`).

#### C. Vector de 9 Features Utilizadas
1. `events_7d`: Frecuencia de paradas en los últimos 7 días.
2. `events_30d`: Frecuencia de paradas en los últimos 30 días.
3. `events_60d`: Frecuencia total de paradas en la ventana de 60 días.
4. `avg_duration_min`: Duración promedio de las intervenciones (minutos).
5. `pct_pm01`: Proporción de eventos de tipo correctivo PM01 sobre el total.
6. `days_since_last_failure`: Días transcurridos desde la última falla PM01.
7. `recurrence_score`: Porcentaje de fallas ocurridas a menos de 7 días de la anterior.
8. `ghost_pct`: Proporción de paros fantasma (`duration_min` = 0).
9. `dayofweek_mode`: Moda del día de la semana en que falla el equipo.

#### D. Obtención de Probabilidad e Inferencia
La inferencia se ejecuta mediante:
$$\text{prob\_7d} = P(Y=1 \mid X) = \text{clf7.predict\_proba}(X)[0, 1]$$
$$\text{prob\_14d} = P(Y=1 \mid X) = \text{clf14.predict\_proba}(X)[0, 1]$$

*(Nota: De forma complementaria, en `forecast_failure_rate()` se implementa una **Regresión Lineal por Mínimos Cuadrados** `scipy.stats.linregress` para estimar cuantitativamente la tendencia de la tasa de fallas y su bondad de ajuste mediante el coeficiente $R^2$).*

---

### 2. Manejo del *Cold Start Problem* (Datos escasos o activos nuevos)

El sistema hace frente al problema de arranque en frío a través de filtros de umbral, valores neutrales por defecto y estados explícitos de "Sin datos":

1. **Filtro de Inclusión en Entrenamiento (`_build_training_dataset`)**:
   * Solo se incluyen en el dataset de entrenamiento los equipos con **al menos 5 eventos registrados** en la base de datos:
     ```sql
     SELECT equnr, COUNT(*) as cnt FROM maintenance_orders GROUP BY equnr HAVING cnt >= 5
     ```
2. **Retorno de Estado "Sin Datos" (`predict_next_failure_probability`)**:
   * Si un activo no registra eventos en los 60 días previos, `_build_feature_row()` devuelve `None`.
   * El predictor captura este valor y retorna inmediatamente:
     ```python
     return {
         "equnr": equnr,
         "prob_7d": None,
         "prob_14d": None,
         "risk_label_7d": "Sin datos",
         "risk_label_14d": "Sin datos",
         "model_available": True
     }
     ```
3. **Manejo de Fallas Raras (Sin paradas PM01 recientes)**:
   * Si el equipo tiene mantenimientos pero no correctivos PM01, `days_since_last_failure` se fija en el tope de la ventana (`60.0` días) y `recurrence_score = 0.0`.
4. **Fallback en Score de Riesgo Compuesto (`calc_risk_score`)**:
   * Si el historial tiene menos de 4 semanas, la componente de frecuencia asigna un valor neutral (`freq_score = 50.0`). Si la tendencia de MTBF carece de puntos suficientes, asigna `trend_score = 50.0`.

---

### 3. Cálculo de MTBF y MTTR ante Ausencia de Timestamps Exactos

#### A. Tratamiento en Ingesta (`ingestion/ingest.py`)
* La función `_normalize_ts()` parsea timestamps de inicio (`GSTRP`) y fin (`GLTRP`) mediante `pd.to_datetime(..., errors="coerce", utc=True)`. Si el timestamp no existe o es inválido, se convierte a `NaT` (`NULL` en SQLite).
* La función `_compute_duration_min()` calcula la diferencia en minutos:
  $$\Delta t = \frac{\text{end\_datetime} - \text{start\_datetime}}{60}$$
* Si falta alguno de los timestamps, $\Delta t$ resulta en `NaN`. Si la duración es negativa (dato corrupto), la convierte a `NaN`.
* Si $\text{start\_datetime} == \text{end\_datetime}$, la duración es $0.0$ y la función `_is_ghost_stop()` lo clasifica como **paro fantasma** (`is_ghost_stop = 1`).

#### B. Cálculo Interno de MTTR (`analysis/kpis.py:L36-L86`)
Se calcula mediante consulta SQL sobre datos no viciados:
```sql
SELECT AVG(mo.duration_min) AS mttr
FROM maintenance_orders mo
WHERE mo.start_datetime >= ? AND mo.start_datetime <= ?
  AND mo.duration_min > 0 AND mo.is_ghost_stop = 0 AND mo.auart = 'PM01'
```
* **Exclusión Rígida**: Las órdenes de trabajo que no tienen horas exactas (duración `NaN`/`NULL`) o cuya duración es $0$ **son excluidas automáticamente** tanto del numerador como del denominador.

#### C. Cálculo Interno de MTBF (`analysis/kpis.py:L132-L174`)
MTBF se calcula como la media de los intervalos de tiempo en horas entre registros de falla correctiva consecutivos:
$$\text{gaps\_hours} = \frac{\text{diff}(\text{start\_datetime})}{3600}$$
* **Timestamp de Referencia**: Se utiliza únicamente `start_datetime` (la fecha/hora en que se abrió o registró el aviso/falla en SAP).
* **Independencia de Hora de Cierre**: Si falta la fecha de fin de la orden, **el MTBF se sigue calculando de forma exacta** porque solo depende del instante de inicio de las fallas.

---

## 🧼 BLOQUE B: Pipeline de Datos y Limpieza

### 1. Reglas Exactas de Limpieza y Normalización de Texto

La función `normalize_failure_text()` ([descriptive.py:L358-L382](file:///d:/01%20Phasor%20Logic/MantOS%20-%20copia%20-%20copia/MantOS/analysis/descriptive.py#L358-L382)) procesa las descripciones de fallas en 4 etapas:

1. **Conversión a Minúsculas y Trimming**:
   `t = text.lower().strip()`
2. **Sustitución Regex de Abreviaciones por Términos Canónicos (`_ABBREV_MAP`)**:
   Sustituye abreviaturas técnicas típicas de SAP PM usando expresiones regulares con límites de palabra (`\b...\b`):
   * `m.paro`, `mparo`, `microparo` $\rightarrow$ `"micro paro"`
   * `atsc`, `atasco` $\rightarrow$ `"atasco"`
   * `rst`, `reset` $\rightarrow$ `"reinicio"`
   * `fallo`, `falllo` $\rightarrow$ `"falla"`
   * `sens`, `sensor` $\rightarrow$ `"sensor"`
   * `temp` $\rightarrow$ `"temperatura"`
   * `prox` $\rightarrow$ `"proximidad"`
   * `optico` $\rightarrow$ `"optico"`
   * `insp`, `inspeccion` $\rightarrow$ `"inspeccion"`
   * `mto`, `mtto`, `mantt` $\rightarrow$ `"mantenimiento"`
   * `calib` $\rightarrow$ `"calibracion"`
   * `cmb` $\rightarrow$ `"cambio"`
   * `aj` $\rightarrow$ `"ajuste"`
   * `prev` $\rightarrow$ `"preventivo"`
   * `corr` $\rightarrow$ `"correctivo"`
3. **Eliminación de Puntuación y Caracteres Especiales**:
   * Retiene únicamente caracteres alfanuméricos y espacios: `re.sub(r"[^\w\s]", " ", t)`.
   * Colapsa espacios múltiples: `re.sub(r"\s+", " ", t)`.
4. **Filtrado de Stopwords e Indicadores Cortos**:
   * Elimina palabras de la lista `_STOPWORDS`:
     * *Gramaticales*: `de`, `en`, `el`, `la`, `los`, `las`, `por`, `con`, `sin`, `se`, `y`, `a`, `un`, `una`, `al`, `del`, `o`, `es`, `no`.
     * *Ruido operacional*: `ok`, `idem`, `anterior`, `ver`, `ot`, `novedad`, `resuelto`, `sin observaciones`, `normalizado`, `equipo`.
   * Filtra tokens de longitud $\le 2$ caracteres (`len(w) > 2`).

*(No utiliza lematizador pesado Spacy/NLTK para garantizar máxima velocidad de procesamiento sin latencia de red ni dependencias pesadas).*

---

### 2. Columnas Mínimas Obligatorias del Parser de Entrada

Para que el script `ingestion/ingest.py` procese el archivo (CSV o Excel) sin lanzar un `sqlite3.IntegrityError` o un error `KeyError`, las columnas mínimas obligatorias exigidas por el parser y el esquema SQL son:

#### 🔴 Columnas Mínimas Obligatorias (`NOT NULL` en Base de Datos):

| Columna SAP Original | Nombre Interno | Restricción en `schema.sql` | Razón de Obligatoriedad |
| :--- | :--- | :---: | :--- |
| **`AUFNR`** | `aufnr` | `TEXT NOT NULL UNIQUE` | Clave primaria de la orden de trabajo. Si falta, SQLite rechaza la inserción. |
| **`GSTRP`** | `start_raw` $\rightarrow$ `start_datetime` | `TEXT NOT NULL` | Fecha de inicio de la orden. Indispensable para el ordenamiento temporal y cálculo de MTBF. |
| **`AUART`** | `auart` | `TEXT NOT NULL` | Clase de orden (`PM01`, `PM02`, `PM03`). Requerida para filtrado y relación de Clave Foránea (`FOREIGN KEY`). |

#### 🟡 Columnas Opcionales (Admiten `NULL` / Vaciado sin Provocar Crash):
* **`GLTRP`** (`end_raw`): Fecha de fin. Si falta, `duration_min` se calcula como `NaN` y el registro se excluye del MTTR sin romper la ingesta.
* **`EQUNR`** (`equnr`): ID de equipo.
* **`QMTXT`** / **`LTXTAUFK`** (`qmtxt` / `ltxtaufk`): Título corto y texto largo. Si faltan, el clasificador 5M asigna la categoría fallback por omisión (`"OTRO"` / `"Sin Descripción Especificada"`).
* **`TPLNR`**, **`QMNUM`**, **`ARBPL`**, **`ERNAM`**: Campos de metadatos opcionales.

---

## 💡 BLOQUE C: Motor Prescriptivo e IA (RAG / LLM)

### 1. Construcción del Contexto y Prompt de Prescripción Técnica

En la versión V1.0 de MantOS, la prescripción se genera mediante un **motor experto de reglas de ingeniería + machine learning** ([prescriptive.py:L53-L215](file:///d:/01%20Phasor%20Logic/MantOS%20-%20copia%20-%20copia/MantOS/analysis/prescriptive.py#L53-L215)).

#### 📌 Variables Inyectadas en el Contexto del Activo:
Para evaluar la prescripción de un equipo, el motor compila un objeto contextual con **9 dimensiones técnicas**:
1. `equnr` & `nombre_equipo` / `tag_equipo`: Identificación del activo y su ubicación técnica.
2. `risk_score` & `risk_level`: Score de riesgo sintético (0 a 100) y su nivel (`CRITICO`, `ALTO`, `MEDIO`, `BAJO`).
3. `prob_7d` & `prob_14d`: Probabilidades continuas estimadas por el modelo Random Forest ML.
4. `top_features`: Las 3 variables con mayor importancia relativa según el clasificador ML (ej: `events_7d`, `days_since_last_failure`).
5. `availability_pct` & `downtime_min`: Disponibilidad acumulada y minutos de parada no planificada.
6. `mttr`: Tiempo Medio de Reparación en minutos.
7. `trend`: Dirección de la tendencia de fallas (`deteriorating`, `stable`, `improving`), su pendiente ($\text{slope}$) y coeficiente $R^2$.
8. `ghost_pct` & `ghost_total`: Porcentaje y conteo de paros fantasma registrados.
9. `maquina_cnt` vs `mano_obra_cnt`: Conteo de eventos agrupados por la taxonomía 5M en memoria.

#### 📄 Estructura del Prompt / Plantilla Estructurada:
```json
{
  "tipo": "INSPECCION_CORRECTIVA_MECANICA",
  "prioridad": 1,
  "urgencia": "URGENTE (< 48 horas)",
  "mensaje": "Inspección mecánica urgente requerida. Score de riesgo de Máquina: 78/100.",
  "justificacion": "El equipo supera el umbral crítico (70). Eventos de Máquina: 12.",
  "fuente": "KPI_MECANICO"
}
```

> **Evolución V2.0 (Plan RAG + LLM)**: En `docs/arquitectura_mantos_v2.md` se especifica que el agente RAG (usando Ollama / Llama3 local) tomará este contexto con las 9 variables anteriores y le inyectará los **Top-K Chunks recuperados del Vector Store (Chroma/FAISS)** desde los manuales PDF del fabricante para redactar el procedimiento paso a paso.

---

### 2. Blindaje contra Alucinaciones Técnicas (*Zero-Hallucination Guardrails*)

1. **Separación Causal Estricta (Filtro 5M)**:
   * El motor evalúa de forma independiente las fallas atribuidas a `MAQUINA` de las atribuidas a `MANO DE OBRA` ([prescriptive.py:L128-L157](file:///d:/01%20Phasor%20Logic/MantOS%20-%20copia%20-%20copia/MantOS/analysis/prescriptive.py#L128-L157)).
   * Si un equipo falla por mala manipulación del operador (`MANO DE OBRA`), el sistema desvía la recomendación hacia `"CAPACITACION_OPERATIVA_5M"` (*Reforzar capacitación sobre montaje*), **impidiendo que el sistema prescriba erróneamente el reemplazo físico de piezas o componentes mecánicos/eléctricos**.
2. **Plantillas de Ingeniería Deterministas (V1.0)**:
   * En V1.0, los mensajes de intervención están acotados a plantillas aprobadas por ingeniería de mantenimiento, las cuales se disparan según umbrales de severidad estrictos (`THRESHOLDS`).
3. **Mapeo Semántico Restringido en RAG (*Grounding* en V2.0)**:
   * En la arquitectura RAG V2.0, la consulta al LLM incluye la instrucción estricta de *Grounding*: el modelo no tiene permitido inventar pasos; únicamente resume los fragmentos extraídos del manual técnico en PDF (`doc_chunks`), adjuntando la página y sección exacta de la documentación técnica.

---

## ⚡ BLOQUE D: Arquitectura y Escalabilidad

### 1. Comportamiento de Streamlit ante Datasets Masivos (> 50.000 filas)

#### 🟢 Aspectos Optimizados (Resisten > 50.000 filas):
1. **Consultas Agregadas en SQLite con Índices**:
   * MantOS no carga todas las 50.000 filas a la memoria de Python para procesarlas. Las agregaciones (`COUNT`, `SUM`, `AVG`, `GROUP BY`) son delegadas al motor SQLite indexado ([schema.sql:L78-L97](file:///d:/01%20Phasor%20Logic/MantOS%20-%20copia%20-%20copia/MantOS/ingestion/schema.sql#L78-L97)). Los índices (`idx_mo_equnr_start`, `idx_mo_start_datetime`) permiten tiempos de respuesta en milisegundos ($\mathcal{O}(\log N)$).
2. **Caché Amortiguadora de Streamlit (`@st.cache_data`)**:
   * Las funciones de carga visual ([streamlit_app.py:L137-L151](file:///d:/01%20Phasor%20Logic/MantOS%20-%20copia%20-%20copia/MantOS/streamlit_app.py#L137-L151)) almacenan los resultados agregados en memoria con un `ttl=3600` (1 hora). La interfaz responde al instante tras la primera carga.
3. **Modo WAL en SQLite (`PRAGMA journal_mode = WAL`)**:
   * Habilita lecturas no bloqueantes y optimiza las transacciones I/O en disco.

#### ⚠️ Cuellos de Botella Identificados (Requieren Atención para > 50.000 filas):
* **Generación del Dataset de Entrenamiento ML (`_build_training_dataset`)**:
  * Actualmente, `train_failure_classifier()` en `predictive.py` recorre el histórico con una ventana deslizante de 14 días sobre todos los equipos. Con 50.000 filas, la construcción de muestras puede tardar entre **15 y 30 segundos** en la primera carga del dashboard.
  * *Solución recomendada:* Persistir el modelo Random Forest en disco (`.pkl` / `.joblib`) en segundo plano.

---

### 2. Pasos Exactos para Desacoplar la Lógica y Convertirla en API REST (FastAPI)

El núcleo de análisis de MantOS (`analysis/`) fue diseñado **100% desacoplado de la interfaz gráfica** (ningún módulo dentro de `analysis/` importa `streamlit`).

Para convertir el backend en un servicio API REST con **FastAPI**, se requieren los siguientes 3 pasos exactos:

#### 1️⃣ Crear el Punto de Entrada REST (`api/main.py`):
Se construye la aplicación FastAPI instanciando las clases de análisis directamente:

```python
from fastapi import FastAPI, Query, HTTPException
from typing import Optional, List
from analysis.kpis import KPICalculator
from analysis.prescriptive import PrescriptiveAnalysis
from analysis.predictive import PredictiveAnalysis

app = FastAPI(title="MantOS Engine REST API", version="1.0.0")

@app.get("/api/v1/kpis/summary")
def get_kpi_summary(
    equnr: Optional[str] = Query(None),
    linea: Optional[str] = Query(None),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None)
):
    with KPICalculator() as kpi:
        return kpi.get_kpi_summary(equnr=equnr, linea=linea, start_date=start_date, end_date=end_date)

@app.get("/api/v1/prescriptive/recommendations")
def get_recommendations(
    equnr: str,
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None)
):
    with PrescriptiveAnalysis() as presc:
        return presc.get_recommendations(equnr=equnr, start_date=start_date, end_date=end_date)

@app.get("/api/v1/predictive/risk-ranking")
def get_risk_ranking(linea: Optional[str] = Query(None)):
    with PredictiveAnalysis() as pred:
        df = pred.get_risk_ranking(linea=linea)
        return df.to_dict(orient="records")
```

#### 2️⃣ Modificación Única en `analysis/base.py` (Pool de Conexiones / Async):
* Sustituir la propiedad `self._conn` de la clase `AnalysisBase` ([base.py:L57-L66](file:///d:/01%20Phasor%20Logic/MantOS%20-%20copia%20-%20copia/MantOS/analysis/base.py#L57-L66)) para que soporte un pool de conexiones thread-safe (usando `check_same_thread=False` en SQLite o migrando a PostgreSQL con `SQLAlchemy` / `psycopg2`). Esto evita bloqueos de hilo cuando múltiples peticiones concurrentes lleguen a Uvicorn/FastAPI.

#### 3️⃣ Modelos de Validación de Datos (`api/schemas.py`):
* Definir clases Pydantic (`BaseModel`) para validar los parámetros de entrada y documentar automáticamente los esquemas JSON de respuesta en la interfaz Swagger interactiva (`/docs`).
