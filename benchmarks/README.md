# Local measurement and reproduction records

These tools use bundled public design fixtures, temporary SQLite databases and
fresh browser profiles. They never open the working project's database or drafts.
The records describe this source snapshot and reference environment; they are
not hardware-independent performance budgets or structural design approval.

Run backend measurements from an activated environment at the repository root:

```bash
python backend/benchmark.py --repeats 3 --output benchmarks/backend-reference.json
```

For function-level read diagnostics, add an extra cProfile read per fixture:

```bash
python backend/benchmark.py --repeats 3 --profile-reads --output benchmarks/backend-read-reference.json
```

This profiling pass is outside ordinary timing/allocation samples and records
call counts, function/relative-file locations and own/cumulative seconds. cProfile
adds overhead, so use unprofiled medians for comparisons. The saved
[backend-read-reference.json](backend-read-reference.json) is a current v2.17
capture; rerunning needs only the locked backend environment and bundled fixtures.

The v2.16 change computes the highest timber level once in `review.evaluate`.
Previously each eligible stud repeated a whole-model scan. The retained
[review-read-comparison.json](review-read-comparison.json) alternates old/new
evaluators and full model reads five times on each identical temporary database.
It records exact response equality and preserved database bytes for every fixture,
evaluator hashes and before/after cProfile. Three-storey median review time changes
from about 230 ms to 10 ms, and complete read from 462 ms to 194 ms. Small fixtures
show little change/noise. This is a historical paired capture, not a promised
uniform speedup or a frozen old release. The current benchmark command can locate
the next hot path; estimating SQL and member decoding dominate the remaining
three-storey read, while its compact payload remains about 5.83 MiB.

The five fixtures are Rectangle, L-shaped, offset two-level, the three-storey
sample, and Rectangle plus a 260-instance manual truss layout. Generation runs
without persistence. The fresh-database pipeline includes generation, input/
physical-cut checks, database bootstrap/inserts, estimating and review snapshots.
The model-read timing includes live review and estimating; serialization is a
separate compact JSON pass. Allocation peaks come from an additional traced
Python generation pass, outside the timing samples. RSS is cumulative process
peak, includes native allocations and is unavailable on some operating systems.

For end-to-end loopback and desktop/mobile browser measurements:

```bash
cd frontend
npm run build
npm run profile -- --repeats 3 --output ../benchmarks/local-reference.json
```

`TIMBERBIM_TEST_PYTHON` can select a Python executable outside PATH, and
`TIMBERBIM_TEST_BROWSER` can select an existing Chromium executable. Otherwise
use an activated backend environment and install Chromium with
`npx playwright install chromium`. The profiler creates portable inputs with the
backend tool, imports each into an independent temporary home and confirms its
member count. It samples 1440 × 1000 and 390 × 844 layouts, JSON transfer/parse,
rendered rebuilds, selection, actual raycasts, idle renderer submissions, enabled
auto-rotation frame intervals, renderer counters
and Chromium heap after collection. Twenty evenly distributed timber members
are selected/raycast; a target centre may hit a nearer member. Pick timing includes
selection, inspector, dimension and view-state work, not just ray intersection.

`?diagnostics=1` enables the optional `window.timberbimDiagnostics` console bridge
used by the profiler. It has snapshot/reset/rebuild/select/rayPick/rotate methods and
bounded timing rings. It performs no server writes, but changes local inspection/
view state, so use a disposable browser profile. The ordinary workspace has no
profiling bridge and retains its existing controls. The viewer coalesces changed
scene/camera work into animation frames, continues while auto-rotating or damping,
and pauses once settled. The profiler waits for settling, asserts zero renderer
submissions over two idle seconds, then enables rotation for a separate two-second
active sample. No idle FPS is reported. Frame intervals describe the active
rotation sample; renderer submission time is CPU/driver time and excludes
an independently measured GPU timer. Counters track explicit buffer create/delete
calls after instrumentation, not GPU bytes or garbage-collector reclamation.

The first capture, [before-instance-disposal.json](before-instance-disposal.json),
showed 16–36 extra explicitly unbalanced instance buffers after a rendered
replacement (constant model geometry counts). Its three rebuilds ran together,
so only the final replacement uploaded GPU data. The final profiler renders each
replacement separately and asserts that its buffer balance returns to baseline.
`Viewer.buildModel` now calls `InstancedMesh.dispose()` as well as geometry and
material disposal. [local-reference.json](local-reference.json) records the final
protocol with before/after counters for each fixture/viewport. The new on-change
viewer defers its first frame until after instrumentation is installed, so its
absolute buffer baseline also includes six initial ground/grid buffers previously
uploaded before instrumentation. Compare each run’s before/after balance, rather
than treating that changed capture boundary as another leak.

[before-demand-rendering.json](before-demand-rendering.json) preserves the v2.14
continuous-render capture: 13–95 idle renderer submissions per two-second fixture/
viewport window on this host. The updated capture uses benchmark schema 2 and
adds settled idle counts and a separate auto-rotation sample. Do not compare its
active rotation intervals directly with the old static idle intervals or claim
an interaction FPS gain from removing idle work. The visual settings, supported
model ranges and rendering framework are unchanged.

[before-review-read-optimization.json](before-review-read-optimization.json)
preserves the v2.15 settled-rendering capture before the review scan change.
Compare it with the updated [local-reference.json](local-reference.json) using
the fixture/model counts, adapter, source fingerprint and protocol. The paired
same-database record above is stronger evidence for this specific read change
than comparing separate end-to-end timing runs.

[before-numerical-contracts.json](before-numerical-contracts.json) and
[before-numerical-backend-read.json](before-numerical-backend-read.json) retain the
v2.16 captures before the derived numerical/preflight contracts. The v2.17
reference preserves all five fixture member counts and the same rendering
protocol. Timing changes between these independent runs are observations, not
a paired claim of faster/slower reads. Current source fingerprints identify the
measured runtime; the v2.16 UI screenshot artifact retains its original version,
while fresh v2.17 full Chromium verification reran all seven-page checks.

Reference host: Python 3.12.3, Node 24.16.0, headless Chromium 151.0.7922.34,
WSL2 Linux, eight available CPU cores, ANGLE/SwiftShader software rendering.
This is useful for repeatable regression comparisons, not a physical phone/GPU
measurement. Three timing repetitions provide coarse p95 values. Payload sizes
include the existing per-member metadata/review structures. Loopback transfer
includes backend work and body receipt, not public-network latency. Compare source
fingerprints, model counts, adapter, viewport and protocol before comparing runs.
Choose actual reference devices and budgets before reducing visual quality or
restricting model sizes; owner decisions C1–C6 remain pending.

The v2.17 reference records **zero settled idle submissions in all ten cases**;
auto-rotation and rendered-rebuild buffer checks passed separately. Backend
measurements identify the larger saved-model reads/payloads as the next profiling
priority; trace `db.model_json`, `review.evaluate` and per-member serialization
before selecting an optimization. These values are local observations, not gates.

| Fixture | Members | Model read / review / estimate median (ms) | Compact model (MiB) |
|---|---:|---:|---:|
| `rectangle` | 271 | 16.3 | 0.44 |
| `l_shape` | 459 | 27.5 | 0.73 |
| `two_level` | 387 | 22.8 | 0.59 |
| `sample_3_storeys` | 3,687 | 229.6 | 5.83 |
| `rectangle_260_trusses` | 3,651 | 208.2 | 6.25 |


For a clean source and dependency installation, from the repository root:

```bash
python scripts/verify_clean.py --output benchmarks/clean-source-reference.json
```

This copies application sources/examples/docs into a temporary directory,
excluding SQLite data/backups, local environment files, credentials, installed
dependencies/builds and external symlinks. It creates a fresh Python environment,
installs the locked Python/npm dependencies, builds and runs backend/contracts/
full Chromium checks, including saved non-sample homes and portable archives.
It installs Chromium unless `--browser /path/to/chromium` is supplied. The local
OS still needs Chromium's system libraries; CI installs them with Playwright's
`--with-deps`. No existing `.venv`, `node_modules`, `dist`, user database or draft
is copied. The command records every step and writes a failure report if stopped.

Optional cache overrides:

```bash
python scripts/verify_clean.py --output benchmarks/clean-source-reference.json \
  --uv-cache /path/to/uv-cache --npm-cache /path/to/npm-cache \
  --browser /path/to/chromium --offline
```

Offline mode requires complete caches for the locked packages; it cannot create
missing tarballs. `uv` is needed only with `--uv-cache`. The normal command uses
pip/npm and downloads dependencies, requiring no session-specific files. The
source-copy report proves reproduction of the current worktree, not a committed
clean checkout or a remote CI result. Retain that distinction until an owner
commits the work and CI runs against that revision.

For page accessibility/visual results and optional report/screenshot capture,
see [ui-assessment.md](ui-assessment.md). The full browser suite includes the
seven-page checks; focused flags are cleared by fresh-source verification.
