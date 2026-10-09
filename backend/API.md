# API and identity conventions

The application serves its API and built workspace from one origin. Generated
OpenAPI is available at `/openapi.json` and interactive documentation at `/docs`.
Pydantic input models in `manual_inputs.py`, `home_definition.py`,
`home_archive.py` and `imports/schemas.py` define the validation schemas.
Frontend model/result interfaces are maintained in `frontend/src/types.ts`.
They are not generated from OpenAPI; contract/fixture checks and that distinction
must remain part of release review. Response dictionaries include geometry,
review and estimating metadata beyond the input schemas shown by OpenAPI.

## Project and revision scope

| Convention | Behavior |
|---|---|
| `project_id` query | `default` selects the legacy database; other IDs are 32 lowercase hex characters, each with its own SQLite file. Identity is project scope, not user authorization. |
| `revision` query | On revision-aware reads/exports, a different saved revision returns 409. It is an optimistic read check, not a historical-read selector. Restore a retained revision explicitly to open it. |
| `If-Match` header | Named-project writes require the displayed integer revision (428 if missing); a stale revision returns 409. |
| `Idempotency-Key` header | Persisted mutation receipts return the previous operation safely on matching replay; reuse for a different operation/input returns 409. Keep the same key when retrying a lost response. |
| `X-Preview-Token` header | Named manual/CSV/home/archive commits require the matching server-issued preview proof. It binds normalized input, home and revision and expires after 30 minutes. Changed input/home/revision needs a fresh preview. |
| `X-Project-ID` response | Validated scope of the handled request; creating a new home returns its new identity inside model metadata. |
| `X-Request-ID` response | Server-generated 32-hex reference, including handled validation/conflict/internal failures. Correlate it with diagnostic events. Caller-supplied IDs are not trusted/reused. |

The default-project compatibility path still permits legacy writes without
If-Match/preview headers. Browser writes and named projects use the strict path.
Removing that compatibility is a separate owner decision. Mutation transactions
preserve the previous model, metadata, source definitions and revision on failure.
The most recent 20 prior revisions support bounded Undo; external SQLite-aware
backups remain separate. Preview geometry is temporary and cannot be addressed as
a saved BOM anchor. Retry transport/server failure with the unchanged input/proof/
key; resolve a 409 and preview again rather than retrying a stale write blindly.

## Units and physical identity

All API geometry lengths/coordinates are millimetres unless a field explicitly
says metres, radians or degrees. Database plan axes are `cx` east, `cy` north,
`cz` elevation up. Manual/CSV `start_z_mm` is the north plan coordinate.
Three.js displays east X, elevation Y and south Z. Manual truss origin is its
centre-span origin, not the first bearing; automatic roof adapters translate
between those conventions. Coordinates may be negative; finite lengths, sizes,
counts, section syntax, openings and enum/range rules are validated separately.
Derived lengths, combined sections and repeated truss placement must also remain
finite. Truss endpoints that collapse at the submitted coordinate precision are
rejected before generation. These checks do not impose an arbitrary coordinate
range; negative and translated designs retain their existing contracts. Floor
polygon area and rotated scan geometry are calculated relative to a local origin
to reduce cancellation. This does not establish GPU precision for extreme world
coordinates.
CSV uploads accept mm, metres and supported feet/inches syntax, normalized to mm.
An empty optional opening head derives from sill plus clear height; explicit zero
is distinct from missing input. JSON cannot encode NaN/Infinity as valid dimensions.
If a client nevertheless submits those non-standard JSON extensions, manual/home
schema errors retain their field locations and return JSON-safe HTTP 422 details.
CSV review rejects non-finite numbers in both known and extra nested cells while
retaining their reviewable text.

`id` is the saved placed-geometry row ID. Connected chord graph segments can have
separate row IDs but one `physical_member_id` and `cut_length_mm`. Cutting identity
is scoped by `(source, source_id, storey, physical_member_id)`; empty legacy IDs
fall back to individual rows and expose unknown truss cut identity. Wall selection
uses logical `segment_id` plus source/batch/level, with `panel_id`, `joint_id` and
`opening_id` for fabrication/void metadata. Truss selection uses `truss_id` in the
same namespace, with `layout_id`/`instance_id` for repetition and node/role fields
for its graph. Equal labels or unscoped IDs do not establish identity.

## Endpoint atlas

| Group | Read / preview / validate | Explicit writes |
|---|---|---|
| Health / projects | `GET /api/health`, `/api/projects`, `/api/model`, `/api/project/revisions`, `/api/project/definitions` | `POST /api/projects`, `/api/project/initialize`, `/api/model`, `/api/project/regenerate`, `/api/project/reset`, `/api/project/revisions/{revision}/restore` |
| Reusable home | `GET /api/project/home`, `/api/project/home/examples`, `/api/project/archive`; `POST /api/project/home/preview`, `/api/project/archive/preview` | `PUT /api/project/home/commit`; `POST /api/project/archive/commit` |
| CSV | `POST /api/import/csv-plan/validate`, `/review`, `/preview`; `GET /api/import/batches` | `POST /api/import/csv-plan/commit`; saved-batch editing and delete routes are listed in OpenAPI |
| Manual wall/truss | `POST /api/manual/wall-frame/preview`, `/api/manual/truss/preview` | Corresponding `POST .../commit` and saved-assembly `PUT` routes |
| Estimates / review | `GET /api/bom.json`, `/api/bom.csv`, `/api/cost-summary`, `/api/pricing`, `/api/warnings` | `POST /api/pricing/overrides` |

Read paths do not silently initialize, migrate, regenerate or apply query settings.
A missing project/model returns 404; corrupt/incompatible/not-ready state returns
503. Health can return `status=uninitialized, ready=true` for a reachable service
without a saved model. Call Initialize explicitly. Use OpenAPI for exact request
shapes and route parameters; the table groups workflows rather than freezing
an independently maintained full schema.

CSV validation/review returns HTTP 200 with `errors`, `warnings`, normalized rows
and `can_preview=false` for a reviewable invalid file. HTTP status alone does not
mean the rows are ready. Malformed/unsupported uploads can return 400/413/422;
preview/commit reject invalid rows with 422. Edits invalidate preview readiness.
Request bodies are bounded to 16 MiB, CSV files to 8 MiB and rows to 10,000.
The body guard checks streamed chunks before appending an oversized chunk; the
CSV reader materializes at most the row limit plus one look-ahead row. Exact byte
limits pass their respective guards; one extra byte returns 413. CSV parsing
failures include row and field locations (`file` or `rows`).
The existing 100,000-member budget applies to generated inputs/layouts, combined
CSV inputs and a generated home. Split runs and porch layouts preflight before
member-list allocation. These are operation budgets, not a global cap on a saved
project accumulated through multiple appends or assurances that every device
will render the maximum comfortably. Complete aggregate/API/custom-topology
resource acceptance remains in V1/M1. No new feature/range restriction is approved.

BOM JSON accepts optional `member_id` (positive SQLite integer range) and returns
complete saved-assembly rows, `scope`, actual `project_revision` and exact
`member_ids` for row location. No anchor means the whole home. Concrete anchors
return 422 and missing members 404. Physical cuts are aggregated before stock,
ply multipliers, pricing and rounding. Unpriced costs are null; zero-valued quotes
are priced. CSV remains the whole-home export with its existing columns, including
when the UI filters/scope a subset. Explicit revision checks prevent stale exports.

Structured review states and source assumptions describe evaluation, unchecked
capacity, geometry and scope. Geometry validity or an API 200 does not grant
structural approval; see `RULES.md` and the plan's qualified-review gates.

## Failure diagnostics

`diagnostics.py` logs JSON messages through `uvicorn.error.timberbim`. Fields include
request reference, route pattern, request/observed project IDs, expected/observed
revision, status, elapsed milliseconds and failure class. Invalid CSV review
results also emit `validation_failed` with counts, even with HTTP 200. Internal
failures include at most eight file/function/line frames, without exception text,
source lines or locals. Unexpected failures return generic JSON 500 and a reference;
handled domain/conflict messages keep their user-facing feedback. A failed logging
sink does not turn a handled response into a second error.

The diagnostics do not log bodies, filenames, labels, credentials, preview tokens,
idempotency keys, raw query/header values, client addresses or complete URL text.
Dynamic route identifiers are replaced by route patterns. Uvicorn may prefix the
JSON message with its normal level formatter. Defaults log failures/validation
rejection only; `TIMBERBIM_LOG_REQUESTS=1` also logs completed requests at INFO.
Use `uvicorn ... --log-level info` for that optional stream. Backend tests capture
the JSON messages independently and check concurrent isolation/redaction.

For a failed import, keep the field/row error shown in the workspace, read its
request reference (or Network response `X-Request-ID`), and locate that event in
server output. Check route, expected/actual revision and failure class. Reproduce
with a disposable fixture/database; do not append the user's plan to logs.
