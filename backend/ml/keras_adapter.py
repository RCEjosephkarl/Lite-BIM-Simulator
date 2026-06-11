"""Keras 3 compatible dependency and detector adapter."""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path
from typing import Any


def dependency_status() -> dict[str, Any]:
    keras = importlib.util.find_spec("keras") is not None
    keras_hub = importlib.util.find_spec("keras_hub") is not None
    keras_cv = importlib.util.find_spec("keras_cv") is not None
    backend = os.getenv("KERAS_BACKEND", "default") if keras else None
    weights = os.getenv("TIMBERBIM_PLAN_MODEL", "")
    available = bool(weights and Path(weights).exists())
    warnings = []
    if not keras:
        warnings.append("Keras 3 is not installed; core BIM features remain available.")
    if keras and not (keras_hub or keras_cv):
        warnings.append("Install KerasHub or legacy KerasCV for detector components.")
    if not available:
        warnings.append("ML model not configured; no geometry will be inferred.")
    return {
        "dependencies_installed": keras,
        "keras_hub": keras_hub,
        "keras_cv": keras_cv,
        "backend": backend,
        "model_available": available,
        "model_path": weights if available else None,
        "warnings": warnings,
    }


class KerasDetectorAdapter:
    """Thin adapter boundary for a future segmentation/object detector."""

    def __init__(self, model_path: str | None = None):
        status = dependency_status()
        path = model_path or status["model_path"]
        if not status["dependencies_installed"] or not path:
            raise RuntimeError("ML model not configured")
        import keras
        self.model = keras.models.load_model(path)

    def predict(self, batch):
        return self.model.predict(batch)
