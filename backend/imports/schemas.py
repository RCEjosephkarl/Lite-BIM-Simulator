"""Pydantic contracts shared by CSV import endpoints."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class CsvPlanPayload(BaseModel):
    rows: list[dict[str, Any]] = Field(default_factory=list)
    units: Literal["mm", "metres", "feet_inches"] = "mm"
    file_name: str = ""


class CsvCommitPayload(CsvPlanPayload):
    mode: Literal[
        "replace_sample_geometry",
        "append_to_sample_geometry",
        "new_project_from_csv",
    ] = "append_to_sample_geometry"


class VisionCommitPayload(BaseModel):
    proposals: list[dict[str, Any]] = Field(default_factory=list)
    mode: Literal[
        "replace_sample_geometry",
        "append_to_sample_geometry",
        "new_project_from_csv",
    ] = "append_to_sample_geometry"
    file_name: str = ""
