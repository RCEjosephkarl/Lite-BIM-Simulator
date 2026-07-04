# TimberBIM Lite

A lite BIM (Building Information Modeling) app for **light timber-framed
residential buildings up to 3 storeys**, referenced to **NZS 3604:2011
*Timber-framed buildings***. The sample model is generated from a 70′ × 60′
single-storey floor plan (garage, left wing, centre core, right wing, patio
and covered porch).

![stack](https://img.shields.io/badge/stack-Python%20·%20SQL%20·%20TypeScript%20·%20JavaScript-blue)

## Features

| # | Feature | How |
|---|---|---|
| 1 | 3D rendered view | Three.js `InstancedMesh` per element function (~1,100–3,600 members) |
| 2 | Rotate / pan / zoom + **auto-rotate** | `OrbitControls` — left-drag orbit, right-drag pan, wheel zoom; *View → Auto-rotate model* toggles a slow turntable |
| 3 | Colour / material / function variation | 3 colour modes: **Function** (stud/plate/nog/lintel/joist/rafter…), **Material** (SG8 H1.2 vs H3.2 vs concrete), **Realistic** timber tones; per-category layer toggles; click any member for its properties |
| 4 | NZS 3604:2011 | Python rules engine (`backend/nzs3604.py`): stud spacing (Table 8.2), plates/nogs (cl. 8.5.2), lintels by span (Table 8.9), floor joists (Table 7.1), ceiling joists (Table 10.3), rafters (Table 10.1), treatments (NZS 3640). Every element stores its clause reference |
| 5 | CSV bill of materials | **Timber only** (concrete slabs excluded), aggregated by a SQL view (`bom`) with stock lengths rounded to 0.3 m increments → `GET /api/bom.csv` |
| 6 | Sample shape | Footprint, walls and openings digitized from the reference floor plan (`backend/geometry.py`) |
| 7 | **Roof style: gable or hip** | Hip framing generates shortened ridge, 190×45 hip rafters to each eave corner (cl. 10.2.1.7), jack rafters on the side and end faces, commons in the straight section |
| 8 | **Wind & snow zone driven spacing** | Wind zone dropdown (Low…Extra High, Table 5.4) *or* a design wind speed (m/s) that auto-derives the zone; snow zone dropdown N0–N5 (Section 15). Stud centres tighten 600 → 480 → 400 crs with wind; rafter centres 900 → 600 crs with snow; out-of-scope inputs are flagged **SED** |
| 9 | **Customizable gable-end studs** | Gable-end stud centres input (300–1200 mm); studs fill each gable triangle under the end rafters (gable roofs only) |
| 10 | **Stud material by scope** | *Wall stud design* panel: SG8 (default) · SG10 · Prolam · Glulam · HyCHORD · HySPAN · Hy90, settable **overall**, **per level** or **per frame segment**. Applies to stud-like verticals only (studs, trimmers, jacks, gable studs); plates/nogs/lintels and floor/roof members stay SG8 |
| 11 | **Stud spacing by scope** | Same three scopes; presets 300/400/450/480/600/900/1200 mm or custom 300–1200 mm. NZS-derived spacing remains the default; any override is flagged *“custom spacing — verify by design/NZS 3604”* and the effective spacing is recorded on each wall element |
| 12 | **Wall-frame plies by scope** | 1–6 plies for `frame_wall()` members only (studs/plates/nogs/trimmers/lintels/sills). Stud visuals widen to plies × 45 mm; BOM lineal metres and costs multiply by plies; sizes display as `2/90x45` |
| 13 | **Frame segment identity** | Deterministic IDs (`G-EXT-001`, `L2-INT-003`…) on every wall element; `meta.frame_segments` lists each segment with length, openings and its effective material/spacing/plies |
| 14 | **USD cost estimating** | Sourced material catalogue (`backend/materials.py`) with NZ retail prices converted to USD/lineal-metre (provenance, FX rate + date, confidence levels); costs in the BOM CSV, `/api/cost-summary`, the stats line and the selected-element panel |
| 15 | **Hover / pin BIM dashboard** | Left icon rail expands on hover and can be pinned. Sections cover Dashboard, Building Specs, BOM, Pricing, Imports, Manual Walls, Manual Trusses, and Settings / Warnings |
| 16 | **Structured CSV plan import** | Mixed wall/opening/truss rows, mm/metres/feet-inches normalization, editable validation review, temporary preview, then append/replace commit |
| 17 | **Manual framing inputs** | Preview-before-commit wall and truss forms, openings, repeated/custom trusses, local drafts, cost/member summaries, and source tracking |
| 18 | **Optional AI adapter** | Keras 3 / KerasHub-KerasCV boundary, status endpoint, image/manifest review workflow, and no-model behavior that never invents geometry |

**Override precedence:** `segment > level > overall > NZS 3604 default`.
Overrides are estimating/design-study options — they never silently replace
the NZS-derived defaults, and they are not engineering approval.

## Languages

- **Python** — parametric framing generator + FastAPI server (`backend/`)
- **SQL** — SQLite schema, element store and BOM aggregation (`backend/schema.sql`)
- **TypeScript** — Three.js viewer, UI, API client (`frontend/src/`)
- **JavaScript** — built bundle + Vite tooling

## Run

```bash
# 1. backend deps
pip install -r backend/requirements.txt

# 2. frontend build (needs Node 18+)
cd frontend && npm install && npm run build && cd ..

# 3. serve (API + built frontend on one port)
cd backend && uvicorn server:app --port 8000
```

Open **http://localhost:8000**. Generation parameters can also be seeded via
URL, e.g. `http://localhost:8000/?roof=hip&storeys=2&wind_speed=48&snow_zone=N3`.
Wall-stud design overrides are reflected in the URL too, so designs are
shareable, e.g.
`/?stud_material_overall=sg10&stud_spacing_overall=400&wall_plies_overall=2&stud_material_segments={"G-EXT-001":"hy90"}`.

Backend tests:

```bash
cd backend && python -m pytest test_smoke.py -q
```

The dashboard is collapsed by default. Hover the left rail to open it, or use
**Pin sidebar** to resize the 3D workspace and keep it open. Building Specs
also includes an element source filter for generated, imported, manual, and
temporary preview members.

## CSV plan import

Use **Imports / Drawing Plans -> Structured CSV**. A combined file can mix
`wall`, `opening`, and `truss` rows. See
[`examples/walls_openings_trusses.csv`](examples/walls_openings_trusses.csv).

```text
wall: type,level,segment_id,label,start_x_mm,start_z_mm,end_x_mm,end_z_mm,height_mm
opening: type,level,wall_segment_id,opening_id,opening_type,
         start_offset_mm OR center_offset_mm,width_mm,height_mm
truss: type,level,truss_id,label,span_mm,pitch_deg,spacing_mm,quantity,
       start_x_mm,start_z_mm,direction_deg
```

Validation never modifies the model. Invalid rows stay visible and editable.
Preview members are temporary and magenta. Commit can append to the sample,
replace its geometry, or start a model from the CSV.

## Manual inputs

**Manual Wall Frame Input** supports coordinates, dimensions, material, stud
spacing, plies, plates, nogs, treatment, and door/window openings. **Manual
Truss Input** supports common, girder, mono, scissor, attic and custom layouts,
repeated quantities, materials, overhang and heel height. Custom examples are
in [`examples/custom_truss_nodes.csv`](examples/custom_truss_nodes.csv) and
[`examples/custom_truss_members.csv`](examples/custom_truss_members.csv).

Both workflows require a successful preview before commit. Drafts and sidebar
pin state are stored in browser `localStorage`.

## Optional AI plan reading

CSV is structured geometry, not an image. The experimental vision workflow is
for raster plan pages (PNG, JPG/JPEG, WEBP) or a CSV manifest referencing those
images. See [`examples/plan_manifest.csv`](examples/plan_manifest.csv).

```bash
pip install -r backend/requirements-ml.txt
export KERAS_BACKEND=tensorflow
export TIMBERBIM_PLAN_MODEL=/path/to/reviewed-detector.keras
```

Without trained weights, `GET /api/ml/status` reports
`model_available=false`, and analysis returns no geometry. Training guidance
and the experimental script are in
[`backend/ml/README.md`](backend/ml/README.md). AI proposals always require
review and explicit acceptance before commit.

Frontend development with hot reload (proxies `/api` to :8000):

```bash
cd frontend && npm run dev
```

## API

| Endpoint | Description |
|---|---|
| `GET /api/model` | Regenerates the SQLite model and returns all elements as JSON. Query params: `storeys` 1–3 · `roof` gable\|hip · `wind_zone` low\|medium\|high\|very high\|extra high · `wind_speed` m/s (overrides `wind_zone`) · `snow_zone` N0–N5 · `gable_spacing` 300–1200 mm. **Wall stud design:** `stud_material_overall` (sg8\|sg10\|prolam\|glulam\|hychord\|hyspan\|hy90) · `stud_spacing_overall` (300–1200 mm) · `wall_plies_overall` (1–6) · per-level / per-segment JSON-object params `stud_material_levels={"2":"hyspan"}`, `stud_spacing_levels={"1":400}`, `wall_plies_levels={"1":2}`, `stud_material_segments={"G-EXT-001":"hy90"}`, `stud_spacing_segments`, `wall_plies_segments`. Invalid values are clamped/ignored with warnings in `meta.warnings`; the response includes `meta.frame_segments` and `meta.cost_summary` |
| `GET /api/bom.csv` | Bill of materials (timber only) from the SQL `bom` view. Columns: category, element, size, grade, treatment, **material, plies**, stock_length_m, qty, total_length_m, **total_effective_length_m** (× plies), **unit_price_usd_per_lm, total_cost_usd, price_confidence, price_source_name, price_source_url**, nzs_3604_2011_ref, notes, **pricing_notes** |
| `GET /api/materials` | Stud material catalogue: sizes, USD/lm estimating prices with source name/URL/date, original currency price/unit, FX rate + date, confidence (high/medium/low) and assumptions |
| `GET /api/cost-summary` | Estimated material cost totals (USD) for the current model: grand total and breakdowns by material, storey, frame segment and element |
| `GET /api/dashboard` | Storeys, zones, element/length/cost/warning summary |
| `GET /api/bom.json` | Grouped in-app BOM rows |
| `GET /api/pricing` | Material price rows and source metadata |
| `GET /api/warnings` | Consolidated model/import/manual/pricing warnings |
| `POST /api/import/csv-plan/validate` | Multipart CSV validation without model mutation |
| `POST /api/import/csv-plan/preview`, `/commit` | Preview or commit reviewed CSV geometry |
| `POST /api/manual/wall-frame/preview`, `/commit` | Preview or commit a manual wall frame |
| `POST /api/manual/truss/preview`, `/commit` | Preview or commit a manual truss layout |
| `GET /api/ml/status` | Optional Keras adapter and model-weight status |
| `POST /api/import/vision-plan/analyze`, `/commit` | Review-first experimental vision workflow |
| `GET /api/import/batches` | Import/manual batch history |
| `POST /api/project/reset`, `/regenerate` | Clear additions or regenerate while preserving selected sources |

## How it works

```
geometry.py (floor plan)  →  framing.py (NZS 3604 member generator,
        ModelConfig: storeys/roof/wind/snow/gable-stud spacing)
        →  SQLite (schema.sql: elements + bom view)
        →  FastAPI (/api/model, /api/bom.csv)
        →  Three.js viewer (TypeScript)
```

Each member is stored as a row: function, size, grade, treatment
(H1.2 / H3.2), length, centre position, yaw and pitch — plus material,
plies, segment id/label, effective stud spacing and estimating price
columns. The frontend instances a unit cube per row.

## Pricing methodology

`backend/materials.py` holds one entry per material with full provenance:

1. **Source** — public NZ retail listings (Kiwi Timber Supplies per-metre
   prices; Mitre 10 category prices for Prolam/glulam), recorded with
   source name, URL and date. Retail prices include 15% NZ GST.
2. **Normalisation** — everything is converted to **USD per lineal metre**
   (per-piece prices ÷ length; missing sizes scaled linearly by
   cross-section area, noted in `pricing_notes`). Lintel-style `2/140x45`
   sizes price at 2 × the single-section rate.
3. **FX** — NZD→USD mid-market rate with source and date recorded
   (0.5795, xe.com / exchange-rates.org, 2026-06-11).
4. **Confidence** — `high` = exact product/size public retail price ·
   `medium` = same brand, size extrapolated · `low` = category estimate.
5. **Cost** — `costed_lm = total_length_m × plies`;
   `cost = costed_lm × unit_price_usd_per_lm`.

**Cost disclaimer:** all prices are *indicative supply-only estimating
data*, not quotes — they exclude delivery, fixings, labour and waste, and
go stale; check `/api/materials` for each figure's source and date.

See **[REPORT.md](REPORT.md)** for the feature report (rules, member
generation logic and verification results).

## Disclaimer

This app is for education, early design, and estimating. Member sizes/spacings are
simplified readings of NZS 3604:2011 common cases — verify all members
against the standard (or specific engineering design) before construction.
NZS 3604 covers buildings within a 10 m height limit; the 3-storey option,
design wind speeds over 55 m/s and snow loads over 2.0 kPa are flagged
accordingly.

**Engineering disclaimer:** the stud material, spacing and ply overrides
are design-study/estimating options only. NZS 3604's tables assume SG8
sawn timber — substituting SG10, glulam or LVL products, changing stud
centres or adding plies requires verification against NZS 3604:2011 or
specific engineering design. Selecting a product here is **not**
engineering approval.

AI plan extraction is approximate and must be reviewed. Imported and manual
geometry must be checked by a qualified designer or engineer. NZS 3604 or
specific engineering design governs real construction decisions.
