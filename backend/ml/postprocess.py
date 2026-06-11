"""Convert detector output into review-only BIM proposals."""

from __future__ import annotations

from typing import Any
import math

CLASSES = {
    "exterior_wall", "interior_wall", "door_opening", "window_opening",
    "garage_opening", "truss_line", "dimension_text", "grid_line", "ignore",
}


def _line(proposal: dict) -> tuple[list[float], list[float]] | None:
    geometry = proposal.get("geometry", {})
    start, end = geometry.get("start"), geometry.get("end")
    if (isinstance(start, list) and isinstance(end, list)
            and len(start) == 2 and len(end) == 2):
        return start, end
    return None


def snap_near_endpoints(proposals: list[dict], tolerance_px: float = 8) -> None:
    """Snap line endpoints to a shared average without creating new lines."""
    points = [
        point for proposal in proposals if _line(proposal)
        for point in _line(proposal)  # type: ignore[union-attr]
    ]
    for point in points:
        near = [
            other for other in points
            if math.hypot(point[0] - other[0], point[1] - other[1])
            <= tolerance_px
        ]
        if len(near) > 1:
            point[0] = sum(other[0] for other in near) / len(near)
            point[1] = sum(other[1] for other in near) / len(near)


def merge_collinear_wall_fragments(
    proposals: list[dict], angle_tolerance_deg: float = 4,
    gap_tolerance_px: float = 12,
) -> list[dict]:
    """Merge touching wall fragments only when detector lines are collinear."""
    output: list[dict] = []
    for proposal in proposals:
        line = _line(proposal)
        if not line or proposal.get("type") not in {
            "exterior_wall", "interior_wall"}:
            output.append(proposal)
            continue
        start, end = line
        angle = math.atan2(end[1] - start[1], end[0] - start[0])
        merged = False
        for current in output:
            current_line = _line(current)
            if (not current_line or current.get("type") != proposal.get("type")
                    or current.get("level") != proposal.get("level")):
                continue
            a, b = current_line
            other_angle = math.atan2(b[1] - a[1], b[0] - a[0])
            delta = abs(math.atan2(
                math.sin(angle - other_angle), math.cos(angle - other_angle)))
            gap = min(
                math.hypot(point[0] - other[0], point[1] - other[1])
                for point in (start, end) for other in (a, b))
            if math.degrees(delta) <= angle_tolerance_deg and gap <= gap_tolerance_px:
                points = (start, end, a, b)
                pair = max(
                    ((left, right) for left in points for right in points),
                    key=lambda pair_: math.hypot(
                        pair_[0][0] - pair_[1][0], pair_[0][1] - pair_[1][1]))
                current["geometry"]["start"] = list(pair[0])
                current["geometry"]["end"] = list(pair[1])
                current["confidence"] = min(
                    current.get("confidence", 0), proposal.get("confidence", 0))
                merged = True
                break
        if not merged:
            output.append(proposal)
    return output


def proposals_from_detections(
    detections: list[dict[str, Any]], drawing_id: str,
    scale_mm_per_px: float | None = None, confidence_threshold: float = 0.25,
) -> tuple[list[dict], list[str]]:
    proposals = []
    warnings = []
    for index, detection in enumerate(detections):
        class_name = detection.get("class_name")
        confidence = float(detection.get("confidence", 0))
        if class_name not in CLASSES or confidence < confidence_threshold:
            continue
        warning = ""
        if confidence < 0.6:
            warning = "low-confidence detection - review required"
            warnings.append(f"{drawing_id} detection {index + 1}: {warning}")
        proposal = {
            "proposal_id": f"{drawing_id}-{index + 1}",
            "type": class_name,
            "level": int(detection.get("level", 1)),
            "geometry": detection.get("geometry", {}),
            "dimensions": dict(detection.get("dimensions") or {}),
            "confidence": confidence,
            "source_drawing": drawing_id,
            "scale_mm_per_px": scale_mm_per_px,
            "warnings": [warning] if warning else [],
            "accepted": confidence >= 0.6,
        }
        line = _line(proposal)
        if line and scale_mm_per_px:
            start, end = line
            proposal["dimensions"]["length_mm"] = round(
                math.hypot(end[0] - start[0], end[1] - start[1])
                * scale_mm_per_px, 1)
        proposals.append(proposal)
    snap_near_endpoints(proposals)
    proposals = merge_collinear_wall_fragments(proposals)
    return proposals, warnings
