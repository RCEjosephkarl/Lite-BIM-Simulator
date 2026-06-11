"""Review-first optional drawing-plan analysis pipeline."""

from __future__ import annotations

from .keras_adapter import KerasDetectorAdapter, dependency_status
from .postprocess import proposals_from_detections
from .preprocess import preprocess_image


def status() -> dict:
    result = dependency_status()
    result.update({
        "active_adapter": (
            "keras_hub" if result["keras_hub"]
            else "keras_cv" if result["keras_cv"] else None
        ),
        "experimental": True,
        "commit_policy": "review_required",
    })
    return result


def analyze_image(
    content: bytes, drawing_id: str, level: int = 1,
    scale_mm_per_px: float | None = None,
) -> dict:
    current = status()
    if not current["model_available"]:
        return {
            "status": "model_not_configured",
            "proposals": [],
            "scale_assumptions": {
                "scale_mm_per_px": scale_mm_per_px,
                "source": "manifest" if scale_mm_per_px else "unknown",
            },
            "warnings": current["warnings"] + [
                "No geometry was generated. Configure trained weights and review all future detections."
            ],
        }
    prepared = preprocess_image(content)
    detector = KerasDetectorAdapter()
    # The adapter output contract is intentionally explicit; a trained model
    # must return decoded detection dictionaries through its serving wrapper.
    raw = detector.predict([prepared["image"]])
    detections = raw if isinstance(raw, list) else []
    for detection in detections:
        detection.setdefault("level", level)
    proposals, warnings = proposals_from_detections(
        detections, drawing_id, scale_mm_per_px)
    return {
        "status": "proposal_ready",
        "proposals": proposals,
        "scale_assumptions": {"scale_mm_per_px": scale_mm_per_px},
        "warnings": warnings + [
            "AI extraction is approximate and requires qualified review."
        ],
    }
