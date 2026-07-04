"""Parametric timber-framing generator.

Turns the floor-plan geometry into individual members (studs, plates,
nogs, lintels, joists, rafters, ...) sized and spaced per NZS 3604:2011.

Element placement model: a box of length_mm (along the member axis) x
w_mm (horizontal, perpendicular to axis) x h_mm (vertical depth), centred
at (cx, cy, cz), rotated yaw radians about the vertical axis (0 = +x east,
+ toward north) then pitch radians about the member's horizontal
perpendicular axis (+ = axis rises).
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

import geometry as g
import materials
import nzs3604 as nz

CUSTOM_SPACING_NOTE = "custom spacing — verify by design/NZS 3604"

# stud-like verticals that take the stud material override
STUD_LIKE = {"stud", "trimmer_stud", "jack_stud"}


def _safe(s: str) -> str:
    """Sanitise user-supplied strings echoed into warnings."""
    return re.sub(r"[<>&]", "", s)[:32]


@dataclass
class ModelConfig:
    """User-adjustable generation parameters."""
    storeys: int = 1
    roof: str = "gable"            # 'gable' | 'hip'
    wind_zone: str = "medium"      # NZS 3604 Table 5.4 zone, or 'speed'
    wind_speed: float | None = None  # m/s; when set, derives the wind zone
    snow_zone: str = "N0"          # Section 15 zone N0..N5
    gable_spacing: int = nz.GABLE_STUD_DEFAULT_SPACING  # gable-end stud crs, mm
    # wall stud design overrides; precedence segment > level > overall > default
    stud_material_overall: str | None = None        # material key, e.g. 'sg10'
    stud_spacing_overall: int | None = None         # mm, 300..1200
    wall_plies_overall: int | None = None           # 1..6
    stud_material_levels: dict[int, str] = field(default_factory=dict)
    stud_spacing_levels: dict[int, int] = field(default_factory=dict)
    wall_plies_levels: dict[int, int] = field(default_factory=dict)
    stud_material_segments: dict[str, str] = field(default_factory=dict)
    stud_spacing_segments: dict[str, int] = field(default_factory=dict)
    wall_plies_segments: dict[str, int] = field(default_factory=dict)
    wall_treatment: str | None = None  # NZS 3640 class, e.g. 'H3.2'
    # populated by normalised(); a dataclass field so it survives asdict()
    override_warnings: list[str] = field(default_factory=list)

    def normalised(self) -> "ModelConfig":
        warns = list(self.override_warnings)

        def material(v: object, label: str) -> str | None:
            if v is None:
                return None
            key = materials.normalise_material_key(str(v))
            if key is None:
                warns.append(f"unknown stud material '{_safe(str(v))}' "
                             f"in {label} — ignored")
            return key

        def spacing(v: object, label: str) -> int | None:
            if v is None:
                return None
            try:
                n = int(v)  # type: ignore[arg-type]
            except (TypeError, ValueError):
                warns.append(f"invalid stud spacing '{_safe(str(v))}' "
                             f"in {label} — ignored")
                return None
            clamped = max(300, min(1200, n))
            if clamped != n:
                warns.append(f"stud spacing {n} mm in {label} "
                             f"clamped to {clamped} mm")
            return clamped

        def plies(v: object, label: str) -> int | None:
            if v is None:
                return None
            try:
                n = int(v)  # type: ignore[arg-type]
            except (TypeError, ValueError):
                warns.append(f"invalid wall plies '{_safe(str(v))}' "
                             f"in {label} — ignored")
                return None
            clamped = max(1, min(6, n))
            if clamped != n:
                warns.append(f"wall plies {n} in {label} "
                             f"clamped to {clamped}")
            return clamped

        def by_level(d: dict, clean, label: str) -> dict:
            out = {}
            for k, v in (d or {}).items():
                try:
                    lvl = int(k)
                except (TypeError, ValueError):
                    warns.append(f"invalid level '{_safe(str(k))}' "
                                 f"in {label} — ignored")
                    continue
                if not 1 <= lvl <= 3:
                    warns.append(f"level {lvl} in {label} "
                                 f"outside 1-3 — ignored")
                    continue
                cv = clean(v, f"{label}[{lvl}]")
                if cv is not None:
                    out[lvl] = cv
            return out

        def treatment(v: object) -> str | None:
            if v is None:
                return None
            t = str(v).strip()
            match = next((opt for opt in nz.TREATMENTS
                          if opt.lower() == t.lower()), None)
            if match is None:
                warns.append(f"unknown treatment '{_safe(t)}' "
                             f"in wall_treatment — ignored")
            return match

        def by_segment(d: dict, clean, label: str) -> dict:
            out = {}
            for k, v in (d or {}).items():
                seg = str(k).strip()
                if not seg:
                    continue
                cv = clean(v, f"{label}[{_safe(seg)}]")
                if cv is not None:
                    out[seg] = cv
            return out

        c = ModelConfig(
            storeys=max(1, min(3, int(self.storeys))),
            roof=self.roof if self.roof in ("gable", "hip") else "gable",
            wind_zone=self.wind_zone,
            wind_speed=self.wind_speed,
            snow_zone=self.snow_zone if self.snow_zone in nz.SNOW_ZONES else "N0",
            gable_spacing=max(300, min(1200, int(self.gable_spacing))),
            stud_material_overall=material(
                self.stud_material_overall, "stud_material_overall"),
            stud_spacing_overall=spacing(
                self.stud_spacing_overall, "stud_spacing_overall"),
            wall_plies_overall=plies(
                self.wall_plies_overall, "wall_plies_overall"),
            stud_material_levels=by_level(
                self.stud_material_levels, material, "stud_material_levels"),
            stud_spacing_levels=by_level(
                self.stud_spacing_levels, spacing, "stud_spacing_levels"),
            wall_plies_levels=by_level(
                self.wall_plies_levels, plies, "wall_plies_levels"),
            stud_material_segments=by_segment(
                self.stud_material_segments, material,
                "stud_material_segments"),
            stud_spacing_segments=by_segment(
                self.stud_spacing_segments, spacing,
                "stud_spacing_segments"),
            wall_plies_segments=by_segment(
                self.wall_plies_segments, plies, "wall_plies_segments"),
            wall_treatment=treatment(self.wall_treatment),
        )
        if c.wind_speed is not None:
            c.wind_zone = nz.wind_zone_for_speed(c.wind_speed)
        elif c.wind_zone not in nz.WIND_ZONES:
            c.wind_zone = "medium"
        c.override_warnings = warns
        return c

    def effective_stud_material(self, storey: int,
                                segment_id: str | None = None) -> str:
        """Material key for stud-like members (segment > level > overall)."""
        if segment_id and segment_id in self.stud_material_segments:
            return self.stud_material_segments[segment_id]
        if storey in self.stud_material_levels:
            return self.stud_material_levels[storey]
        return self.stud_material_overall or "sg8"

    def effective_stud_spacing(self, storey: int, segment_id: str | None,
                               nzs_default: int) -> int:
        if segment_id and segment_id in self.stud_spacing_segments:
            return self.stud_spacing_segments[segment_id]
        if storey in self.stud_spacing_levels:
            return self.stud_spacing_levels[storey]
        if self.stud_spacing_overall is not None:
            return self.stud_spacing_overall
        return nzs_default

    def effective_wall_plies(self, storey: int,
                             segment_id: str | None = None) -> int:
        if segment_id and segment_id in self.wall_plies_segments:
            return self.wall_plies_segments[segment_id]
        if storey in self.wall_plies_levels:
            return self.wall_plies_levels[storey]
        return self.wall_plies_overall or 1

    def has_spacing_override(self) -> bool:
        return (self.stud_spacing_overall is not None
                or bool(self.stud_spacing_levels)
                or bool(self.stud_spacing_segments))

    def warnings(self) -> list[str]:
        out = []
        if nz.scope_note(self.storeys):
            out.append(nz.scope_note(self.storeys))
        if self.wind_zone == "sed":
            out.append(nz.WIND_SED_NOTE)
        if nz.SNOW_ZONES.get(self.snow_zone, 0.0) is None:
            out.append(nz.SNOW_SED_NOTE)
        return out

WALL_H = nz.PLATE_THICK + nz.STUD_HEIGHT + 2 * nz.PLATE_THICK  # 2535
STUD_TOP = nz.PLATE_THICK + nz.STUD_HEIGHT                     # 2445
MAX_PIECE = 6000


def _el(els: list, type_code: str, storey: int, size: str, length: float,
        w: float, h: float, cx: float, cy: float, cz: float,
        yaw: float = 0.0, pitch: float = 0.0, grade: str = nz.GRADE,
        treatment: str = nz.WALL_TREATMENT, note: str = "") -> None:
    if length <= 1:
        return
    els.append(dict(type_code=type_code, storey=storey, size=size, grade=grade,
                    treatment=treatment, length_mm=round(length, 1),
                    w_mm=w, h_mm=h, cx=round(cx, 1), cy=round(cy, 1),
                    cz=round(cz, 1), yaw=round(yaw, 5), pitch=round(pitch, 5),
                    note=note, material=grade, plies=1, segment_id="",
                    segment_label="", stud_spacing_mm=None))


# ---------------------------------------------------------------------------
# Wall framing — NZS 3604 section 8
# ---------------------------------------------------------------------------

def frame_wall(els: list, wall: g.Wall, storey: int, spacing: int,
               z: float, note: str = "", *, material: str = "SG8",
               plies: int = 1, segment_id: str = "",
               segment_label: str = "",
               treatment: str = nz.WALL_TREATMENT) -> None:
    dx, dy = wall.x2 - wall.x1, wall.y2 - wall.y1
    length = math.hypot(dx, dy)
    if length < 100:
        return
    start = len(els)
    vert_breadth = 45.0 * plies  # multi-ply studs widen along the wall
    yaw = math.atan2(dy, dx)
    ux, uy = dx / length, dy / length

    def at(s: float) -> tuple[float, float]:
        return wall.x1 + ux * s, wall.y1 + uy * s

    def horiz(code: str, size: str, s1: float, s2: float, z1: float, z2: float,
              w: float = 90.0, **kw) -> None:
        """Member along the wall from s1..s2, vertically z1..z2 (above floor)."""
        for a, b in _split(s1, s2):
            x, y = at((a + b) / 2)
            _el(els, code, storey, size, b - a, w, z2 - z1,
                x, y, z + (z1 + z2) / 2, yaw, 0, note=kw.get("note", note),
                treatment=kw.get("treatment", nz.WALL_TREATMENT))

    def vert(code: str, s: float, z1: float, z2: float) -> None:
        """Stud-type member at station s from z1..z2 above floor."""
        x, y = at(s)
        _el(els, code, storey, "90x45", z2 - z1, 90, vert_breadth,
            x, y, z + (z1 + z2) / 2, yaw, math.pi / 2, note=note)

    half = 22.5  # half stud breadth

    # --- plates ---
    door_spans = [(o.offset, o.offset + o.width) for o in wall.openings
                  if o.sill <= 0]
    for a, b in _complement(0, length, door_spans):
        horiz("plate_bottom", "90x45", a, b, 0, nz.PLATE_THICK)
    horiz("plate_top", "90x45", 0, length, STUD_TOP, STUD_TOP + 45)
    horiz("plate_top", "90x45", 0, length, STUD_TOP + 45, WALL_H)

    # --- common studs (skip across openings + trimmer zones) ---
    stations = [half]
    s = spacing
    while s < length - spacing / 2:
        stations.append(s)
        s += spacing
    stations.append(length - half)
    keep_out = [(o.offset - 135, o.offset + o.width + 135) for o in wall.openings]
    studs = [st for st in stations
             if not any(a <= st <= b for a, b in keep_out)]
    for st in studs:
        vert("stud", st, nz.PLATE_THICK, STUD_TOP)

    all_verticals = list(studs)

    # --- openings: trimmers, lintels, sills ---
    for o in wall.openings:
        s1, s2 = o.offset, o.offset + o.width
        label, depth, _breadth = nz.lintel_for_span(o.width)
        lintel_z1 = min(o.head, STUD_TOP - 45)
        lintel_z2 = min(lintel_z1 + depth, STUD_TOP)

        for side in (-1, 1):
            edge = s1 if side < 0 else s2
            for k in (1, 2):
                st = edge + side * (half + (k - 1) * 45)
                st = min(max(st, half), length - half)
                vert("trimmer_stud", st, nz.PLATE_THICK, STUD_TOP)
                all_verticals.append(st)

        horiz("lintel", label, s1 - 90, s2 + 90, lintel_z1, lintel_z2,
              note=(note or nz.scope_note(0)) if "SED" not in label
              else f"span {o.width / 1000:.1f} m exceeds Table 8.9 — SED")

        # cripples between lintel and top plate
        gap_top = STUD_TOP - lintel_z2
        if gap_top >= 150:
            c = s1 + 300
            while c < s2 - 100:
                x, y = at(c)
                _el(els, "jack_stud", storey, "90x45", gap_top, 90,
                    vert_breadth, x, y, z + lintel_z2 + gap_top / 2,
                    yaw, math.pi / 2, note=note)
                c += 600

        if o.sill > 0:  # window: sill trimmer + jack studs under it
            horiz("sill_trimmer", "90x45", s1, s2, o.sill - 45, o.sill)
            c = s1 + 300
            while c < s2 - 100:
                x, y = at(c)
                _el(els, "jack_stud", storey, "90x45", o.sill - 45 - nz.PLATE_THICK,
                    90, vert_breadth, x, y,
                    z + nz.PLATE_THICK + (o.sill - 45 - nz.PLATE_THICK) / 2,
                    yaw, math.pi / 2, note=note)
                c += 600

    # --- nogs at mid-height between verticals ---
    nog_z = nz.PLATE_THICK + nz.STUD_HEIGHT / 2
    pts = sorted(all_verticals)
    for a, b in zip(pts, pts[1:]):
        gap = b - a - 45
        if gap < 120:
            continue
        mid = (a + b) / 2
        blocked = any(o.offset - 45 < mid < o.offset + o.width + 45
                      and o.sill < nog_z + 25 and o.head > nog_z - 25
                      for o in wall.openings)
        if blocked:
            continue
        x, y = at(mid)
        _el(els, "nog", storey, "90x45", gap, 90, 45, x, y, z + nog_z, yaw,
            0, note=note)

    # --- stamp wall-frame design metadata on everything just emitted ---
    for e in els[start:]:
        e["plies"] = plies
        e["segment_id"] = segment_id
        e["segment_label"] = segment_label
        e["stud_spacing_mm"] = spacing
        e["treatment"] = treatment
        if e["type_code"] in STUD_LIKE:
            e["material"] = material
            e["grade"] = material


def _split(a: float, b: float) -> list[tuple[float, float]]:
    """Split a run into <= 6 m pieces."""
    total = b - a
    if total <= MAX_PIECE:
        return [(a, b)] if total > 1 else []
    n = math.ceil(total / MAX_PIECE)
    step = total / n
    return [(a + i * step, a + (i + 1) * step) for i in range(n)]


def _complement(a: float, b: float, spans: list[tuple[float, float]]
                ) -> list[tuple[float, float]]:
    out, cur = [], a
    for s1, s2 in sorted(spans):
        if s1 > cur:
            out.append((cur, min(s1, b)))
        cur = max(cur, s2)
    if cur < b:
        out.append((cur, b))
    return [(p, q) for p, q in out if q - p > 1]


# ---------------------------------------------------------------------------
# Floor / ceiling membranes (scanline over rectilinear polygon)
# ---------------------------------------------------------------------------

def _h_intervals(poly: list[tuple[float, float]], y: float
                 ) -> list[tuple[float, float]]:
    """x-intervals of a horizontal line inside a rectilinear polygon (mm)."""
    xs = []
    n = len(poly)
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        if x1 == x2 and min(y1, y2) <= y < max(y1, y2):
            xs.append(x1)
    xs.sort()
    return list(zip(xs[0::2], xs[1::2]))


def frame_floor(els: list, poly_mm: list[tuple[float, float]], storey: int,
                z: float, note: str = "") -> None:
    """Floor joists (next storey's platform) sitting on top of walls at z."""
    ys = sorted({p[1] for p in poly_mm})
    y0, y1 = ys[0], ys[-1]
    depth, breadth = nz.JOIST_SIZE
    y = y0 + 225
    rows = []
    while y < y1:
        for ix1, ix2 in _h_intervals(poly_mm, y):
            cuts = [x for x in g.JOIST_SUPPORT_XS if ix1 + 300 < x < ix2 - 300]
            pieces = list(zip([ix1] + cuts, cuts + [ix2]))
            for a, b in pieces:
                ln = b - a
                n = (f"span {ln / 1000:.1f} m > {nz.JOIST_MAX_SPAN / 1000:.1f} m "
                     f"({nz.JOIST_REF}) — add support/SED" if ln > nz.JOIST_MAX_SPAN
                     else note)
                _el(els, "joist", storey, "190x45", ln, breadth, depth,
                    (a + b) / 2, y, z + depth / 2, 0, 0, note=n)
        rows.append(y)
        y += nz.JOIST_SPACING
    # blocking along internal support lines
    for x in g.JOIST_SUPPORT_XS:
        for ya, yb in zip(rows, rows[1:]):
            if yb - ya > nz.JOIST_SPACING * 1.5:
                continue
            iv = _h_intervals(poly_mm, (ya + yb) / 2)
            if not any(a + 200 < x < b - 200 for a, b in iv):
                continue
            _el(els, "blocking", storey, "190x45", yb - ya - 45, 45, depth,
                x, (ya + yb) / 2, z + depth / 2, math.pi / 2, 0, note=note)


def frame_ceiling(els: list, poly_mm: list[tuple[float, float]], storey: int,
                  z: float, note: str = "") -> None:
    ys = sorted({p[1] for p in poly_mm})
    depth, breadth = nz.CEILING_JOIST_SIZE
    y = ys[0] + 300
    while y < ys[-1]:
        for ix1, ix2 in _h_intervals(poly_mm, y):
            cuts = [x for x in g.JOIST_SUPPORT_XS if ix1 + 300 < x < ix2 - 300]
            for a, b in zip([ix1] + cuts, cuts + [ix2]):
                _el(els, "ceiling_joist", storey, "90x45", b - a, breadth, depth,
                    (a + b) / 2, y, z + depth / 2, 0, 0, note=note)
        y += nz.CEILING_JOIST_SPACING


# ---------------------------------------------------------------------------
# Roof framing (gable or hip)
#
# Roofs are framed in (u, v) coordinates: u along the ridge, v across it.
# For a north-south ridge (axis 'y') the axes are swapped, which is a
# reflection — in-plane angles flip sign, handled by `mirror`.
# ---------------------------------------------------------------------------

class _Roof:
    def __init__(self, els: list, rect_ft, storey: int, z: float, note: str):
        x1, y1, x2, y2, axis = rect_ft
        x1, y1, x2, y2 = g.ft(x1), g.ft(y1), g.ft(x2), g.ft(y2)
        self.els, self.storey, self.z, self.note = els, storey, z, note
        self.axis = axis
        if axis == "y":
            self.u1, self.v1, self.u2, self.v2 = y1, x1, y2, x2
            self.base_yaw, self.mirror = math.pi / 2, -1.0
        else:
            self.u1, self.v1, self.u2, self.v2 = x1, y1, x2, y2
            self.base_yaw, self.mirror = 0.0, 1.0
        self.pitch = math.radians(nz.ROOF_PITCH_DEG)
        self.tanp, self.cosp = math.tan(self.pitch), math.cos(self.pitch)
        self.over = nz.EAVE_OVERHANG
        self.half = (self.v2 - self.v1) / 2
        self.vc = (self.v1 + self.v2) / 2
        self.apex = z + 100 + self.half * self.tanp
        self.run = self.half + self.over            # eave to ridge, in plan
        self.eave_z = self.apex - self.run * self.tanp

    def place(self, u: float, v: float, zz: float, code: str, size: str,
              length: float, w: float, h: float, uv_yaw: float, pch: float,
              treatment: str = nz.WALL_TREATMENT) -> None:
        """Place a member whose plan direction is uv_yaw within roof space."""
        x, y = (v, u) if self.axis == "y" else (u, v)
        _el(self.els, code, self.storey, size, length, w, h, x, y, zz,
            self.base_yaw + self.mirror * uv_yaw, pch,
            note=self.note, treatment=treatment)

    def cross_rafter(self, u: float, run: float, side: int,
                     code: str = "rafter") -> None:
        """Rafter perpendicular to the ridge, from the eave up toward it."""
        if run < 250:
            return
        rdepth, rbreadth = nz.RAFTER_SIZE
        edge = self.v1 - self.over if side < 0 else self.v2 + self.over
        vmid = edge + (run / 2 if side < 0 else -run / 2)
        zmid = self.eave_z + run * self.tanp / 2
        uv_yaw = side * math.pi / 2  # descending away from the ridge
        self.place(u, vmid, zmid, code, f"{rdepth}x{rbreadth}",
                   run / self.cosp, rbreadth, rdepth, uv_yaw, -self.pitch)

    def ridge_board(self, ua: float, ub: float) -> None:
        for a, b in _split(ua, ub):
            self.place((a + b) / 2, self.vc, self.apex, "ridge",
                       f"{nz.RIDGE_SIZE[0]}x{nz.RIDGE_SIZE[1]}", b - a, 45,
                       nz.RIDGE_SIZE[0], 0, 0)

    def fascia_u(self, ua: float, ub: float, v: float) -> None:
        for a, b in _split(ua, ub):
            self.place((a + b) / 2, v, self.eave_z, "fascia", "180x25",
                       b - a, 25, 180, 0, 0, treatment=nz.OUTDOOR_TREATMENT)

    def fascia_v(self, va: float, vb: float, u: float) -> None:
        for a, b in _split(va, vb):
            self.place(u, (a + b) / 2, self.eave_z, "fascia", "180x25",
                       b - a, 25, 180, math.pi / 2, 0,
                       treatment=nz.OUTDOOR_TREATMENT)


def frame_gable_roof(els: list, rect_ft, storey: int, z: float,
                     rspacing: int, gable_spacing: int, note: str = "",
                     *, material: str = "SG8") -> None:
    r = _Roof(els, rect_ft, storey, z, note)
    r.ridge_board(r.u1, r.u2)

    u = r.u1 + 150
    while u <= r.u2 - 100:
        for side in (-1, 1):
            r.cross_rafter(u, r.run, side)
        u += rspacing

    for side in (-1, 1):
        r.fascia_u(r.u1, r.u2, r.vc + side * r.run)

    # gable-end studs: verticals under the end rafters at custom centres,
    # standing on the end wall's top plate (roof rects overhang walls ~1 ft)
    start = len(els)
    for u_face in (r.u1 + g.ft(1), r.u2 - g.ft(1)):
        offsets = [0.0]
        k = gable_spacing
        while k < r.half - 100:
            offsets += [k, -k]
            k += gable_spacing
        for dv in sorted(offsets):
            h = (r.half - abs(dv)) * r.tanp + 60
            if h < 150:
                continue
            r.place(u_face, r.vc + dv, z + h / 2, "gable_stud", "90x45",
                    h, 90, 45, 0, math.pi / 2)
    for e in els[start:]:  # only gable_stud emitted above
        e["material"] = material
        e["grade"] = material
        e["stud_spacing_mm"] = gable_spacing


def frame_hip_roof(els: list, rect_ft, storey: int, z: float,
                   rspacing: int, note: str = "") -> None:
    r = _Roof(els, rect_ft, storey, z, note)
    ur1, ur2 = r.u1 + r.half, r.u2 - r.half  # ridge shortened by hip ends
    if ur1 > ur2:
        ur1 = ur2 = (r.u1 + r.u2) / 2        # square plan => pyramid
    else:
        r.ridge_board(ur1, ur2)

    # common rafters along the straight middle section
    u = ur1
    while u <= ur2:
        for side in (-1, 1):
            r.cross_rafter(u, r.run, side)
        u += rspacing

    # side jack rafters in the hip-end triangles (shorten toward corners)
    for u_end, direction in ((ur1, -1), (ur2, 1)):
        k = rspacing
        while True:
            u = u_end + direction * k
            run = r.run - k
            if run < 250:
                break
            for side in (-1, 1):
                r.cross_rafter(u, run, side, "jack_rafter")
            k += rspacing

    # end-face jacks: run parallel to the ridge, from the end eave to the hips
    for u_end, direction in ((ur1, -1), (ur2, 1)):
        eave_u = u_end + direction * r.run
        offsets = [0.0]
        k = rspacing
        while k < r.run - 250:
            offsets += [k, -k]
            k += rspacing
        for dv in offsets:
            run = r.run - abs(dv)
            if run < 250:
                continue
            umid = eave_u - direction * run / 2
            zmid = r.eave_z + run * r.tanp / 2
            code = "rafter" if dv == 0.0 else "jack_rafter"
            rdepth, rbreadth = nz.RAFTER_SIZE
            r.place(umid, r.vc + dv, zmid, code, f"{rdepth}x{rbreadth}",
                    run / r.cosp, rbreadth, rdepth,
                    0 if direction > 0 else math.pi, -r.pitch)

    # hip rafters: ridge ends down to the four eave corners
    rise = r.apex - r.eave_z
    for u_end, direction in ((ur1, -1), (ur2, 1)):
        for side in (-1, 1):
            cu = u_end + direction * r.run
            cv = r.vc + side * r.run
            plan = math.hypot(cu - u_end, cv - r.vc)
            uv_yaw = math.atan2(cv - r.vc, cu - u_end)
            r.place((u_end + cu) / 2, (r.vc + cv) / 2,
                    (r.apex + r.eave_z) / 2, "hip_rafter",
                    f"{nz.HIP_SIZE[0]}x{nz.HIP_SIZE[1]}",
                    math.hypot(plan, rise), 45, nz.HIP_SIZE[0],
                    uv_yaw, -math.atan2(rise, plan))

    # fascia all four sides
    for side in (-1, 1):
        r.fascia_u(r.u1 - r.over, r.u2 + r.over, r.vc + side * r.run)
    r.fascia_v(r.v1 - r.over, r.v2 + r.over, r.u1 - r.over)
    r.fascia_v(r.v1 - r.over, r.v2 + r.over, r.u2 + r.over)


# ---------------------------------------------------------------------------
# Porch + slabs
# ---------------------------------------------------------------------------

def frame_porch(els: list, note: str = "") -> None:
    beam_z1, beam_z2 = 2300, 2300 + nz.PORCH_BEAM_SIZE[0]
    py = g.ft(g.PORCH_POST_Y_FT)
    for px in g.PORCH_POST_XS_FT:
        _el(els, "post", 1, "90x90", beam_z1, 90, 90, g.ft(px), py,
            beam_z1 / 2, 0, math.pi / 2, treatment=nz.OUTDOOR_TREATMENT, note=note)
    x1, x2 = g.ft(g.PORCH_X1_FT), g.ft(g.PORCH_X2_FT)
    for a, b in _split(x1, x2):
        _el(els, "beam", 1, "2/190x45", b - a, 90, nz.PORCH_BEAM_SIZE[0],
            (a + b) / 2, py, (beam_z1 + beam_z2) / 2, 0, 0,
            treatment=nz.OUTDOOR_TREATMENT, note=note)
    # skillion rafters back to the house wall
    wall_y, wall_z = g.ft(g.PORCH_BACK_Y_FT), 2700
    dy, dz = wall_y - py, wall_z - beam_z2
    rlen = math.hypot(dy, dz)
    pitch = math.atan2(dz, dy)
    x = x1 + 150
    while x <= x2 - 100:
        _el(els, "rafter", 1, "140x45", rlen, 45, 140, x, (py + wall_y) / 2,
            (beam_z2 + wall_z) / 2, math.pi / 2, pitch,
            treatment=nz.OUTDOOR_TREATMENT, note=note)
        x += nz.RAFTER_SPACING


def slabs(els: list) -> None:
    for name, x1, y1, x2, y2 in g.SLAB_RECTS_FT:
        x1, y1, x2, y2 = g.ft(x1), g.ft(y1), g.ft(x2), g.ft(y2)
        _el(els, "slab", 1, "100 thk", x2 - x1, y2 - y1, 100,
            (x1 + x2) / 2, (y1 + y2) / 2, -50, 0, 0,
            grade="concrete", treatment="-", note=name)


# ---------------------------------------------------------------------------
# Top-level generator
# ---------------------------------------------------------------------------

@dataclass
class GenerateResult:
    elements: list[dict]
    segments: list[dict]   # frame-segment metadata for meta.frame_segments
    warnings: list[str]    # scope + override + unknown-segment warnings


def generate(cfg: ModelConfig | None = None) -> GenerateResult:
    cfg = (cfg or ModelConfig()).normalised()
    storeys = cfg.storeys
    note = "; ".join(cfg.warnings())
    rspacing = nz.rafter_spacing(cfg.snow_zone)
    els: list[dict] = []
    segments: list[dict] = []
    slabs(els)

    upper_poly = [(g.ft(x), g.ft(y)) for x, y in g.UPPER_POLY_FT]
    full_poly = [(g.ft(x), g.ft(y)) for x, y in g.EXTERIOR_POLY_FT]
    envelope_warns: list[str] = []

    for s in range(1, storeys + 1):
        z = (s - 1) * nz.STOREY_RISE
        nzs_default = nz.stud_spacing(s, storeys, cfg.wind_zone)
        if s == 1:
            walls = g.ground_exterior_walls() + g.ground_interior_walls()
        else:
            walls = g.upper_exterior_walls() + g.upper_interior_walls()
        counters = {True: 0, False: 0}
        for w in walls:
            counters[w.exterior] += 1
            prefix = "G" if s == 1 else f"L{s}"
            kind = "EXT" if w.exterior else "INT"
            seg_id = f"{prefix}-{kind}-{counters[w.exterior]:03d}"
            label = (f"L{s} {'Exterior' if w.exterior else 'Interior'} "
                     f"Wall {counters[w.exterior]:02d}")
            mat_key = cfg.effective_stud_material(s, seg_id)
            spacing = cfg.effective_stud_spacing(s, seg_id, nzs_default)
            plies = cfg.effective_wall_plies(s, seg_id)
            wall_note = note
            if spacing != nzs_default:
                wall_note = (f"{note}; " if note else "") + CUSTOM_SPACING_NOTE
            seg_len = round(math.hypot(w.x2 - w.x1, w.y2 - w.y1), 1)
            if seg_len > 6000:
                envelope_warns.append(
                    f"{seg_id}: wall length {seg_len / 1000:.1f} m exceeds "
                    "the 6 m x 3 m frame envelope — verify panel joins")
            segments.append(dict(
                segment_id=seg_id, storey=s, label=label,
                length_mm=seg_len,
                exterior=w.exterior, openings=len(w.openings),
                material=materials.display_name(mat_key),
                spacing_mm=spacing, plies=plies,
                treatment=cfg.wall_treatment or nz.WALL_TREATMENT))
            frame_wall(els, w, s, spacing, z, wall_note,
                       material=materials.display_name(mat_key), plies=plies,
                       segment_id=seg_id, segment_label=label,
                       treatment=cfg.wall_treatment or nz.WALL_TREATMENT)
        if s < storeys:  # platform for the storey above
            frame_floor(els, upper_poly, s, z + WALL_H, note)

    top_z = (storeys - 1) * nz.STOREY_RISE + WALL_H
    top_poly = full_poly if storeys == 1 else upper_poly
    frame_ceiling(els, top_poly, storeys, top_z, note)

    roof_rects = [(rect, storeys, top_z) for rect in g.MAIN_ROOF_FT]
    roof_rects.append((g.GARAGE_ROOF_FT, 1, WALL_H))
    for rect, st, zz in roof_rects:
        if cfg.roof == "hip":
            frame_hip_roof(els, rect, st, zz, rspacing, note)
        else:
            gable_mat = materials.display_name(
                cfg.effective_stud_material(st, None))
            frame_gable_roof(els, rect, st, zz, rspacing,
                             cfg.gable_spacing, note, material=gable_mat)
    frame_porch(els, note)

    warnings = (list(cfg.warnings()) + list(cfg.override_warnings)
                + envelope_warns)
    if cfg.has_spacing_override():
        warnings.append(CUSTOM_SPACING_NOTE)
    known = {sg["segment_id"] for sg in segments}
    for param, d in (("stud_material_segments", cfg.stud_material_segments),
                     ("stud_spacing_segments", cfg.stud_spacing_segments),
                     ("wall_plies_segments", cfg.wall_plies_segments)):
        for seg in d:
            if seg not in known:
                warnings.append(f"unknown frame segment '{_safe(seg)}' "
                                f"in {param} — ignored")
    return GenerateResult(els, segments, warnings)


if __name__ == "__main__":
    from collections import Counter
    for cfg in (ModelConfig(),
                ModelConfig(storeys=2, roof="hip"),
                ModelConfig(storeys=3, wind_zone="very high", snow_zone="N3"),
                ModelConfig(wind_speed=58.0, snow_zone="N5", gable_spacing=400),
                ModelConfig(storeys=2, stud_material_overall="sg10",
                            stud_spacing_overall=400, wall_plies_overall=2,
                            stud_material_levels={2: "hyspan"},
                            stud_material_segments={"G-EXT-001": "glulam"})):
        res = generate(cfg)
        els = res.elements
        c = Counter(e["type_code"] for e in els)
        bad = [e for e in els if e["length_mm"] <= 0]
        print(f"{cfg} -> warnings={res.warnings}")
        print(f"  {len(els)} elements, {len(res.segments)} segments, "
              f"zero-length={len(bad)}")
        print("  ", dict(sorted(c.items())))
