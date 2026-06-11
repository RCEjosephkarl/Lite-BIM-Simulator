"""Sample building geometry digitized from the reference floor plan.

70' x 60' single-storey plan: garage protruding at the bottom-left, left
wing (bedroom 1 / kitchen / living), centre core (foyer / pantry / kitchen),
right wing (living / dining / bedrooms 2-3 / master), patio at the top and
covered porch at the bottom-right. Plan coordinates: x = east, y = north,
origin at the bottom-left of the 70x60 bounding box. Internally everything
is millimetres (feet * 304.8).
"""

from __future__ import annotations

from dataclasses import dataclass, field

FT = 304.8


def ft(v: float) -> float:
    return v * FT


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


def _win(offset_ft: float, width_ft: float, sill: float = WINDOW_SILL,
         head: float = WINDOW_HEAD) -> Opening:
    return Opening(ft(offset_ft), ft(width_ft), sill, head, "window")


def _door(offset_ft: float, width_ft: float, head: float = DOOR_HEAD,
          kind: str = "door") -> Opening:
    return Opening(ft(offset_ft), ft(width_ft), 0, head, kind)


def _wall(x1: float, y1: float, x2: float, y2: float, exterior: bool,
          openings: list[Opening] | None = None) -> Wall:
    return Wall(ft(x1), ft(y1), ft(x2), ft(y2), exterior, openings or [])


# Exterior footprint, counter-clockwise (feet).
EXTERIOR_POLY_FT = [
    (10, 0), (34, 0), (34, 8), (70, 8), (70, 58),
    (44, 58), (44, 52), (2, 52), (2, 24), (10, 24),
]

# Ground-storey exterior walls (one per polygon edge) with openings.
def ground_exterior_walls() -> list[Wall]:
    p = EXTERIOR_POLY_FT
    walls = []
    edge_openings = {
        0: [_door(4, 16, GARAGE_HEAD, "garage")],            # garage door
        2: [_door(6, 3), _door(16, 6, DOOR_HEAD, "door"),    # entry + slider to porch
            _win(26, 4)],
        3: [_win(6, 5), _win(22, 4), _win(40, 4)],           # master, bed 3, bed 2
        4: [_win(2, 4), _win(12, 6)],                        # bed 2, living (right)
        6: [_door(8, 8, DOOR_HEAD, "door"),                  # slider to patio
            _win(22, 4), _win(32, 5)],                       # kitchen, bed 1
        7: [_win(4, 4), _win(21, 2, 1400, 2100)],            # bed 1, bathroom
        8: [_door(3, 3)],                                    # stoop / laundry door
    }
    for i in range(len(p)):
        x1, y1 = p[i]
        x2, y2 = p[(i + 1) % len(p)]
        walls.append(_wall(x1, y1, x2, y2, True, edge_openings.get(i)))
    return walls


def ground_interior_walls() -> list[Wall]:
    d = DOOR_HEAD_INT
    return [
        _wall(10, 24, 34, 24, False, [_door(20, 3, d)]),       # garage common wall
        _wall(34, 8, 34, 24, False, [_door(8, 3, d)]),         # garage / pantry
        _wall(2, 40, 16, 40, False, [_door(10, 2.7, d)]),      # bedroom 1 south
        _wall(16, 40, 16, 52, False),                          # bedroom 1 / kitchen
        _wall(2, 32, 22, 32, False, [_door(17, 2.7, d)]),      # bathroom south
        _wall(28, 24, 28, 36, False, [_door(5, 3, d)]),        # foyer west
        _wall(28, 36, 40, 36, False, [_door(4, 6, d, "cased")]),  # living (L) south
        _wall(40, 24, 40, 52, False, [_door(6, 3, d), _door(20, 5, d, "cased")]),
        _wall(44, 8, 44, 24, False, [_door(9, 2.7, d)]),       # bath 2 west
        _wall(44, 24, 70, 24, False, [_door(4, 2.7, d), _door(18, 3, d)]),
        _wall(57, 8, 57, 24, False, [_door(9, 2.7, d)]),       # bath 2 / master
        _wall(58, 24, 58, 46, False, [_door(4, 2.7, d), _door(16, 2.7, d)]),
        _wall(58, 38, 70, 38, False, [_door(3, 2.7, d)]),      # bedroom 3 north
        _wall(58, 44, 70, 44, False, [_door(3, 2.7, d)]),      # bedroom 2 south
        _wall(44, 46, 58, 46, False, [_door(4, 8, d, "cased")]),  # living/dining
    ]


# Upper storeys: footprint minus the single-storey garage.
UPPER_POLY_FT = [
    (34, 8), (70, 8), (70, 58), (44, 58), (44, 52),
    (2, 52), (2, 24), (34, 24),
]


def upper_exterior_walls() -> list[Wall]:
    """Exterior walls for storeys 2-3 with evenly auto-placed windows."""
    p = UPPER_POLY_FT
    walls = []
    for i in range(len(p)):
        x1, y1 = p[i]
        x2, y2 = p[(i + 1) % len(p)]
        w = _wall(x1, y1, x2, y2, True)
        length = ((w.x2 - w.x1) ** 2 + (w.y2 - w.y1) ** 2) ** 0.5
        n = int(length // ft(15))
        if n > 0 and length > ft(8):
            step = length / (n + 1)
            for k in range(1, n + 1):
                w.openings.append(
                    Opening(k * step - ft(2), ft(4), WINDOW_SILL, WINDOW_HEAD, "window"))
        walls.append(w)
    return walls


def upper_interior_walls() -> list[Wall]:
    """Simplified bearing lines on upper storeys (support floor joists)."""
    d = DOOR_HEAD_INT
    return [
        _wall(2, 32, 22, 32, False, [_door(17, 2.7, d)]),
        _wall(2, 40, 16, 40, False, [_door(10, 2.7, d)]),
        _wall(28, 24, 28, 52, False, [_door(5, 3, d)]),
        _wall(40, 24, 40, 52, False, [_door(6, 3, d)]),
        _wall(44, 24, 70, 24, False, [_door(4, 2.7, d), _door(18, 3, d)]),
        _wall(58, 24, 58, 46, False, [_door(4, 2.7, d), _door(16, 2.7, d)]),
        _wall(44, 46, 58, 46, False, [_door(4, 8, d, "cased")]),
    ]


# Interior wall lines used to break long floor-joist runs into spans (mm).
JOIST_SUPPORT_XS = [ft(v) for v in (16, 28, 34, 40, 44, 57, 58)]

# ---------------------------------------------------------------------------
# Roofs: (x1, y1, x2, y2, ridge_axis) in feet. ridge_axis 'x' = ridge runs
# east-west, 'y' = ridge runs north-south.
# ---------------------------------------------------------------------------

GARAGE_ROOF_FT = (9, -1, 35, 25, "x")
MAIN_ROOF_FT = [
    (1, 23, 45, 53, "x"),    # left wing + centre
    (43, 7, 71, 59, "y"),    # right wing
]

# ---------------------------------------------------------------------------
# Concrete slabs (storey 1 visuals; excluded from the timber BOM).
# ---------------------------------------------------------------------------

SLABS_FT = [
    ("Floor slab", EXTERIOR_POLY_FT),     # rendered as bounding boxes per rect below
]
SLAB_RECTS_FT = [
    ("floor slab (garage)", 10, 0, 34, 24),
    ("floor slab (left wing)", 2, 24, 44, 52),
    ("floor slab (right wing)", 44, 8, 70, 58),
    ("patio slab", 28, 52, 44, 60),
    ("porch slab", 40, 4, 64, 8),
    ("stoop", 3, 20, 10, 24),
]

# Covered porch: posts along the front edge + beam + skillion roof back to wall.
PORCH_POST_XS_FT = [40.5, 46, 52, 58, 63.5]
PORCH_POST_Y_FT = 4.3
PORCH_BACK_Y_FT = 8
PORCH_X1_FT, PORCH_X2_FT = 40, 64
