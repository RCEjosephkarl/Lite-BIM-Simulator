# TimberBIM Lite — Feature Update Report

**Date:** 2026-06-10 · **Version:** 1.1 · **Standard referenced:** NZS 3604:2011

This report documents the four features added on top of the v1.0 viewer
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
