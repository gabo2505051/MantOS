"""
config_loader.py — Módulo Cargador de Configuración Centralizada de MantOS
-------------------------------------------------------------------------
Carga dinámicamente el archivo `config.yaml` y expone funciones auxiliares
para acceder a los umbrales prescriptivos, pesos de modelos y parámetros operacionales.
Incluye fallbacks por omisión para garantizar cero excepciones si el archivo no existe.
"""

from pathlib import Path
from typing import Dict, Any
import yaml

_CONFIG_PATH = Path(__file__).resolve().parent / "config.yaml"

# Configuración por omisión (fallback de seguridad)
DEFAULT_CONFIG: Dict[str, Any] = {
    "client": {
        "name": "Planta Galletera Sur (PGS)",
        "facility": "Línea LA4",
        "environment": "production",
    },
    "operation": {
        "operating_hours_per_day": 24.0,
        "ml_lookback_days": 60,
        "ml_step_days": 14,
    },
    "risk_model": {
        "weights": {
            "frecuencia_reciente": 0.40,
            "tendencia_mtbf": 0.30,
            "recurrencia": 0.20,
            "ghost_stops_pct": 0.10,
        }
    },
    "prescriptive": {
        "thresholds": {
            "risk_score_critical": 70.0,
            "risk_score_high": 45.0,
            "ml_prob_critical": 0.75,
            "ml_prob_high": 0.50,
            "availability_critical": 0.95,
            "mttr_high_min": 60.0,
            "mtbf_drop_pct": 0.30,
            "ghost_pct_warning": 0.20,
            "weekly_spike_zscore": 2.0,
        }
    },
}


def load_config(config_path: Path = _CONFIG_PATH) -> Dict[str, Any]:
    """
    Carga el archivo YAML de configuración. Si el archivo no existe o contiene errores,
    devuelve la configuración por omisión (DEFAULT_CONFIG).
    """
    if not config_path.exists():
        return DEFAULT_CONFIG

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
            return cfg if isinstance(cfg, dict) else DEFAULT_CONFIG
    except Exception:
        return DEFAULT_CONFIG


# Instancia global de configuración cargada al importar el módulo
CONFIG = load_config()


def get_config() -> Dict[str, Any]:
    """Retorna la configuración completa del sistema."""
    return CONFIG


def get_thresholds() -> Dict[str, float]:
    """Retorna el diccionario de umbrales prescriptivos."""
    return CONFIG.get("prescriptive", {}).get("thresholds", DEFAULT_CONFIG["prescriptive"]["thresholds"])


def get_risk_weights() -> Dict[str, float]:
    """Retorna el diccionario de ponderaciones para el cálculo de score de riesgo."""
    return CONFIG.get("risk_model", {}).get("weights", DEFAULT_CONFIG["risk_model"]["weights"])


def get_operation_params() -> Dict[str, Any]:
    """Retorna los parámetros operacionales (horas diarias, lookback ML, etc.)."""
    return CONFIG.get("operation", DEFAULT_CONFIG["operation"])

