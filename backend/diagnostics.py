"""Small request diagnostics with bounded metadata, never uploaded plan content."""
from contextvars import ContextVar
from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
import traceback

from starlette.routing import Match

LOGGER = logging.getLogger("uvicorn.error.timberbim")
context = ContextVar("request_diagnostics", default=None)


def observed_revision(project_id, revision):
    current = context.get()
    if current is not None:
        current["observed_project_id"] = project_id
        current["actual_revision"] = revision


def validation_result(result):
    current = context.get()
    if current is not None and not result.get("can_preview", True):
        current.update(outcome="validation_failed", error_count=len(result.get("errors", [])),
                       warning_count=len(result.get("warnings", [])))
    return result


def route_pattern(request):
    route = request.scope.get("route")
    if route is not None:
        return getattr(route, "path", "unmatched")
    # Early middleware rejections have not yet reached FastAPI routing. Match
    # without executing it so dynamic IDs and unrecognized URL text stay out.
    for route in request.app.routes:
        if route.matches(request.scope)[0] is Match.FULL:
            return getattr(route, "path", "unmatched")
    return "unmatched"


def emit(request, current, status, duration_ms, error_type=None, failure=None):
    outcome = current.get("outcome") or ("request_failed" if status >= 400 else "request_completed")
    if outcome == "request_completed" and os.getenv("TIMBERBIM_LOG_REQUESTS") != "1":
        return
    payload = {"event": outcome, "timestamp": datetime.now(timezone.utc).isoformat(),
               "request_id": current["request_id"], "method": request.method,
               "route": route_pattern(request), "project_id": current.get("project_id", "invalid"),
               "expected_revision": current.get("expected_revision"),
               "observed_project_id": current.get("observed_project_id"),
               "actual_revision": current.get("actual_revision"),
               "status_code": status, "duration_ms": round(duration_ms, 3)}
    for key in ("error_count", "warning_count"):
        if key in current:
            payload[key] = current[key]
    if error_type is not None:
        payload["error_type"] = error_type
    if status >= 500 and failure is not None:
        payload["frames"] = [{"file": Path(frame.filename).name, "line": frame.lineno,
                              "function": frame.name} for frame in traceback.extract_tb(failure.__traceback__)[-8:]]
    level = logging.ERROR if status >= 500 else logging.WARNING if outcome != "request_completed" else logging.INFO
    # Diagnostics must not turn an otherwise handled failure into another one.
    try:
        LOGGER.log(level, json.dumps(payload, separators=(",", ":")))
    except Exception:
        pass
