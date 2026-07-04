"""Manual wall-frame and truss contracts plus deterministic member generators."""

from __future__ import annotations

import math
import uuid
from typing import Literal

from pydantic import BaseModel, Field, model_validator

import materials
import nzs3604 as nz


class ManualOpening(BaseModel):
    opening_id: str = ""
    opening_type: Literal["door", "window", "garage", "custom"] = "window"
    start_offset_mm: float = Field(ge=0)
    width_mm: float = Field(gt=0)
    height_mm: float = Field(gt=0)
    sill_height_mm: float = Field(default=900, ge=0)
    head_height_mm: float | None = Field(default=None, gt=0)
    lintel_size: str = ""
    notes: str = ""


class ManualWallFrameInput(BaseModel):
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
    stud_spacing_mm: float = Field(default=600, ge=200, le=2400)
    plies: int = Field(default=1, ge=1, le=12)
    bottom_plate_size: str = "90x45"
    top_plate_size: str = "90x45"
    nog_count: int = Field(default=1, ge=0, le=10)
    nog_spacing_mm: float | None = Field(default=None, gt=0)
    treatment: Literal["H1.2", "H3.1", "H3.2", "H4", "H5"] = "H1.2"
    exterior: bool = True
    load_bearing: bool = True
    openings: list[ManualOpening] = Field(default_factory=list)

    @model_validator(mode="after")
    def geometry_is_valid(self):
        length = math.hypot(
            self.end_x_mm - self.start_x_mm,
            self.end_z_mm - self.start_z_mm)
        if length < 300:
            raise ValueError("wall must be at least 300 mm long")
        height = self.wall_height_mm
        if not ((length <= 6000 and height <= 3000)
                or (length <= 3000 and height <= 6000)):
            raise ValueError(
                f"wall frame {length / 1000:.2f} m x {height / 1000:.2f} m "
                "exceeds the 6 m x 3 m envelope (dimensions interchangeable)")
        for opening in self.openings:
            if opening.start_offset_mm + opening.width_mm > length:
                raise ValueError(
                    f"opening {opening.opening_id or opening.opening_type} "
                    "does not fit within the wall")
            head = opening.head_height_mm or (
                opening.sill_height_mm + opening.height_mm)
            if head > self.wall_height_mm:
                raise ValueError("opening head exceeds wall height")
        return self


class TrussNode(BaseModel):
    id: str
    x: float
    y: float


class TrussMember(BaseModel):
    start_node: str
    end_node: str
    element_type: str = "web"
    size: str = "90x45"
    material: str = "SG8"


class ManualTrussInput(BaseModel):
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
    nodes: list[TrussNode] = Field(default_factory=list)
    members: list[TrussMember] = Field(default_factory=list)

    @model_validator(mode="after")
    def custom_is_valid(self):
        if self.truss_type == "custom":
            ids = {node.id for node in self.nodes}
            if len(ids) < 2 or not self.members:
                raise ValueError("custom truss requires nodes and members")
            if any(m.start_node not in ids or m.end_node not in ids
                   for m in self.members):
                raise ValueError("custom truss member references unknown node")
        return self


def _size(size: str, default=(90.0, 45.0)) -> tuple[float, float]:
    try:
        clean = size.split("/")[-1].split()[0]
        a, b = clean.lower().split("x", 1)
        return float(a), float(b)
    except (ValueError, AttributeError):
        return default


def _base_element(
    code: str, level: int, size: str, material: str, treatment: str,
    length: float, w: float, h: float, cx: float, cy: float, cz: float,
    yaw: float, pitch: float, source: str, source_id: str, note: str = "",
    **extra,
) -> dict:
    return {
        "type_code": code, "storey": level, "size": size,
        "grade": material, "treatment": treatment,
        "length_mm": round(length, 2), "w_mm": round(w, 2),
        "h_mm": round(h, 2), "cx": round(cx, 2), "cy": round(cy, 2),
        "cz": round(cz, 2), "yaw": round(yaw, 6),
        "pitch": round(pitch, 6), "note": note, "material": material,
        "plies": int(extra.pop("plies", 1)),
        "segment_id": extra.pop("segment_id", ""),
        "segment_label": extra.pop("segment_label", ""),
        "stud_spacing_mm": extra.pop("stud_spacing_mm", None),
        "source": source, "source_id": source_id, "editable": True,
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
    segment_id = spec.segment_id or sid
    dx = spec.end_x_mm - spec.start_x_mm
    dy = spec.end_z_mm - spec.start_z_mm
    length = math.hypot(dx, dy)
    ux, uy = dx / length, dy / length
    yaw = math.atan2(dy, dx)
    base_z = (spec.level - 1) * nz.STOREY_RISE
    _stud_depth, stud_breadth = _size(spec.stud_size)
    warnings = wall_warnings(spec)
    note = "; ".join(warnings)
    els: list[dict] = []

    def point(station: float) -> tuple[float, float]:
        return spec.start_x_mm + ux * station, spec.start_z_mm + uy * station

    def horizontal(code: str, size: str, a: float, b: float,
                   z1: float, z2: float) -> None:
        if b - a <= 1:
            return
        x, y = point((a + b) / 2)
        depth, breadth = _size(size)
        els.append(_base_element(
            code, spec.level, size, spec.stud_material, spec.treatment,
            b - a, depth, z2 - z1 or breadth, x, y,
            base_z + (z1 + z2) / 2, yaw, 0, source, sid, note,
            plies=spec.plies, segment_id=segment_id,
            segment_label=spec.segment_label,
            stud_spacing_mm=spec.stud_spacing_mm, warnings=warnings))

    def vertical(code: str, station: float, z1: float, z2: float) -> None:
        if z2 - z1 <= 1:
            return
        x, y = point(station)
        els.append(_base_element(
            code, spec.level, spec.stud_size, spec.stud_material,
            spec.treatment, z2 - z1, spec.wall_thickness_mm,
            stud_breadth * spec.plies, x, y, base_z + (z1 + z2) / 2,
            yaw, math.pi / 2, source, sid, note, plies=spec.plies,
            segment_id=segment_id, segment_label=spec.segment_label,
            stud_spacing_mm=spec.stud_spacing_mm, warnings=warnings))

    plate_h = _size(spec.bottom_plate_size)[1]
    top_h = _size(spec.top_plate_size)[1]
    openings = sorted(spec.openings, key=lambda o: o.start_offset_mm)
    door_spans = [
        (o.start_offset_mm, o.start_offset_mm + o.width_mm)
        for o in openings if o.sill_height_mm <= 0
    ]
    cursor = 0.0
    for a, b in door_spans:
        horizontal("plate_bottom", spec.bottom_plate_size, cursor, a, 0, plate_h)
        cursor = b
    horizontal("plate_bottom", spec.bottom_plate_size, cursor, length, 0, plate_h)
    horizontal("plate_top", spec.top_plate_size, 0, length,
               spec.wall_height_mm - 2 * top_h, spec.wall_height_mm - top_h)
    horizontal("plate_top", spec.top_plate_size, 0, length,
               spec.wall_height_mm - top_h, spec.wall_height_mm)

    keepouts = [
        (o.start_offset_mm - stud_breadth * 2,
         o.start_offset_mm + o.width_mm + stud_breadth * 2)
        for o in openings
    ]
    stations = [stud_breadth / 2]
    station = spec.stud_spacing_mm
    while station < length - stud_breadth / 2:
        stations.append(station)
        station += spec.stud_spacing_mm
    stations.append(length - stud_breadth / 2)
    verticals = []
    for station in stations:
        if not any(a <= station <= b for a, b in keepouts):
            vertical("stud", station, plate_h, spec.wall_height_mm - 2 * top_h)
            verticals.append(station)

    for opening in openings:
        a = opening.start_offset_mm
        b = a + opening.width_mm
        sill = opening.sill_height_mm
        head = opening.head_height_mm or sill + opening.height_mm
        for station in (max(stud_breadth / 2, a - stud_breadth / 2),
                        min(length - stud_breadth / 2, b + stud_breadth / 2)):
            vertical("trimmer_stud", station, plate_h,
                     spec.wall_height_mm - 2 * top_h)
            verticals.append(station)
        lintel_size = opening.lintel_size or nz.lintel_for_span(
            opening.width_mm)[0]
        lintel_depth = _size(lintel_size, (140, 45))[0]
        horizontal("lintel", lintel_size, max(0, a - stud_breadth),
                   min(length, b + stud_breadth), head,
                   min(spec.wall_height_mm - 2 * top_h, head + lintel_depth))
        if sill > 0:
            horizontal("sill_trimmer", spec.stud_size, a, b,
                       max(plate_h, sill - stud_breadth), sill)

    nog_heights: list[float] = []
    clear_height = spec.wall_height_mm - plate_h - 2 * top_h
    if spec.nog_spacing_mm:
        nog_z = plate_h + spec.nog_spacing_mm
        while nog_z < spec.wall_height_mm - 2 * top_h:
            nog_heights.append(nog_z)
            nog_z += spec.nog_spacing_mm
    elif spec.nog_count:
        nog_heights = [
            plate_h + clear_height * row / (spec.nog_count + 1)
            for row in range(1, spec.nog_count + 1)
        ]
    if nog_heights:
        bays = sorted(set(verticals))
        for z in nog_heights:
            for a, b in zip(bays, bays[1:]):
                gap = b - a - stud_breadth
                if gap > 100:
                    horizontal("nog", spec.stud_size,
                               a + stud_breadth / 2,
                               b - stud_breadth / 2,
                               z - stud_breadth / 2, z + stud_breadth / 2)
    return els, warnings


def truss_warnings(spec: ManualTrussInput) -> list[str]:
    out = ["truss geometry is conceptual - supplier/specific design required"]
    if spec.pitch_deg < 10 or spec.pitch_deg > 45:
        out.append("pitch is outside the common residential range")
    if spec.spacing_mm not in {450, 600, 900, 1200}:
        out.append("custom truss spacing requires design verification")
    return out


def generate_truss(
    spec: ManualTrussInput, source: str = "manual_truss",
    source_id: str | None = None,
) -> tuple[list[dict], list[str]]:
    sid = source_id or spec.input_id or f"truss-{uuid.uuid4().hex[:10]}"
    truss_id = spec.truss_id or sid
    warnings = truss_warnings(spec)
    note = "; ".join(warnings)
    angle = math.radians(spec.direction_deg)
    along = (math.cos(angle), math.sin(angle))
    across = (-math.sin(angle), math.cos(angle))
    wall_top = nz.PLATE_THICK + nz.STUD_HEIGHT + 2 * nz.PLATE_THICK
    floor_z = (spec.level - 1) * nz.STOREY_RISE + wall_top
    rise = (spec.span_mm / 2) * math.tan(math.radians(spec.pitch_deg))

    if spec.truss_type == "custom":
        nodes = {n.id: (n.x, n.y) for n in spec.nodes}
        members = [
            (m.start_node, m.end_node, m.element_type, m.size, m.material)
            for m in spec.members
        ]
    elif spec.truss_type == "mono":
        nodes = {"L": (-spec.span_mm / 2, 0), "R": (spec.span_mm / 2, 0),
                 "T": (spec.span_mm / 2, rise * 2)}
        members = [
            ("L", "T", "top_chord", spec.top_chord_size,
             spec.top_chord_material),
            ("L", "R", "bottom_chord", spec.bottom_chord_size,
             spec.bottom_chord_material),
            ("R", "T", "web", spec.web_size, spec.web_material),
        ]
    else:
        nodes = {
            "L": (-spec.span_mm / 2 - spec.overhang_mm, 0),
            "BL": (-spec.span_mm / 2, 0), "C": (0, rise),
            "BR": (spec.span_mm / 2, 0),
            "R": (spec.span_mm / 2 + spec.overhang_mm, 0),
            "Q1": (-spec.span_mm / 4, rise / 2),
            "Q2": (spec.span_mm / 4, rise / 2),
        }
        members = [
            ("L", "C", "top_chord", spec.top_chord_size,
             spec.top_chord_material),
            ("C", "R", "top_chord", spec.top_chord_size,
             spec.top_chord_material),
            ("BL", "BR", "bottom_chord", spec.bottom_chord_size,
             spec.bottom_chord_material),
            ("BL", "C", "king_post", spec.web_size, spec.web_material),
            ("BR", "C", "web", spec.web_size, spec.web_material),
            ("BL", "Q2", "web", spec.web_size, spec.web_material),
            ("BR", "Q1", "web", spec.web_size, spec.web_material),
        ]
        if spec.truss_type == "scissor":
            members[2] = ("BL", "C", "bottom_chord",
                          spec.bottom_chord_size, spec.bottom_chord_material)
            members.append(("C", "BR", "bottom_chord",
                            spec.bottom_chord_size,
                            spec.bottom_chord_material))

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
        shift_x = across[0] * instance * spec.spacing_mm
        shift_y = across[1] * instance * spec.spacing_mm
        for start, end, member_type, size, material in members:
            ax, az = nodes[start]
            bx, bz = nodes[end]
            x1 = spec.start_x_mm + shift_x + along[0] * ax
            y1 = spec.start_z_mm + shift_y + along[1] * ax
            x2 = spec.start_x_mm + shift_x + along[0] * bx
            y2 = spec.start_z_mm + shift_y + along[1] * bx
            z1 = floor_z + spec.heel_height_mm + az
            z2 = floor_z + spec.heel_height_mm + bz
            plan = math.hypot(x2 - x1, y2 - y1)
            length = math.hypot(plan, z2 - z1)
            depth, breadth = _size(size)
            code = code_map.get(member_type, "truss_web")
            if spec.truss_type == "girder":
                code = "truss_girder"
            els.append(_base_element(
                code, spec.level, size, material, spec.treatment, length,
                breadth, depth, (x1 + x2) / 2, (y1 + y2) / 2, (z1 + z2) / 2,
                math.atan2(y2 - y1, x2 - x1),
                math.atan2(z2 - z1, plan), source, sid, note,
                warnings=warnings, truss_id=truss_id,
                truss_label=spec.truss_label, pitch_deg=spec.pitch_deg,
                span_mm=spec.span_mm, spacing_mm=spec.spacing_mm,
                plies=3 if spec.truss_type == "girder" else 1))
    return els, warnings
