# TimberBIM Lite — Development Report

**Latest:** 2026-06-16 · **Standard referenced:** NZS 3604:2011 ·
**Status:** work in progress

> This report leads with the **most heavily-prompted, most-iterated
> development** — the dashboard, imports, manual framing and UI-layout work
> (v2.0 → v2.1) — because that is where most of the recent effort has gone. The
> earlier feature history (v1.1 roof/exposure rules, v1.2 stud-design overrides
> and cost estimating) follows below for completeness.

---

# 🟢 Development focus — Dashboard, Imports, Manual Framing & UI layout (v2.0–v2.1)

This is the largest and most-iterated slice of the project to date: it turned a
read-only 3D viewer into an interactive workspace where users feed in their own
geometry, review it before it touches the model, and read the results back from
a dedicated dashboard. It also absorbed the most prompt iterations — the UI
layout in particular went through a follow-up fix (v2.1) after the first cut
(v2.0) crammed output into the input sidebar and let nav labels paint over
content.

## What was built (v2.0)

**Interactive sidebar + dashboard.** A hover-expand, keyboard-accessible left
sidebar with persisted pin state, plus a dashboard summary, grouped BOM table,
pricing provenance and session price overrides.

**Structured CSV import.** Mixed-row (`wall` / `opening` / `truss`) CSV
validation, editable review, temporary magenta preview, and append / replace
commit modes — validation never mutates the model, invalid rows stay editable.

**Manual framing.** Manual wall-frame and truss generators with
preview-before-commit, `localStorage` drafts, repeated/custom trusses, pricing
and warnings.

**Provenance & lifecycle.** Element source / source-id / editability /
confidence metadata and import batches; project reset and regeneration that
preserve manual/imported members by default.

**Optional ML boundary — scaffold only.** A Keras 3 adapter, ML status
endpoint, image/manifest analysis boundary, a postprocessing contract, and an
experimental training-data skeleton. **No trained model ships**: with no
weights, `GET /api/ml/status` reports `model_available=false` and analysis
returns no geometry. This is deliberately far from neural-network development —
the boundary exists so that nothing can auto-invent walls.

### Persistence & compatibility

The generated sample remains the default `/api/model` behavior. SQLite now
stores source-tracked additions beside generated members. Parameter
regeneration preserves committed manual/imported members by default, while
project reset restores only the sample geometry. Existing `/api/model` and
`/api/bom.csv` endpoints remain available.

## The most-iterated piece — UI layout fix (v2.1, 2026-06-16)

**Problem.** In the expanded sidebar the navigation buttons were sized
`calc(var(--sidebar) - 15px)` (~445 px) but lived inside the 64 px icon rail,
which had no clipping. On hover/pin the revealed nav **labels** (Building
Specs, BOM, Pricing…) painted across the full width and overlapped the active
content panel — section names bleeding behind the dashboard cards. The
dashboard summary cards were also crammed into the sidebar alongside the input
controls.

**Changes.**

- **Icon rail is now icon-only.** Nav/pin buttons are constrained to the rail
  width (50 px), `.sidebar-rail` clips overflow, and `.nav-label` is hidden.
  Section identity comes from the content-panel title and `title` tooltips
  (VS Code activity-bar pattern), so labels can no longer paint over content.
- **Dashboard output moved to a floating HUD.** The storeys / zones / element /
  length / cost / warning summary plus the Regenerate / Download BOM actions now
  render in a collapsible `#dashboard-hud` overlay anchored top-right of the
  3D viewport, fully separated from the input sidebar. A **–/+** toggle
  collapses it. All input panels stay in the sidebar.
- The `dashboard` sidebar section was removed (rail icon **DB** dropped); the
  sidebar now defaults to **Building Specs**.

| File | Change |
|---|---|
| `frontend/index.html` | rail `overflow:hidden`, icon-only nav-button sizing, `.nav-label { display:none }`, new `.hud` styles, `#dashboard-hud` container |
| `frontend/src/dashboard.ts` | renders the HUD shell (header + collapse toggle + body) instead of a sidebar section |
| `frontend/src/sidebar.ts` | removed the `dashboard` section, default active section `specs` |
| `frontend/src/types.ts` | dropped `"dashboard"` from `SidebarSection` |
| `frontend/src/main.ts` | `Dashboard` now targets `#dashboard-hud` |

## Verification (v2.0–v2.1)

- Backend smoke suite: CSV validity and required fields, opening bounds, manual
  wall preview/commit, truss chord/web generation, source tracking, BOM JSON,
  legacy model/BOM behavior, and **ML-unavailable status**.
- `tsc && vite build` — type-check and bundle clean; built `dist/index.html`
  contains `#dashboard-hud`, the 50 px rail buttons and the hidden nav labels.
- Inputs (storeys, roof, exposure, wall-stud design, source filter, imports,
  manual wall/truss, settings) all remain in the sidebar; only the read-only
  summary + regenerate/download moved to the HUD.

## Engineering disclaimer (v2.0–v2.1)

The dashboard remains an education, early-design and estimating tool, and the
whole project is still a work in progress. AI plan extraction is experimental,
review-only, and presently has no model behind it. Imported/manual geometry
must be checked by a qualified designer or engineer, and NZS 3604 or specific
engineering design governs construction decisions.

---

# Earlier development history

The sections below predate the focus work above and are kept for reference.

---

## v1.1 — Roof, exposure and gable framing (2026-06-10)

This documents the four features added on top of the v1.0 viewer
(3D framing model of the 70′ × 60′ sample plan, colour modes, NZS clause
tagging, SQL-driven timber BOM export).

---

## 1. Auto-rotation toggle

A *View → Auto-rotate model* checkbox spins the model as a slow turntable
(1.5°-equivalents per frame via `OrbitControls.autoRotate`). Manual orbit,
pan and zoom keep working while it is on; interaction takes priority because
the control damping loop already runs every frame.

| Layer | Change |
|---|---|
| `frontend/src/scene.ts` | `Viewer.setAutoRotate(on)` → `controls.autoRotate`, speed 1.5 |
| `frontend/src/ui.ts` | "View" section with the checkbox |

## 2. Hip roof framing

A *Roof style* selector (Gable / Hip) regenerates all three roof planes
(left wing, right wing, garage). Hip framing per rectangle consists of:

| Member | Size | Generation rule | NZS 3604 ref |
|---|---|---|---|
| Ridge board | 190×45 | shortened by one half-span at each end (45° hips); square plans degenerate to a pyramid | cl. 10.2.1.6 |
| Hip rafters (4) | 190×45 | ridge end → each eave corner; pitch = atan(rise / plan-diagonal) | cl. 10.2.1.7 |
| Common rafters | 140×45 | straight mid-section, both sides, at snow-adjusted centres | Table 10.1 |
| Jack rafters (side faces) | 140×45 | parallel to commons, runs shorten linearly toward the corners (45° hip line) | Table 10.1 |
| Jack rafters (end faces) | 140×45 | parallel to the ridge, from end eave up to the hip lines, plus a full-length king common | Table 10.1 |
| Fascia | 180×25 H3.2 | all four eaves (gable roofs: two) | cl. 10.2 |

Implementation: `backend/framing.py` — roof framing was refactored into a
`_Roof` helper that works in (u = along ridge, v = across ridge)
coordinates; north–south ridges swap axes, which is a *reflection*, so
in-plane angles are sign-flipped through a `mirror` factor.

Result for the default 1-storey hip model: 12 hip rafters (3 roofs × 4),
~104–160 jack rafters depending on rafter centres, 3 ridge pieces.

## 3. Wind-zone / snow-zone driven spacing

**Inputs** (*Site exposure* section):

- **Wind zone dropdown** — Low / Medium / High / Very High / Extra High
  (NZS 3604 cl. 5.2, Table 5.4), plus **"By design wind speed…"**, which
  reveals a numeric **wind speed (m/s)** input. A speed input derives the
  zone from the Table 5.4 caps (32 / 37 / 44 / 50 / 55 m/s); above 55 m/s
  the model is flagged **SED** (outside NZS 3604).
- **Snow zone dropdown** — N0 (none) to N4 (2.0 kPa) per Section 15;
  N5 (> 2.0 kPa) is generated at the tightest centres and flagged **SED**.

**Effect on the generated framing** (simplified Table 8.2 / Section 15 rules
in `backend/nzs3604.py`):

| Input | Member | Centres |
|---|---|---|
| Low / Medium wind | wall studs 90×45 SG8 | 600 mm |
| High wind | wall studs | 480 mm |
| Very High / Extra High / SED | wall studs | 400 mm |
| Multi-storey (any wind) | lowest-storey studs | min(zone value, 400 mm) |
| Snow ≤ 1.0 kPa (N0–N2) | rafters 140×45 | 900 mm |
| Snow 1.5–2.0 kPa (N3–N4) | rafters | 600 mm |
| Snow > 2.0 kPa (N5, SED) | rafters | 480 mm |

The applied values are echoed in the panel
(e.g. *“Studs L1 @ 480 crs — wind: high · Rafters @ 600 crs — snow: N3”*),
stored with the model (`model_meta.params` in SQLite) and visible in every
element's note/clause data. The BOM therefore always reflects the chosen
exposure.

**Verified:** wind speed 48 m/s → zone *very high*, studs at 400 crs
(281 wall studs vs 189 at medium); N3 snow → rafters 600 crs (130 rafters
vs 92); 58 m/s and N5 produce explicit SED warnings.

## 4. Customizable gable-end studs

Gable roofs now include **gable-end studs** (90×45, cl. 8.5 gable-end
framing): verticals standing on the end wall's top plate, filling each
gable triangle under the roof line, tallest at the ridge. The
**centres are user-settable** (300–1200 mm input, default 600 mm) and the
input only applies to gable roofs (hidden when Hip is selected).

**Verified:** 600 mm centres → 82 gable studs across the 6 gable ends;
400 mm → 122. Each stud's height follows the 25° roof slope.

---

## API additions

```
GET /api/model?storeys=1..3&roof=gable|hip
              &wind_zone=low|medium|high|very high|extra high
              &wind_speed=<m/s>          (optional, overrides wind_zone)
              &snow_zone=N0..N5
              &gable_spacing=300..1200   (mm)
```

The response `meta` now carries the effective `wind_zone`, `wind_speed`,
`snow_zone`, `roof`, `gable_spacing`, per-storey `stud_spacing_mm`,
`rafter_spacing_mm` and a `warnings[]` list. The same parameters can seed
the UI through the page URL (e.g. `/?roof=hip&wind_speed=48&snow_zone=N3`).

## Files changed

| File | Change |
|---|---|
| `backend/nzs3604.py` | wind zones (Table 5.4) + speed→zone mapping, snow zones (§15), `stud_spacing(…, wind_zone)`, `rafter_spacing(snow)`, new element types: hip rafter, jack rafter, gable-end stud |
| `backend/framing.py` | `ModelConfig` dataclass (normalisation + SED warnings), `_Roof` shared roof geometry, `frame_hip_roof`, gable-end studs in `frame_gable_roof`, spacing parameters threaded through `generate(cfg)` |
| `backend/db.py` | model keyed on the full parameter set (stored as JSON in `model_meta`), richer `meta` payload |
| `backend/server.py` | new validated query parameters |
| `frontend/src/*` | auto-rotate toggle, roof/exposure/gable controls, spacing status line, warning display, URL parameter seeding |
| `README.md` | feature table, API docs, run instructions updated |

## Verification summary

- `python3 backend/framing.py` — 4 config permutations, **0 zero-length
  members**, expected count shifts in every case (counts in §3–§4 above).
- `tsc && vite build` — type-check and bundle clean.
- API smoke tests via `curl` for hip/wind/snow/gable-spacing parameters.
- Headless-browser screenshots of `/?roof=hip` and
  `/?roof=gable&gable_spacing=400` confirm correct hip geometry
  (diagonal hips, shortening jacks, 4-sided fascia) and gable-end stud
  infill; BOM CSV reflects the active configuration.

## Limitations

- Hip/jack rafter sizing reuses the common-rafter table (Table 10.1) with
  hips one size deeper — birdsmouths, under-purlins and ridge struts are
  not modelled.
- Wind/snow rules are simplified single-dimension lookups; the real
  Table 8.2 also varies stud size with loaded dimension and height, and
  Section 15 adjusts lintels and fixings as well.
- Valley framing where the two wings intersect is not generated (roof
  planes simply overlap), consistent with the "lite" scope.

---

# Feature Update — v1.2 (2026-06-11)

Adds wall-stud design overrides (material / spacing / plies at three
scopes), deterministic frame-segment identity, and USD material cost
estimating on top of v1.1.

## 5. Stud material, spacing and plies by scope

Three independent wall-stud design dimensions, each settable at three
scopes with resolution order **segment > level > overall > default**:

| Dimension | Options | Default | Applies to |
|---|---|---|---|
| Stud material | SG8, SG10, Prolam, Glulam, HyCHORD, HySPAN, Hy90 (keys `sg8`…`hy90`) | SG8 | stud-like verticals only: `stud`, `trimmer_stud`, `jack_stud`, `gable_stud` |
| Stud spacing | presets 300/400/450/480/600/900/1200 or custom 300–1200 mm | NZS 3604 Table 8.2 (wind-zone/storey derived) | common-stud centres per wall (`frame_wall`) |
| Wall plies | integers 1–6 | 1 | all `frame_wall()` members: studs, plates, nogs, trimmers, lintels, sills — never floor/ceiling/roof/outdoor/concrete |

Implementation: `ModelConfig` gained nine override fields (three scalars,
three per-level dicts, three per-segment dicts) plus
`effective_stud_material / effective_stud_spacing / effective_wall_plies`
resolvers. `normalised()` is defensive: unknown material keys are dropped,
spacing clamps to 300–1200, plies clamp to 1–6, bad level keys are dropped
— each with a warning surfaced in `meta.warnings`. Spacing overrides also
tag affected wall elements and `meta.warnings` with
*“custom spacing — verify by design/NZS 3604”*; the NZS-derived default is
never silently replaced.

Geometry: multi-ply studs render as one element widened to plies × 45 mm
along the wall axis (option A — no overlapping duplicates to confuse
picking). Horizontal wall members keep their geometry and carry `plies`
as data only, so plates do not intersect studs; this is a documented
visual approximation. Element `size` stays the base section; the BOM view
derives `2/90x45`-style display sizes (without double-prefixing lintels
that are already `2/140x45`).

## 6. Frame segment identity

Every wall is assigned a deterministic id during `generate()`:
`G-EXT-001`, `G-INT-004`, `L2-EXT-003`… (storey 1 = `G`; EXT/INT from the
wall list source; 1-based index per storey+kind, stable because the
geometry wall lists are fixed-order). Wall elements store `segment_id` +
`segment_label`; `meta.frame_segments` lists every segment with storey,
label, length, exterior flag, opening count and its *effective*
material/spacing/plies. Unknown segment ids in override params are ignored
with a warning (stale overrides survive in the URL when storeys change —
harmless and reversible).

## 7. USD material cost estimating

`backend/materials.py` is the pricing catalogue — one entry per material
with key, display name, category (`sawn_timber|glulam|lvl`), typical/default
sizes, USD/lm prices, and full provenance (source name/URL/date, original
currency price + unit, FX rate/source/date, confidence, assumptions).

Methodology:

1. Public NZ retail prices collected 2026-06-11 — Kiwi Timber Supplies
   per-lineal-metre listings (SG8 90x45 H1.2 $6.07/lm; SG10 90x45 from the
   5.4 m piece $38.51; hyCHORD 90x45 $19.04/lm exact; hySPAN from 150x45
   $43.85/lm; hy90 from 150x90 $55.17/lm) and Mitre 10 laminated-beam
   category pricing for Prolam/generic glulam. Retail prices include 15% GST.
2. Normalised to **USD per lineal metre** at NZD→USD 0.5795
   (xe.com / exchange-rates.org mid-market, 2026-06-11). Sizes the
   retailer does not list are scaled linearly by cross-section area and
   flagged in `pricing_notes`; lintel-style `N/depthx45` sizes multiply
   the single-section rate by N.
3. Confidence: `high` = exact product/size public price (SG8, SG10,
   HyCHORD) · `medium` = same brand, size extrapolated (HySPAN, Hy90) ·
   `low` = category estimate (Prolam, Glulam).
4. Costs: every timber element stores `unit_price_usd_per_lm` +
   confidence/source; `costed_lm = length_m × plies`;
   `cost = costed_lm × unit_price`. Note a 2-ply wall’s `2/140x45` lintel
   costs intrinsic 2× *and* plies 2× — the spec’d behaviour, by design.

Surfaces: BOM CSV (material, plies, effective length, unit price, cost,
confidence, source, pricing notes columns), `GET /api/materials`,
`GET /api/cost-summary` (totals by material/storey/segment/element +
grand total), `meta.cost_summary`, the stats line and the
selected-element panel (unit price, est. cost, confidence + source link).

**Cost disclaimer:** estimating data only — supply-only, GST-inclusive
retail snapshots converted to USD; not quotes; exclude delivery, fixings,
labour, waste.

**Engineering disclaimer:** material substitutions, spacing changes and
added plies require verification against NZS 3604:2011 or specific
engineering design; NZS 3604 tables assume SG8. Material selection here is
an estimating choice, not engineering approval.

## API additions (v1.2)

```
GET /api/model?…existing…
              &stud_material_overall=sg8|sg10|prolam|glulam|hychord|hyspan|hy90
              &stud_spacing_overall=300..1200
              &wall_plies_overall=1..6
              &stud_material_levels={"2":"hyspan"}     (JSON object)
              &stud_spacing_levels={"1":400}
              &wall_plies_levels={"1":2}
              &stud_material_segments={"G-EXT-001":"hy90"}
              &stud_spacing_segments={"G-EXT-001":300}
              &wall_plies_segments={"G-EXT-001":3}
GET /api/materials
GET /api/cost-summary
```

Malformed JSON params are ignored with a warning; the same params seed the
UI via the page URL and are written back with `history.replaceState`, so
designs are shareable.

## Files changed (v1.2)

| File | Change |
|---|---|
| `backend/materials.py` | **new** — priced material catalogue + lookup helpers |
| `backend/framing.py` | ModelConfig overrides + resolvers + defensive `normalised()`, segment ids in `generate()` (now returns `GenerateResult`), ply-aware `frame_wall`, material-aware `frame_gable_roof` |
| `backend/schema.sql` | elements: material/plies/segment/spacing/price columns; BOM view groups by material+plies, adds effective length + cost |
| `backend/db.py` | price enrichment on insert, segments/warnings persisted, canonical-JSON param caching, `cost_summary()`, extended BOM CSV |
| `backend/server.py` | nine new query params (JSON dicts parsed defensively), `/api/materials`, `/api/cost-summary` |
| `backend/test_smoke.py` | **new** — 11 pytest cases (precedence, isolation, BOM cost math, endpoints, invalid input) |
| `frontend/src/*` | Wall stud design panel (scope selector, segment dropdown, clear-override), URL write-back, material-keyed colours + legend, cost in stats and element panel |

## Verification summary (v1.2)

- `python -m pytest backend/test_smoke.py` — **11 passed**: defaults
  byte-compatible with v1.1 behaviour, old URLs work, overall/level/segment
  precedence, plies isolation from non-wall members, BOM cost ×plies,
  materials/cost-summary endpoints, clamp/ignore warnings.
- `python backend/framing.py` — 5 permutations, 0 zero-length members;
  default model unchanged at 1,163 elements / 25 segments.
- `tsc && vite build` — clean.

## Limitations (v1.2)

- Multi-ply visuals widen studs only; doubled plates/lintels are
  data+cost, not geometry.
- Engineered-product prices for stud sizes (Prolam/Glulam, hySPAN/hy90
  90x45) are cross-section extrapolations — see `pricing_notes`.
- Prices are point-in-time retail snapshots; refresh `materials.py`
  before relying on totals.

---

*The v2.0 dashboard / imports / manual framing and v2.1 UI-layout work — the
most-prompted development to date — is covered in the **Development focus**
section at the top of this report.*
