# Changelog

All notable releases of **TimberBIM Lite** are documented here. See [REPORT.md](REPORT.md) for detailed implementation notes, file lists, and verification records.

## [2.18.0] — 2026-11-18

### Changed
- **Edge-outline selection highlighting:** Selecting a member, assembly, or BOM row now renders 3D edge outlines (`THREE.LineSegments` in white `#ffffff` for the primary member and warm yellow `#ffe08a` for the rest of the assembly, clipping-plane aware) instead of overwriting instance colours, preserving Function / Material / Realistic colours.
- **BOM row-click navigation:** Clicking anywhere on a BOM table row (as well as **Locate in model**) isolates its saved member IDs, switches the viewer to **Material** colour mode, frames the geometry, and focuses the 3D canvas.
- **Material & treatment colour mapping:** Case-insensitive material and grade lookup with `Other / custom material` fallback, plus `H3.1–H5` NZS 3640 treatment green shifts in **Material** mode.
- **Unified default-model reset:** Renamed and unified **Reset to default BIM model** across the 3D workspace toolbar, **Building Specs**, and **Settings / Warnings**. Resetting restores the default 1-storey SG8 gable configuration, clears pricing overrides and import provenance, restores `"Sample home"` on the `default` project, resets local view filters/camera/edit URL state, and records an undoable `"reset to default"` revision.
- **Publishing documentation:** Coordinated release metadata at `2.18.0`, added `CHANGELOG.md`, and aligned `README.md`, `REPORT.md`, `improvement_plan.md`, `backend/FRAMING.md`, `backend/API.md`, and `benchmarks/README.md` with the current workspace.

## [2.17.0] — 2026-10-09

### Added & Fixed
- Derived finite-geometry, section, and repeated-truss placement validation prior to generation; JSON-safe HTTP 422 row/field error locations for non-finite values.
- Bounded CSV row reading, streamed 16 MiB body guard, split/porch preflight checks, and spacing progress guards.
- Local-origin floor polygon and rotated scanline calculations preserving geometry under large translations.
- [backend/FRAMING.md](backend/FRAMING.md) implementation handover for wall framing, named/custom truss formulas, physical cuts, bearings, and legacy layouts.

## [2.16.0] — 2026-10-09

### Changed
- Computed highest timber level once per `review.evaluate` pass instead of repeating whole-model scans per stud, reducing three-storey read latency while preserving exact responses and database bytes.
- Added seven-page desktop/mobile Chromium accessibility and visual assessment ([benchmarks/ui-assessment.md](benchmarks/ui-assessment.md)), accessible table names/headers, and non-overlapping rail label tooltips.

## [2.15.0] — 2026-10-09

### Changed
- Switched the Three.js viewer to render on scene/camera changes and pause when settled (while keeping OrbitControls damping and enabled auto-rotation active), recording zero settled idle renderer submissions across bundled fixtures.

## [2.14.0] — 2026-10-09

### Added
- Server-generated `X-Request-ID` references and redacted JSON diagnostics ([backend/API.md](backend/API.md)).
- Backend (`backend/benchmark.py`) and browser (`npm run profile`) measurement tools, `InstancedMesh.dispose()` cleanup, and clean-source verification (`scripts/verify_clean.py`).

## [2.13.0] — 2026-10-09

### Added
- Hierarchical **Model browser** (`Level → source batch → Walls / truss layout → assembly → panels / physical members`) with lazy loading and search.
- Source-scoped **BOM for assembly**, exact row **Locate in model**, and keyboard camera controls (`arrows`, `Shift + arrows`, `+`/`-`, `Home`).

## [2.12.0] — 2026-10-09

### Added
- Guided **Manual Wall** and **Manual Truss** form sections (`Placement`, `Geometry`, `Materials`, `Openings / Webs`, `Review`), inline native/server field errors, and local draft schema 2 preserving raw opening blanks.

## [2.11.0] — 2026-10-09

### Added & Fixed
- Per-home persistent view preferences (`workspaceState.ts`), orthographic Plan/Front/Side views, visible extents dimensions, and axis section clipping.
- Fixed automatic truss bearing center-span alignment in reusable-home roof zones and added rule profile 2 bearing-alignment diagnostics.

## [2.10.0] — 2026-10-09

### Added
- Auditable applicability reporting in `backend/review.py` and [backend/RULES.md](backend/RULES.md) with four explicit states (`reference_only`, `evaluated_within_assumptions`, `requires_specific_design`, `not_evaluated`) and per-revision snapshots.

## [2.9.0] — 2026-10-09

### Added
- Reusable versioned `HomeDefinition` schema, automatic gable truss roof zones, sample fixtures (`examples/homes/`), and portable home archive export/import.

## [2.8.0] — 2026-10-09

### Added
- In-place editing and replacement previews for saved CSV batches and manual wall/truss assemblies, plus idempotent home-creation retries.

## [2.7.0] — 2026-10-09

### Added
- Versioned local form drafts with recovery download/discard, coordinated request exclusivity, and abortable preview cancellation.

## [2.6.0] — 2026-10-09

### Added
- Physical cutting identities (`physical_member_id`, `cut_length_mm`) across connected truss chords, independent section/assembly ply board counts, historical FX/pricing provenance, unpriced-coverage reporting, wide BOM/Pricing dialogs, and SQLite schema 5.

## [2.5.0] — 2026-10-09

### Added
- Shared wall framing engine (`backend/walls.py`) for sample, manual, and CSV walls with fabrication panels, paired joint studs, parallel plies, and unit examples (`mm`, `metres`, `feet_inches`).

## [2.4.0] — 2026-10-09

### Added
- Canonical connected truss graphs (`backend/trusses.py`) with split chords, vertical king posts, differentiated scissor/attic/girder/mono templates, repeated instance IDs, and the viewport Model browser / Selection inspector.

## [2.3.0] — 2026-10-09

### Added
- Independent per-home SQLite project databases, non-mutating reads, `If-Match` optimistic revision checks, signed preview tokens, `Idempotency-Key` support, 20-revision bounded undo, and persisted pricing overrides.

## [2.2.0] — 2026-10-09

### Added
- Transactional database rebuilds, forward schema migrations with automatic backups (`backend/manage_db.py`), shared CSV/domain validation, CI workflow (`.github/workflows/verify.yml`), and pinned environment locks.

## [2.0.0] – [2.1.0] — 2026-06-11 – 2026-07-04

### Added
- Collapsible/pinnable sidebar, grouped BOM & pricing overrides, structured CSV import, manual wall/truss inputs, whole-assembly selection, selectable NZS 3640 treatments (`H1.2`–`H5`), 6 m × 3 m wall-frame envelope, and GL8/GL10/GL12 glulam catalogue entries.

## [1.0.0] – [1.2.0] — 2026-06-10 – 2026-06-11

### Added
- Initial Three.js 3D framing viewer, NZS 3604:2011 conceptual rules engine, SQL-backed timber BOM CSV export, auto-rotate, hip roofs, wind/snow zone spacing, customizable gable studs, scoped wall-stud material/spacing/ply overrides, and USD retail cost estimating.
