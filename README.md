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
| 12 | **Wall-frame plies by scope** | 1–6 plies for `frame_wall()` members only (studs/plates/nogs/trimmers/lintels/sills). Parallel plies increase member depth across the wall, retaining opening clearance; BOM lineal metres and costs multiply by plies; sizes display as `2/90x45` |
| 13 | **Frame segment identity** | Deterministic IDs (`G-EXT-001`, `L2-INT-003`…) on every wall element; `meta.frame_segments` lists each segment with length, openings and its effective material/spacing/plies |
| 14 | **USD cost estimating** | Sourced material catalogue (`backend/materials.py`) with NZ retail prices converted to USD/lineal-metre (provenance, FX rate + date, confidence levels); costs in the BOM CSV, `/api/cost-summary`, the stats line and the selected-element panel |
| 15 | **Hover / pin sidebar** | Left icon rail expands on hover and can be pinned. Sections cover Building Specs, BOM, Pricing, Imports, Manual Walls, Manual Trusses, and Settings / Warnings |
| 16 | **Structured CSV plan import** | Mixed wall/opening/truss rows, mm/metres/feet-inches normalization, editable validation review, temporary preview, then append/replace commit |
| 17 | **Manual framing inputs** | Preview-before-commit wall and truss forms, openings, repeated/custom trusses, local drafts, cost/member summaries, and source tracking |
| 18 | **Whole-frame selection** | One click on any member selects its entire wall-frame segment or truss (group tinted, clicked member white) and shows aggregate metadata: stud spacing, timber sizes, openings, plies, treatment, member count and estimated cost |
| 19 | **Selectable treatments** | NZS 3640 hazard classes H1.2 / H3.1 / H3.2 / H4 / H5 as a building-level wall override (`wall_treatment`) and per manual wall/truss input |
| 20 | **6 m × 3 m wall envelope** | Single manual frames retain 6 m × 3 m (orientation interchangeable); logical runs can be split into panels with paired end studs and unchecked connections |
| 21 | **Glulam grade catalogue** | GL8 / GL10 / GL12 estimating entries alongside SG8, SG10, Prolam, generic Glulam, HyCHORD, HySPAN and Hy90 |

**Override precedence:** `segment > level > overall > NZS 3604 default`.
Overrides are estimating/design-study options — they never silently replace
the NZS-derived defaults, and they are not engineering approval.

## Languages

- **Python** — parametric framing generator + FastAPI server (`backend/`)
- **SQL** — SQLite tables (`backend/schema.sql`) and shared BOM views (`backend/bom_queries.py`, installed by migrations)
- **TypeScript** — Three.js viewer, UI, API client (`frontend/src/`)
- **JavaScript** — built bundle + Vite tooling

## Run

```bash
# 1. isolated backend dependencies (verified with Python 3.12)
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r backend/requirements.lock.txt

# 2. frontend build (needs Node 18+)
cd frontend && npm ci && npm run build && cd ..

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
cd backend && python -m pytest -q
```

The sidebar is collapsed by default. Hover the left rail to open it, or use
**Pin sidebar** to resize the 3D workspace and keep it open. Building Specs
also includes an element source filter for generated, imported, manual, and
temporary preview members.

Release **2.17.0** validates derived geometry before generation, bounds CSV
reading before row allocation, and preserves field locations for non-finite
JSON errors. Floor polygon/rotation calculations use a local origin, preserving
ordinary geometry when a home is translated. Split/porch preflight and coordinate
progress guards prevent oversized allocations and stalled framing loops. Existing
feature options, ranges and resource limits are retained. Release 2.16.0 removes repeated full-model level scans during review and adds
a seven-page desktop/mobile accessibility assessment. Pricing/CSV tables have
accessible names and explicit headers; focused navigation labels stay outside
the editable panel. It renders the viewer when its scene or camera changes and pauses
while settled. Auto-rotation and camera damping still animate; model/color/layer/
section/selection/dimension changes, resize and visibility/context restoration
request a frame. It includes correlated failure diagnostics, repeatable profiling,
fresh-source reproduction checks and the level/source/assembly hierarchy,
exact assembly BOM navigation and keyboard camera controls. It includes guided wall/truss forms, inline errors, raw opening draft
recovery and explicit review progress. It includes home-local view/camera recovery, orthographic views,
visible dimensions/sections, a mobile bottom sheet and corrected automatic truss
bearing placement. It includes isolated homes, non-mutating reads, revision checks,
restorable revisions, saved source definitions, signed previews, idempotent
commits, project pricing, connected truss graphs, shared panelized wall framing, physical cutting identities, stock/board estimating, and model inspection tools. It includes the transactional persistence, CSV
validation, mobile layout, and browser checks introduced in 2.2.0. The remaining implementation work and
expert resume points are tracked in [improvement_plan.md](improvement_plan.md).
The wall/panel and truss template, bearing and physical-cut handover is in
[backend/FRAMING.md](backend/FRAMING.md).

## Database safety and recovery

The default database is `backend/model.db`. Set `TIMBERBIM_DB_PATH` before
launching the server to use a separate database, including for automated tests:

```bash
TIMBERBIM_DB_PATH=/tmp/timberbim-study.db uvicorn server:app --port 8000
```

Run that command from `backend/` with the Python environment activated.
Regeneration now replaces generated members in one transaction and preserves
committed manual/imported members and their IDs. Generation or insertion
failure rolls back; unreadable data or corrupt project parameters are reported
instead of silently resetting the model. Existing unversioned databases migrate
in place to schema version 5, with a SQLite snapshot named
`model.db.backup-v<previous-version>-...` beside the database before migration.

`GET /api/health` inspects schema readiness without creating, migrating, or
regenerating a database. A fresh installation reports `uninitialized`; an
existing schema requiring migration or an unreadable/incompatible database
returns 503. `POST /api/project/initialize` explicitly initializes or migrates
the default project; the browser issues that command when needed. Read endpoints
never initialize, migrate, or regenerate a database.

Create a consistent snapshot, including committed WAL data:

```bash
cd backend
python manage_db.py backup --output /tmp/timberbim-snapshot.db
```

Stop the server and every other database user before restoring:

```bash
cd backend
python manage_db.py restore /tmp/timberbim-snapshot.db --confirm-replace
```

Restore verifies the snapshot, saves a `backup-before-restore-...` copy of the
previous database, and installs the snapshot atomically. It refuses to overwrite
an existing backup or restore while SQLite sidecar files are present. Resolve
open connections/checkpoint recovery before retrying; retain the original files.
The same `TIMBERBIM_DB_PATH` environment setting applies to these commands.

## Model inspection and trusses

The viewport status bar shows the active home, revision, geometry mode, warnings,
and temporary preview count. Use **Cancel preview** to return to saved geometry.
**Model browser** organizes levels, source batches, walls and truss layouts/instances.
Expand **Panels and physical members** to find fabrication panels and connected
cut identities; members load in batches, with **Show more** instead of truncation.
Search labels, source IDs, openings, panels, nodes or member roles. Select an assembly to
open its inspector; **Isolate selection** and **Show all** control the visible
assembly set. **Fit model**, **Plan**, **Front**, and **Side** frame the current
geometry, including homes translated away from the sample's origin. Layer choices
survive model rebuilds; selections are retained when the same visible member exists.
**Fit selection** frames the selected assembly. Plan/front/side are orthographic;
plan north points upward. The inspector's wall extent/direction/base/height values
describe the selected geometry. Manual wall previews also show the validated span,
opening offsets, widths, clear heights, sills and heads in the status area.

Focus the **3D home model** canvas to use arrow keys for pan, Shift + arrows
for orbit, + / − for zoom, and Home for Fit model. Tab leaves the canvas. Mobile forms and the selection inspector use bottom
sheets with canvas space reserved above them. Picking a member on mobile closes
the form sheet while retaining its active page and draft; reopen that page to resume.
The same actions have buttons under **Filters, dimensions and section → Camera
controls**. Keyboard camera changes use the existing home-local view recovery;
text inputs keep their normal arrow-key behavior. Selection has a checkmark and
pressed state, and temporary assembly buttons say **PREVIEW**.

Open **Filters, dimensions and section** for level isolation, Roof only, Show all
layers, visible extents and a geometric clipping plane. Section axes are east (X),
north (plan Z) and elevation; enter a finite position in millimetres and choose
which coordinates to keep. Fit and selection use the retained geometry. The three
dimension labels describe the visible model or selected assembly, including
section cuts; they do not replace fabrication cut lengths in the inspector/BOM.
Section faces are uncapped and are viewing aids, rather than fabrication drawings.

View preferences are scoped to each saved home: colour, layers, source, level,
stable member selection/isolation, camera/projection/zoom, motion, dimensions and
section. Reloading or returning to a home restores its view. Changed or removed
members are reconciled using physical/node identities; legacy row-only selections
clear across revisions. Previews temporarily clear source/level/isolation/section
filters, and Cancel restores the saved camera and filters. Deliberate layer,
colour, dimension and motion changes survive cancellation. View/level/source and
section hints appear in the URL; a URL still requires the matching saved home.

Malformed/future/cross-home view data remains recoverable using **Download saved
view** and **Discard saved view**. Browser storage failure leaves live controls
usable with feedback. View storage is separate from saved geometry and archives.
On screens up to 600 px, panels open as a bottom sheet with **Close panel** and
Escape recovery, leaving the upper canvas available. Closing an expanded table
first preserves its return focus; model-browser keyboard selection focuses the
inspector's Fit selection action.

Manual/CSV trusses now use a connected node/member graph. Chords are split at web
attachments and bearings; heel and overhang geometry are explicit. King posts are
vertical. Scissor bottom chords differ from top chords; attic trusses preserve a
conceptual room void. Girder assemblies use three plies while retaining chord/web
roles. Every repeated physical truss has separate `truss_id` and `instance_id`, with
its common `layout_id`, node endpoints and `engineering_status` in member metadata.
Manual/CSV `start_x_mm`/`start_z_mm` locate the template center between its bearings;
custom nodes are relative to that origin. Automatic roof zones translate this
origin to the midpoint of their explicitly checked bearing positions.

Custom trusses require chords and web/post members, distinct nodes, a connected
closed framework, and explicit nodes at crossings. Their textarea CSV accepts
optional headers, quoted fields and blank lines. The initial example includes a
web; invalid unfinished text stays editable and yields visible preview errors.
Custom node elevations are explicit above the bearing plane; heel/overhang controls
do not move those nodes. One custom graph is limited to 1,024 input nodes, 2,048
input members and 4,096 split members, in addition to the overall generation limit.

Connected graph segments share a `physical_member_id` and full `cut_length_mm`.
Template collinear chords remain continuous cutting pieces across web/bearing
junctions; custom input member rows explicitly define cuts. A custom 9 m bottom
chord split at its central web is one 9 m blank per truss, and retains the special
order/splice warning. New manual definitions include topology schema 2 and its
physical-cut mapping. Legacy truss rows remain intact and expose unknown cut
identity; review/recreate from saved definitions before relying on stock counts.
Splice/connection design and actual supplier stock availability remain unchecked.

These are **conceptual geometry templates**. Strength, deflection, connections,
reactions, attic occupancy/floor loads, and supplier specifications remain unchecked.
The sample house still uses its existing rafter/ridge system; automatic support-aware
truss roofs are available through reusable home definitions. Roof joins, specialized transitions and supplier/structural review remain open T2 gates.

## Request and preview state

A shared request coordinator keeps each response tied to the home and revision
where it started. Delayed responses from another home or an older revision cannot
replace current model, BOM, pricing or warning data. One modifying operation runs
at a time; related form controls are disabled across pages and the viewport shows
its pending state. Navigation/view controls remain available.

Editing a manual/CSV draft or changing CSV commit mode clears the visible overlay
and commit readiness. **Cancel preview** also cancels a preview still loading,
clears its proof and restores the saved view; a late response cannot reappear.
A fresh preview is required before committing. Failed settings writes restore
controls to the saved normalized parameters, and successful model writes clear
stale error banners. The active sidebar page is retained by the `section` URL
parameter; the URL does not serialize an entire project or its unsaved drafts.

## Local draft recovery

Manual drafts are scoped to the home and saved in versioned envelopes with typed
raw form fields. Unfinished custom CSV is preserved without being treated as a
validated model. A valid legacy draft migrates; a malformed/wrong-version/wrong-
home draft opens a default form with **Download saved draft** and **Discard saved
draft** recovery actions. Original raw data is retained under a recovery key until
discarded or the form is explicitly reset. Preview/commit readiness is never
restored from local storage. If storage is unavailable, the live draft remains
editable and the form explains that it must be copied before leaving.

Local form draft schema **2** stores opening numeric fields as text, including
unfinished blanks. Schema 1 numeric openings and earlier flat drafts migrate
without changing their geometry intent; unsupported data remains downloadable for
recovery. Optional empty opening heads derive from sill plus clear height at
preview time. Drafts remain separate from saved source definitions/API inputs.

Run the pure draft-contract checks with `npm run test:contracts` from `frontend/` (Node 24). This includes request exclusivity, revision/home response boundaries and returning-home race checks.
The isolated browser suite also verifies corruption downloads, unfinished CSV
reload, unavailable storage, wide estimate tables and keyboard focus restoration.

## Homes and revisions

Open **Settings / Warnings** to create or select a saved home and restore a prior
revision. New custom homes start empty; sample homes retain the existing sample
controls. Changing exposure or roof settings on custom geometry does not insert
sample walls. Regenerate on a custom home asks you to edit its assemblies; the
explicit **Restore sample** command can replace it after confirmation.

The original database is project `default`. Named homes have validated UUIDs and
live in `<TIMBERBIM_DB_PATH>.projects/<project_id>.db`, beside the default database.
Back up both the default file and every named-home database; each uses the same
SQLite snapshot procedure. `manage_db.py backup/restore --project-id <id>` selects
a named home. Keep the whole project directory when moving installations.

All project endpoints accept `?project_id=<id>`; omitted IDs use `default`.
Model responses include `meta.project` and `meta.params`. Named-project writes
require `If-Match: <revision>`; stale writes return **409**, missing revisions
**428**. Existing default-project integrations retain optional revision headers;
new integrations should send them. Model GET settings are now read-only: migrate
old clients to **POST /api/model** with the same setting query parameters.

A preview returns `preview_token`, bound to its normalized input, project and
revision, valid for 30 minutes. Named-project commits require that token in
`X-Preview-Token`; the browser supplies it for every commit. The default project
retains token-optional legacy commits. Send `Idempotency-Key` for safe retry;
reusing a key with different input returns 409. Tokens expire on server restart
unless all workers share `TIMBERBIM_PREVIEW_SECRET`; set that environment variable
for multiple workers. Do not put it in the frontend or a committed file.

CSV replacement updates the selected home and clears old segment/warning metadata.
**New project from CSV** creates and selects another home, retaining the original.
Accepted definitions are available through `/api/project/definitions`; manual
assembly edits use explicit PUT endpoints rather than duplicate appends.

The most recent **20 prior revisions** are retained inside each database.
Restoration includes member IDs, settings, pricing, definitions, and batch history,
and records a new revision. It is bounded undo, so keep external snapshots too.
BOM downloads include `revision=<displayed revision>` and reject a changed home
instead of silently exporting its new state.

Pricing overrides are saved per home as USD per **physical board metre**, applied
to all sizes of that material. Removing an override restores size-specific
catalogue estimates. Unsupported sizes are unpriced; derived-size estimates have
low confidence. `cost_summary.estimate_complete` and `coverage.unpriced_members`
identify incomplete totals; physical quantity and stock-purchase reconciliation
remain tracked under E1 in the plan.

## Browser regression checks

Backend tests currently include persistence failure injection, snapshot/restore,
CSV conversion agreement, wall opening clearance, and geometry rejection.
Browser checks exercise edited CSV validation/preview/commit, the pinned
mobile viewport, malformed storage, project prices, custom-home creation, wall
commits, settings/reload preservation, model browsing/inspection/isolation, camera
views, and custom truss CSV/header/error flows. They always launch a server with a temporary database.

With the backend environment activated and Node **20+** for browser tooling
(**Node 24** recommended to match CI and run native TypeScript contract tests):

```bash
cd frontend
npm ci
npm run build
npx playwright install chromium
npm run test:browser
```

If Python is outside the active PATH, set `TIMBERBIM_TEST_PYTHON` to its executable.
`TIMBERBIM_TEST_BROWSER` optionally selects an existing Chromium executable.
The CI workflow installs browser system dependencies and runs backend tests,
the production build, and browser checks on Python 3.12 / Node 24.

## Diagnostics, profiling and reproduction

Handled API responses include a generated **X-Request-ID**. Failed requests show
that reference beside the workspace error; server field errors retain it in the
form summary. Match it with JSON diagnostics in server output. Invalid CSV
validation/review also logs a `validation_failed` event even when HTTP status is
200. Events include route pattern, project/revision context, duration and failure
class. They exclude plan bodies, labels, filenames, credentials, proofs and raw
headers/queries. Unexpected internal failures have generic JSON 500 and safe
file/function/line frames in the server event. `TIMBERBIM_LOG_REQUESTS=1` enables
completed-request events at INFO; normal failure logging needs no extra service.
See [backend/API.md](backend/API.md) for scope, units, identity, errors and diagnostic
workflow. Generated input contracts are available at `/openapi.json` and `/docs`;
frontend response interfaces remain manually maintained.

Run `python backend/benchmark.py --repeats 3 --output benchmarks/backend-reference.json`
for isolated generation/persistence/read/serialization/estimating measurements.
Add `--profile-reads` for an extra cProfile read of each fixture, outside timing
samples. Profiling identified a full timber-level scan repeated for each eligible
stud; review now computes that level once. Alternating same-database comparisons
preserved complete responses and database bytes for all five fixtures; the
three-storey read median fell from about 462 ms to 194 ms on the local host.
Smaller fixtures showed little change. These are observations, not device budgets.
Run `npm run profile -- --repeats 3 --output ../benchmarks/local-reference.json`
from `frontend/` after building/installing Chromium for the desktop/mobile browser
measurements. Both use bundled fixtures and disposable data. Profiling identified
missing instance-buffer disposal; rebuilds now dispose the `InstancedMesh` as well
as its geometry/material. The profiler asserts stable explicit buffer balance
across rendered replacements. Its console bridge exists only with `?diagnostics=1`.
The profiler also verifies zero idle renderer submissions after controls settle
and measures enabled auto-rotation separately. A paused viewer has no idle FPS;
frame intervals describe the active rotation sample, not a phone/GPU guarantee.

Run `python scripts/verify_clean.py --output benchmarks/clean-source-reference.json`
for a fresh source copy, Python environment, locked Python/npm installations,
production build, backend/contracts and full browser checks. No user database,
draft, existing environment/dependencies/build or external symlink is copied.
The default command needs network access for dependencies/Chromium; complete
cache/browser overrides support offline use. See [benchmarks/README.md](benchmarks/README.md)
for exact commands, protocol, recorded results and limits. The verified fresh-source
snapshot uses Python 3.12.3 / Node 24.16.0; it is not a remote CI/committed-checkout
claim. Physical reference devices and budgets remain to be agreed.

The full browser suite now checks accessible names and ARIA references on all
seven panels, real Tab reachability, keyboard CSV review/preview/cancel, named
tables, native modal/background focus, mobile canvas/form separation and reduced
motion. [benchmarks/ui-assessment.md](benchmarks/ui-assessment.md) links the current
record and desktop/mobile screenshots, describes measured feedback-text contrast,
and identifies physical-device/assistive-technology review that remains. Optional
`TIMBERBIM_ACCESSIBILITY_REPORT` exports the record and screenshots; no extra UI
framework or product dependency is needed.

The supported operating workflow is a local workspace served on loopback with
SQLite storage. Project IDs scope saved homes and do not authenticate users.
Public/multi-user hosting requires a separate owner-approved deployment design
for authentication, ownership, operational backups and upload controls before
publishing; this implementation does not add that deployment target.

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

Edits/deletions invalidate the preview. Use **Validate edited rows**, then
**Preview in model**, before Commit becomes available. Server errors identify
the row and field. Empty replacements are rejected, optional blank offsets are
normalized, explicit zero overhang/heel values are preserved, and fractional
levels/quantities are rejected. Requests are limited to 8 MiB, 10,000 CSV rows,
and a conservative 100,000 generated members; row/member limits can be configured
with `TIMBERBIM_MAX_IMPORT_ROWS` / `TIMBERBIM_MAX_GENERATED_MEMBERS`.

The mixed example's 9 m and 7 m logical runs now use explicit fabrication panels.
CSV wall rows default to `panelize=true`; set false for a single-frame envelope
check. Manual input offers the same option explicitly. Panels are at most 6 m long
for heights up to 3 m, or 3 m long for heights up to 6 m. Boundaries avoid opening
jambs, and paired panel-end studs are adjacent physical pieces with one shared
joint ID. Plate laps, fasteners, bracing and tall-wall sizing remain unchecked.

The same framing routine serves sample/manual/CSV walls: full jambs, shorter
bearing jacks, lintels, sills, and upper/lower cripples. No member enters an opening
void. Heads equal sill plus height; lintels fit below the plates; jamb bays and
sill clearance are validated. Stud section governs actual depth; a conflicting
nominal wall thickness produces a review warning. Frame plies form parallel layers
across wall depth and preserve the opening width. `plate_material` controls plates,
nogs and sills; `lintel_material` controls lintels; stud material controls verticals.
Sample defaults keep non-stud framing SG8.

Working unit examples: [millimetres](examples/plan_mm.csv),
[metres](examples/plan_metres.csv), and [feet/inches](examples/plan_feet_inches.csv).
The first two use centre offsets and zero truss overhang/heel. Feet/inches includes
quoted dimensions and a negative origin. All examples have end-to-end API tests.
Section strings stay in millimetres regardless of the coordinate-unit selection.

## Manual inputs

**Manual Wall Frame Input** supports coordinates, dimensions, material, stud
spacing, plies, plates, nogs, treatment, and door/window openings. **Manual
Truss Input** supports common, girder, mono, scissor, attic and custom layouts,
repeated quantities, materials, overhang and heel height. Custom examples are
in [`examples/custom_truss_nodes.csv`](examples/custom_truss_nodes.csv) and
[`examples/custom_truss_members.csv`](examples/custom_truss_members.csv).

Both workflows require a successful preview before commit. Drafts and sidebar
pin state are stored in browser `localStorage`.

Forms group **Placement**, **Geometry**, **Materials**, **Openings / Webs** and
**Review**. Draft summaries show wall span/direction and first-to-last truss layout
length. Required finite inputs, opening head/height conflicts and structured server
field errors appear beside the relevant control with an error-summary link.
Keyboard preview moves focus to the first invalid field. Head may be left empty
to derive sill + clear height; unfinished opening blanks survive reloads. Decimal
coordinates/pitch and positive optional nog spacing retain the backend's accepted
ranges. Structural validation remains on the server.

Review indicates **Draft → Validated → Previewed → Committed** in text. Edits and
Cancel invalidate readiness; inspecting an assembly leaves the form open. A failed
transport/server save retains the unchanged preview for an idempotent retry.
Client validation/revision/proof failures require another preview. A successful
retry removes stale errors and records the saved stage. Opening deletion restores
focus to the next opening or Add opening.

Shared visual tokens/components are in `frontend/src/styles.css`. Settings choice
buttons expose pressed states. CSV review cells expose row/column names and linked
validation messages, with keyboard focus recovery after deletion.
Opening a mobile sidebar panel closes the model browser, inspector and expanded
view options to free the upper canvas. Desktop inspection keeps the form in place.

For a focused form regression run, set `TIMBERBIM_TEST_FORMS_ONLY=1` before
`npm run test:browser`; it uses a fresh profile and temporary sample database.
Use `TIMBERBIM_TEST_NAVIGATION_ONLY=1` for the independent saved-home hierarchy,
assembly BOM, row location, request race and camera/focus checks. The default
full suite includes both form and navigation checks.
The default browser command also runs these cases after the full home/CSV/view
workflow. CI continues to run the complete command.

Frontend development with hot reload (proxies `/api` to :8000):

```bash
cd frontend && npm run dev
```

## API

| Endpoint | Description |
|---|---|
| `GET /api/health` | Non-mutating readiness/version inspection; incompatible or unreadable existing databases return 503 |
| `GET /api/model` | Reads the selected project without modifying it. Geometry/settings query parameters do not change saved data. Returns identity, revision, mode and saved parameters in `meta`. |
| `POST /api/model` | Explicitly updates settings and regenerates sample/mixed geometry; custom geometry is retained. Query params: `storeys` 1–3 · `roof` gable\|hip · `wind_zone` low\|medium\|high\|very high\|extra high · `wind_speed` m/s (overrides `wind_zone`) · `snow_zone` N0–N5 · `gable_spacing` 300–1200 mm · `wall_treatment` H1.2\|H3.1\|H3.2\|H4\|H5. **Wall stud design:** `stud_material_overall` (sg8\|sg10\|prolam\|glulam\|gl8\|gl10\|gl12\|hychord\|hyspan\|hy90) · `stud_spacing_overall` (300–1200 mm) · `wall_plies_overall` (1–6) · per-level / per-segment JSON-object params `stud_material_levels={"2":"hyspan"}`, `stud_spacing_levels={"1":400}`, `wall_plies_levels={"1":2}`, `stud_material_segments={"G-EXT-001":"hy90"}`, `stud_spacing_segments`, `wall_plies_segments`. Invalid values are clamped/ignored with warnings in `meta.warnings`; the response includes `meta.frame_segments` and `meta.cost_summary` |
| `GET /api/bom.csv` | Bill of materials (timber only) from the SQL `bom` view. Includes assembly/section plies, cuts/board quantities, net/stock board metres, cut/stock costs, missing-price status, price provenance, NZS reference and stock/legacy notes; see quantity definitions below |
| `GET /api/materials` | Stud material catalogue: sizes, USD/lm estimating prices with source name/URL/date, original currency price/unit, FX rate + date, confidence (high/medium/low) and assumptions |
| `GET /api/cost-summary` | Estimated material cost totals (USD) for the current model: grand total and breakdowns by material, storey, frame segment and element |
| `GET /api/bom.json` | Grouped in-app BOM rows |
| `GET /api/pricing` | Material price rows, source metadata, and saved project overrides |
| `POST /api/pricing/overrides` | Save `{ "overrides": { "sg8": 99 } }`; recompute member/BOM/export costs atomically |
| `GET /api/warnings` | Consolidated model/import/manual/pricing warnings |
| `POST /api/import/csv-plan/validate` | Multipart CSV validation without model mutation |
| `POST /api/import/csv-plan/review` | Revalidate edited JSON rows with the same domain contracts used during generation |
| `POST /api/import/csv-plan/preview`, `/commit` | Preview or commit reviewed CSV geometry |
| `POST /api/manual/wall-frame/preview`, `/commit` | Preview or commit a manual wall frame |
| `POST /api/manual/truss/preview`, `/commit` | Preview or commit a manual truss layout |
| `GET /api/import/batches` | Project import/manual batch history |
| `DELETE /api/import/batches/{id}` | Delete the selected batch/assembly with a restorable revision |
| `GET /api/projects`, `POST /api/projects` | List homes or create `{ "name": "My home", "geometry_mode": "custom" }` (`sample` also supported) |
| `POST /api/project/initialize` | Explicit default-project initialization/migration |
| `GET /api/project/definitions` | Saved CSV rows and manual wall/truss definitions |
| `PUT /api/manual/wall-frame/{id}`, `/api/manual/truss/{id}` | Update an existing assembly using its newly previewed definition |
| `GET /api/project/revisions`, `POST /api/project/revisions/{revision}/restore` | List and restore retained revisions; restore creates a new revision |
| `POST /api/project/reset`, `/regenerate` | Clear additions or regenerate while preserving selected sources |

## How it works

```
geometry.py (floor plan)  →  framing.py (NZS 3604 member generator,
        ModelConfig: storeys/roof/wind/snow/gable-stud spacing)
        →  SQLite (schema.sql tables + bom_queries.py views)
        →  FastAPI (/api/model, /api/bom.csv)
        →  Three.js viewer (TypeScript)
```

Each rendered member segment is stored as a row: function, size, grade, treatment
(H1.2 / H3.2), length, centre position, yaw and pitch — plus material,
plies, segment id/label, effective stud spacing and estimating price
columns. The frontend instances a unit cube per row.

## Pricing and physical BOM quantities

Open **Pricing** to save a project override in USD per physical board metre.
Its scope covers all sections/treatments of that material and is disclosed as a
user assumption. Clear the override and save to restore catalogue prices.
Current supplier quotations can be entered through this workflow; automatic
price refresh and a configurable project currency are not implemented.
The source catalogue remains separately available from `/api/materials`.

Prices are historical **2026-06-11** snapshots, using recorded NZD→USD FX
**0.5795** on that date. They have not been refreshed as current market prices.
Each new/repriced member retains source/date/currency/FX and pricing notes;
project overrides retain their save date, USD basis and explicit scope.
Derived sections and unsupported treatment scope reduce confidence to `low`;
unsupported sections remain unpriced. Legacy price provenance is marked unknown
rather than assigning a new date to old values.

BOM definitions:

| Field | Meaning |
|---|---|
| `qty` | Physical assembly cutting pieces, independent of connected graph-segment count |
| `plies` / `section_plies` | Assembly plies and the intrinsic `N/size` multiplier, separately |
| `physical_qty` | `qty × plies × section_plies` individual boards |
| `total_length_m` | Net geometric cutting length before ply multipliers |
| `total_effective_length_m` | Cutting length × assembly plies; retained compatibility field |
| `cut_board_m` | Net cutting length × both ply multipliers |
| `stock_length_m` | One piece length rounded **up** to 300 mm; over 6 m requires splice/special-order review |
| `stock_board_m` | Rounded stock length × individual board count |
| `total_cost_usd` | Cutting length × assembly plies × section price (price already includes intrinsic plies) |
| `stock_cost_usd` | Rounded stock length × assembly plies × section price |

A `2/140x45` section in a three-ply assembly represents six boards for each cut.
Rendering includes both multipliers. Stock estimating uses **one blank per board**;
it does not optimize cuts or reuse offcuts. Stock minus cut metres represents
rounding allowance only; supplier waste, kerf and fabrication details are excluded.
BOM monetary groups are rounded to cents before summing the displayed/exported
subtotal. The model and preview use the same grouping basis.

Missing prices produce JSON `null` and blank CSV costs, displayed as **Unpriced**.
Project totals are explicitly **priced cut subtotals**, with unpriced board
coverage alongside them. The separate stock subtotal uses the same known prices.
Zero-valued user prices remain valid priced entries. Estimates exclude delivery,
fixings, labour and fabrication waste; check supplier quotations before ordering.

Use **Expand BOM** or **Expand Pricing** for a wide table. BOM search, level/category
and unpriced filters, sorting and column controls apply to the same live table.
The BOM inspector and CSV retain price dates, currency/FX, assumptions and legacy
cut warnings. Escape closes the expanded workspace and restores keyboard focus.

Choose **BOM for assembly** in the selection inspector for complete saved wall
or truss-instance quantities. The server scopes by source namespace, batch, level
and assembly identity; matching labels cannot merge different sources. This view
includes hidden or clipped members of that assembly. Connected chord segments
still count as one physical cut. **Show whole-home BOM** clears the scope; changing
home/revision also clears it. Temporary members must be saved before opening their BOM.

Each row’s **Locate in model** isolates its exact saved member IDs, frames their
geometry and focuses the canvas; the table dialog/mobile sheet closes. Use
**Show all** in the inspector to release the isolation. A whole-home row may
contain cuts from several assemblies. The inspector describes the first selected
assembly within that visible row, while the camera frames the entire row.
**Export whole-home CSV** keeps its existing full-home scope and columns even
when the table is filtered. Assembly subtotals round their own monetary groups
to cents; summing separately scoped subtotals can differ from the full-home
subtotal by rounding.

`GET /api/bom.json?member_id=<saved-element-id>&project_id=<home>&revision=<revision>`
returns the scoped `rows`, `scope`, actual `project_revision` and JSON-only
`member_ids` per row. Omit `member_id` for whole-home rows. Stale revisions
return 409, missing members 404, invalid/nonpositive IDs and concrete anchors
422. Reads do not initialize or mutate the database. The shared SQL in
`backend/bom_queries.py` preserves existing cutting/BOM views at schema 5.

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

Imported and manual geometry must be checked by a qualified designer or
engineer. NZS 3604 or specific engineering design governs real construction
decisions.

Saved assemblies can be edited from **Imports → Committed batches → Edit**.
Manual wall/truss editors retain their source ID and keep editing drafts separate
from new-assembly drafts, scoped to the home and assembly. CSV editing starts from
saved normalized millimetre rows; those row edits remain temporary until saved.
Preview hides the target's saved geometry and displays its proposed replacement.
Saving replaces only that assembly and creates a restorable revision. Legacy
assemblies without a saved definition must be reviewed and recreated.

New-home creation uses a stable retry key, including sample homes created from a
later revision of another home. If a reply is lost, retrying the same creation
returns the same home. API clients must retain their Idempotency-Key for retries.

Reusable home definitions and automatic roofs are available in **Imports / Drawing
Plans → Reusable homes**. Choose Rectangle, L-shaped or Two levels; preview and
save the proposed geometry. **Edit current definition** exposes stable entities,
explicit elevations, wall openings, finite floor supports and roof zones. Truss
zones include connected webs and individual physical instance/cutting IDs, check
bearing placement, and avoid duplicate rafters/ceiling joists. Rafter gable/hip
systems remain available. Overlapping zones report unresolved roof joins.
Automatic truss placement before **2.11.0** used a bearing edge as the template
center. Existing geometry remains saved; review its bearing warning, back up the
home and use **Regenerate model** to place it correctly on the referenced walls.
Rule profile version **2** detects physical BL/BR nodes away from actual wall
runs/tops, including older layouts. Alignment is a geometry diagnostic; supplier
bearing capacity and connections remain unchecked. Regeneration creates a revision
and retains the previous geometry through revision recovery.

**Download saved home** includes definition, settings, USD quote overrides and
dates, source assembly definitions, original revision and catalogue provenance.
Open that file in another home to preview/import an independent copy; archive
import replaces that home's geometry/pricing and creates an undoable revision.
Legacy geometry without definitions is retained and flagged for recreation.
Estimates use the installed catalogue and imported overrides; catalogue drift is
reported. Portable files contain the current inputs, while SQLite backups preserve
full revision history. Manual/JSON draft edits are local/temporary until saved.
See [the home fixture and format guide](examples/homes/README.md) for coordinate
conventions, examples, limits, API routes and qualified-review gates.

Applicability reporting in **Settings / Warnings** separates source references,
geometry checks within stated assumptions, requirements for specific design, and
checks not evaluated. Warnings aggregate repeated occurrences and open the related
assembly in the inspector. Actual model height uses member bounds and explicit
level elevations; partial/legacy inputs without a datum remain unchecked. Each
revision stores a review snapshot, while read-only assessments use the current
software rule version. Connected webs, prices, stronger material names and denser
spacing never imply structural approval. The conceptual NZ reference profile is
not independently verified; see [the rule/reviewer register](backend/RULES.md).
