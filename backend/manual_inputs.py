"""Manual wall-frame and truss contracts plus deterministic member generators."""

from __future__ import annotations

import math
import hashlib
import os
import re
import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

import materials
import nzs3604 as nz
from trusses import canonical_graph
import walls
from geometry_checks import finite, midpoint

MAX_MEMBERS = int(os.environ.get("TIMBERBIM_MAX_GENERATED_MEMBERS", "100000"))


def estimated_member_count(spec) -> int:
    """Conservative preflight bound, including nog rows and repeated layouts."""
    if isinstance(spec, ManualWallFrameInput):
        length = math.hypot(spec.end_x_mm - spec.start_x_mm, spec.end_z_mm - spec.start_z_mm)
        finite("wall length", length)
        studs = math.ceil(length / spec.stud_spacing_mm) + 2 + len(spec.openings) * 4
        if spec.nog_spacing_mm and spec.nog_spacing_mm < spec.wall_height_mm / MAX_MEMBERS:
            return MAX_MEMBERS + 1
        nogs = math.ceil(spec.wall_height_mm / spec.nog_spacing_mm) if spec.nog_spacing_mm else spec.nog_count
        return studs * (nogs + 1) + len(spec.openings) * 30 + 10
    return spec.quantity * (len(spec.members) if spec.truss_type == "custom" else 32)


class GeometryInput(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)


class ManualOpening(GeometryInput):
    opening_id: str = ""
    opening_type: Literal["door", "window", "garage", "custom"] = "window"
    start_offset_mm: float = Field(ge=0)
    width_mm: float = Field(gt=0)
    height_mm: float = Field(gt=0)
    sill_height_mm: float = Field(default=900, ge=0)
    head_height_mm: float | None = Field(default=None, gt=0)
    lintel_size: str = ""
    notes: str = ""

    @field_validator("lintel_size")
    @classmethod
    def section_valid(cls, value):
        if value:
            _size(value)
        return value


class ManualWallFrameInput(GeometryInput):
    input_id: str = ""
    level: int = Field(default=1, ge=1, le=20)
    segment_id: str = ""
    segment_label: str = "Manual wall"
    start_x_mm: float = 0
    start_z_mm: float = 0
    end_x_mm: float = 6000
    end_z_mm: float = 0
    wall_height_mm: float = Field(default=2535, gt=300)
    wall_thickness_mm: float = Field(default=90, gt=20)
    stud_size: str = "90x45"
    stud_material: str = "SG8"
    plate_material: str = "SG8"
    lintel_material: str = "SG8"
    panelize: bool = False
    stud_spacing_mm: float = Field(default=600, ge=200, le=2400)
    plies: int = Field(default=1, ge=1, le=12)
    bottom_plate_size: str = "90x45"
    top_plate_size: str = "90x45"
    nog_count: int = Field(default=1, ge=0, le=10)
    nog_spacing_mm: float | None = Field(default=None, gt=0)
    treatment: Literal["H1.2", "H3.1", "H3.2", "H4", "H5"] = "H1.2"
    exterior: bool = True
    load_bearing: bool = True
    openings: list[ManualOpening] = Field(default_factory=list, max_length=1024)

    @field_validator("stud_size", "bottom_plate_size", "top_plate_size")
    @classmethod
    def section_valid(cls, value):
        _size(value)
        return value

    @model_validator(mode="after")
    def geometry_is_valid(self):
        length = math.hypot(
            self.end_x_mm - self.start_x_mm,
            self.end_z_mm - self.start_z_mm)
        finite("wall length", length)
        if length < 300:
            raise ValueError("wall must be at least 300 mm long")
        for size in (self.stud_size, self.bottom_plate_size, self.top_plate_size):
            depth, breadth = _size(size)
            finite("wall section dimensions", depth * self.plies,
                   breadth * materials.section_plies(size))
        height = self.wall_height_mm
        bottom_h = _size(self.bottom_plate_size)[1] * materials.section_plies(self.bottom_plate_size)
        top_h = _size(self.top_plate_size)[1] * materials.section_plies(self.top_plate_size)
        if height <= bottom_h + 2 * top_h:
            raise ValueError("plate thicknesses leave no clear stud height")
        if not self.panelize and not ((length <= 6000 and height <= 3000)
                or (length <= 3000 and height <= 6000)):
            raise ValueError(
                f"wall frame {length / 1000:.2f} m x {height / 1000:.2f} m "
                "exceeds the 6 m x 3 m envelope (dimensions interchangeable)")
        width = _size(self.stud_size)[1] * materials.section_plies(self.stud_size)
        if length < 2*width:
            raise ValueError("wall length must accommodate its two end studs")
        for opening in self.openings:
            if opening.start_offset_mm + opening.width_mm > length:
                raise ValueError(
                    f"opening {opening.opening_id or opening.opening_type} "
                    "does not fit within the wall")
            if opening.start_offset_mm < 2*width or opening.start_offset_mm+opening.width_mm > length-2*width:
                raise ValueError("opening requires two jamb studs at each edge within the wall")
            if 0 < opening.sill_height_mm <= bottom_h+width:
                raise ValueError("window sill leaves no room for the sill member and lower cripples")
            head = opening.head_height_mm or (
                opening.sill_height_mm + opening.height_mm)
            if head > self.wall_height_mm:
                raise ValueError("opening head exceeds wall height")
            if not math.isclose(head, opening.sill_height_mm + opening.height_mm, abs_tol=0.01):
                raise ValueError("opening head must equal sill height plus opening height")
            lintel = opening.lintel_size or nz.lintel_for_span(opening.width_mm)[0]
            finite("wall lintel section dimensions",
                   _size(lintel)[1] * materials.section_plies(lintel) * self.plies)
            if head <= bottom_h:
                raise ValueError("opening head leaves no clear jamb height above the bottom plate")
            if head + _size(lintel)[0] > self.wall_height_mm - 2 * top_h:
                raise ValueError("opening lintel does not fit below the top plates")
        ordered = sorted(self.openings, key=lambda item: item.start_offset_mm)
        for left, right in zip(ordered, ordered[1:]):
            if left.start_offset_mm + left.width_mm > right.start_offset_mm:
                raise ValueError("wall openings overlap")
            if right.start_offset_mm-(left.start_offset_mm+left.width_mm) < 4*width:
                raise ValueError("adjacent openings leave insufficient room for their jamb studs")
        if estimated_member_count(self) > MAX_MEMBERS:
            raise ValueError(f"wall would exceed the {MAX_MEMBERS} member generation limit; increase nog spacing")
        walls.panel_layout(self, width)
        return self


class TrussNode(GeometryInput):
    id: str
    x: float
    y: float


class TrussMember(GeometryInput):
    start_node: str
    end_node: str
    element_type: str = "web"
    size: str = "90x45"
    material: str = "SG8"

    @field_validator("size")
    @classmethod
    def section_valid(cls, value):
        _size(value)
        return value


class ManualTrussInput(GeometryInput):
    input_id: str = ""
    level: int = Field(default=1, ge=1, le=20)
    truss_id: str = ""
    truss_label: str = "Manual truss"
    span_mm: float = Field(default=9000, gt=500)
    pitch_deg: float = Field(default=25, ge=1, le=80)
    spacing_mm: float = Field(default=900, gt=0)
    quantity: int = Field(default=1, ge=1, le=500)
    start_x_mm: float = 0
    start_z_mm: float = 0
    direction_deg: float = 0
    top_chord_size: str = "140x45"
    top_chord_material: str = "SG8"
    bottom_chord_size: str = "90x45"
    bottom_chord_material: str = "SG8"
    web_size: str = "90x45"
    web_material: str = "SG8"
    overhang_mm: float = Field(default=450, ge=0)
    heel_height_mm: float = Field(default=100, ge=0)
    treatment: Literal["H1.2", "H3.1", "H3.2", "H4", "H5"] = "H1.2"
    truss_type: Literal[
        "common", "girder", "mono", "scissor", "attic", "custom"
    ] = "common"
    nodes: list[TrussNode] = Field(default_factory=list, max_length=1024)
    members: list[TrussMember] = Field(default_factory=list, max_length=2048)

    @field_validator("top_chord_size", "bottom_chord_size", "web_size")
    @classmethod
    def section_valid(cls, value):
        _size(value)
        return value

    @model_validator(mode="after")
    def custom_is_valid(self):
        if estimated_member_count(self) > MAX_MEMBERS:
            raise ValueError(f"truss layout exceeds the {MAX_MEMBERS} member generation limit")
        if self.truss_type == "custom":
            ids = {node.id for node in self.nodes}
            if len(ids) != len(self.nodes):
                raise ValueError("custom truss node IDs must be unique")
            if len(ids) < 2 or not self.members:
                raise ValueError("custom truss requires nodes and members")
            if any(m.start_node not in ids or m.end_node not in ids
                   for m in self.members):
                raise ValueError("custom truss member references unknown node")
            nodes = {node.id: node for node in self.nodes}
            for member in self.members:
                start, end = nodes[member.start_node], nodes[member.end_node]
                if math.hypot(end.x - start.x, end.y - start.y) <= 1:
                    raise ValueError("truss member must be longer than 1 mm")
        _nodes, graph = canonical_graph(self)
        if len(graph) * self.quantity > MAX_MEMBERS:
            raise ValueError(f"truss layout exceeds the {MAX_MEMBERS} member generation limit")
        frame_plies = 3 if self.truss_type == "girder" else 1
        for edge in graph:
            depth, breadth = _size(edge[3])
            finite("truss section dimensions", depth, breadth * frame_plies * materials.section_plies(edge[3]))
        for instance in {0, self.quantity - 1}:
            positions = _truss_positions(self, _nodes, instance)
            for start, end, *_ in graph:
                length = math.dist(positions[start], positions[end])
                finite("placed truss member length", length)
                if length < 1:
                    raise ValueError("truss placement collapses member endpoints at this coordinate precision")
        return self


def _size(size: str, default=(90.0, 45.0)) -> tuple[float, float]:
    match = re.fullmatch(r"(?:(\d+)/)?(\d+(?:\.\d+)?)\s*[xX]\s*(\d+(?:\.\d+)?)(?: \(SED\))?", size.strip())
    if not match:
        raise ValueError("section must be positive depth x breadth, e.g. 90x45 or 2/140x45")
    a, b = float(match[2]), float(match[3])
    if not math.isfinite(a) or not math.isfinite(b) or a <= 0 or b <= 0 or (match[1] and int(match[1]) < 1):
        raise ValueError("section dimensions and plies must be positive")
    try:
        finite("combined section breadth", b * (int(match[1]) if match[1] else 1))
    except OverflowError:
        raise ValueError("combined section breadth must remain finite after calculation") from None
    return a, b


def _truss_positions(spec, nodes, instance):
    """One placement transform for validation and generation, in millimetres."""
    angle = math.radians(spec.direction_deg)
    along, across = (math.cos(angle), math.sin(angle)), (-math.sin(angle), math.cos(angle))
    offset = instance * spec.spacing_mm
    finite("truss layout offset", offset)
    shift_x, shift_y = across[0] * offset, across[1] * offset
    floor_z = (spec.level - 1) * nz.STOREY_RISE + nz.PLATE_THICK + nz.STUD_HEIGHT + 2 * nz.PLATE_THICK
    positions = {}
    for identifier, (x, z) in nodes.items():
        position = (spec.start_x_mm + shift_x + along[0] * x,
                    spec.start_z_mm + shift_y + along[1] * x, floor_z + z)
        finite("truss placement coordinates", *position)
        positions[identifier] = position
    return positions


def _base_element(
    code: str, level: int, size: str, material: str, treatment: str,
    length: float, w: float, h: float, cx: float, cy: float, cz: float,
    yaw: float, pitch: float, source: str, source_id: str, note: str = "",
    **extra,
) -> dict:
    finite("member geometry", length, w, h, cx, cy, cz, yaw, pitch)
    if min(length, w, h) <= 0:
        raise ValueError("member length and section dimensions must be positive")
    return {
        "type_code": code, "storey": level, "size": size,
        "grade": material, "treatment": treatment,
        "length_mm": length, "w_mm": w,
        "h_mm": h, "cx": cx, "cy": cy,
        "cz": cz, "yaw": yaw,
        "pitch": pitch, "note": note, "material": material,
        "plies": int(extra.pop("plies", 1)),
        "segment_id": extra.pop("segment_id", ""),
        "segment_label": extra.pop("segment_label", ""),
        "stud_spacing_mm": extra.pop("stud_spacing_mm", None),
        "source": source, "source_id": source_id, "editable": source != "generated",
        "confidence": extra.pop("confidence", None),
        "warnings": extra.pop("warnings", []),
        "truss_id": extra.pop("truss_id", ""),
        "truss_label": extra.pop("truss_label", ""),
        "pitch_deg": extra.pop("pitch_deg", None),
        "span_mm": extra.pop("span_mm", None),
        "spacing_mm": extra.pop("spacing_mm", None),
        **extra,
    }


def wall_warnings(spec: ManualWallFrameInput) -> list[str]:
    out = []
    if spec.level > 3:
        out.append("level is outside the sample model range")
    if spec.stud_spacing_mm not in {300, 400, 450, 480, 600}:
        out.append("custom spacing - verify by design/NZS 3604")
    if materials.normalise_material_key(spec.stud_material) is None:
        out.append("custom material has no catalogue price")
    if spec.plies > 6:
        out.append("plies exceed the design-control range (1-6)")
    return out


def generate_wall(
    spec: ManualWallFrameInput, source: str = "manual_wall",
    source_id: str | None = None,
) -> tuple[list[dict], list[str]]:
    sid = source_id or spec.input_id or f"wall-{uuid.uuid4().hex[:10]}"
    return walls.frame(spec, source, sid, _base_element, _size, wall_warnings(spec))


def truss_warnings(spec: ManualTrussInput) -> list[str]:
    out = ["truss geometry is conceptual - supplier/specific design required"]
    if spec.pitch_deg < 10 or spec.pitch_deg > 45:
        out.append("pitch is outside the common residential range")
    if spec.spacing_mm not in {450, 600, 900, 1200}:
        out.append("custom truss spacing requires design verification")
    if spec.truss_type == "custom":
        out.append("custom node elevations define the bearing plane; heel/overhang controls do not modify explicit nodes")
    if spec.truss_type == "attic":
        out.append("attic void is conceptual; occupancy, headroom and floor loads have not been checked")
    if spec.truss_type == "girder":
        out.append("three-ply girder is a conceptual assembly; support reactions and connections have not been checked")
    return out


def generate_truss(
    spec: ManualTrussInput, source: str = "manual_truss",
    source_id: str | None = None,
    *, instance_offset: int = 0,
) -> tuple[list[dict], list[str]]:
    sid = source_id or spec.input_id or f"truss-{uuid.uuid4().hex[:10]}"
    truss_id = spec.truss_id or sid
    warnings = truss_warnings(spec)
    note = "; ".join(warnings)
    nodes, members = canonical_graph(spec, include_cuts=True)

    code_map = {
        "top_chord": "truss_top_chord",
        "bottom_chord": "truss_bottom_chord",
        "web": "truss_web",
        "king_post": "truss_king_post",
        "queen_post": "truss_queen_post",
        "girder": "truss_girder",
    }
    els: list[dict] = []
    for instance in range(spec.quantity):
        positions = _truss_positions(spec, nodes, instance)
        for start, end, member_type, size, material, cut_id, cut_length in members:
            x1, y1, z1 = positions[start]
            x2, y2, z2 = positions[end]
            plan = math.hypot(x2 - x1, y2 - y1)
            length = math.hypot(plan, z2 - z1)
            depth, breadth = _size(size)
            code = code_map.get(member_type, "truss_web")
            frame_plies = 3 if spec.truss_type == "girder" else 1
            els.append(_base_element(
                code, spec.level, size, material, spec.treatment, length,
                breadth * frame_plies * materials.section_plies(size), depth,
                midpoint(x1, x2), midpoint(y1, y2), midpoint(z1, z2),
                math.atan2(y2 - y1, x2 - x1),
                math.atan2(z2 - z1, plan), source, sid, note,
                warnings=warnings, truss_id=f"{truss_id}-{instance + 1:03d}",
                layout_id=truss_id, instance_id=f"{sid}:{instance + instance_offset + 1:03d}",
                truss_type=spec.truss_type, member_role=member_type,
                start_node=start, end_node=end, engineering_status="unchecked",
                physical_member_id=hashlib.sha256(f"{source}:{sid}:{spec.level}:{instance + instance_offset}:{cut_id}".encode()).hexdigest()[:24],
                cut_length_mm=cut_length,
                truss_label=spec.truss_label, pitch_deg=spec.pitch_deg,
                span_mm=spec.span_mm, spacing_mm=spec.spacing_mm,
                plies=frame_plies))
    return els, warnings
