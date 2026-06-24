"""Sample building geometry digitized from examples/sample_building_plans.pdf.

Reference: the "Proposed home" consent-drawing set (FLOORPLAN sheet, scale
1:100, Building Area 183.15 m² / 178.7 m² over frame). It is a single-storey,
light timber-framed house on a ~18.68 m (E-W) x 11.17 m (N-S) footprint:

  * GARAGE in the south-east corner (4.5 m sectional door on the south wall),
  * BEDROOM 2 / BEDROOM 3 / WC stacked above the garage on the east side,
  * central LOUNGE / BATH / STORE / ENTRY core,
  * BEDROOM 1 / ENS / WIR to the centre-north,
  * open-plan KITCHEN / DINING / LIVING on the west,
  * a COVERED AREA (outdoor) notched into the north-west corner,
  * a 28° trussed roof (trusses @ 900 c/c), Colorsteel longrun roofing.

This is a *simplified* digitization for the lite BIM simulator: the overall
footprint, the major openings (garage door, sliders, windows) and the room
partitions follow the PDF, but it is not a measured reproduction — verify any
member against the consent drawings or NZS 3604:2011 / specific design.

Plan coordinates: x = east, y = north, origin at the south-west corner.
Everything is millimetres. `ft()` survives for the framing generator, which
multiplies the *_FT polygons/rects by it; those values are authored as
millimetres-expressed-in-the-internal-unit via `_f()` (`ft(_f(mm)) == mm`).
"""

from __future__ import annotations

from dataclasses import dataclass, field

FT = 304.8


def ft(v: float) -> float:
    return v * FT


def _f(mm: float) -> float:
    """Express a millimetre dimension in the internal `ft()` unit (mm / 304.8).

    The framing generator stores roof rects, slab rects and the porch in the
    legacy "feet" unit and converts them with `ft()`; authoring them through
    `_f()` keeps the source metric while preserving that contract.
    """
    return mm / FT


# ---------------------------------------------------------------------------
# Openings + walls
# ---------------------------------------------------------------------------

DOOR_HEAD = 2100
DOOR_HEAD_INT = 1980
WINDOW_SILL = 900
WINDOW_HEAD = 2100
GARAGE_HEAD = 2134  # 7'


@dataclass
class Opening:
    offset: float          # mm from wall start, to opening start
    width: float           # clear span, mm
    sill: float            # mm above floor (0 for doors)
    head: float            # mm above floor
    kind: str              # 'door' | 'window' | 'garage' | 'cased'


@dataclass
class Wall:
    x1: float
    y1: float
    x2: float
    y2: float
    exterior: bool
    openings: list[Opening] = field(default_factory=list)


def _win(offset: float, width: float, sill: float = WINDOW_SILL,
         head: float = WINDOW_HEAD) -> Opening:
    """Window opening, all dimensions in millimetres."""
    return Opening(offset, width, sill, head, "window")


def _door(offset: float, width: float, head: float = DOOR_HEAD,
          kind: str = "door") -> Opening:
    """Door / slider / garage opening, all dimensions in millimetres."""
    return Opening(offset, width, 0, head, kind)


def _wall(x1: float, y1: float, x2: float, y2: float, exterior: bool,
          openings: list[Opening] | None = None) -> Wall:
    """Wall on millimetre coordinates."""
    return Wall(x1, y1, x2, y2, exterior, openings or [])


# ---------------------------------------------------------------------------
# Footprint (mm). Heated envelope = the 18.68 x 11.17 m bounding rectangle with
# the covered-area notch removed from the north-west corner. Counter-clockwise.
# ---------------------------------------------------------------------------

W = 18680     # overall east-west
D = 11170     # overall north-south
GARAGE_W = 6000   # garage bay (south-east), x 12680..18680
GARAGE_D = 6000   # garage depth, y 0..6000
COV_W = 4500      # covered-area notch width (north-west)
COV_D = 3000      # covered-area notch depth
GX = W - GARAGE_W   # 12680 — garage / house party line
CY = D - COV_D      # 8170  — covered-area notch south edge

EXTERIOR_POLY_MM = [
    (0, 0), (W, 0), (W, D), (COV_W, D), (COV_W, CY), (0, CY),
]
EXTERIOR_POLY_FT = [(_f(x), _f(y)) for x, y in EXTERIOR_POLY_MM]


def ground_exterior_walls() -> list[Wall]:
    """Exterior walls (one per footprint edge) with the PDF's major openings."""
    p = EXTERIOR_POLY_MM
    edge_openings = {
        # 0: south wall, west->east (living slider, entry, lounge, garage door)
        0: [_door(1200, 2400, DOOR_HEAD, "door"),         # living stacker slider
            _door(8200, 910, DOOR_HEAD, "door"),          # entry
            _win(10200, 1500),                            # lounge
            _door(13780, 4500, GARAGE_HEAD, "garage")],   # 4.5 m garage door
        # 1: east wall, south->north (bedroom 2 / 3 windows)
        1: [_win(7000, 1800), _win(9500, 1500)],
        # 2: north wall, east->west (bedroom 2, hall, kitchen, dining)
        2: [_win(1500, 1500), _win(5000, 1200),
            _win(9500, 1800), _win(12500, 1500)],
        # 3: covered-area notch (vertical), north->south — slider to covered area
        3: [_door(400, 2100, DOOR_HEAD, "door")],
        # 4: covered-area notch (horizontal), east->west — slider to covered area
        4: [_door(1000, 2400, DOOR_HEAD, "door")],
        # 5: west wall, north->south (living / dining windows)
        5: [_win(1500, 1500), _win(5000, 1200)],
    }
    walls = []
    for i in range(len(p)):
        x1, y1 = p[i]
        x2, y2 = p[(i + 1) % len(p)]
        walls.append(_wall(x1, y1, x2, y2, True, edge_openings.get(i)))
    return walls


def ground_interior_walls() -> list[Wall]:
    d = DOOR_HEAD_INT
    return [
        # West open-plan wing: living (south) / kitchen+dining (north) divider
        _wall(0, 5500, 5000, 5500, False, [_door(3500, 1500, d, "cased")]),
        # West wing / central core party line (x = 5000)
        _wall(5000, 0, 5000, D, False, [_door(3000, 900, d)]),
        # Central core / lounge-bath zone party line (x = 8500)
        _wall(8500, 0, 8500, D, False,
              [_door(2500, 900, d), _door(8000, 820, d)]),
        # House / east-block (garage + east bedrooms) party line (x = 12680)
        _wall(GX, 0, GX, D, False, [_door(6500, 900, d, "cased")]),
        # Lounge (south) / store + bath (north) divider in the central zone
        _wall(8500, 6000, GX, 6000, False, [_door(2000, 820, d)]),
        # Garage (south) / east bedrooms (north) divider
        _wall(GX, GARAGE_D, W, GARAGE_D, False, [_door(500, 900, d)]),
        # East bedroom 2 / bedroom 3 divider (x = 15600)
        _wall(15600, GARAGE_D, 15600, D, False, [_door(1000, 820, d)]),
        # East bedrooms / hall divider (y = 8800)
        _wall(GX, 8800, 15600, 8800, False, [_door(1500, 820, d)]),
        # Bedroom 1 (north) / entry (south) divider in the central core
        _wall(5000, CY, 8500, CY, False, [_door(2500, 820, d)]),
        # WIR partition off bedroom 1
        _wall(6800, CY, 6800, D, False, [_door(800, 720, d)]),
    ]


# ---------------------------------------------------------------------------
# Synthesized newer floors (storeys below the sample/ground plan). Footprint =
# the heated envelope minus the single-storey garage bay; windows auto-placed.
# ---------------------------------------------------------------------------

UPPER_POLY_MM = [
    (0, 0), (GX, 0), (GX, GARAGE_D), (W, GARAGE_D), (W, D),
    (COV_W, D), (COV_W, CY), (0, CY),
]
UPPER_POLY_FT = [(_f(x), _f(y)) for x, y in UPPER_POLY_MM]


def upper_exterior_walls() -> list[Wall]:
    """Exterior walls for the synthesized lower storeys, auto-placed windows."""
    p = UPPER_POLY_MM
    walls = []
    for i in range(len(p)):
        x1, y1 = p[i]
        x2, y2 = p[(i + 1) % len(p)]
        w = _wall(x1, y1, x2, y2, True)
        length = ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5
        n = int(length // 4500)
        if n > 0 and length > 2400:
            step = length / (n + 1)
            for k in range(1, n + 1):
                w.openings.append(_win(k * step - 600, 1200))
        walls.append(w)
    return walls


def upper_interior_walls() -> list[Wall]:
    """Simplified bearing lines on the synthesized lower storeys."""
    d = DOOR_HEAD_INT
    return [
        _wall(0, 5500, 5000, 5500, False, [_door(3500, 1500, d, "cased")]),
        _wall(5000, 0, 5000, D, False, [_door(3000, 900, d)]),
        _wall(8500, 0, 8500, D, False, [_door(2500, 900, d)]),
        _wall(GX, 0, GX, D, False, [_door(6500, 900, d)]),
        _wall(8500, 6000, GX, 6000, False, [_door(2000, 820, d)]),
        _wall(GX, 8800, W, 8800, False, [_door(1500, 820, d)]),
    ]


# Interior wall lines used to break long floor-joist runs into spans (mm).
JOIST_SUPPORT_XS = [5000.0, 8500.0, float(GX), 15600.0]

# ---------------------------------------------------------------------------
# Roofs: (x1, y1, x2, y2, ridge_axis) authored in millimetres via _f().
# ridge_axis 'x' = ridge runs east-west, 'y' = ridge runs north-south.
# Roof planes simply overlap at the wing intersections (no valley framing).
# ---------------------------------------------------------------------------

GARAGE_ROOF_FT = (_f(GX), _f(0), _f(W), _f(GARAGE_D), "x")
MAIN_ROOF_FT = [
    (_f(0), _f(0), _f(GX), _f(D), "x"),            # west + central block
    (_f(GX), _f(GARAGE_D), _f(W), _f(D), "y"),     # east bedrooms wing
]

# ---------------------------------------------------------------------------
# Concrete slabs (storey-1 visuals; excluded from the timber BOM).
# ---------------------------------------------------------------------------

SLAB_RECTS_FT = [
    ("floor slab (west / central)", _f(0), _f(0), _f(GX), _f(CY)),
    ("floor slab (north wing)", _f(COV_W), _f(CY), _f(GX), _f(D)),
    ("garage slab", _f(GX), _f(0), _f(W), _f(GARAGE_D)),
    ("floor slab (east bedrooms)", _f(GX), _f(GARAGE_D), _f(W), _f(D)),
    ("covered area slab", _f(0), _f(CY), _f(COV_W), _f(D)),
]

# Covered area (north-west): posts along the open north edge carry the eave;
# the main roof oversails the bay (lean-to/skillion not separately framed).
PORCH_POST_XS_FT = [_f(x) for x in (300, 1400, 2500, 3600, 4400)]
PORCH_POST_Y_FT = _f(D)        # open north edge of the covered area
PORCH_BACK_Y_FT = _f(CY)       # building wall the bay leans against
PORCH_X1_FT, PORCH_X2_FT = _f(0), _f(COV_W)
