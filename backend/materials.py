"""Stud material catalogue with sourced USD-per-lineal-metre pricing.

Estimating data only — NOT quote-grade. Prices were collected from public
NZ retail listings on the dates recorded below, converted to USD at the
recorded FX rate. Sizes the retailer does not list are linearly scaled by
cross-section area and marked in `pricing_notes`. Selecting an engineered
product (Prolam/Glulam/LVL) here is a costing choice only; it is not an
engineering substitution — verify against NZS 3604:2011 or SED.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field

FX_RATE_NZD_USD = 0.5795
FX_SOURCE = "xe.com / exchange-rates.org mid-market rate"
FX_DATE = "2026-06-11"

DISCLAIMERS = [
    "Prices are indicative supply-only estimates from public NZ retail "
    "listings, converted to USD; they are not quotes and exclude delivery, "
    "fixings, labour and waste.",
    "NZ retail prices include 15% GST; trade pricing is typically lower.",
    "Material substitutions, stud spacing and ply changes require "
    "verification against NZS 3604:2011 or specific engineering design.",
]


@dataclass(frozen=True)
class Material:
    key: str                    # internal key, e.g. 'sg8'
    display_name: str           # exact display string, e.g. 'HySPAN'
    category: str               # 'sawn_timber' | 'glulam' | 'lvl'
    typical_sizes_mm: tuple[str, ...]
    default_size_mm: str
    default_usd_per_lm: float
    price_confidence: str       # 'high' | 'medium' | 'low'
    price_source_name: str
    price_source_url: str
    price_source_date: str
    source_currency: str
    source_price: float
    source_unit: str
    fx_rate_to_usd: float = FX_RATE_NZD_USD
    fx_source: str = FX_SOURCE
    fx_date: str = FX_DATE
    pricing_notes: str = ""
    # per-size USD/lm map; sizes not listed fall back to default_usd_per_lm
    size_prices_usd_per_lm: dict[str, float] = field(default_factory=dict)


def _usd(nzd_per_lm: float) -> float:
    return round(nzd_per_lm * FX_RATE_NZD_USD, 2)


_KIWI = "Kiwi Timber Supplies (Auckland, NZ)"

MATERIALS: dict[str, Material] = {
    "sg8": Material(
        key="sg8", display_name="SG8", category="sawn_timber",
        typical_sizes_mm=("90x45", "140x45", "190x45", "240x45", "290x45"),
        default_size_mm="90x45",
        default_usd_per_lm=_usd(6.07),
        price_confidence="high",
        price_source_name=_KIWI,
        price_source_url="https://kiwitimber.co.nz/index.php?"
                         "route=product/search&search=90x45",
        price_source_date="2026-06-11",
        source_currency="NZD", source_price=6.07,
        source_unit="NZD per lineal metre (90x45 H1.2 SG8 KD, incl. GST)",
        pricing_notes="Exact-size public retail per-metre price for 90x45 "
                      "H1.2 SG8. Other sizes scaled linearly by "
                      "cross-section area from the 90x45 rate.",
        size_prices_usd_per_lm={
            "90x45": _usd(6.07), "140x45": _usd(9.44), "190x45": _usd(12.81),
            "240x45": _usd(16.19), "290x45": _usd(19.56),
            "180x25": _usd(6.74), "90x90": _usd(12.14),
        },
    ),
    "sg10": Material(
        key="sg10", display_name="SG10", category="sawn_timber",
        typical_sizes_mm=("90x45", "140x45", "190x45"),
        default_size_mm="90x45",
        default_usd_per_lm=_usd(7.13),
        price_confidence="high",
        price_source_name=_KIWI,
        price_source_url="https://kiwitimber.co.nz/index.php?"
                         "route=product/search&search=90x45",
        price_source_date="2026-06-11",
        source_currency="NZD", source_price=38.51,
        source_unit="NZD per 5.4 m length (90x45 H1.2 SG10 KD, incl. GST)",
        pricing_notes="Derived from the 5.4 m piece price: "
                      "38.51 / 5.4 = 7.13 NZD/lm.",
        size_prices_usd_per_lm={"90x45": _usd(7.13)},
    ),
    "prolam": Material(
        key="prolam", display_name="Prolam", category="glulam",
        typical_sizes_mm=("140x42", "190x90", "240x90", "240x42"),
        default_size_mm="90x45",
        default_usd_per_lm=_usd(29.13),
        price_confidence="low",
        price_source_name="Mitre 10 NZ — Prolam laminated radiata beams",
        price_source_url="https://www.mitre10.co.nz/shop/building-hardware/"
                         "timber/structural-framing/structural-framing/"
                         "laminated-radiata-beams/c/RC61530",
        price_source_date="2026-06-11",
        source_currency="NZD", source_price=123.0,
        source_unit="NZD per lineal metre (PL8 190x90 non-visual H1.2, "
                    "incl. GST)",
        pricing_notes="Prolam does not publish stud-size (90x45) lineal "
                      "pricing; estimate scaled by cross-section area from "
                      "the PL8 190x90 retail rate (123 x 4050/17100 = "
                      "29.13 NZD/lm).",
    ),
    "glulam": Material(
        key="glulam", display_name="Glulam", category="glulam",
        typical_sizes_mm=("90x45", "140x45", "240x90"),
        default_size_mm="90x45",
        default_usd_per_lm=_usd(28.88),
        price_confidence="low",
        price_source_name="Mitre 10 NZ — laminated radiata beams (generic)",
        price_source_url="https://www.mitre10.co.nz/shop/building-hardware/"
                         "timber/structural-framing/structural-framing/"
                         "laminated-radiata-beams/c/RC61530",
        price_source_date="2026-06-11",
        source_currency="NZD", source_price=154.0,
        source_unit="NZD per lineal metre (240x90 laminated beam, incl. GST)",
        pricing_notes="No public 90x45 glulam lineal price found (GL8 OEL "
                      "90x45 exists but is quote-only); scaled by "
                      "cross-section area from a 240x90 laminated radiata "
                      "beam retail rate (154 x 4050/21600 = 28.88 NZD/lm).",
    ),
    "gl8": Material(
        key="gl8", display_name="GL8", category="glulam",
        typical_sizes_mm=("90x45", "140x45", "190x45", "240x90"),
        default_size_mm="90x45",
        default_usd_per_lm=_usd(28.88),
        price_confidence="low",
        price_source_name="Mitre 10 NZ — laminated radiata beams (generic)",
        price_source_url="https://www.mitre10.co.nz/shop/building-hardware/"
                         "timber/structural-framing/structural-framing/"
                         "laminated-radiata-beams/c/RC61530",
        price_source_date="2026-06-11",
        source_currency="NZD", source_price=154.0,
        source_unit="NZD per lineal metre (240x90 laminated beam, incl. GST)",
        pricing_notes="GL8 grade priced at the generic laminated radiata "
                      "beam rate (retail GL8 pieces are quote-only); 90x45 "
                      "base scaled by cross-section area from the 240x90 "
                      "rate, other sizes scaled linearly by area.",
        size_prices_usd_per_lm={
            "90x45": _usd(28.88), "140x45": _usd(44.92),
            "190x45": _usd(60.97), "240x90": _usd(154.0),
        },
    ),
    "gl10": Material(
        key="gl10", display_name="GL10", category="glulam",
        typical_sizes_mm=("90x45", "140x45", "190x45", "240x90"),
        default_size_mm="90x45",
        default_usd_per_lm=_usd(31.77),
        price_confidence="low",
        price_source_name="Mitre 10 NZ — laminated radiata beams (generic)",
        price_source_url="https://www.mitre10.co.nz/shop/building-hardware/"
                         "timber/structural-framing/structural-framing/"
                         "laminated-radiata-beams/c/RC61530",
        price_source_date="2026-06-11",
        source_currency="NZD", source_price=154.0,
        source_unit="NZD per lineal metre (240x90 laminated beam, incl. GST)",
        pricing_notes="GL10 grade estimated at 1.10 x the generic laminated "
                      "radiata beam rate (no public GL10 lineal pricing); "
                      "sizes scaled linearly by cross-section area.",
        size_prices_usd_per_lm={
            "90x45": _usd(31.77), "140x45": _usd(49.42),
            "190x45": _usd(67.07), "240x90": _usd(169.42),
        },
    ),
    "gl12": Material(
        key="gl12", display_name="GL12", category="glulam",
        typical_sizes_mm=("90x45", "140x45", "190x45", "240x90"),
        default_size_mm="90x45",
        default_usd_per_lm=_usd(36.10),
        price_confidence="low",
        price_source_name="Mitre 10 NZ — laminated radiata beams (generic)",
        price_source_url="https://www.mitre10.co.nz/shop/building-hardware/"
                         "timber/structural-framing/structural-framing/"
                         "laminated-radiata-beams/c/RC61530",
        price_source_date="2026-06-11",
        source_currency="NZD", source_price=154.0,
        source_unit="NZD per lineal metre (240x90 laminated beam, incl. GST)",
        pricing_notes="GL12 grade estimated at 1.25 x the generic laminated "
                      "radiata beam rate (no public GL12 lineal pricing); "
                      "sizes scaled linearly by cross-section area.",
        size_prices_usd_per_lm={
            "90x45": _usd(36.10), "140x45": _usd(56.16),
            "190x45": _usd(76.21), "240x90": _usd(192.53),
        },
    ),
    "hychord": Material(
        key="hychord", display_name="HyCHORD", category="lvl",
        typical_sizes_mm=("90x45", "140x45", "190x45"),
        default_size_mm="90x45",
        default_usd_per_lm=_usd(19.04),
        price_confidence="high",
        price_source_name=_KIWI,
        price_source_url="https://kiwitimber.co.nz/index.php?"
                         "route=product/search&search=hychord",
        price_source_date="2026-06-11",
        source_currency="NZD", source_price=19.04,
        source_unit="NZD per lineal metre (hyCHORD H1.2 90x45, incl. GST)",
        pricing_notes="Exact-size public retail per-metre price "
                      "(Futurebuild/CHH hyCHORD, special order).",
        size_prices_usd_per_lm={
            "90x45": _usd(19.04), "140x45": _usd(29.62),
            "190x45": _usd(40.20),
        },
    ),
    "hyspan": Material(
        key="hyspan", display_name="HySPAN", category="lvl",
        typical_sizes_mm=("150x45", "200x45", "240x45", "300x45"),
        default_size_mm="90x45",
        default_usd_per_lm=_usd(26.31),
        price_confidence="medium",
        price_source_name=_KIWI,
        price_source_url="https://kiwitimber.co.nz/index.php?"
                         "route=product/search&search=hyspan",
        price_source_date="2026-06-11",
        source_currency="NZD", source_price=43.85,
        source_unit="NZD per lineal metre (hySPAN LVL H1.2 150x45, "
                    "incl. GST)",
        pricing_notes="hySPAN range starts at 150x45; 90x45 and 140x45 "
                      "scaled linearly by depth from the 150x45 rate "
                      "(retail per-lm prices are near-linear in depth: "
                      "200x45 listed 58.51 vs scaled 58.47).",
        size_prices_usd_per_lm={
            "90x45": _usd(26.31), "140x45": _usd(40.93),
            "150x45": _usd(43.85), "190x45": _usd(55.54),
            "200x45": _usd(58.51), "240x45": _usd(70.14),
            "300x45": _usd(87.70),
        },
    ),
    "hy90": Material(
        key="hy90", display_name="Hy90", category="lvl",
        typical_sizes_mm=("150x90", "200x90", "240x90", "300x90"),
        default_size_mm="90x45",
        default_usd_per_lm=_usd(16.55),
        price_confidence="medium",
        price_source_name=_KIWI,
        price_source_url="https://kiwitimber.co.nz/index.php?"
                         "route=product/search&search=hy90",
        price_source_date="2026-06-11",
        source_currency="NZD", source_price=55.17,
        source_unit="NZD per lineal metre (hy90 H1.2 150x90, incl. GST)",
        pricing_notes="hy90 range is 90 mm-thick beams from 150x90 up; the "
                      "90x45 stud rate is a cross-section scale-down of the "
                      "150x90 retail rate (55.17 x 4050/13500 = "
                      "16.55 NZD/lm).",
        size_prices_usd_per_lm={
            "90x45": _usd(16.55), "150x90": _usd(55.17),
            "200x90": _usd(75.72), "240x90": _usd(94.73),
            "300x90": _usd(137.36),
        },
    ),
}

_BY_DISPLAY = {m.display_name.lower(): m.key for m in MATERIALS.values()}

_SIZE_PREFIX = re.compile(r"^(\d+)/(.+)$")


def normalise_material_key(s: str | None) -> str | None:
    """Accept internal keys ('hyspan') or display names ('HySPAN')."""
    if not s:
        return None
    k = s.strip().lower()
    if k in MATERIALS:
        return k
    return _BY_DISPLAY.get(k)


def display_name(key: str) -> str:
    m = MATERIALS.get(key)
    return m.display_name if m else "SG8"


def unit_price_usd_per_lm(material_key: str,
                          size: str) -> tuple[float, str, str, str, str]:
    """(usd_per_lm, confidence, source_name, source_url, pricing_notes).

    Handles lintel-style 'N/90x45' multipliers and a trailing ' (SED)'.
    """
    m = MATERIALS.get(material_key, MATERIALS["sg8"])
    base = size.removesuffix(" (SED)").strip()
    mult = 1
    if (pm := _SIZE_PREFIX.match(base)):
        mult = int(pm.group(1))
        base = pm.group(2)
    per_lm = m.size_prices_usd_per_lm.get(base, m.default_usd_per_lm)
    return (round(mult * per_lm, 2), m.price_confidence,
            m.price_source_name, m.price_source_url, m.pricing_notes)


def catalogue_json() -> dict:
    return {
        "materials": [asdict(m) for m in MATERIALS.values()],
        "disclaimers": DISCLAIMERS,
        "fx": {"rate_nzd_to_usd": FX_RATE_NZD_USD,
               "source": FX_SOURCE, "date": FX_DATE},
    }
