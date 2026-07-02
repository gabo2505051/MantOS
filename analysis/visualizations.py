"""
visualizations.py
-----------------
Generador de gráficos para los reportes de MantOS usando Matplotlib.
Guarda las imágenes PNG en la ruta data/assets/ para que puedan ser incrustadas
en los PDFs generados.
"""

import os
from pathlib import Path
from typing import Optional

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

# Directorio donde se guardarán temporalmente los assets gráficos
ASSETS_DIR = Path(__file__).resolve().parent.parent / "data" / "assets"
ASSETS_DIR.mkdir(parents=True, exist_ok=True)

# Estilo global de MantOS
plt.style.use('seaborn-v0_8-darkgrid')
plt.rcParams.update({
    'font.size': 10,
    'axes.titlesize': 14,
    'axes.labelsize': 12,
    'xtick.labelsize': 10,
    'ytick.labelsize': 10,
    'legend.fontsize': 10,
    'figure.titlesize': 16,
    'figure.dpi': 150,
})

_COLOR_PRIMARY = '#2b5797'
_COLOR_SECONDARY = '#e81123'
_COLOR_SUCCESS = '#00a300'
_COLOR_WARNING = '#ffb900'


class ChartGenerator:
    """Clase estática para generar gráficos específicos de MantOS."""

    @staticmethod
    def plot_pareto(df: pd.DataFrame, title: str, output_filename: str) -> str:
        """
        Genera un diagrama de Pareto (barras + línea acumulada) a partir
        de un DataFrame con 'group_key', 'downtime_min', 'cumulative_pct'.
        """
        out_path = ASSETS_DIR / output_filename
        
        # Limitar a top 10 para claridad visual
        plot_df = df.head(10).copy()
        if plot_df.empty or "downtime_min" not in plot_df.columns:
            return ""

        fig, ax1 = plt.subplots(figsize=(10, 5))

        # Eje Y principal: barras de downtime
        bars = ax1.bar(plot_df["group_key"], plot_df["downtime_min"], color=_COLOR_PRIMARY, alpha=0.7)
        ax1.set_ylabel("Downtime (minutos)", color=_COLOR_PRIMARY)
        ax1.tick_params(axis='y', labelcolor=_COLOR_PRIMARY)
        ax1.set_xticks(np.arange(len(plot_df)))
        ax1.set_xticklabels(plot_df["group_key"], rotation=45, ha='right')

        # Eje Y secundario: curva de % acumulado
        ax2 = ax1.twinx()
        ax2.plot(plot_df["group_key"], plot_df["cumulative_pct"], color=_COLOR_SECONDARY, marker='o', linewidth=2)
        ax2.set_ylabel("Porcentaje Acumulado (%)", color=_COLOR_SECONDARY)
        ax2.tick_params(axis='y', labelcolor=_COLOR_SECONDARY)
        ax2.set_ylim([0, 105])

        # Linea de 80% (Regla 80/20)
        ax2.axhline(80, color='grey', linestyle='--', alpha=0.5)

        plt.title(title)
        fig.tight_layout()
        plt.savefig(out_path, format='png')
        plt.close(fig)

        return str(out_path.absolute()).replace("\\", "/")

    @staticmethod
    def plot_kpi_trend(df: pd.DataFrame, title: str, output_filename: str) -> str:
        """
        Genera un gráfico de línea para la tasa de fallas (eventos en el tiempo)
        y su media móvil. Recibe el dataframe de calc_failure_rate().
        """
        out_path = ASSETS_DIR / output_filename

        if df.empty or "period" not in df.columns or "failure_count" not in df.columns:
            return ""

        fig, ax = plt.subplots(figsize=(10, 4))
        
        ax.plot(df["period"], df["failure_count"], color=_COLOR_PRIMARY, marker='o', linestyle='-', label='Eventos')
        
        if "rolling_mean_4" in df.columns:
            ax.plot(df["period"], df["rolling_mean_4"], color=_COLOR_WARNING, linestyle='--', linewidth=2, label='Media Móvil (4 per.)')

        # Mejorar formato de fechas si hay muchas
        if len(df) > 12:
            ax.set_xticks(np.arange(0, len(df), max(1, len(df)//12)))
        ax.set_xticklabels(df["period"][ax.get_xticks()], rotation=45, ha='right')

        ax.set_ylabel("Cantidad de Eventos")
        ax.legend(loc='upper left')
        plt.title(title)
        fig.tight_layout()
        plt.savefig(out_path, format='png')
        plt.close(fig)

        return str(out_path.absolute()).replace("\\", "/")

    @staticmethod
    def plot_heatmap(df: pd.DataFrame, title: str, output_filename: str) -> str:
        """
        Genera un mapa de calor temporal (Días x Horas).
        """
        out_path = ASSETS_DIR / output_filename
        
        if df.empty:
            return ""

        fig, ax = plt.subplots(figsize=(8, 6))
        
        # Plotear imshow
        cax = ax.imshow(df.values, cmap='YlOrRd', aspect='auto')
        
        ax.set_xticks(np.arange(len(df.columns)))
        ax.set_yticks(np.arange(len(df.index)))
        ax.set_xticklabels(df.columns)
        ax.set_yticklabels(df.index)
        
        plt.setp(ax.get_xticklabels(), rotation=45, ha="right", rotation_mode="anchor")

        # Colorbar
        cbar = fig.colorbar(cax, ax=ax)
        cbar.ax.set_ylabel('N° de Eventos', rotation=-90, va="bottom")

        plt.title(title)
        fig.tight_layout()
        plt.savefig(out_path, format='png')
        plt.close(fig)

        return str(out_path.absolute()).replace("\\", "/")

    @staticmethod
    def plot_kpi_comparison(df: pd.DataFrame, title: str, output_filename: str) -> str:
        """
        Genera un gráfico de barras comparativo de Disponibilidad, MTTR y MTBF 
        para un conjunto de equipos.
        df debe contener: 'equnr', 'availability_pct', 'mttr_min', 'mtbf_hours'
        """
        out_path = ASSETS_DIR / output_filename
        
        if df.empty or "availability_pct" not in df.columns:
            return ""

        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))
        
        if "tag_equipo" in df.columns:
            equipos = df["tag_equipo"].astype(str)
        else:
            equipos = df["equnr"].astype(str)
        x = np.arange(len(equipos))
        width = 0.35

        # Subplot 1: Disponibilidad
        ax1.bar(equipos, df["availability_pct"], color=_COLOR_SUCCESS, alpha=0.8)
        ax1.set_ylabel("Disponibilidad (%)")
        ax1.set_title("Disponibilidad por Equipo")
        ax1.set_ylim([max(0, df["availability_pct"].min() - 5), 105])
        ax1.tick_params(axis='x', rotation=45)

        # Subplot 2: MTTR vs MTBF (Dual Axis)
        # Reemplazar NaN/None con 0
        mttr = df.get("mttr_min", pd.Series([0]*len(df))).fillna(0)
        mtbf = df.get("mtbf_hours", pd.Series([0]*len(df))).fillna(0)

        bars = ax2.bar(x - width/2, mttr, width, color=_COLOR_SECONDARY, label='MTTR (min)')
        ax2.set_ylabel("MTTR (minutos)", color=_COLOR_SECONDARY)
        ax2.tick_params(axis='y', labelcolor=_COLOR_SECONDARY)
        ax2.set_xticks(x)
        ax2.set_xticklabels(equipos, rotation=45, ha='right')

        ax3 = ax2.twinx()
        lines = ax3.bar(x + width/2, mtbf, width, color=_COLOR_PRIMARY, label='MTBF (horas)')
        ax3.set_ylabel("MTBF (horas)", color=_COLOR_PRIMARY)
        ax3.tick_params(axis='y', labelcolor=_COLOR_PRIMARY)

        # Leyendas combinadas
        ax2.set_title("Mantenibilidad (MTTR) vs Confiabilidad (MTBF)")
        
        fig.suptitle(title, fontsize=14)
        fig.tight_layout()
        plt.savefig(out_path, format='png')
        plt.close(fig)

        return str(out_path.absolute()).replace("\\", "/")

    @staticmethod
    def cleanup_assets():
        """Elimina todos los archivos PNG temporales en la carpeta assets."""
        if ASSETS_DIR.exists():
            for f in ASSETS_DIR.glob("*.png"):
                try:
                    f.unlink()
                except OSError:
                    pass
