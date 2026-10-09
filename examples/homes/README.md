# Reusable home fixtures and portable files

Open **Imports / Drawing Plans → Reusable homes** and select Rectangle, L-shaped,
or Two levels. Preview, inspect the webs/bearings, then save after the replacement
summary. Use an empty custom home to keep the existing sample separate. Download
the saved home, create another empty home, and open/preview/import that file to
reproduce it. Settings / Warnings provides revision restore.

| Fixture | Geometry and purpose |
|---|---|
| [rectangle.json](rectangle.json) | 9 m × 6 m, one level, doorway, common trusses with a ridge along X. |
| [l_shape.json](l_shape.json) | L-shaped footprint, two adjacent zones, both ridge orientations, explicit internal bearing wall. Zone connections still require design. |
| [two_level.json](two_level.json) | Smaller offset upper footprint, upper elevation 4,100 mm, different wall heights, finite lower support segment, upper truss roof. |

These are conceptual modelling fixtures, not construction designs. Web connectivity,
member identity, placement, input persistence and estimating are tested; member
capacity, reactions, bracing, connectors, roof junctions and floor transfers are
unchecked. The tall two-level separation is deliberately different from the sample
to test explicit elevations; it needs a designed floor/connection arrangement.

Definitions use `schema_version: 1`, `units: "mm"` and the conceptual
`NZS3604:2011-conceptual` profile. Plan X is east, plan Z (`start_z_mm`) is north;
backend `cz` is elevation. The viewer converts elevation to scene Y and north to
negative scene Z. Convert other source units before JSON import; CSV supports mm,
metres and feet/inches and persists normalized mm.

Levels have stable IDs, numbers and explicit elevations/default wall heights.
Wall entities reference a level ID and reuse the manual wall contract. A wall's
explicit height wins; an omitted height inherits its level. Opening IDs are
preserved; omitted IDs receive deterministic IDs on normalization. Keep saved
entity/opening IDs when editing or reordering. `inherit_design_settings: true`
applies Building Specs material/spacing/ply/treatment overrides. Set it to false
to retain the wall's explicit choices. Other wall fields remain in the definition.

Floors define a simple boundary, disjoint interior holes, joist direction,
spacing/elevation offset, and finite support segments. Scanlines handle sloped
edges and rotated directions. Openings omit joists through the void; headers,
opening trim, rim framing and support capacity require separate design.

Roof zones use rectangular extents with an X/Y ridge axis. Roof shape and framing
system are separate. Gable truss layouts reuse the manual connected graph and
place an explicit first/last truss; the final gap can be shorter than spacing.
Bearings must lie on the referenced walls at a common elevation. Missing or
non-bearing references generate review messages. Every physical instance and cut
has separate identity. Ceiling joists are clipped from truss zones to avoid
duplicating their bottom chords. Rafter gable/hip roofs remain available with
explicit pitch, heel and overhang; first/last offsets describe truss placement.
Specialized templates remain conceptual. Automatic hip transitions require a
reviewed layout; the existing hip rafter and manual truss workflows remain.
Overlapping roof zones disclose unresolved valley/trim/load transfer.

Since **2.11.0**, the automatic adapter places the manual template's center at the
midpoint between those bearings. Earlier saved layouts can be displaced by half
their span. Profile 2 checks actual BL/BR nodes against wall runs and wall-top
geometry; inspect the warning and explicitly regenerate a backed-up home to
correct its layout. The previous revision remains available. The diagnostic
checks geometry; bearing capacity and connections still require supplier review.

`archive_schema_version: 1` files include the home definition, normalized settings,
USD quote overrides and original quote date, assembly definitions, original project
identity/revision, generation version and catalogue snapshot. Known assemblies
regenerate from definitions. Legacy members without definitions are preserved
explicitly and flagged for review/recreation. Import retains the destination home
ID, creates a new local revision, replaces geometry/pricing atomically, and allows
undo. Historical revision history and browser drafts belong to the original
database/browser and are not in the portable file; use the SQLite backup tool for
complete database recovery.

Estimates use the installed catalogue plus imported overrides. Catalogue drift is
reported; an archive identifies historical price inputs but does not freeze the
pricing engine across future catalogue/rule versions. This remains an E1/M1
reproducibility gate. No imported quote is relabelled with a fresh supplier date.

API: scoped `GET /api/project/home`, `GET /api/project/home/examples`,
`POST /api/project/home/preview`, `PUT /api/project/home/commit?preserve_additions=true`,
`GET /api/project/archive`, and archive `/preview` and `/commit` POST commands.
Named-home writes require `If-Match`; commits require the matching preview token
and should retain their idempotency key for retries. JSON input is bounded by the
16 MiB API limit and the aggregate member budget. Unsupported versions, unknown
definition fields, invalid references/polygons and out-of-bounds bearings return
actionable validation errors without altering saved work.

Verify from `backend/` with `python -m pytest test_home_definition.py -q`.
See [improvement_plan.md](../../improvement_plan.md) section 9 for the next ticket
and [README.md](../../README.md) for isolated test/backup commands.
