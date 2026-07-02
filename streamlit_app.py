import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime
from pathlib import Path
import sys

# Ensure MantOS modules can be imported
_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(_ROOT))

from analysis.descriptive import DescriptiveAnalysis
from analysis.diagnostic import DiagnosticAnalysis
from analysis.kpis import KPICalculator
from analysis.base import AnalysisBase

DB_PATH = _ROOT / "data" / "mantos.db"

# Page config
st.set_page_config(page_title="MantOS Dashboard", page_icon="🏭", layout="wide")

# Custom CSS
st.markdown("""
<style>
    .metric-card {
        background-color: #1e1e1e;
        padding: 20px;
        border-radius: 10px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.3);
    }
</style>
""", unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# Data Loading & Caching
# -----------------------------------------------------------------------------
@st.cache_resource
def get_db_connection():
    return AnalysisBase(DB_PATH)

@st.cache_data
def get_lines_and_equipment():
    db = get_db_connection()
    df_eq = db.query("SELECT equnr, nombre_equipo, linea, tplnr FROM equipment")
    # Parse tag from tplnr
    def extract_tag(t):
        if pd.isna(t): return ""
        parts = str(t).split("-")
        return f"{parts[-2]}_{parts[-1]}" if len(parts) >= 2 else t
    df_eq["tag"] = df_eq["tplnr"].apply(extract_tag)
    return df_eq

@st.cache_data
def load_kpi_summary(equnr, linea, start, end):
    # Cache busted for new metrics
    kpi = KPICalculator(DB_PATH)
    return kpi.get_kpi_summary(equnr=equnr, linea=linea, start_date=start, end_date=end)

@st.cache_data
def load_top_equipment(auart, linea, start, end):
    desc = DescriptiveAnalysis(DB_PATH)
    # The underlying method accepts a single auart string currently. 
    # Let's use None to get all if multiple are selected, or the first one.
    if len(auart) == 1:
        a = auart[0]
    else:
        a = None # all
    return desc.get_top_equipment_by_events(n=10, auart=a, linea=linea, start_date=start, end_date=end)

@st.cache_data
def load_temporal_heatmap(equnr, linea, start, end):
    desc = DescriptiveAnalysis(DB_PATH)
    return desc.get_temporal_heatmap(equnr=equnr, linea=linea, start_date=start, end_date=end)

@st.cache_data
def load_top_keywords(equnr, linea, start, end):
    desc = DescriptiveAnalysis(DB_PATH)
    return desc.get_top_keywords(equnr=equnr, linea=linea, n=20, start_date=start, end_date=end)

@st.cache_data
def load_pareto(start, end, group_by="equnr", linea=None):
    diag = DiagnosticAnalysis(DB_PATH)
    return diag.get_pareto(metric="downtime", group_by=group_by, linea=linea, start_date=start, end_date=end, top_n=15)

@st.cache_data
def load_ghost_stops(start, end):
    diag = DiagnosticAnalysis(DB_PATH)
    return diag.audit_ghost_stops(start_date=start, end_date=end)

# -----------------------------------------------------------------------------
# Sidebar
# -----------------------------------------------------------------------------
st.sidebar.title("🏭 MantOS Dashboard")
st.sidebar.markdown("---")

df_eq = get_lines_and_equipment()
lineas = ["Todas"] + sorted(df_eq["linea"].dropna().unique().tolist())
selected_linea = st.sidebar.selectbox("Línea de Producción", lineas)

if selected_linea != "Todas":
    equipos_linea = df_eq[df_eq["linea"] == selected_linea]
else:
    equipos_linea = df_eq

equipos_opciones = ["Todos"] + equipos_linea["equnr"].tolist()
# Create a formatting function for the equipment dropdown
def format_eq(eq):
    if eq == "Todos": return "Todos los Equipos"
    row = df_eq[df_eq["equnr"] == eq].iloc[0]
    return f"{row['tag']} - {row['nombre_equipo']}"

selected_equipo = st.sidebar.selectbox("Equipo", equipos_opciones, format_func=format_eq)

st.sidebar.markdown("---")
# Date range
start_d = st.sidebar.date_input("Fecha Inicio", value=datetime(2023, 10, 1))
end_d = st.sidebar.date_input("Fecha Fin", value=datetime(2026, 3, 31))

# Convert to ISO format
start_iso = start_d.strftime("%Y-%m-%dT00:00:00Z")
end_iso = end_d.strftime("%Y-%m-%dT23:59:59Z")

st.sidebar.markdown("---")
# Maintenance type
auart_options = ["PM01 (Correctivo)", "PM02 (Preventivo)", "PM03 (Operacional)"]
selected_auart = st.sidebar.multiselect("Tipo de Mantenimiento", auart_options, default=auart_options)
# Map back to codes
auart_codes = [x.split(" ")[0] for x in selected_auart]

# Params for backend
p_linea = selected_linea if selected_linea != "Todas" else None
p_equnr = selected_equipo if selected_equipo != "Todos" else None

# -----------------------------------------------------------------------------
# Main Content
# -----------------------------------------------------------------------------
st.title("Panel de Control — Análisis de Mantenimiento")

tab1, tab2, tab3 = st.tabs(["📊 Resumen General y KPIs", "📈 Análisis Descriptivo", "🛠️ Diagnóstico"])

with tab1:
    st.header("KPIs Principales")
    kpi_data = load_kpi_summary(p_equnr, p_linea, start_iso, end_iso)
    
    # Calculate some aggregates
    total_events = sum(kpi_data["event_counts"].get(code, 0) for code in auart_codes)
    
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total Eventos", f"{total_events:,}")
    with col2:
        # Availability
        if p_equnr and kpi_data["availability"]:
            avail = kpi_data["availability"].get("availability_pct", 0)
            st.metric("Disponibilidad", f"{avail:.2f}%")
        elif isinstance(kpi_data["availability"], list) and len(kpi_data["availability"]) > 0:
            avg_avail = sum(x["availability_pct"] for x in kpi_data["availability"]) / len(kpi_data["availability"])
            st.metric("Disponibilidad Promedio", f"{avg_avail:.2f}%")
        else:
            st.metric("Disponibilidad", "N/A")
            
    with col3:
        if kpi_data["mttr"]:
            st.metric("MTTR (Promedio)", f"{kpi_data['mttr']:.1f} min")
        else:
            st.metric("MTTR (Promedio)", "N/A")
            
    with col4:
        if kpi_data["mtbf"]:
            st.metric("MTBF", f"{kpi_data['mtbf']:.1f} h")
        else:
            st.metric("MTBF", "N/A")
            
    st.markdown("---")
    
    if not p_equnr and isinstance(kpi_data["availability"], list) and len(kpi_data["availability"]) > 0:
        df_avail = pd.DataFrame(kpi_data["availability"])
        
        # Fallback para evitar errores si el caché de Streamlit está desactualizado
        if "mttr_min" not in df_avail.columns:
            df_avail["mttr_min"] = 0
        if "mtbf_hours" not in df_avail.columns:
            df_avail["mtbf_hours"] = 0
            
        if p_linea:
            st.subheader(f"Comparativa de Equipos - Línea {p_linea}")
            df_plot = df_avail
            x_col = "tag_equipo"
            x_label = "Equipo"
        else:
            st.subheader("Comparativa de Líneas")
            df_plot = df_avail.groupby("linea")[["availability_pct", "mttr_min", "mtbf_hours"]].mean().reset_index()
            x_col = "linea"
            x_label = "Línea"
            
        c1, c2, c3 = st.columns(3)
        with c1:
            fig1 = px.bar(df_plot.sort_values("availability_pct"), 
                         x=x_col, y="availability_pct", 
                         title="Disponibilidad",
                         color="availability_pct", color_continuous_scale="RdYlGn",
                         labels={"availability_pct": "Disp. (%)", x_col: x_label})
            fig1.update_layout(yaxis_range=[max(0, df_plot["availability_pct"].min() - 5), 105], height=400)
            st.plotly_chart(fig1, use_container_width=True)
        with c2:
            fig2 = px.bar(df_plot.sort_values("mttr_min", ascending=False), 
                         x=x_col, y="mttr_min", 
                         title="MTTR Promedio",
                         color="mttr_min", color_continuous_scale="Reds",
                         labels={"mttr_min": "MTTR (min)", x_col: x_label})
            fig2.update_layout(height=400)
            st.plotly_chart(fig2, use_container_width=True)
        with c3:
            fig3 = px.bar(df_plot.sort_values("mtbf_hours"), 
                         x=x_col, y="mtbf_hours", 
                         title="MTBF Promedio",
                         color="mtbf_hours", color_continuous_scale="Blues",
                         labels={"mtbf_hours": "MTBF (h)", x_col: x_label})
            fig3.update_layout(height=400)
            st.plotly_chart(fig3, use_container_width=True)

with tab2:
    st.header("Análisis Descriptivo")
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.subheader("Top Equipos por Fallas")
        df_top = load_top_equipment(auart_codes, p_linea, start_iso, end_iso)
        if not df_top.empty:
            df_top["nombre_corto"] = df_top["equnr"].astype(str) + " - " + df_top["nombre_equipo"].fillna("")
            fig = px.bar(df_top, x="event_count", y="nombre_corto", orientation='h',
                         title="Equipos con Mayor Cantidad de Eventos",
                         labels={"event_count": "Cantidad de Eventos", "nombre_corto": "Equipo"},
                         color="downtime_min", color_continuous_scale="Reds")
            fig.update_layout(yaxis={'categoryorder':'total ascending'})
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No hay datos para mostrar.")
            
    with col2:
        st.subheader("Términos Frecuentes")
        kws = load_top_keywords(p_equnr, p_linea, start_iso, end_iso)
        if kws:
            df_kws = pd.DataFrame(kws, columns=["Término", "Frecuencia"])
            fig = px.bar(df_kws.head(10), x="Frecuencia", y="Término", orientation='h',
                         title="Top 10 Palabras Clave")
            fig.update_layout(yaxis={'categoryorder':'total ascending'}, height=400)
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
                        color_continuous_scale="YlOrRd",
                        aspect="auto")
        fig.update_layout(height=400)
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No hay datos para el mapa de calor.")

with tab3:
    st.header("Análisis de Diagnóstico")
    
    st.subheader("Pareto de Downtime (Regla 80/20)")
    group_param = "linea" if p_linea is None else "equnr"
    df_pareto = load_pareto(start_iso, end_iso, group_param, p_linea)
    
    if not df_pareto.empty:
        fig = go.Figure()
        
        # Bar chart for downtime
        fig.add_trace(go.Bar(
            x=df_pareto["group_key"],
            y=df_pareto["downtime_min"],
            name="Downtime (min)",
            marker_color="#2b5797"
        ))
        
        # Line chart for cumulative percentage
        fig.add_trace(go.Scatter(
            x=df_pareto["group_key"],
            y=df_pareto["cumulative_pct"],
            name="% Acumulado",
            yaxis="y2",
            mode="lines+markers",
            marker_color="#e81123"
        ))
        
        fig.update_layout(
            xaxis=dict(title="Equipo / Línea"),
            yaxis=dict(title="Downtime (min)"),
            yaxis2=dict(
                title="Porcentaje Acumulado (%)",
                overlaying="y",
                side="right",
                range=[0, 105]
            ),
            legend=dict(x=0.01, y=0.99),
            height=500
        )
        
        # 80% line
        fig.add_hline(y=80, line_dash="dash", line_color="gray", yref="y2", annotation_text="80%")
        
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No hay datos suficientes para el Pareto.")
        
    st.markdown("---")
    st.subheader("Auditoría de Paros Fantasma (is_ghost_stop = 1)")
    
    ghost_data = load_ghost_stops(start_iso, end_iso)
    if ghost_data["total_ghost_stops"] > 0:
        st.warning(f"Se detectaron {ghost_data['total_ghost_stops']} paros fantasma en el período seleccionado.")
        
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("**Top Generadores (Equipos)**")
            st.dataframe(ghost_data["by_equipment"].head(10), use_container_width=True)
            
        with c2:
            st.markdown("**Top Generadores (Usuarios)**")
            st.dataframe(ghost_data["by_user"].head(10), use_container_width=True)
    else:
        st.success("¡Excelente! No se detectaron paros fantasma en este período.")

