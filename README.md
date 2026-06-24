# TimberBIM Lite

> ⚠️ **Work in progress.** This is an evolving experiment, not a finished
> product. The 3D model, the NZS 3604 rules, the pricing data and the UI are
> all *lite* by design. And to set expectations early: the "AI" piece here is
> a scaffold with **no trained model behind it** — we are still a long way from
> any real neural-network development.

![stack](https://img.shields.io/badge/stack-Python%20·%20SQL%20·%20TypeScript%20·%20JavaScript-blue)
![status](https://img.shields.io/badge/status-work%20in%20progress-orange)
![ml](https://img.shields.io/badge/neural%20network-not%20yet-lightgrey)

## The story so far

It starts with a drawing. The default building is digitized from
[`examples/sample_building_plans.pdf`](examples/sample_building_plans.pdf) — a
12-sheet "Proposed home" consent-drawing set (FLOORPLAN at 1:100, Building Area
183.15 m²). It is a single-storey, light timber-framed house on a
~18.68 m × ~11.17 m footprint: an attached **garage** (4.5 m door) in the
south-east, **bedrooms 2/3** above it, a central **lounge/bath/entry** core,
**bedroom 1/ens/wir** to the north, open-plan **kitchen/dining/living** on the
west, an outdoor **covered area** in the north-west corner, and a **28°
trussed roof** (trusses @ 900 c/c) — the kind of building that **NZS 3604:2011
*Timber-framed buildings*** is written for.

The question this project keeps asking is: *how far can we take that one
drawing as data?*

**First, the drawing becomes geometry.** The footprint, walls and openings from
the PDF are digitized into `backend/geometry.py` (a *simplified* reading, not a
measured reproduction). Nothing intelligent yet — just coordinates standing in
for lines on paper.

**Then the geometry becomes a building.** `backend/framing.py` walks that plan
and grows a frame on it: studs, plates, nogs, lintels, joists, rafters,
trusses — roughly 840 to 2,700 members depending on how the building is
configured. Every member is generated against a simplified reading of
NZS 3604: stud spacing from Table 8.2, lintels by span from Table 8.9, rafters
from Table 10.1, treatments from NZS 3640. Each piece *remembers the clause it
came from*. The model isn't just shapes — it's shapes that can cite a reason
for existing.

**Then the building answers questions.** Tell it the site is in a High wind
zone (or hand it a design wind speed and let it derive the zone from
Table 5.4) and the wall studs tighten from 600 → 480 → 400 centres. Tell it the
snow zone is N3 and the rafters pull in from 900 → 600 centres. Ask for a hip
roof instead of a gable and it regenerates the ridge, hip rafters to each eave
corner, and the jack rafters that shorten toward the corners. Ask for floor
level 2 or 3 — which the drawing set doesn't cover — and it *synthesizes* them:
the digitized ground plan stays on the **topmost** level and the new floors are
stacked **underneath** it. Anything outside the standard's scope — a 3rd
storey, >55 m/s wind, >2.0 kPa snow — is flagged **SED** ("specific engineering
design") rather than silently guessed.

**Then the building becomes a spreadsheet.** Every member is a row in SQLite
(`backend/schema.sql`) carrying its function, size, grade, treatment, length,
position, material, plies and price. A SQL `bom` view aggregates the timber
(concrete slabs excluded), rounds to stock lengths, and `GET /api/bom.csv`
hands you a bill of materials. `backend/materials.py` attaches indicative
**NZD-per-lineal-metre** costs taken from public NZ retail listings in their
native currency (GST-inclusive, valuation 2026-06-23 — no FX conversion), each
figure carrying a confidence level and a link back to where it came from.

**Then the building becomes editable.** Beyond the generated sample you can
feed it your own data: a structured CSV mixing wall / opening / truss rows
(mm, metres or feet-inches, all normalized), or manual wall-frame and truss
forms — each one preview-before-commit, so nothing touches the model until
you've reviewed it. Overrides let you study material (SG8 → SG10 → Prolam,
Glulam, HyCHORD, HySPAN, Hy90), spacing and plies at three scopes —
*segment > level > overall > NZS default* — but these are estimating and
design-study options, never engineering approval, and the NZS-derived default
is never silently replaced.

**And finally — barely — the building wants to read drawings by itself.** This
is the frontier, and it is mostly fence. There is an optional adapter
(`backend/ml/`) wired for a Keras 3 plan detector, a status endpoint, and an
image/manifest review workflow. But there is **no model**: without trained
weights `GET /api/ml/status` reports `model_available=false` and analysis
returns *no geometry at all*. It will never invent a wall. The honest summary
is that the plumbing for AI plan reading exists and the intelligence does not.
**We are far from neural-network development** — what's there today is a
boundary and a promise, not a brain.

## Where it is on the map

| Stage | Status |
|---|---|
| Floor plan → geometry | working (digitized from `examples/sample_building_plans.pdf`) |
| Geometry → NZS 3604 framing | working, *simplified* common-case rules |
| Wind / snow / roof-style driven generation | working |
| SQL element store + timber BOM | working |
| NZD cost estimating with provenance | working, *indicative* retail snapshots |
| CSV import + manual wall/truss entry | working, preview-before-commit |
| Dashboard + hover/pin sidebar UI | working (most recently reworked — see REPORT) |
| Optional AI plan reading | **scaffold only — no trained model** |
| Neural-network development | **not started** |

## What's under the hood

| # | Capability | How |
|---|---|---|
| 1 | 3D rendered view | Three.js `InstancedMesh` per element function (~840–2,700 members) |
| 2 | Rotate / pan / zoom + **auto-rotate** | `OrbitControls`; *View → Auto-rotate model* toggles a slow turntable |
| 3 | Colour / material / function modes | **Function**, **Material** (SG8 H1.2 vs H3.2 vs concrete), **Realistic** timber tones; per-category layer toggles; click any member for its properties |
| 4 | NZS 3604:2011 rules engine | `backend/nzs3604.py`: stud spacing (Table 8.2), plates/nogs (cl. 8.5.2), lintels (Table 8.9), floor/ceiling joists (Tables 7.1 / 10.3), rafters (Table 10.1), treatments (NZS 3640) — every element stores its clause |
| 5 | CSV bill of materials | Timber only, aggregated by the SQL `bom` view, stock lengths rounded to 0.3 m → `GET /api/bom.csv` |
| 6 | Sample shape | Footprint, walls and openings digitized from `examples/sample_building_plans.pdf` (`backend/geometry.py`) |
| 7 | Roof style: gable or hip | Hip framing builds a shortened ridge, hip rafters to each eave corner (cl. 10.2.1.7), jack and common rafters |
| 8 | Wind & snow driven spacing | Wind zone or design wind speed → stud centres 600/480/400; snow zone N0–N5 → rafter centres 900/600; out-of-scope inputs flagged **SED** |
| 9 | Customizable gable-end studs | 300–1200 mm centres, filling each gable triangle (gable roofs only) |
| 10 | Stud material by scope | SG8 · SG10 · Prolam · Glulam · HyCHORD · HySPAN · Hy90, set overall / per level / per segment; stud-like verticals only |
| 11 | Stud spacing by scope | Presets 300–1200 mm or custom; NZS default kept, overrides flagged *"verify by design/NZS 3604"* |
| 12 | Wall-frame plies by scope | 1–6 plies for `frame_wall()` members; visuals widen to plies × 45 mm; BOM length and cost scale with plies |
| 13 | Frame segment identity | Deterministic IDs (`G-EXT-001`…) on every wall element; `meta.frame_segments` lists each segment's effective material/spacing/plies |
| 14 | NZD cost estimating | Sourced catalogue (`backend/materials.py`) with provenance, valuation date (2026-06-23), confidence levels |
| 15 | Hover/pin input sidebar + floating dashboard | Icon-only rail (tooltips on hover, pinnable) for input panels; the read-only summary lives in a separate collapsible HUD over the 3D viewport so output never overlaps input |
| 16 | Structured CSV plan import | Mixed wall/opening/truss rows, unit normalization, editable validation review, temporary preview, then append/replace commit |
| 17 | Manual framing inputs | Preview-before-commit wall and truss forms, openings, repeated/custom trusses, local drafts, source tracking |
| 18 | Optional AI adapter | Keras 3 boundary, status endpoint, image/manifest review workflow — and **no-model behavior that never invents geometry** |

**Override precedence:** `segment > level > overall > NZS 3604 default`.
Overrides are estimating/design-study options — they never silently replace
the NZS-derived defaults, and they are not engineering approval.

## Languages

- **Python** — parametric framing generator + FastAPI server (`backend/`)
- **SQL** — SQLite schema, element store and BOM aggregation (`backend/schema.sql`)
- **TypeScript** — Three.js viewer, UI, API client (`frontend/src/`)
- **JavaScript** — built bundle + Vite tooling

## Run it

```bash
# 1. backend deps
pip install -r backend/requirements.txt

# 2. frontend build (needs Node 18+)
cd frontend && npm install && npm run build && cd ..

# 3. serve (API + built frontend on one port)
cd backend && uvicorn server:app --port 8000
```

Open **http://localhost:8000**. Generation parameters can be seeded via URL,
e.g. `http://localhost:8000/?roof=hip&storeys=2&wind_speed=48&snow_zone=N3`.
Wall-stud design overrides are reflected in the URL too, so designs are
shareable, e.g.
`/?stud_material_overall=sg10&stud_spacing_overall=400&wall_plies_overall=2&stud_material_segments={"G-EXT-001":"hy90"}`.

Backend tests:

```bash
cd backend && python -m pytest test_smoke.py -q
```

Frontend development with hot reload (proxies `/api` to :8000):

```bash
cd frontend && npm run dev
```

The input sidebar is collapsed to an icon rail by default. Hover the rail to
open the active input panel, or use **Pin sidebar** to resize the 3D workspace
and keep it open. Building Specs includes an element source filter for
generated, imported, manual, and temporary preview members. The model summary
shows in a **floating dashboard HUD** at the top-right of the 3D view; use its
**–/+** button to collapse it.

## Feeding it your own data

### CSV plan import

Use **Imports / Drawing Plans → Structured CSV**. A combined file can mix
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

### Manual inputs

**Manual Wall Frame Input** supports coordinates, dimensions, material, stud
spacing, plies, plates, nogs, treatment, and door/window openings. **Manual
Truss Input** supports common, girder, mono, scissor, attic and custom layouts,
repeated quantities, materials, overhang and heel height. Custom examples are
in [`examples/custom_truss_nodes.csv`](examples/custom_truss_nodes.csv) and
[`examples/custom_truss_members.csv`](examples/custom_truss_members.csv).

Both workflows require a successful preview before commit. Drafts and sidebar
pin state are stored in browser `localStorage`.

### Optional AI plan reading — the part that isn't built yet

CSV is structured geometry, not an image. The *experimental* vision workflow is
for raster plan pages (PNG, JPG/JPEG, WEBP) or a CSV manifest referencing those
images. See [`examples/plan_manifest.csv`](examples/plan_manifest.csv).

```bash
pip install -r backend/requirements-ml.txt
export KERAS_BACKEND=tensorflow
export TIMBERBIM_PLAN_MODEL=/path/to/reviewed-detector.keras
```

Without trained weights, `GET /api/ml/status` reports `model_available=false`
and analysis returns no geometry. Training guidance and the experimental
skeleton are in [`backend/ml/README.md`](backend/ml/README.md). **There is no
trained model in this repository, and producing a real one is future work** —
AI proposals, when there ever are any, always require review and explicit
acceptance before commit.

## API

| Endpoint | Description |
|---|---|
| `GET /api/model` | Regenerates the SQLite model and returns all elements as JSON. Query params: `storeys` 1–3 · `roof` gable\|hip · `wind_zone` low…extra high · `wind_speed` m/s (overrides `wind_zone`) · `snow_zone` N0–N5 · `gable_spacing` 300–1200 mm. **Wall stud design:** `stud_material_overall` · `stud_spacing_overall` · `wall_plies_overall` plus per-level / per-segment JSON-object params. Invalid values clamp/ignore with `meta.warnings`; response includes `meta.frame_segments` and `meta.cost_summary` |
| `GET /api/bom.csv` | Bill of materials (timber only) from the SQL `bom` view, including material, plies, effective length, NZD unit price + cost, confidence and source, NZS clause ref |
| `GET /api/materials` | Stud material catalogue: sizes, NZD/lm prices, source/date, confidence, assumptions |
| `GET /api/cost-summary` | Estimated NZD totals: grand total and breakdowns by material, storey, segment and element |
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
(H1.2 / H3.2), length, centre position, yaw and pitch — plus material, plies,
segment id/label, effective stud spacing and estimating price columns. The
frontend instances a unit cube per row.

## Pricing methodology

`backend/materials.py` holds one entry per material with full provenance:

1. **Source** — public NZ retail listings (Kiwi Timber Supplies per-metre
   prices; Mitre 10 category prices for Prolam/glulam), recorded with name, URL
   and date. Retail prices include 15% NZ GST.
2. **Currency** — figures are reported in their **native New Zealand dollars
   (NZD per lineal metre)**; no FX conversion is applied (the "rate to NZD" is
   1.0), valuation date **2026-06-23**. Missing sizes are scaled linearly by
   cross-section area (noted in `pricing_notes`); `2/140x45`-style sizes price
   at 2× the single-section rate.
3. **Confidence** — `high` = exact product price · `medium` = brand, size
   extrapolated · `low` = category estimate.
4. **Cost** — `costed_lm = total_length_m × plies`;
   `cost = costed_lm × unit_price_nzd_per_lm`.

**Cost disclaimer:** all prices are *indicative supply-only estimating data* in
NZD, not quotes — they exclude delivery, fixings, labour and waste, and go
stale; check `/api/materials` for each figure's source and date.

See **[REPORT.md](REPORT.md)** for the development report — including the newest
work (v2.2 — the PDF default plan, multi-storey synthesis and NZD costing) and
the earlier dashboard, imports/manual framing and UI-layout iterations, rules,
member-generation logic and verification results.

## Disclaimer

This app is for education, early design, and estimating, and it is **still a
work in progress**. Member sizes/spacings are simplified readings of NZS
3604:2011 common cases — verify all members against the standard (or specific
engineering design) before construction. NZS 3604 covers buildings within a
10 m height limit; the 3-storey option, design wind speeds over 55 m/s and snow
loads over 2.0 kPa are flagged accordingly.

**Engineering disclaimer:** the stud material, spacing and ply overrides are
design-study/estimating options only. NZS 3604's tables assume SG8 sawn timber
— substituting other products, changing centres or adding plies requires
verification against NZS 3604:2011 or specific engineering design. Selecting a
product here is **not** engineering approval.

**AI disclaimer:** there is no trained plan-reading model in this project. The
AI adapter is a scaffold; any future extraction will be approximate and must be
reviewed. Imported and manual geometry must be checked by a qualified designer
or engineer. NZS 3604 or specific engineering design governs real construction
decisions.
