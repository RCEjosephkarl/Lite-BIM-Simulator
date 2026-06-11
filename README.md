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

Frontend development with hot reload (proxies `/api` to :8000):

```bash
cd frontend && npm run dev
```

## API

| Endpoint | Description |
|---|---|
| `GET /api/model` | Regenerates the SQLite model and returns all elements as JSON. Query params: `storeys` 1–3 · `roof` gable\|hip · `wind_zone` low\|medium\|high\|very high\|extra high · `wind_speed` m/s (overrides `wind_zone`) · `snow_zone` N0–N5 · `gable_spacing` 300–1200 mm |
| `GET /api/bom.csv` | Bill of materials (timber only) from the SQL `bom` view |

## How it works

```
geometry.py (floor plan)  →  framing.py (NZS 3604 member generator,
        ModelConfig: storeys/roof/wind/snow/gable-stud spacing)
        →  SQLite (schema.sql: elements + bom view)
        →  FastAPI (/api/model, /api/bom.csv)
        →  Three.js viewer (TypeScript)
```

Each member is stored as a row: function, size, grade (SG8), treatment
(H1.2 / H3.2), length, centre position, yaw and pitch — the frontend
instances a unit cube per row.

See **[REPORT.md](REPORT.md)** for the feature report (rules, member
generation logic and verification results).

## Disclaimer

Indicative model for estimating and education. Member sizes/spacings are
simplified readings of NZS 3604:2011 common cases — verify all members
against the standard (or specific engineering design) before construction.
NZS 3604 covers buildings within a 10 m height limit; the 3-storey option,
design wind speeds over 55 m/s and snow loads over 2.0 kPa are flagged
accordingly.
