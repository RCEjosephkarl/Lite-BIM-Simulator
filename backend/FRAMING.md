# Wall and truss implementation handover

This describes the current v2.17 generators, their physical identities and the
unresolved fabrication/support work. Start in **Manual Wall Frame Input** for
panel/opening problems, **Manual Truss Input** for graph/section problems, and
**Imports / Drawing Plans** for an automatic reusable-home layout. Settings /
Warnings shows the recorded geometry/source assumptions. See [API.md](API.md)
for revisions/coordinates and [RULES.md](RULES.md) for qualified-review gates.

## Shared wall framing

`manual_inputs.ManualWallFrameInput` validates inputs before `walls.frame` creates
the members. CSV conversion uses `imports/contracts.py`; the sample adapter and
reusable home walls use this same wall generator. A logical wall retains one
`segment_id`; fabrication pieces additionally carry `panel_id`, `joint_id`,
`opening_id` and `physical_member_id`. Identity also includes source/batch/level.

| Behavior | Current geometry | Where to continue |
|---|---|---|
| Panel envelope | Up to 6,000 mm long when height is at most 3,000 mm; otherwise up to 3,000 mm long with height at most 6,000 mm. Manual unpanelized input must fit the interchangeable envelope. | `walls.panel_layout`, `test_walls.py`; the envelope is a geometric constraint, not a stud-capacity rule. |
| Panel joints | Greedy joints avoid each opening and its three-stud-breadth clearance zone. No suitable joint returns a validation error. Adjacent panels have separate end studs and a shared joint identity. | Reviewed plate laps, fixing, bracing, assembly and joint-detail exports remain open. |
| Plates | Bottom plate excludes zero-sill opening intervals; two top plates follow panel boundaries. | Confirm plate continuity/laps and construction details with the reviewer. |
| Openings | Full-height trimmers, shorter bearing jacks, lintels, raised-window sills and grid-based upper/lower cripples. Head derives from sill plus clear height unless explicitly supplied; conflicting heads, overlaps and insufficient jamb space are rejected. | Validate loads, bearing lengths, lintel selection and connections independently. |
| Nogs | Rows follow count or explicit vertical spacing. Nogs only connect studs that cover the row and avoid the opening/sill/lintel exclusion volume. | Bracing, fixing, services and unusual opening arrangements need reviewed details. |
| Parallel frame plies | Assembly plies extend through wall depth and retain the opening width. Intrinsic section plies, for example `2/140x45`, are distinct from assembly plies. | Keep geometry, board count and connection assumptions separate. |

The section text is depth × breadth. The stud section governs member depth;
`wall_thickness_mm` is declared intent and a mismatch emits a warning. Stud,
plate and lintel materials are independent inputs. The current member boxes and
BOM do not provide fixing schedules, bracing panels, connection capacity, saw
angles or a fabrication drawing. Exporting BOM CSV does not complete W1's detail
export requirement.

Wall offsets are distances from the submitted start along its plan direction.
Manual level elevation uses `(level - 1) × STOREY_RISE`; reusable home generation
repositions members to the explicit level elevation. Changes to either adapter
must preserve opening, physical-cut and source-scoped navigation tests.

## Truss templates and support intent

`trusses.canonical_graph` defines connected conceptual geometry. Local `x` runs
left-to-right in the truss plane and local `y` is elevation above the bearing
plane. For named templates, bearings `BL` and `BR` are at `(-span/2, 0)` and
`(+span/2, 0)`. The manual fields named `start_x_mm`/`start_z_mm` place the
**centre between these bearings**. They do not place the left bearing.

Let `H = span/2`, `R = H × tan(pitch)`, `h = heel_height_mm`, and
`o = overhang_mm`. The named-template differences are explicit generator
formulas rather than supplier designs:

| Template | Geometry and web intent | Unresolved support/design intent |
|---|---|---|
| Common | Symmetric apex at `(0, h + R)`; horizontal bottom chord through `(0, 0)`; vertical central king post, quarter-span diagonal webs and heel webs. | Member forces, bearing reactions, restraint and every connection. |
| Girder | Same graph and chord/web roles as common; **three assembly plies** on every member. | Concentrated supported loads, reactions, ply fixing and bearing capacity are not calculated. |
| Mono | Single top slope from `(-H, h)` to `(+H, h + 2R)`; horizontal bottom chord, middle web, heel webs and a diagonal web. | High-end support, uplift and connection/load path. |
| Scissor | Symmetric top; bottom midpoint at `(0, 0.45R)`; inclined bottom chords meet below the apex, with a vertical central post and quarter-span webs. | Horizontal reactions, deflection, ceiling arrangement and bearing/connection design. The 0.45 factor is conceptual. |
| Attic | Central bottom interval from `-0.18span` to `+0.18span`; upper room nodes at `0.4R`; queen posts and webs around that central void. | Occupancy, headroom, attic floor loads, chord sizing and connections. The proportions are conceptual. |
| Custom | Explicit submitted nodes and member rows; a row is an intended physical cut. Additional nodes on a cut split its connected geometry. | No explicit custom bearing-node/load schema exists; infer neither bearing capacity nor intended supports from its bounding box. |

Symmetric templates extend eave nodes to `±(H + o)` at elevation
`h - o × tan(pitch)`. Mono extends each end along its single roof slope.
With zero heel/overhang, coincident named nodes intentionally share an identity;
this is different from submitting duplicate custom node positions.

All templates retain top/bottom chord and web/post roles. Selecting Girder does
not relabel every member as a girder and does not change structural review to
approved. Changing material or section is geometric/estimating intent until
independently assessed.

## Connected geometry and physical cuts

`split_at_nodes` turns each intermediate node on a chord into a real endpoint.
Graph validation requires distinct positions, positive member length,
non-collinear connected geometry, top/bottom chords, webs/posts and a graph
cycle. Duplicate edges, unused/disconnected nodes and unsupported roles are
rejected. Crossing members require an explicit shared node.

`continuous_chords` joins collinear named-template chord chains with matching
section/material into an intended physical cut. It preserves the graph segments
used to attach webs. Custom rows bypass that joining step because their cut
intent is explicit. Each placed segment carries its graph endpoints,
`physical_member_id` and complete `cut_length_mm`.

The estimating code aggregates a physical cut once before multiplying intrinsic
section plies and assembly plies. Counting viewer boxes as boards overstates
split chords. A continuous cut also does not prescribe a splice, offcut reuse or
supplier stock availability. Those workflows remain in E1/W1/T1.

For a 6,000 mm span, 25° pitch, 100 mm heel, 450 mm overhang, one instance and
default single-ply sections, the current generator produces:

| Template | Nodes | Placed graph segments | Physical cuts | Assembly plies |
|---|---:|---:|---:|---:|
| Common | 10 | 13 | 8 | 1 |
| Girder | 10 | 13 | 8 | 3 |
| Mono | 8 | 10 | 6 | 1 |
| Scissor | 10 | 13 | 9 | 1 |
| Attic | 13 | 20 | 14 | 1 |

These are worked geometry counts inspected from the current source, not invariant
counts for every heel/overhang or a capacity example. Existing topology/endpoint
tests exercise all five templates with both zero and nonzero heel/overhang.
Saved manual source definitions include topology schema 2 nodes, members and
physical-cut mappings; older definitions remain reviewable and are not silently
rewritten to claim current fabrication intent.

## Placement and automatic reusable-home layouts

Direction is in degrees in the plan plane. At angle `a`, local span advances along
`(cos(a), sin(a))`; repeated instance `i`, starting at zero, advances by
`i × spacing × (-sin(a), cos(a))`. Manual bearing elevation is
`(level - 1) × STOREY_RISE + 2535 mm`. Named heel controls chord geometry above
that plane. Custom elevations are relative to that same placement plane;
span/pitch/heel/overhang controls do not reshape submitted custom nodes.

`home_definition._truss_roof` adapts an explicit gable roof zone to that centre
convention, rotates across the ridge axis and moves the bearing plane to the
explicit wall top/level. First/last offsets locate individual instances along the
ridge; each gets its own cut/instance identity. Specified bearing walls must be
two distinct walls on the same level; each placed bearing must lie on its wall
segment. Missing/non-bearing references produce unresolved support messages.
The physical BL/BR diagnostic also checks actual placed endpoints against wall
runs and tops within 1 mm; it does not calculate reactions or support capacity.

The half-span automatic placement defect was corrected in v2.11. Older saved
layouts/revisions retain their geometry and require explicit regeneration into
a recoverable revision. Preserve their old review snapshots and re-evaluate
current physical endpoints rather than trusting adapter metadata alone.

Automatic truss zones currently require an explicit gable shape. Existing hip
rafter framing remains available. Rectangular roof overlaps warn about unresolved
valley/trim/load transfer; no reviewed transition truss or roof-junction system
is generated. Continue T2 here before treating arbitrary joined roof zones as
complete framing.

## Expert resume and acceptance

Run from `backend/` with the locked environment:

```bash
python -m pytest test_walls.py test_trusses.py test_home_definition.py test_estimating.py test_review.py test_resource_contracts.py -q
```

Resource tests include disk-backed multipart uploads; a restricted runner must
permit worker-thread wakeup sockets. All tests isolate the development database.
See [the plan](../improvement_plan.md#9-expert-handover-and-resume-record) for full
browser/fresh-install verification and the current ticket statuses.

The next implementation work is explicit support/section-intent metadata and
fabrication detail exports, followed by legacy-definition recreation/review
coverage. Qualified reviewers must resolve joints/bracing, reactions, member and
connection capacity, roof transitions and supplier fabrication. Cross-version
catalogue/rule replay also remains open. This document completes the description
of current templates and boundaries; it does not complete those gates. Owner
confirmation remains required before restricting any existing feature/framework.
