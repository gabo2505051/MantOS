"""
test_config.py — Pruebas Unitarias para el Módulo de Configuración Centralizada
-----------------------------------------------------------------------------
Verifica la lectura de config.yaml, los fallbacks de seguridad, las ponderaciones
de modelos y la integración con los motores prescriptivos y de riesgo.
"""

import pytest
from pathlib import Path
from config_loader import (
    load_config,
    get_config,
    get_thresholds,
    get_risk_weights,
    get_operation_params,
    DEFAULT_CONFIG,
)
from analysis.prescriptive import THRESHOLDS


class TestConfigLoader:

    def test_load_config_structure(self):
        cfg = get_config()
        assert isinstance(cfg, dict)
        assert "client" in cfg
        assert "operation" in cfg
        assert "risk_model" in cfg
        assert "prescriptive" in cfg

    def test_client_metadata_present(self):
        cfg = get_config()
        client = cfg.get("client", {})
        assert "name" in client
        assert "facility" in client
        assert "environment" in client

    def test_get_thresholds_valid(self):
        th = get_thresholds()
        assert isinstance(th, dict)
        assert "risk_score_critical" in th
        assert "risk_score_high" in th
        assert th["risk_score_critical"] > th["risk_score_high"]

    def test_get_risk_weights_sum_to_one(self):
        weights = get_risk_weights()
        assert isinstance(weights, dict)
        total_weight = sum(weights.values())
        assert abs(total_weight - 1.0) < 1e-5, f"La suma de pesos debe ser 1.0, fue {total_weight}"

    def test_get_operation_params(self):
        op = get_operation_params()
        assert isinstance(op, dict)
        assert op.get("operating_hours_per_day") == 24.0

    def test_fallback_on_non_existent_file(self):
        fake_path = Path("/tmp/non_existent_config_12345.yaml")
        cfg = load_config(fake_path)
        assert cfg == DEFAULT_CONFIG

    def test_prescriptive_thresholds_synced(self):
        th = get_thresholds()
        assert THRESHOLDS["risk_score_critical"] == th["risk_score_critical"]
        assert THRESHOLDS["risk_score_high"] == th["risk_score_high"]
