import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime
from pathlib import Path
import sys

# ─── Module resolution ────────────────────────────────────────────────────────
_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(_ROOT))

from analysis.descriptive  import DescriptiveAnalysis
from analysis.diagnostic   import DiagnosticAnalysis
from analysis.kpis         import KPICalculator
from analysis.predictive   import PredictiveAnalysis
from analysis.prescriptive import PrescriptiveAnalysis
from analysis.base         import AnalysisBase

DB_PATH  = _ROOT / "data" / "mantos.db"
CSV_PATH = _ROOT / "data" / "sap_raw_export.csv"

# ─── Auto-init DB ─────────────────────────────────────────────────────────────
if not DB_PATH.exists():
    from ingestion.ingest import load_data, init_db, insert_orders
    from ingestion.catalog_loader import load_reference_tables
    with st.spinner("⚙️ Inicializando base de datos por primera vez..."):
        df = load_data(CSV_PATH)
        conn = init_db(DB_PATH)
        load_reference_tables(conn)
        insert_orders(conn, df)
        conn.close()
    st.success("✅ Base de datos lista.")
    st.rerun()

# ─── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="MantOS Dashboard",
    page_icon="🏭",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─── Custom CSS ───────────────────────────────────────────────────────────────
st.markdown("""
<style>
    .risk-CRITICO  { color: #ff4b4b; font-weight: bold; }
    .risk-ALTO     { color: #ffa500; font-weight: bold; }
    .risk-MEDIO    { color: #ffd700; font-weight: bold; }
    .risk-BAJO     { color: #00c851; font-weight: bold; }
    .alert-CRITICA { background-color: #3d0000; border-left: 4px solid #ff4b4b; padding: 8px 12px; border-radius: 4px; margin: 4px 0; }
    .alert-ALTA    { background-color: #3d1e00; border-left: 4px solid #ffa500; padding: 8px 12px; border-radius: 4px; margin: 4px 0; }
    .alert-MEDIA   { background-color: #3d3000; border-left: 4px solid #ffd700; padding: 8px 12px; border-radius: 4px; margin: 4px 0; }
    .health-badge  { font-size: 2.5rem; font-weight: 900; }
</style>
""", unsafe_allow_html=True)

# ─── Helpers ──────────────────────────────────────────────────────────────────
RISK_COLORS = {"CRITICO": "#ff4b4b", "ALTO": "#ffa500", "MEDIO": "#ffd700", "BAJO": "#00c851"}
RISK_ORDER  = {"CRITICO": 0, "ALTO": 1, "MEDIO": 2, "BAJO": 3}

def extract_tag(t):
    if pd.isna(t) or not t: return ""
    parts = str(t).split("-")
    return f"{parts[-2]}_{parts[-1]}" if len(parts) >= 2 else t

# ─── Cached data loaders ──────────────────────────────────────────────────────
@st.cache_resource
def _base_conn():
    return AnalysisBase(DB_PATH)

@st.cache_data
def get_lines_and_equipment():
    db = _base_conn()
    df = db.query("SELECT equnr, nombre_equipo, linea, tplnr FROM equipment")
    df["tag"] = df["tplnr"].apply(extract_tag)
    return df

@st.cache_data
def load_kpi_summary(equnr, linea, start, end):
    kpi = KPICalculator(DB_PATH)
    return kpi.get_kpi_summary(equnr=equnr, linea=linea, start_date=start, end_date=end)

@st.cache_data
def load_top_equipment(auart, linea, start, end):
    desc = DescriptiveAnalysis(DB_PATH)
    a = auart[0] if len(auart) == 1 else None
    return desc.get_top_equipment_by_events(n=10, auart=a, linea=linea, start_date=start, end_date=end)

@st.cache_data
def load_temporal_heatmap(equnr, linea, start, end):
    return DescriptiveAnalysis(DB_PATH).get_temporal_heatmap(equnr=equnr, linea=linea, start_date=start, end_date=end)

@st.cache_data
def load_top_keywords(equnr, linea, start, end):
    return DescriptiveAnalysis(DB_PATH).get_top_keywords(equnr=equnr, linea=linea, n=20, start_date=start, end_date=end)

@st.cache_data
def load_pareto(start, end, group_by="equnr", linea=None):
    return DiagnosticAnalysis(DB_PATH).get_pareto(
        metric="downtime", group_by=group_by, linea=linea,
        start_date=start, end_date=end, top_n=15
    )

@st.cache_data
def load_ghost_stops(start, end):
    return DiagnosticAnalysis(DB_PATH).audit_ghost_stops(start_date=start, end_date=end)

@st.cache_data(ttl=3600)
def load_risk_ranking(linea, start, end):
    return PredictiveAnalysis(DB_PATH).get_risk_ranking(linea=linea, start_date=start, end_date=end)

@st.cache_data(ttl=3600)
def load_failure_forecast(equnr, start, end):
    return PredictiveAnalysis(DB_PATH).forecast_failure_rate(equnr=equnr, start_date=start, end_date=end)

@st.cache_data(ttl=3600)
def load_anomalies(equnr, linea, start, end):
    return PredictiveAnalysis(DB_PATH).detect_anomalies(equnr=equnr, linea=linea, start_date=start, end_date=end)

@st.cache_data(ttl=3600)
def load_ml_predictions(linea, start, end):
    return PredictiveAnalysis(DB_PATH).get_all_predictions(linea=linea, start_date=start, end_date=end)

@st.cache_data(ttl=3600)
def load_ml_prediction_single(equnr, start, end):
    return PredictiveAnalysis(DB_PATH).predict_next_failure_probability(equnr=equnr, start_date=start, end_date=end)

@st.cache_data(show_spinner="Calculando plan de acción...", ttl=3600)
def load_action_plan(linea, start, end):
    return PrescriptiveAnalysis(DB_PATH).get_action_plan(linea=linea, start_date=start, end_date=end)

@st.cache_data(show_spinner="Verificando alertas activas...", ttl=3600)
def load_alerts(equnr, linea, start, end):
    return PrescriptiveAnalysis(DB_PATH).check_alerts(equnr=equnr, linea=linea, start_date=start, end_date=end)

@st.cache_data(show_spinner="Calculando salud de planta...", ttl=3600)
def load_plant_health(linea, start, end):
    return PrescriptiveAnalysis(DB_PATH).get_plant_health_score(linea=linea, start_date=start, end_date=end)

@st.cache_data(ttl=3600)
def load_recommendations(equnr, start, end):
    return PrescriptiveAnalysis(DB_PATH).get_recommendations(equnr=equnr, start_date=start, end_date=end)

# ─── Auto-train ML model on first run ─────────────────────────────────────────
@st.cache_resource(show_spinner="🤖 Entrenando modelo ML (primera vez — puede tardar ~60s)...")
def ensure_model_trained():
    pred = PredictiveAnalysis(DB_PATH)
    return pred.train_failure_classifier(force=False)

model_meta = ensure_model_trained()

# ─── Sidebar ──────────────────────────────────────────────────────────────────
st.sidebar.title("🏭 MantOS")
st.sidebar.markdown("**Panel de Control de Mantenimiento**")
st.sidebar.markdown("---")

df_eq = get_lines_and_equipment()
lineas = ["Todas"] + sorted(df_eq["linea"].dropna().unique().tolist())
selected_linea = st.sidebar.selectbox("🏭 Línea de Producción", lineas, key="sel_linea")

equipos_linea = df_eq[df_eq["linea"] == selected_linea] if selected_linea != "Todas" else df_eq
equipos_opciones = ["Todos"] + equipos_linea["equnr"].tolist()

def format_eq(eq):
    if eq == "Todos": return "Todos los Equipos"
    row = df_eq[df_eq["equnr"] == eq]
    if row.empty: return eq
    r = row.iloc[0]
    return f"{r['tag']} — {r['nombre_equipo']}"

selected_equipo = st.sidebar.selectbox("⚙️ Equipo", equipos_opciones, format_func=format_eq, key="sel_eq")

st.sidebar.markdown("---")
start_d = st.sidebar.date_input("📅 Fecha Inicio", value=datetime(2023, 10, 1))
end_d   = st.sidebar.date_input("📅 Fecha Fin",   value=datetime(2026, 3, 31))

st.sidebar.markdown("---")
auart_options = ["PM01 (Correctivo)", "PM02 (Preventivo)", "PM03 (Operacional)"]
selected_auart = st.sidebar.multiselect("🔧 Tipo de Mantenimiento", auart_options, default=auart_options)
auart_codes = [x.split(" ")[0] for x in selected_auart]

# Modelo ML info
if model_meta and "auc_roc_14d" in model_meta:
    st.sidebar.markdown("---")
    st.sidebar.caption(f"🤖 Modelo ML entrenado\n\n"
                       f"AUC 7d: `{model_meta.get('auc_roc_7d', 'N/A')}` | "
                       f"AUC 14d: `{model_meta.get('auc_roc_14d', 'N/A')}`\n\n"
                       f"Muestras: `{model_meta.get('n_samples', 'N/A')}`")

# ─── Resolved params ──────────────────────────────────────────────────────────
start_iso = start_d.strftime("%Y-%m-%dT00:00:00Z")
end_iso   = end_d.strftime("%Y-%m-%dT23:59:59Z")
p_linea   = selected_linea  if selected_linea  != "Todas" else None
p_equnr   = selected_equipo if selected_equipo != "Todos" else None

# ─── Title ────────────────────────────────────────────────────────────────────
scope_label = f"— {p_linea}" if p_linea else "— Toda la Planta"
if p_equnr:
    eq_row = df_eq[df_eq["equnr"] == p_equnr]
    scope_label = f"— {eq_row.iloc[0]['tag']} ({p_equnr})" if not eq_row.empty else f"— {p_equnr}"

st.title(f"Panel de Control {scope_label}")

# ─── Tabs ─────────────────────────────────────────────────────────────────────
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "📊 KPIs",
    "📈 Descriptivo",
    "🛠️ Diagnóstico",
    "🤖 Predictivo",
    "💡 Prescriptivo",
])

# ═══════════════════════════════════════════════════════════════════════════════
# TAB 1 — KPIs
# ═══════════════════════════════════════════════════════════════════════════════
with tab1:
    st.header("KPIs Principales")
    kpi_data = load_kpi_summary(p_equnr, p_linea, start_iso, end_iso)

    total_events = sum(kpi_data["event_counts"].get(code, 0) for code in auart_codes)

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total Eventos", f"{total_events:,}")
    with col2:
        if p_equnr and kpi_data["availability"]:
            avail = kpi_data["availability"].get("availability_pct", 0)
            st.metric("Disponibilidad", f"{avail:.2f}%")
        elif isinstance(kpi_data["availability"], list) and kpi_data["availability"]:
            avg_a = sum(x["availability_pct"] for x in kpi_data["availability"]) / len(kpi_data["availability"])
            st.metric("Disponibilidad Promedio", f"{avg_a:.2f}%")
        else:
            st.metric("Disponibilidad", "N/A")
    with col3:
        st.metric("MTTR (Promedio)", f"{kpi_data['mttr']:.1f} min" if kpi_data["mttr"] else "N/A")
    with col4:
        st.metric("MTBF (Promedio)", f"{kpi_data['mtbf']:.1f} h" if kpi_data["mtbf"] else "N/A")

    st.markdown("---")

    if not p_equnr and isinstance(kpi_data["availability"], list) and kpi_data["availability"]:
        df_avail = pd.DataFrame(kpi_data["availability"])
        if "mttr_min"   not in df_avail.columns: df_avail["mttr_min"]   = 0
        if "mtbf_hours" not in df_avail.columns: df_avail["mtbf_hours"] = 0

        if p_linea:
            st.subheader(f"Comparativa de Equipos — {p_linea}")
            df_plot, x_col, x_label = df_avail, "tag_equipo", "Equipo"
        else:
            st.subheader("Comparativa de Líneas")
            df_plot = df_avail.groupby("linea")[["availability_pct", "mttr_min", "mtbf_hours"]].mean().reset_index()
            x_col, x_label = "linea", "Línea"

        c1, c2, c3 = st.columns(3)
        with c1:
            fig = px.bar(df_plot.sort_values("availability_pct"), x=x_col, y="availability_pct",
                         title="Disponibilidad (%)", color="availability_pct",
                         color_continuous_scale="RdYlGn",
                         labels={"availability_pct": "Disp. (%)", x_col: x_label})
            fig.update_layout(yaxis_range=[max(0, df_plot["availability_pct"].min() - 5), 105], height=400)
            st.plotly_chart(fig, use_container_width=True)
        with c2:
            fig = px.bar(df_plot.sort_values("mttr_min", ascending=False), x=x_col, y="mttr_min",
                         title="MTTR Promedio (min)", color="mttr_min",
                         color_continuous_scale="Reds",
                         labels={"mttr_min": "MTTR (min)", x_col: x_label})
            fig.update_layout(height=400)
            st.plotly_chart(fig, use_container_width=True)
        with c3:
            fig = px.bar(df_plot.sort_values("mtbf_hours"), x=x_col, y="mtbf_hours",
                         title="MTBF Promedio (h)", color="mtbf_hours",
                         color_continuous_scale="Blues",
                         labels={"mtbf_hours": "MTBF (h)", x_col: x_label})
            fig.update_layout(height=400)
            st.plotly_chart(fig, use_container_width=True)

# ═══════════════════════════════════════════════════════════════════════════════
# TAB 2 — DESCRIPTIVO
# ═══════════════════════════════════════════════════════════════════════════════
with tab2:
    st.header(f"Análisis Descriptivo {scope_label}")

    col1, col2 = st.columns([2, 1])
    with col1:
        st.subheader("Top Equipos por Fallas")
        df_top = load_top_equipment(tuple(auart_codes), p_linea, start_iso, end_iso)
        if not df_top.empty:
            df_top["nombre_corto"] = df_top["equnr"].astype(str) + " — " + df_top["nombre_equipo"].fillna("")
            fig = px.bar(df_top, x="event_count", y="nombre_corto", orientation="h",
                         title="Equipos con Mayor Cantidad de Eventos",
                         labels={"event_count": "Cantidad de Eventos", "nombre_corto": "Equipo"},
                         color="downtime_min", color_continuous_scale="Reds")
            fig.update_layout(yaxis={"categoryorder": "total ascending"})
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No hay datos para mostrar.")

    with col2:
        st.subheader("Términos Frecuentes")
        kws = load_top_keywords(p_equnr, p_linea, start_iso, end_iso)
        if kws:
            df_kws = pd.DataFrame(kws, columns=["Término", "Frecuencia"])
            fig = px.bar(df_kws.head(10), x="Frecuencia", y="Término", orientation="h",
                         title="Top 10 Palabras Clave")
            fig.update_layout(yaxis={"categoryorder": "total ascending"}, height=400)
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No hay textos suficientes.")

    st.markdown("---")
    st.subheader("Mapa de Calor Temporal (Día vs Hora)")
    df_heat = load_temporal_heatmap(p_equnr, p_linea, start_iso, end_iso)
    if not df_heat.empty:
        fig = px.imshow(df_heat.T,
                        labels=dict(x="Hora del Día", y="Día de la Semana", color="Eventos"),
                        x=df_heat.index.astype(str) + "h",
                        y=df_heat.columns,
                        color_continuous_scale="YlOrRd", aspect="auto")
        fig.update_layout(height=400)
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No hay datos para el mapa de calor.")

# ═══════════════════════════════════════════════════════════════════════════════
# TAB 3 — DIAGNÓSTICO
# ═══════════════════════════════════════════════════════════════════════════════
with tab3:
    st.header(f"Análisis de Diagnóstico {scope_label}")

    st.subheader("Pareto de Downtime (Regla 80/20)")
    group_param = "linea" if p_linea is None else "equnr"
    df_pareto   = load_pareto(start_iso, end_iso, group_param, p_linea)

    if not df_pareto.empty:
        fig = go.Figure()
        fig.add_trace(go.Bar(
            x=df_pareto["group_key"], y=df_pareto["downtime_min"],
            name="Downtime (min)", marker_color="#2b5797"
        ))
        fig.add_trace(go.Scatter(
            x=df_pareto["group_key"], y=df_pareto["cumulative_pct"],
            name="% Acumulado", yaxis="y2", mode="lines+markers",
            marker_color="#e81123"
        ))
        fig.update_layout(
            xaxis=dict(title="Equipo / Línea"),
            yaxis=dict(title="Downtime (min)"),
            yaxis2=dict(title="% Acumulado", overlaying="y", side="right", range=[0, 105]),
            legend=dict(x=0.01, y=0.99), height=500,
        )
        fig.add_hline(y=80, line_dash="dash", line_color="gray", yref="y2", annotation_text="80%")
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No hay datos suficientes para el Pareto.")

    st.markdown("---")
    st.subheader("Auditoría de Paros Fantasma (is_ghost_stop = 1)")
    ghost_data = load_ghost_stops(start_iso, end_iso)
    if ghost_data["total_ghost_stops"] > 0:
        st.warning(f"Se detectaron **{ghost_data['total_ghost_stops']}** paros fantasma en el período seleccionado.")
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("**Top Generadores (Equipos)**")
            st.dataframe(ghost_data["by_equipment"].head(10), use_container_width=True)
        with c2:
            st.markdown("**Top Generadores (Usuarios)**")
            st.dataframe(ghost_data["by_user"].head(10), use_container_width=True)
    else:
        st.success("¡No se detectaron paros fantasma en este período.")

# ═══════════════════════════════════════════════════════════════════════════════
# TAB 4 — PREDICTIVO
# ═══════════════════════════════════════════════════════════════════════════════
with tab4:
    st.header(f"Análisis Predictivo {scope_label}")

    # ── Sección A: Ranking de Riesgo ──────────────────────────────────────────
    st.subheader("Ranking de Riesgo por Equipo")
    df_risk = load_risk_ranking(p_linea, start_iso, end_iso)

    if not df_risk.empty:
        # Tabla con semáforo de colores
        def style_risk(val):
            c = {"CRITICO": "#ff4b4b", "ALTO": "#ffa500", "MEDIO": "#ffd700", "BAJO": "#00c851"}.get(val, "white")
            return f"color: {c}; font-weight: bold;"

        # Barras de riesgo
        df_display = df_risk[["tag_equipo", "linea", "risk_score", "risk_level", "trend_direction"]].copy()
        df_display.columns = ["Equipo", "Línea", "Risk Score", "Nivel", "Tendencia"]

        # Gráfico barra horizontal de riesgo
        fig_risk = px.bar(
            df_risk.sort_values("risk_score"),
            x="risk_score", y="tag_equipo", orientation="h",
            color="risk_level",
            color_discrete_map=RISK_COLORS,
            category_orders={"risk_level": ["BAJO", "MEDIO", "ALTO", "CRITICO"]},
            title="Score de Riesgo por Equipo",
            labels={"risk_score": "Risk Score (0-100)", "tag_equipo": "Equipo", "risk_level": "Nivel"},
        )
        fig_risk.add_vline(x=70, line_dash="dash", line_color="#ff4b4b", annotation_text="Umbral Crítico")
        fig_risk.add_vline(x=45, line_dash="dot",  line_color="#ffa500", annotation_text="Umbral Alto")
        fig_risk.update_layout(height=max(400, len(df_risk) * 28), xaxis_range=[0, 105])
        st.plotly_chart(fig_risk, use_container_width=True)

        with st.expander("Ver tabla completa de riesgo"):
            st.dataframe(
                df_display.style.map(style_risk, subset=["Nivel"]),
                use_container_width=True,
            )
    else:
        st.info("No hay datos de riesgo disponibles.")

    st.markdown("---")

    # ── Sección B: Predicción ML (7d y 14d) ───────────────────────────────────
    st.subheader("Predicción ML — Probabilidad de Falla")

    col_ml1, col_ml2 = st.columns([1, 2])

    with col_ml1:
        if p_equnr:
            # Equipo seleccionado: gauge individual
            ml_pred = load_ml_prediction_single(p_equnr, start_iso, end_iso)
            prob_7d  = ml_pred.get("prob_7d",  0) or 0
            prob_14d = ml_pred.get("prob_14d", 0) or 0

            for label, prob in [("7 días", prob_7d), ("14 días", prob_14d)]:
                color = "#ff4b4b" if prob >= 0.75 else "#ffa500" if prob >= 0.50 else "#ffd700" if prob >= 0.25 else "#00c851"
                fig_gauge = go.Figure(go.Indicator(
                    mode="gauge+number",
                    value=round(prob * 100, 1),
                    title={"text": f"Prob. Falla {label}"},
                    number={"suffix": "%"},
                    gauge={
                        "axis": {"range": [0, 100]},
                        "bar":  {"color": color},
                        "steps": [
                            {"range": [0,  25], "color": "#1a3a1a"},
                            {"range": [25, 50], "color": "#3a3a1a"},
                            {"range": [50, 75], "color": "#3a2a1a"},
                            {"range": [75, 100], "color": "#3a1a1a"},
                        ],
                        "threshold": {"line": {"color": "white", "width": 2}, "thickness": 0.75, "value": 75},
                    },
                ))
                fig_gauge.update_layout(height=250)
                st.plotly_chart(fig_gauge, use_container_width=True)
        else:
            st.info("Selecciona un equipo específico para ver los gauges de probabilidad ML.")

    with col_ml2:
        # Tabla de predicciones para todos los equipos
        with st.spinner("Calculando predicciones ML..."):
            df_preds = load_ml_predictions(p_linea, start_iso, end_iso)

        if not df_preds.empty:
            # Filtrar solo los que tienen probabilidad
            df_preds_show = df_preds[df_preds["prob_14d"].notna()].copy()
            df_preds_show["prob_7d_pct"]  = (df_preds_show["prob_7d"]  * 100).round(1)
            df_preds_show["prob_14d_pct"] = (df_preds_show["prob_14d"] * 100).round(1)

            fig_ml = px.scatter(
                df_preds_show,
                x="prob_7d_pct", y="prob_14d_pct",
                color="risk_label_14d",
                color_discrete_map=RISK_COLORS,
                hover_data=["tag_equipo", "linea"],
                text="tag_equipo",
                title="Mapa de Riesgo ML: Prob. 7d vs 14d",
                labels={"prob_7d_pct": "Prob. Falla 7 días (%)", "prob_14d_pct": "Prob. Falla 14 días (%)"},
            )
            fig_ml.update_traces(textposition="top center", marker=dict(size=10))
            fig_ml.add_hline(y=75, line_dash="dash", line_color="#ff4b4b", annotation_text="Crítico")
            fig_ml.add_vline(x=75, line_dash="dash", line_color="#ff4b4b")
            fig_ml.update_layout(height=420, showlegend=True)
            st.plotly_chart(fig_ml, use_container_width=True)
        else:
            st.info("No hay predicciones ML disponibles. El modelo puede estar entrenándose.")

    st.markdown("---")

    # ── Sección C: Tendencia de Fallas + Proyección ───────────────────────────
    st.subheader("Tendencia de Fallas y Proyección")
    if p_equnr:
        # Mostrar serie temporal + proyección a futuro
        from analysis.kpis import KPICalculator as _KPI
        df_trend = _KPI(DB_PATH).calc_failure_rate(equnr=p_equnr, freq="W", start_date=start_iso, end_date=end_iso)
        forecast  = load_failure_forecast(p_equnr, start_iso, end_iso)

        if not df_trend.empty:
            fig_trend = go.Figure()
            # Serie histórica
            fig_trend.add_trace(go.Scatter(
                x=df_trend["period"].astype(str), y=df_trend["failure_count"],
                mode="lines+markers", name="Fallas (historial)", line=dict(color="#4fc3f7", width=2),
            ))
            # Punto de proyección
            if forecast.get("predicted_events_next_period") is not None:
                last_period_idx = len(df_trend)
                fig_trend.add_trace(go.Scatter(
                    x=["Próxima semana"], y=[forecast["predicted_events_next_period"]],
                    mode="markers", name=f"Proyección ({forecast['trend']})",
                    marker=dict(color="#ff8f00", size=14, symbol="star"),
                ))
                fig_trend.add_annotation(
                    x="Próxima semana", y=forecast["predicted_events_next_period"],
                    text=f"R²={forecast['confidence_r2']}", showarrow=True, arrowhead=2,
                )
            trend_color = {"deteriorating": "#ff4b4b", "improving": "#00c851", "stable": "#ffd700",
                           "insufficient_data": "gray"}.get(forecast.get("trend", ""), "white")
            fig_trend.update_layout(
                title=f"Tasa de Fallas Semanal — Tendencia: {forecast.get('trend', 'N/A')}",
                xaxis_title="Semana", yaxis_title="Fallas",
                height=380,
                plot_bgcolor="rgba(0,0,0,0)",
                paper_bgcolor="rgba(0,0,0,0)",
            )
            st.plotly_chart(fig_trend, use_container_width=True)
        else:
            st.info("Datos insuficientes para mostrar la tendencia.")
    else:
        st.info("Selecciona un equipo específico para ver la tendencia y proyección de fallas.")

    st.markdown("---")

    # ── Sección D: Detección de Anomalías ─────────────────────────────────────
    st.subheader("Detección de Anomalías Temporales (Z-score)")
    df_anom = load_anomalies(p_equnr, p_linea, start_iso, end_iso)

    if not df_anom.empty:
        n_anom = int(df_anom["is_anomaly"].sum())
        if n_anom > 0:
            st.warning(f"⚠️ Se detectaron **{n_anom}** semanas anómalas en el período.")
        else:
            st.success("✅ No se detectaron semanas anómalas.")

        df_norm = df_anom[df_anom["is_anomaly"] == False]
        df_anml = df_anom[df_anom["is_anomaly"] == True]

        fig_anom = go.Figure()
        # Banda ± 2σ
        fig_anom.add_trace(go.Scatter(
            x=pd.concat([df_anom["period"], df_anom["period"].iloc[::-1]]).astype(str),
            y=pd.concat([df_anom["mean"] + 2 * df_anom["std"], (df_anom["mean"] - 2 * df_anom["std"]).iloc[::-1]]),
            fill="toself", fillcolor="rgba(100,100,100,0.2)", line=dict(color="rgba(0,0,0,0)"),
            name="Banda ±2σ", showlegend=True,
        ))
        # Línea de media
        fig_anom.add_trace(go.Scatter(
            x=df_anom["period"].astype(str), y=df_anom["mean"],
            mode="lines", name="Media", line=dict(color="gray", dash="dash"),
        ))
        # Puntos normales
        if not df_norm.empty:
            fig_anom.add_trace(go.Scatter(
                x=df_norm["period"].astype(str), y=df_norm["event_count"],
                mode="markers+lines", name="Normal",
                marker=dict(color="#4fc3f7", size=7),
                line=dict(color="#4fc3f7"),
            ))
        # Anomalías
        if not df_anml.empty:
            fig_anom.add_trace(go.Scatter(
                x=df_anml["period"].astype(str), y=df_anml["event_count"],
                mode="markers", name="⚠️ Anomalía",
                marker=dict(color="#ff4b4b", size=12, symbol="x"),
            ))
        fig_anom.update_layout(
            xaxis_title="Semana", yaxis_title="Eventos",
            height=420, title="Frecuencia de Eventos — Detección de Anomalías",
        )
        st.plotly_chart(fig_anom, use_container_width=True)
    else:
        st.info("No hay suficientes datos para detectar anomalías (se necesitan al menos 4 semanas).")

# ═══════════════════════════════════════════════════════════════════════════════
# TAB 5 — PRESCRIPTIVO
# ═══════════════════════════════════════════════════════════════════════════════
with tab5:
    st.header(f"Análisis Prescriptivo {scope_label}")

    # ── Sección A: Score de Salud de Planta/Línea ─────────────────────────────
    st.subheader("Score de Salud Operacional")
    health = load_plant_health(p_linea, start_iso, end_iso)

    if health["health_score"] is not None:
        h_score = health["health_score"]
        h_label = health["health_label"]
        h_color = {"SALUDABLE": "#00c851", "ESTABLE": "#ffd700", "EN RIESGO": "#ffa500", "CRITICO": "#ff4b4b"}.get(h_label, "white")

        c_health, c_by_level = st.columns([1, 1])
        with c_health:
            fig_health = go.Figure(go.Indicator(
                mode="gauge+number",
                value=h_score,
                title={
                    "text": f"<b>Salud de {'Línea '+p_linea if p_linea else 'Planta'}</b><br>"
                            f"<span style='font-size:1.1em; color:{h_color}'>{h_label}</span>",
                    "font": {"size": 16},
                },
                number={
                    "suffix": "%",
                    "font": {"color": h_color, "size": 64},
                    "valueformat": ".1f",
                },
                gauge={
                    "axis": {
                        "range": [0, 100],
                        "tickwidth": 1,
                        "tickcolor": "#888",
                        "tickfont": {"size": 12},
                    },
                    "bar": {"color": h_color, "thickness": 0.3},
                    "bgcolor": "rgba(0,0,0,0)",
                    "borderwidth": 0,
                    "steps": [
                        {"range": [0, 35],  "color": "#3a1a1a"},
                        {"range": [35, 55], "color": "#3a2a1a"},
                        {"range": [55, 75], "color": "#3a3a1a"},
                        {"range": [75, 100], "color": "#1a3a1a"},
                    ],
                    "threshold": {
                        "line": {"color": "white", "width": 2},
                        "thickness": 0.75,
                        "value": 55,
                    },
                },
            ))
            fig_health.update_layout(
                height=360,
                margin=dict(t=80, b=30, l=30, r=30),
                paper_bgcolor="rgba(0,0,0,0)",
                font_color="white",
            )
            st.plotly_chart(fig_health, use_container_width=True)

        with c_by_level:
            st.markdown(f"**{health['n_equipos']} equipos analizados**")
            by = health["by_level"]
            fig_donut = px.pie(
                names=["Crítico", "Alto", "Medio", "Bajo"],
                values=[by["CRITICO"], by["ALTO"], by["MEDIO"], by["BAJO"]],
                color=["Crítico", "Alto", "Medio", "Bajo"],
                color_discrete_map={"Crítico": "#ff4b4b", "Alto": "#ffa500", "Medio": "#ffd700", "Bajo": "#00c851"},
                hole=0.55,
                title="Distribución por Nivel de Riesgo",
            )
            fig_donut.update_traces(
                textposition="outside",
                textinfo="label+percent",
                textfont_size=13,
                pull=[0.05, 0.02, 0, 0],
            )
            fig_donut.update_layout(
                height=360,
                margin=dict(t=50, b=20, l=20, r=20),
                legend=dict(orientation="v", yanchor="middle", y=0.5, xanchor="left", x=1.02),
                paper_bgcolor="rgba(0,0,0,0)",
                font_color="white",
            )
            st.plotly_chart(fig_donut, use_container_width=True)
    else:
        st.info("No hay datos suficientes para calcular el score de salud.")

    st.markdown("---")

    # ── Sección B: Alertas Activas ────────────────────────────────────────────
    st.subheader("Alertas Activas")
    with st.spinner("Verificando alertas..."):
        alerts = load_alerts(p_equnr, p_linea, start_iso, end_iso)

    if alerts:
        n_criticas = sum(1 for a in alerts if a["severidad"] == "CRITICA")
        n_altas    = sum(1 for a in alerts if a["severidad"] == "ALTA")
        n_medias   = sum(1 for a in alerts if a["severidad"] == "MEDIA")

        a1, a2, a3 = st.columns(3)
        with a1: st.metric("🔴 Alertas Críticas", n_criticas)
        with a2: st.metric("🟠 Alertas Altas",    n_altas)
        with a3: st.metric("🟡 Alertas Medias",   n_medias)

        for alert in alerts:
            sev    = alert["severidad"]
            icon   = {"CRITICA": "🔴", "ALTA": "🟠", "MEDIA": "🟡", "BAJA": "🟢"}.get(sev, "⚪")
            tag    = alert.get("tag", alert["equnr"])
            linea  = alert.get("linea", "")
            linea_str = f" [{linea}]" if linea else ""
            st.markdown(
                f"""<div class="alert-{sev}">
                    {icon} <strong>[{sev}] {tag}{linea_str}</strong><br>
                    <small>{alert['tipo']}</small> — {alert['mensaje']}
                </div>""",
                unsafe_allow_html=True,
            )
    else:
        st.success("✅ No se detectaron alertas activas para la selección actual.")

    st.markdown("---")

    # ── Sección C: Plan de Acción ─────────────────────────────────────────────
    st.subheader("Plan de Acción Priorizado")
    with st.spinner("Calculando plan de acción..."):
        plan = load_action_plan(p_linea, start_iso, end_iso)

    plan_tabs = st.tabs([
        f"🚨 Urgente ({len(plan['urgente'])})",
        f"📋 Planificado ({len(plan['planificado'])})",
        f"👁️ Monitoreo ({len(plan['monitoreo'])})",
    ])

    def render_plan_cards(items, color):
        if not items:
            st.info("Sin elementos en esta categoría.")
            return
        for item in items:
            ml_str = f" | ML 14d: **{item['ml_prob_14d']*100:.0f}%**" if item.get("ml_prob_14d") else ""
            rec_str = f"\n> {item['top_recommendation']}" if item.get("top_recommendation") else ""
            st.markdown(f"""
**{item['tag_equipo']}** — *{item.get('nombre_equipo', '')}* `[{item.get('linea', '')}]`  
Risk Score: **{item['risk_score']:.0f}/100** `{item['risk_level']}`{ml_str}  
Tendencia: `{item.get('trend', 'N/A')}`{rec_str}
""")
            st.divider()

    with plan_tabs[0]:
        render_plan_cards(plan["urgente"], "#ff4b4b")
    with plan_tabs[1]:
        render_plan_cards(plan["planificado"], "#ffa500")
    with plan_tabs[2]:
        render_plan_cards(plan["monitoreo"], "#4fc3f7")

    # ── Sección D: Recomendaciones detalladas (solo si hay equipo seleccionado) ──
    if p_equnr:
        st.markdown("---")
        st.subheader(f"Recomendaciones Detalladas — {scope_label}")
        with st.spinner("Generando recomendaciones..."):
            recs = load_recommendations(p_equnr, start_iso, end_iso)

        urgency_icons = {"URGENTE": "🚨", "PLANIFICADO": "📋", "MONITOREO": "👁️"}
        fuente_icons  = {"ML": "🤖", "KPI": "📊", "AUDITORIA": "🔍"}

        for rec in recs:
            urg_key = rec["urgencia"].split("(")[0].strip().upper()
            icon    = urgency_icons.get(urg_key, "📌")
            src     = fuente_icons.get(rec.get("fuente", ""), "📌")
            with st.expander(f"{icon} [{rec['urgencia']}] {src} {rec['tipo']} — {rec['mensaje'][:80]}..."):
                st.markdown(f"**Acción:** {rec['mensaje']}")
                st.markdown(f"**Justificación técnica:** _{rec['justificacion']}_")
                st.markdown(f"**Fuente:** `{rec.get('fuente', 'N/A')}`")
