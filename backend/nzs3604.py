"""NZS 3604:2011 rules engine (simplified, "lite BIM" scope).

Member sizes, spacings and clause references for light timber-framed
buildings. Values follow NZS 3604:2011 *Timber-framed buildings* for
common residential loading; this is a teaching/estimating aid, not a
substitute for the standard or for specific engineering design (SED).
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# General
# ---------------------------------------------------------------------------

GRADE = "SG8"                  # NZS 3604 cl. 2.3 — minimum structural grade
WALL_TREATMENT = "H1.2"        # cl. 4 / NZS 3640 — enclosed framing
OUTDOOR_TREATMENT = "H3.2"     # exposed posts/beams
# NZS 3640 hazard-class treatments selectable for wall framing
TREATMENTS = ("H1.2", "H3.1", "H3.2", "H4", "H5")

STUD_HEIGHT = 2400             # common storey stud height (mm)
PLATE_THICK = 45               # 90x45 plate laid flat
WALL_THICK = 90                # framing depth
STOREY_RISE = 2400 + 3 * 45 + 190 + 20  # studs + 3 plates + joist + flooring

# NZS 3604 scope: buildings within 10 m height envelope (~2.5 storeys).
MAX_STOREYS_IN_SCOPE = 2
SED_NOTE = "outside NZS 3604 scope (>10 m / 3 storeys) — SED required"

# ---------------------------------------------------------------------------
# Site exposure — Section 5
# ---------------------------------------------------------------------------

# Wind zones (cl. 5.2 / Table 5.4) with their ULS design wind speed caps (m/s).
WIND_ZONES: dict[str, float] = {
    "low": 32.0,
    "medium": 37.0,
    "high": 44.0,
    "very high": 50.0,
    "extra high": 55.0,
}
WIND_REF = "Table 5.4"
WIND_SED_NOTE = "design wind speed > 55 m/s — outside NZS 3604, SED required"

# Snow zones (Section 15) — ground snow load (kPa). None => beyond scope.
SNOW_ZONES: dict[str, float | None] = {
    "N0": 0.0,    # no snow load
    "N1": 0.5,
    "N2": 1.0,
    "N3": 1.5,
    "N4": 2.0,
    "N5": None,   # sub-alpine / > 2.0 kPa — SED
}
SNOW_REF = "Section 15"
SNOW_SED_NOTE = "snow load > 2.0 kPa — outside NZS 3604, SED required"


def wind_zone_for_speed(speed_ms: float) -> str:
    """Smallest wind zone whose design speed covers the input (Table 5.4)."""
    for zone, cap in WIND_ZONES.items():
        if speed_ms <= cap:
            return zone
    return "sed"


# ---------------------------------------------------------------------------
# Wall framing — Section 8
# ---------------------------------------------------------------------------

STUD_SIZE = (90, 45)           # Table 8.2
STUD_SPACING_TOP = 600         # Table 8.2 — single / top storey
STUD_SPACING_LOWER = 400       # Table 8.2 — lowest storey of multi-storey

# Table 8.2 selects studs by wind zone; simplified here as max centres for
# 90x45 SG8 studs at 2.4 m height.
STUD_SPACING_BY_WIND = {
    "low": 600,
    "medium": 600,
    "high": 480,
    "very high": 400,
    "extra high": 400,
    "sed": 400,
}

PLATE_SIZE = (90, 45)          # cl. 8.5.2 (top plate doubled)
NOG_SIZE = (90, 45)            # cl. 8.5.2.4
NOG_MAX_SPACING = 1350         # cl. 8.5.2.4 — max nog/dwang centres

# Lintels — Table 8.9 (simplified by clear span, light roof loading).
# (max_span_mm, size_label, depth_mm, breadth_mm)
LINTEL_TABLE = [
    (1200, "2/90x45", 90, 90),
    (2100, "2/140x45", 140, 90),
    (3000, "2/190x45", 190, 90),
    (4200, "2/240x45", 240, 90),
    (5000, "2/290x45", 290, 90),   # garage door — verify against Table 8.9
]
LINTEL_REF = "Table 8.9"
TRIMMER_REF = "cl. 8.5.3"

# ---------------------------------------------------------------------------
# Floors — Section 7
# ---------------------------------------------------------------------------

JOIST_SIZE = (190, 45)         # Table 7.1 — SG8 @ 450 crs, span <= ~3.9 m
JOIST_SPACING = 450
JOIST_MAX_SPAN = 3900
JOIST_REF = "Table 7.1"
BLOCKING_REF = "cl. 7.1.4"

# ---------------------------------------------------------------------------
# Ceiling + roof — Section 10
# ---------------------------------------------------------------------------

CEILING_JOIST_SIZE = (90, 45)  # Table 10.3 @ 600 crs
CEILING_JOIST_SPACING = 600
CEILING_REF = "Table 10.3"

RAFTER_SIZE = (140, 45)        # Table 10.1 @ 900 crs, light roof
RAFTER_SPACING = 900
RAFTER_REF = "Table 10.1"
RIDGE_SIZE = (190, 45)         # cl. 10.2.1.6
RIDGE_REF = "cl. 10.2.1.6"
HIP_SIZE = (190, 45)           # hip/valley rafters one size deeper, cl. 10.2.1.7
HIP_REF = "cl. 10.2.1.7"
ROOF_PITCH_DEG = 25.0
EAVE_OVERHANG = 450

# Gable-end studs (support roof framing at gable ends, cl. 8.5 / 10.4).
GABLE_STUD_SIZE = (90, 45)
GABLE_STUD_REF = "cl. 8.5 (gable-end framing)"
GABLE_STUD_DEFAULT_SPACING = 600


def rafter_spacing(snow_zone: str) -> int:
    """Rafter centres reduced for snow-loaded roofs (Section 15, simplified)."""
    load = SNOW_ZONES.get(snow_zone, 0.0)
    if load is None:       # N5: keep tightest centres, flagged SED elsewhere
        return 480
    if load <= 1.0:
        return RAFTER_SPACING
    return 600

# ---------------------------------------------------------------------------
# Outdoor (porch) — exposed members
# ---------------------------------------------------------------------------

POST_SIZE = (90, 90)           # verandah posts, H3.2
POST_REF = "cl. 6.12 / NZS 3640"
PORCH_BEAM_SIZE = (190, 90)    # 2/190x45 built-up verandah beam
PORCH_BEAM_REF = "Table 10.5"

# ---------------------------------------------------------------------------
# Element-type catalogue: code -> (name, category, nzs_ref, color_hex)
# Colors drive the frontend "color by function" mode.
# ---------------------------------------------------------------------------

ELEMENT_TYPES = {
    "stud":          ("Wall stud",          "wall",    "Table 8.2",   "#fbbf24"),
    "trimmer_stud":  ("Trimming stud",      "wall",    TRIMMER_REF,   "#f97316"),
    "jack_stud":     ("Jack/cripple stud",  "wall",    TRIMMER_REF,   "#fb7185"),
    "plate_bottom":  ("Bottom plate",       "wall",    "cl. 8.5.2",   "#1d4ed8"),
    "plate_top":     ("Top plate",          "wall",    "cl. 8.5.2",   "#3b82f6"),
    "nog":           ("Nog / dwang",        "wall",    "cl. 8.5.2.4", "#22c55e"),
    "lintel":        ("Lintel",             "wall",    LINTEL_REF,    "#ef4444"),
    "sill_trimmer":  ("Sill trimmer",       "wall",    TRIMMER_REF,   "#ec4899"),
    "joist":         ("Floor joist",        "floor",   JOIST_REF,     "#14b8a6"),
    "blocking":      ("Joist blocking",     "floor",   BLOCKING_REF,  "#0d9488"),
    "ceiling_joist": ("Ceiling joist",      "ceiling", CEILING_REF,   "#a855f7"),
    "rafter":        ("Rafter",             "roof",    RAFTER_REF,    "#84cc16"),
    "hip_rafter":    ("Hip rafter",         "roof",    HIP_REF,       "#4d7c0f"),
    "jack_rafter":   ("Jack rafter",        "roof",    RAFTER_REF,    "#d9f99d"),
    "gable_stud":    ("Gable-end stud",     "roof",    GABLE_STUD_REF, "#fde047"),
    "ridge":         ("Ridge board",        "roof",    RIDGE_REF,     "#b91c1c"),
    "fascia":        ("Fascia",             "roof",    "cl. 10.2",    "#0ea5e9"),
    "post":          ("Verandah post",      "outdoor", POST_REF,      "#92400e"),
    "beam":          ("Verandah beam",      "outdoor", PORCH_BEAM_REF, "#7c3aed"),
    "truss_top_chord": ("Truss top chord", "roof", "specific design / supplier", "#65a30d"),
    "truss_bottom_chord": ("Truss bottom chord", "roof", "specific design / supplier", "#15803d"),
    "truss_web":     ("Truss web member", "roof", "specific design / supplier", "#4ade80"),
    "truss_king_post": ("Truss king post", "roof", "specific design / supplier", "#22c55e"),
    "truss_queen_post": ("Truss queen post", "roof", "specific design / supplier", "#86efac"),
    "truss_girder":  ("Girder truss member", "roof", "specific design / supplier", "#166534"),
    "slab":          ("Concrete slab",      "concrete", "NZS 3604 cl. 7.5 (slab-on-ground)", "#9ca3af"),
}


def stud_spacing(storey: int, total_storeys: int, wind_zone: str = "medium") -> int:
    """Table 8.2 — centres reduce with wind zone, and again for the lowest
    storey(s) of a multi-storey wall."""
    base = STUD_SPACING_BY_WIND.get(wind_zone, STUD_SPACING_LOWER)
    if total_storeys > 1 and storey < total_storeys:
        return min(base, STUD_SPACING_LOWER)
    return base


def lintel_for_span(span_mm: float) -> tuple[str, int, int]:
    """Return (size_label, depth_mm, breadth_mm) for an opening clear span."""
    for max_span, label, depth, breadth in LINTEL_TABLE:
        if span_mm <= max_span:
            return label, depth, breadth
    # Beyond tabulated spans: flag, keep largest member so the model renders.
    label, depth, breadth = LINTEL_TABLE[-1][1:]
    return f"{label} (SED)", depth, breadth


def scope_note(total_storeys: int) -> str:
    return SED_NOTE if total_storeys > MAX_STOREYS_IN_SCOPE else ""
