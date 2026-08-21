"""
test_mlops.py — Pruebas Unitarias MLOps para la Persistencia del Modelo con Joblib
----------------------------------------------------------------------------------
Verifica la generación del archivo failure_classifier.joblib, la velocidad de carga
sub-segundo (< 100ms) y la integridad de las predicciones.
"""

import time
import pytest
from pathlib import Path
import joblib
from analysis.predictive import PredictiveAnalysis, _MODEL_PATH


class TestMLOpsJoblib:

    def test_train_creates_joblib_file(self):
        pred = PredictiveAnalysis()
        meta = pred.train_failure_classifier(force=False)
        assert _MODEL_PATH.exists(), f"El archivo {_MODEL_PATH} debe existir tras el entrenamiento."
        assert _MODEL_PATH.suffix == ".joblib"
        assert "auc_roc_7d" in meta
        assert "auc_roc_14d" in meta

    def test_joblib_fast_load_under_100ms(self):
        assert _MODEL_PATH.exists()
        start = time.perf_counter()
        clf_dict = joblib.load(_MODEL_PATH)
        elapsed_ms = (time.perf_counter() - start) * 1000.0

        assert isinstance(clf_dict, dict)
        assert "clf7" in clf_dict
        assert "clf14" in clf_dict
        assert elapsed_ms < 100.0, f"La carga del modelo tomó {elapsed_ms:.2f}ms, debe ser < 100ms."

    def test_prediction_integrity(self):
        pred = PredictiveAnalysis()
        result = pred.predict_next_failure_probability(equnr="10004003")
        assert "prob_7d" in result
        assert "prob_14d" in result
        assert result.get("model_available") is True
