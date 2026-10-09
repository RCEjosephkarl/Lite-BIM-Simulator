# TimberBIM Lite — Feature Update Report

## Numerical and resource contracts — v2.17.0 (2026-10-09)

Finite input coordinates could previously overflow during wall-length calculation,
and truss repeats or enormous sections could yield non-finite members. Manual/CSV
validation now checks derived lengths and sections, and uses the same truss
placement transform as generation. The first/last instance checks reject overflow
and endpoints that collapse at coordinate precision before geometry is generated.
Member constructors also reject non-finite derived geometry.

CSV reading now stops after the existing row limit plus one look-ahead row.
Split/porch layouts check the existing generation budget before constructing
member lists; rafter/porch spacing that cannot advance raises a useful error
instead of looping. The API body guard checks the next streamed chunk before
appending it. The 16 MiB body, 8 MiB CSV, row/member budgets, templates, materials,
coordinate signs, UI ranges and frameworks retain their existing contracts.

Invalid CSV NaN/Infinity values, including extra nested cells, remain reviewable
and JSON-safe. Manual/home schema errors preserve field locations instead of
losing them during serialization. CSV parser failures now include a field as well
as a row. Floor polygon area and rotated joist/support/hole calculations use a
local origin; regressions at positive/negative 10^12 mm translations preserve
member dimensions/counts and translated positions. This is backend numerical
evidence, not a claim about extreme-coordinate GPU rendering.

The worktree passed **224 backend tests**, production build and frontend
contracts. Thirty-three added resource/API tests cover derived overflow across
CSV review/preview/commit without mutation, malformed JSON dimensions with field
locations, parser row allocation, exact/overflow byte and split limits, framing
progress guards and translated floors. Fresh locked Python/npm installations
also passed all 224 tests, production build, contracts and full Chromium,
including seven-page desktop/mobile
accessibility, reusable homes, connected webs, editing, archives, pricing and
view/draft/race/retry workflows. All five fixtures at desktop/mobile also passed
refreshed profiling: member counts match the previous reference, settled idle
submissions are zero, rotation
remains active and instance-buffer balance is stable across rendered rebuilds.
Current runtime source fingerprints match the refreshed backend read/CPU record;
prior v2.16 captures are retained for historical comparison. The apparent
multipart-test stall was reproduced inside the restricted sandbox and resolved
with worker-thread wakeup
sockets enabled; the streamed-body test itself passes. Runtime/database behavior
was not changed to work around the test environment.

`backend/FRAMING.md` now documents wall panel/opening/ply behavior, all six
truss input types, exact template formulas, worked graph/cut/ply counts, bearing
conventions and legacy layouts. Explicit support/section-intent metadata and
fabrication detail exports remain separate implementation gates.

Versions are coordinated at **2.17.0**; SQLite schema 5, rule profile 2 and draft
schema 2 remain. Tests use temporary databases. No owner database or feature/
framework restriction was introduced. Full V1/M1 resource acceptance, complex
topology/aggregate resource profiling, estimating-read work, fabrication/support
implementation, roof/floor domain gates and qualified review remain active.

## Review-read optimization and seven-page accessibility assessment — v2.16.0 (2026-10-09)

Profiling the three-storey temporary fixture found about five million generator
iterations in `review.evaluate`: each eligible stud recomputed the highest timber
level. The level is now derived once per evaluation, preserving the whole-model
timber definition and its empty default. A new regression checks out-of-order
groups, lower/top-level spacing, an upper roof without studs, concrete exclusion,
stale configuration storeys and absence of an implicit capacity pass.

Five alternating same-database comparisons preserved complete responses and
database bytes. Three-storey median review evaluation fell from about 230 ms to
10 ms, and full model read from 462 ms to 194 ms; smaller fixtures showed little
change and some noise. `benchmarks/review-read-comparison.json` retains the paired
samples, evaluator hashes, exact-equality evidence and before/after cProfile.
The optional benchmark `--profile-reads` now records one extra profiled read per
fixture outside normal timing samples. Current read profiling puts estimating
SQL and member decoding ahead of review; payload shapes/quantities remain intact.

The new seven-page audit checks Chromium's accessibility tree and real Tab cycles
at desktop/mobile sizes, including editable CSV cells, opening/custom CSV fields
and definition editing. It identified and fixed unnamed Pricing/CSV tables and
navigation label chips covering panel content. Tables now have names and explicit
column headers; CSV actions are named. Tooltips remain outside desktop panels or
above mobile sheets. Keyboard CSV review/preview/cancel, enabled-control reachability,
intact ARIA references, native modal background inertness/escape focus, mobile
canvas space and reduced-motion transitions pass. Native browser-chrome Tab
boundaries are recorded rather than replaced by a custom focus trap.

The focused sample capture records 1,141 reachable enabled targets across fourteen
page/viewport cases and two modal cases. Feedback/secondary text contrast on solid
panels measures 6.20:1–13.54:1. Desktop/mobile screenshots and limitations are linked
from `benchmarks/ui-assessment.md`; this is local software/visual assessment, not
assistive-technology or physical-device certification.

Fresh locked Python/npm installations passed **191 backend tests**, production
build, frontend contracts and full Chromium acceptance, including the audit on a
saved reusable home and prior rendering/view/draft/race/retry contracts. All ten fixture/viewport profiling cases
passed with zero settled idle submissions, active rotation and stable rebuilt
instance-buffer balance. Versions are coordinated at **2.16.0**;
SQLite schema 5, rule profile 2 and draft schema 2 remain unchanged. No workspace
database was created/modified or feature/framework restriction introduced.

Next: finish M1/V1 contract/resource-bound acceptance, measured estimating-read
and payload work, W1 fabrication details, T1 template/support documentation,
roof/floor domain gates and cross-version price/rule replay. Physical devices,
assistive-technology/enlarged-text review, owner-committed/remote CI and qualified
R1 structural/supplier audit remain outstanding.

## Viewer rendering on change — v2.15.0 (2026-10-09)

The v2.14 profile recorded 13–95 renderer submissions during each two-second
idle fixture/viewport window. The viewer now coalesces scene and camera changes
into animation frames and stops once controls settle. OrbitControls change events
keep damping live; enabled auto-rotation continues requesting frames. Model,
material colour, layers, section, selection, dimensions, camera projection/fit,
resize and visibility/WebGL-context restoration all request repaint. Rendering
quality, supported ranges and frameworks are preserved.

The optional diagnostic bridge counts actual renderer submissions and exposes
pending-frame state. Profiling schema 2 separates a settled two-second idle count
from a two-second enabled-rotation interval sample and checks both behaviours.
The previous capture is retained as `benchmarks/before-demand-rendering.json`.
Active rotation intervals and static idle intervals are different workloads;
the change removes idle work without claiming an interaction FPS improvement.

Focused Chromium checks passed for idle stop, visibly different camera/colour
pixels, selection/clear, filters, section, dimensions, enabled rotation, post-drag
damping and settling, resize, rebuild and return-to-visible repaint. Fresh locked
installs passed 190 backend tests, production build, frontend contracts and full
Chromium acceptance, including the rendering checks. The offline reproduction
used complete locked-package caches and a selected existing Chromium binary; it
still created new dependency installations and disposable application data.
All five fixtures at desktop/mobile sizes passed: zero renderer submissions
after settling over each two-second idle window, continuing rotation with camera
motion, and unchanged explicit buffer balance across rendered rebuilds. The
current schema-2 capture and fresh-install report are retained in `benchmarks/`.
SQLite schema 5, rule profile 2 and draft schema 2 remain unchanged.

Next: complete U2 accessibility/visual assessment and M1 API/resource-bound
coverage and measured read/payload improvements. Physical reference devices and
budgets, owner-committed/remote-CI verification, W1/T1/T2 details, cross-version
replay and qualified R1 structural/supplier gates remain open.

## Failure diagnostics, resource profiling and fresh-source verification — v2.14.0 (2026-10-09)

Every handled response now carries a server-generated request reference. Structured
JSON events identify route pattern, request/observed home, expected/actual revision,
status, duration and failure class. CSV validation/review failures log counts even
with HTTP 200. Logs omit uploaded rows, labels, filenames, credentials, tokens,
operation keys, raw query/header values and exception text/locals. Unexpected
failures return generic JSON 500 and a reference; their events contain at most
eight file/function/line frames. Request ContextVars preserve concurrent isolation,
and logging-sink failure leaves handled responses usable. Frontend errors and
server-field summaries display the reference without changing inline focus/retry.

`backend/benchmark.py` measures five bundled/synthetic fixtures in temporary
databases. `npm run profile` imports portable fixture archives into disposable
homes and records loopback transfer/parse, mesh build, selection/raycast, idle
frame intervals, renderer counters and collected Chromium heap at desktop/mobile
sizes. The opt-in diagnostic console bridge is absent from normal workspaces.
Measurements found replaced instance buffers lacked explicit disposal; the local
Three.js implementation confirms `InstancedMesh.dispose()` removes them. That
call now accompanies geometry/material disposal. Rendered replacement tests keep
the explicit buffer balance stable for all fixture/viewports. Counts are not GPU
bytes, and the local ANGLE/SwiftShader baseline is not a physical device budget.
See `benchmarks/README.md` and the JSON records for protocol, inputs and provenance.

`verify_clean.py` copies source/examples/docs into a new temporary tree, excludes
local stores/secrets/dependencies/builds/symlinks, creates a fresh Python environment
and installs the locked Python/npm packages. Its completed run passed **190 backend
tests**, production build, frontend contracts and full Chromium workflows,
including saved non-sample homes, portable archives, error references and prior
view/draft/navigation/retry gates. The initial offline attempt lacked npm tarballs;
existing cache entries plus downloads of the remaining locked packages completed
setup. The final record describes a fresh worktree-source snapshot, not an
uncommitted worktree becoming a Git checkout or remotely executed CI.

Versions remain coordinated at **2.14.0**; SQLite schema **5**, rule profile **2**
and draft schema **2** are unchanged. No real workspace database was created or
modified, and no framework/feature restriction was introduced. API/identity and
local-deployment conventions are now documented explicitly.

Next: complete U2 accessibility/visual assessment and M1 contract/resource-bound
coverage. Use the measurements to assess review/estimating-read cost, repeated
metadata payloads and idle rendering before changing behavior. Agree physical
reference devices/budgets, then run CI against an owner-committed revision. Continue
W1/T1/T2/R1 details, domain/replay and qualified structural/supplier review gates.

## Model hierarchy, assembly BOM and keyboard camera — v2.13.0 (2026-10-09)

The model browser now groups Level → source batch → Walls / truss layout →
assembly → panels / physical members. Equal labels/IDs in different sources stay
separate. Native disclosure controls and buttons support keyboard navigation;
physical members load lazily in batches, with Show more and focus on the first
new item. Search includes source
IDs, panel/opening/node IDs, roles and cuts. Selection has a checkmark/pressed
state and temporary assembly buttons include PREVIEW text.

BOM for assembly scopes complete saved quantities by source, batch, level and
wall/truss identity, independently of visual clipping/layers. JSON rows carry
exact member IDs for Locate in model: the row geometry is isolated/framed and
canvas focus is restored after closing a dialog/mobile sheet. Whole-home rows
may span multiple assemblies. Clear scope restores the full home; home/revision
changes reset stale anchors. Own request tickets and API revision checks prevent
late responses from restoring a prior scope. The CSV remains the whole-home
export with its previous columns. Connected chords stay one cut; plies multiply
boards independently. Scoped cents round separately from whole-home groups.

The existing cutting/BOM SQL moves to `bom_queries.py`, shared by migration
bootstrap and navigation queries. Persisted view columns/formulas are unchanged;
SQLite schema **5**, rule profile **2**, and draft schema **2** remain. No real
workspace database was created or modified. No framework/feature restriction
was introduced, and C1–C6 still require owner confirmation.

The focusable canvas supports arrows for pan, Shift + arrows for orbit, + / −
for zoom and Home for Fit model, with visible button equivalents and instructions.
Tab leaves the canvas, form inputs retain normal keys and camera changes use
existing home-local recovery. Rendering without a selection clears old inspector
state so another home's stale assembly cannot remain visible. Mobile inspection
uses a 45 vh bottom sheet with separate canvas space; form sheets reserve 55 vh.
Picking a member collapses the mobile form sheet without deleting its draft or
changing the active page. Inspector label/value layout is shared with the sidebar.

Verification: **181 backend tests**, production build and Node contracts passed.
Six new backend cases check unchanged whole-home quantities/CSV/read-only state,
full chords/plies within one instance, source collisions, revision/ID validation,
and concrete/empty-home behavior. Focused and full combined Chromium checks
passed for the hierarchy (including 260 truss instances and paging focus),
source-safe assembly BOM, exact row isolation, request races, camera keys,
dialog-to-canvas focus and non-overlapping mobile inspection/form space.

Next: finish U2 accessibility/visual review across desktop/mobile, especially
workspace overlays and dense hierarchies. Continue M1 structured diagnostics,
representative performance measurements, API contracts and a clean-checkout
non-sample handover. Domain/replay and qualified-review gates remain open.

## Guided forms and unfinished opening recovery — v2.12.0 (2026-10-09)

Manual Wall and Truss forms now group Placement, Geometry, Materials,
Openings/Webs and Review without removing existing fields, template types or
ranges. Live summaries show rotated wall span/direction and the first-to-last
truss layout length. Required numeric inputs keep blank distinct from zero;
decimal coordinates/pitch and positive optional nog spacing remain accepted.
Opening head/sill/height conflicts appear beside Head. Server field paths map
to the matching opening or custom graph input, with summary links, associated
feedback and keyboard focus. Custom CSV parse errors appear at their textarea.

Review progress uses text and checkmarks for Draft, Validated, Previewed and
Committed. Edits/Cancel invalidate readiness. Failed transport/server saves retain
an unchanged preview for idempotent retry, while client/proof/revision errors
require re-preview. Success clears stale errors. Inspection leaves the active
form/draft available, and deleting an opening recovers focus.

Local draft schema **2** preserves raw opening blanks. Schema 1 numeric openings
and legacy flat drafts migrate to text without modifying saved source definitions
or the API format. Unsupported data retains the existing download/discard flow.
Shared CSS tokens/components move to `frontend/src/styles.css`; settings choice
buttons expose pressed state and CSV cells expose row/column names, error
descriptions and pending state. User-supplied column attributes are escaped.

Verification: **175 backend tests**, production build and Node contracts passed.
New contract cases cover opening migration/blanks, field paths, head conflicts,
rotated dimensions and repeated layout intent. Focused and full combined Chromium
checks passed for form grouping, native/server errors and focus, blank opening
reloads, decimal inputs, stale previews, lost-response retry and mobile overlays.
Schema remains **5**, rule profile remains **2**, and owner decisions C1–C6 remain
pending. No feature/framework restriction was introduced.

Next: complete **U2** model hierarchy/BOM
navigation, keyboard camera interaction and remaining accessibility review.
Continue **M1** logging, performance measurements, contracts and clean-checkout
handover, together with the remaining domain/replay and qualified-review gates.


## Home view state, dimensions and bearing placement — v2.11.0 (2026-10-09)

`workspaceState.ts` now owns the displayed home, reversible preview and view
preferences. Home-local storage retains colour/layers, source/level,
physical/node selection and isolation, camera/projection/zoom, motion, dimensions
and section. Revision reconciliation removes stale identities. Previews use
temporary filters/cameras; cancellation restores the committed view, while
deliberate display preferences survive. Unsupported saved view data supports exact
download/discard recovery, and unavailable storage leaves live controls usable.
Small view/section hints join the project/section URLs.

Plan/front/side use orthographic projection; plan north points up. Fit-all and
fit-selection use oriented, clipped member bounds. Section filtering applies to
rendering, picking and fitting. Dimension lines/labels show visible bounds in mm;
manual wall preview intent separately displays span, openings and elevation.
Roof-only/level controls, keyboard selection/focus and a bounded mobile bottom
sheet keep dense framing and forms accessible. Escape in table dialogs preserves
return focus instead of closing the panel behind the dialog.

Visual review found the automatic roof adapter was passing a bearing edge to the
manual truss generator's center origin. The adapter now uses the bearing midpoint;
the manual/CSV placement convention stays compatible and is labeled explicitly.
Ten new cases check physical BL/BR positions and actual wall-top elevation for all
five templates on both axes in a translated home. Rule profile **2** adds actual
bearing geometry diagnostics and detects pre-2.11 displacement or missing support
geometry. Saved older geometry is reviewed on reads; explicit regeneration creates
corrected geometry and a recoverable revision. Alignment never grants capacity or
connection approval.

Verification: **175 backend tests**, production build and Node contracts passed.
The view contracts cover home/revision boundaries, reversible previews,
corruption/storage failure, finite cameras, URLs, rotated sections and a large
group without argument-stack overflow. Chromium passed the full workflow including
view recovery/reload/home switching, section-aware fitting, wall/opening dimensions,
preview camera/filter restoration, keyboard selection and mobile/table focus.
SQLite schema remains **5**. No feature/range/framework restriction was introduced;
owner decisions C1–C6 and qualified structural/supplier review remain pending.

Next: **U2** guided Manual Wall/Truss forms, inline errors and the remaining
accessibility/visual-system gates; **M1** logging, performance measurements,
contracts and clean-checkout handover. Continue the open domain/replay/review gates.


## Auditable applicability and inspection — v2.10.0 (2026-10-09)

`review.py` separates reference-only information, software geometry checks within
stated assumptions, requirements for specific design and checks not evaluated.
Actual oriented model bounds and explicit level elevations replace storey-count
inference for height diagnostics. Truss geometry checks physical node agreement,
connected chords/webs and graph closure; capacity, reactions, connectors and
supplier design remain required. Stud/floor geometry is checked against the
source's disclosed simplified inputs, while complete loads, loaded dimensions,
foundations, bracing and connections remain unevaluated. No result creates
structural approval or upgrades the unverified standards/manufacturer basis.

Each revisioned write stores an assessment in the same transactional snapshot.
Read-only model/warning responses and previews carry their own rule/version/input
assessment. Repeated source warnings aggregate by source/assembly/message.
Settings exposes cause/action/assumptions and opens the related assembly, clearing
filters/isolation and revealing its category. Inspector review remains distinct
from structural approval. The [rule register](backend/RULES.md) lists inputs,
limitations and the required qualified-review handover.

Verification: **164 backend tests**, production build and Node contracts passed.
Seven new tests cover actual height/datum, topology versus capacity, legacy/broken
endpoints, unpriced/denser assemblies, warning aggregation, persisted/read-only
assessments, exposure and jurisdiction-profile rejection. Chromium verifies
applicability status and warning inspection alongside reusable-home/editing/
pricing/draft/retry flows. Schema remains **5**; remote CI and independent
structural/standards/supplier review remain outstanding.

Next: **U1/U2** shared view state, dimensions/section views, guided forms and
accessibility; **M1** logging, performance and clean-checkout handover. Continue
R1 with a qualified reviewer, and retain the open W1/T1/T2/E1 domain/replay gates.


## Reusable homes and automatic roof trusses — v2.9.0 (2026-10-09)

A strict versioned home definition now stores levels/elevations, stable wall and
opening IDs, floor boundaries/holes/directions/support segments, rectangular roof
zones, slabs and porches. The sample runs through the same domain generator;
one-, two- and three-storey parity probes retain the previous member coordinates
and counts. Existing options/frameworks remain available. Roof shape and framing
system are separate. Automatic gable trusses use the manual connected chord/web
graph, explicit first/last spacing and actual bearing-wall elevation, with unique
instances and physical cuts. Truss zones omit duplicate ceiling joists/rafters.
Overlapping zones now disclose unresolved valley/trim/load transfer.

Imports has example selection, current-definition editing, full replacement
previews, cancellation, save with affected-member confirmation, and portable
download/import. The rectangle, L-shaped and offset two-level examples save,
reopen and regenerate independently. Archives contain settings, original quote
dates/overrides, source definitions, project revision and catalogue provenance.
Known assemblies regenerate; legacy output is explicitly retained with review
feedback. Import is atomic, idempotent and undoable. Catalogue drift is reported;
import estimates use the installed catalogue and imported quote overrides.

Verification: **157 backend tests**, production build and Node contracts passed.
Chromium passed example preview/save, connected webs, download, a second design,
cancellation, reload and archive restoration, alongside existing project/editing/
pricing/draft/race flows. Twenty-five new domain/API tests cover three home copies,
both roof axes, topology, elevations, finite support extents, rotated floors/holes,
invalid references/polygons/limits, stable IDs, legacy recovery, stale preview
generation, quote preservation and late-insert rollback. Schema remains **5**;
no user database was created/modified. Remote CI remains unrun.

Next: **R1** auditable applicability/status and warning links; remaining **U1/U2**
view state, dimensions/sections, guided forms and accessibility; **M1** logging,
performance/clean-checkout handover. D1/T2 still need supplier/structural review,
roof junction/hip-transition rules, floor trimming/load transfer and cross-version
price/rule reproducibility. See [home fixtures](examples/homes/README.md).


## Saved assembly editing and home creation — v2.8.0 (2026-10-09)

Imports now opens saved wall/truss definitions and normalized CSV batches for
editing. Save replaces only the selected assembly and preserves its source ID,
other assemblies and revision history. Replacement previews exclude the saved
target from the scene. Manual editing drafts have separate home/assembly
namespaces, and edit links reopen the correct definition. Missing legacy
definitions have a visible recreation path. CSV row edits are temporary until
save; CSV local draft recovery remains a future improvement.

Home creation uses the new home's revision and stable retry identity. Matching
concurrent retries create one home; a lost server reply can be retried safely.
Reusing a key with different input conflicts, and missing project metadata cannot
quietly replace existing geometry. Definition/history reads enforce revisions.

Verification: **132 backend tests**, TypeScript/Vite build, Node draft/request
contracts and isolated Chromium checks passed. Browser coverage includes editing
CSV/wall/truss assemblies, reload and replacement previews, plus sample-home
creation after the server accepts the request but the reply is lost. The user's
development database was not created or modified. Remote CI remains unrun.

Next: **D1/T2**, beginning with a versioned reusable home definition, explicit
levels/supports and roof systems, then UI import/export and three saved-home
fixtures. Structural/supplier review and C1–C6 decisions remain outstanding.


## Draft and request safety — v2.7.0 (2026-10-09)

Versioned manual drafts preserve raw fields and unfinished custom CSV, validate
form/home identity and field types, migrate valid legacy data, and retain malformed
raw data for download/discard recovery. Storage denial leaves the live form usable
and shows feedback. No saved draft restores a preview proof or commit readiness.

A shared request coordinator captures home/revision/epoch for every request,
rejects obsolete responses, and permits one modifying operation at a time.
Pending controls synchronize across manual/import/pricing/specs/settings pages.
Read refresh errors are visible; obsolete refreshes are ignored. Manual/CSV edits,
CSV commit-mode changes and home switches cancel overlays/readiness. Cancelling
an in-flight preview aborts its browser request and proof, releases controls and
prevents a late response from restoring the overlay. Failed settings writes reset
controls to saved normalized values. Successful writes clear stale model errors.
The active sidebar section has a validated deep link and accessible current state.

Verification: **122 backend tests**, TypeScript/Vite build and Node draft/request
contract scripts passed. Isolated Chromium checks passed for delayed cross-home
BOM responses, shared pending controls, edit/pending-preview cancellation and
retry, literal labels, storage recovery, wide tables and existing project flows.
Health checks additionally detect missing BOM/cutting views without rebuilding.
Remote CI remains unrun. A comprehensive shared view/camera state, dimensions,
section views and the remaining accessibility gates are still tracked in the plan.

Next: **S2 assembly editing** from Imports / committed batches and Manual Wall/
Truss Input, then **D1/T2** reusable home definitions and support-aware automatic
roofs. Structural/supplier review and C1–C6 owner decisions remain outstanding.

## Physical cuts and estimating — v2.6.0 (2026-10-09)

Connected truss graph segments now share physical cutting identities. Template
collinear chords stay continuous across bearing/web joints; custom member rows
remain explicit cuts. Each instance has its own cut IDs and declared full lengths.
The persisted topology schema 2 includes a graph-to-cut mapping. Section and
assembly plies multiply physical quantities and geometry independently.

The SQL BOM groups cuts before stock rounding, exposes board counts and net/stock
board metres, and separates cut cost from one-blank-per-board stock cost. Unpriced
costs remain NULL/blank rather than zero, and summaries/previews expose coverage.
Monetary groups round to cents before subtotaling. Overflow fails inside the price
transaction and restores the previous revision.

Per-member price records now retain historical source dates, currency/FX and
assumptions. Section/treatment mismatches reduce confidence. Overrides retain
USD/save-date provenance and explicit all-section/treatment scope; clearing an
override restores the catalogue. Forward schema 5 preserves old IDs, prices and
geometry, takes a pre-upgrade snapshot, and flags unknown legacy truss cut identity
and missing historical price provenance without fabricating either.

BOM and Pricing expand into accessible wide dialogs using their existing controls.
BOM adds sorting, price filters, column controls, priced subtotals and unpriced
board counts. Status/inspector/manual/import preview surfaces disclose coverage
and physical cuts. Desktop/mobile dialogs, column/filter/sort controls and keyboard focus restoration passed isolated browser checks.

Verification: **121 backend tests passed**, including **12 physical estimating
cases**, and TypeScript/Vite production build passed. The expanded isolated browser
flow passed, including physical cuts, missing prices and wide-table interactions. Prices were not refreshed; optimization/offcut reuse,
actual supplier stock and structural splice/connection design remain outside these
estimates. Remote CI has not been executed here.

Versioned local drafts now include form/home identity, save date and typed raw
fields. The decoder rejects malformed shapes, unsupported versions, invalid
choices and cross-home data; valid legacy drafts migrate. Unfinished custom CSV
survives reload without restoring commit readiness. Invalid raw drafts are retained
under recovery keys, with visible download/discard controls. Storage denial keeps
the live form editable and shows feedback. A Node 24 contract script and isolated
browser checks cover these boundaries, legacy quoting and recovery downloads.

Next: U1 coordinated requests/preview cancellation, then S2 assembly editing and
D1/T2 reusable homes/automatic roof framing. The remaining plan and owner
confirmations remain in `improvement_plan.md`.

## Shared walls and panels — v2.5.0 (2026-10-09)

Sample/manual/CSV walls now share `walls.py`. Logical wall runs retain their wall
identity while fabrication panels have separate IDs and paired end studs with
shared joint IDs. The manual form keeps single-frame mode and adds explicit
panelization; CSV runs default to panelized mode. The 6 m × 3 m interchangeable
panel policy is retained, including tall-wall review warnings.

Jambs, lintel-bearing jacks, sills, and upper/lower cripples use one rule set.
Framing avoids rotated opening voids, validates jamb/sill/plate clearance, and
records exterior/bearing intent. Frame plies now form parallel wall layers rather
than widening into opening clearances. Plate/nog/sill and lintel materials have
separate controls; stud sections determine real depth. Physical member IDs and
panel/joint/opening metadata are persisted by forward schema 4 migration. Active
wall metadata is derived from the read snapshot, including imported/manual walls.

The mixed long-wall CSV and repaired custom-truss files now work. Added mm,
metres, and feet/inches examples exercise centre offsets, zero heel/overhang,
quoting and negative origins. Feet/inches conversion now applies a leading minus
to the whole measurement and rejects non-finite converted dimensions.

Verification: **109 backend tests** (including **15 wall/unit cases**), production
build, and the full isolated browser flow passed. Panel connections, bracing, load-bearing sizing,
and fabrication certification are explicitly unchecked. Continuous truss-chord
cutting identity and full board/stock estimate reconciliation remain under T1/E1.

Next: E1 physical quantities, missing-price display and provenance; S2 assembly
editing; D1 reusable home definitions and T2 support-aware automatic roofs.

## Truss and inspection implementation — v2.4.0 (2026-10-09)

Manual/CSV trusses use canonical connected graphs. Web attachments split chords;
heel/bearing/overhang points align, king posts are vertical, scissor chords differ,
and attic templates retain a room void. Girder plies preserve chord/web roles.
Repeated trusses now have separate physical IDs plus layout identity. Custom inputs
require webs, connected non-collinear closed geometry, distinct nodes and explicit
crossing connections. Geometry retains full precision until display/export rounding.
Manual source definitions include the canonical graph; schema 3 adds role/node/
instance metadata without replacing existing members.

The viewport now has a home/revision/preview bar, cancel-preview action, searchable
model browser, selection inspector, isolation, and fit/plan/front/side views.
Layer choices persist across rebuilds, retained selections respect level/source,
and manual drafts are scoped to the home. Custom text supports CSV headers and
quotes, retains unfinished drafts, and shows parse errors without uncaught failures.

Verification: **94 backend tests** and TypeScript/Vite build passed. Isolated Chromium checks passed for imports/mobile/storage, homes/prices,
model inspection/views/isolation, and custom-truss headers/instances/error recovery. Remote CI has not been run here. No structural certification
was performed: every member still records engineering status **unchecked**.

Next: W1 logical-wall panels/shared framing and long CSV examples, then reusable
home definitions and support-aware automatic roofs. Continue the remaining S2/V2,
E1/R1 and U1/U2 gates in the plan's resume tracker.

## Project implementation — v2.3.0 (2026-10-09)

Homes now have independent SQLite files, names, stable IDs, geometry modes, and
monotonic revisions. GET endpoints read saved geometry; POST updates settings.
Custom homes retain imported/manual members when exposure or roof controls change.
CSV creation now creates another home; replacement clears stale sample metadata.

Named-project writes check `If-Match` atomically. Signed previews bind input and
revision; commit idempotency keys prevent duplicate retries. Source definitions
are persisted, manual assemblies have PUT update endpoints, and the last 20 prior
revisions can be restored through Settings. Default-project compatibility for
optional write headers is documented in README. Schema 2 upgrades retain existing
members and create a pre-upgrade SQLite snapshot.

Pricing now persists with the home and updates model, BOM, exports, and previews.
Unsupported sizes are unpriced; derived estimates have lower confidence and
summaries report unpriced-member coverage. Literal user text is escaped in
selection, warnings, manual results and pricing links; optional browser storage
cannot throw during startup. Manual writes now expose errors and pending states.

Verification: **73 backend tests**, TypeScript/Vite build, and extended isolated
Chromium project/pricing/model-inspection flows passed. Remote CI has not been executed here.

Remaining: long logical-wall panels/shared framing; truss topology and complete
webs/templates; general home definitions and automatic roof framing; complete
physical-board/stock estimates; assembly editing UI, coordinated view state,
preview cancellation, model tree/inspector and camera views; qualified rule review.
See the current resume tracker in `improvement_plan.md`.

## Stability implementation — v2.2.0 (2026-10-09)

Implemented the first persistence/validation milestone from
[`improvement_plan.md`](improvement_plan.md). All existing roof/truss/material
options and the TypeScript/Vite/Three.js/FastAPI/SQLite stack remain available.

- **S1 completed:** idempotent schema bootstrap, forward schema version 1
  migration, automatic pre-upgrade SQLite snapshots, transactional regeneration,
  preserved addition IDs/batches, configurable database path, non-mutating health,
  and validated offline snapshot/restore commands. Corrupt metadata and newer
  schemas are reported instead of replaced.
- **V1 in progress:** CSV validation and generation share domain-input mappings;
  errors include row/field context; blank offsets and explicit zero values are
  handled consistently; empty replacements, invalid treatments/sections,
  overlapping/conflicting openings, fractional counts, and resource-limit
  violations are rejected. Edited-row review and fresh-preview gating are in the
  import UI, with pending actions disabled.
- **W1/T1 partial corrections:** manual nogs avoid opening voids even on rotated
  walls; custom trusses reject duplicate node IDs and zero-length members. Complete
  panelization/shared framing and connected web topology remain to implement.
- **E1/U2 partial corrections:** fractional stock cuts round upward; mobile pinning
  preserves viewport width; the renderer observes container resize; rail buttons
  no longer overlap panel controls and only the active tooltip is shown.
- **M1 in progress:** a pinned backend environment, declared Pydantic dependency,
  shared release version, repository browser checks, and CI workflow were added.

Verification: **57 backend tests**, including late-insert and migration failure
injection and WAL-aware recovery, plus the TypeScript/Vite production build and
isolated Chromium import/mobile checks. The CI workflow is configured; it has not
been executed by a remote CI runner in this workspace.

Outstanding first: **S2 project identity/revisions**, non-mutating model reads,
source-definition persistence/idempotency, then long-wall panelization and full
truss/web topology. The bundled long-wall CSV now receives descriptive validation
errors rather than a 500; its complete panelized workflow is still pending.
Server-side binding of previews to project revisions remains pending with S2.

The original feature reports below are historical verification, not claims that
all current improvement-plan gates are complete.

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

# Imports and Manual Framing - v2.0 (2026-06-11)

## Added vertical slices

- Hover-expand, keyboard-accessible left sidebar with persisted pin state.
- Grouped BOM table, pricing provenance and session price overrides.
- Structured mixed-row CSV validation, editable review, temporary preview and
  append/replace commit modes.
- Manual wall-frame and truss generators with preview-before-commit,
  localStorage drafts, repeated/custom trusses, pricing and warnings.
- Element source/source-id/editability/confidence metadata and import batches.
- Project reset and regeneration with manual/import preservation options.

## Persistence and compatibility

The generated sample remains the default `/api/model` behavior. SQLite now
stores source-tracked additions beside generated members. Parameter
regeneration preserves committed manual/imported members by default, while
project reset restores only the sample geometry. Existing `/api/model` and
`/api/bom.csv` endpoints remain available.

## Verification

- Backend smoke suite: CSV validity and required fields, opening bounds,
  manual wall preview/commit, truss chord/web generation, source tracking,
  BOM JSON, and legacy model/BOM behavior.
- Frontend TypeScript and Vite production build.

## Engineering disclaimer

The app remains an education, early-design and estimating tool.
Imported/manual geometry must be checked by a qualified designer or
engineer, and NZS 3604 or specific engineering design governs construction
decisions.

# Frame selection, treatments and envelope - v2.1 (2026-07-04)

## Changes

- Removed the Dashboard section and the experimental ML/vision plan
  reader; "Regenerate model" now lives in Settings and the Imports
  section is CSV-only.
- One click on a 3D member now selects its whole wall-frame segment or
  truss (group tinted, clicked member white) and shows aggregate
  metadata: stud spacing, timber sizes, openings, plies, treatment,
  member count, lineal metres and estimated cost.
- NZS 3640 treatments (H1.2, H3.1, H3.2, H4, H5) are selectable per
  manual wall/truss input and as a building-level `wall_treatment`
  override validated server-side.
- Wall frames are limited to a 6 m x 3 m envelope (orientation
  interchangeable): manual inputs are rejected beyond it, auto-generated
  segments over 6 m carry a "verify panel joins" warning.
- Added GL8/GL10/GL12 glulam grade catalogue entries (area-scaled,
  low-confidence estimating prices).
- Sidebar rail labels render as solid tooltip chips on rail hover only,
  so they no longer wash out over panel content; API validation errors
  now surface their descriptive message in the UI.

## Verification

- Backend smoke suite (20 tests): treatments override, envelope
  accept/reject, materials completeness, ML routes removed.
- Frontend TypeScript build plus headless-browser end-to-end pass:
  wall/truss group selection, empty-click clearing, colour-mode switch
  with active selection, manual-wall envelope rejection message,
  treatment dropdowns, URL `wall_treatment` round-trip, regenerate from
  Settings.
