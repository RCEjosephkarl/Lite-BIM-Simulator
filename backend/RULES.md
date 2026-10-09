# Rule applicability and reviewer handover

The installed profile is **NZS3604:2011-conceptual**, software rule version **2**.
It is a New Zealand reference profile. Its standards/manufacturer basis has **not
been independently verified**. Other home geometry is reusable; this does not
establish applicability to a different jurisdiction. No check produces structural
approval, and stored member `engineering_status` remains `unchecked`.

`review.py` produces four result states:

| State | Meaning |
|---|---|
| `reference_only` | Source lookup/reference is disclosed; capacity/applicability is unverified. |
| `evaluated_within_assumptions` | A specified software geometry diagnostic passed its stated assumptions. This is not a structural capacity pass. |
| `requires_specific_design` | Source assumptions are exceeded, or a supplier/specific engineering check is required. |
| `not_evaluated` | Required information or an implemented/verified check is absent. |

Overall status remains `not_evaluated` or `requires_specific_design`. A height
envelope or connected truss graph never clears the complete building load path.
Price coverage, stronger material names, extra plies and denser spacing never
establish structural approval.

| Diagnostic / source | Recorded inputs and implementation | Review still needed |
|---|---|---|
| Actual model height | Oriented member bounds, lowest explicit level elevation, height above that level; source candidate 10,000 mm. Missing explicit datum returns `not_evaluated`. Storey count is separate. | Confirm site/ground definition, relevant scope/edition/amendments and permissible arrangements. |
| Wind/snow selection | Normalized wind zone/speed, snow zone, existing simplified `nzs3604.py` selection and beyond-profile flags. | Establish site classification and design loading; audit limits and combined loading. |
| Wall stud assumptions | Actual stud lengths, section/material, frame plies and spacing against the source's nominal 90x45 SG8/2,400 mm/single-ply basis. | Actual loaded dimension, height/section, load-bearing role, lateral/bracing loads, treatment exposure and ply connections. |
| Floor span assumption | Cut span, section/material and home floor spacing where known. Source nominal 190x45 SG8/450 mm/3,900 mm basis. | Loads, deflection, continuity, bearings, actual support capacity, holes, headers/rim members and load transfer. |
| Truss connectivity | Individual instance node IDs, actual 3D endpoints (1 mm agreement), connected graph, chord/web roles and a graph cycle. Missing legacy nodes remain unchecked. | Forces, reactions, strength/stiffness, bearings, connectors, bracing, uplift, fire/durability and supplier fabrication. |
| Automatic truss bearing alignment (profile 2) | Physical BL/BR nodes on explicitly referenced wall segments and actual wall tops within 1 mm. Missing references/geometry are not evaluated; displaced positions require review. Older half-span-shifted layouts are detected without modifying saved geometry. | Support capacity/loaded length, connections, reactions and supplier fabrication. Explicit regeneration corrects the pre-2.11 adapter placement and creates a recoverable revision. |
| Member references | `nzs3604.py ELEMENT_TYPES` clause/table labels for studs, plates/nogs, lintels, floors/ceilings, rafters/ridge/hips, posts/beams. | Audit each source rule/table input and product application. Lintel loaded dimensions, rafter/beam/post capacity and connection systems are not evaluated by the geometry diagnostics. |
| Roof junction | Explicit same-level rectangular roof-zone intersections with source/zone identity. | Reviewed junction/valley/trim members, non-duplicate physical cuts and support/load transfer. |
| Complete building | Explicit `not_evaluated` result for the overall load path. | Foundation, bracing, uplift, hold-downs, connections, floor/roof junctions and member/joint capacity. |

Each result records code, stable check ID, status/severity, source/assembly/level,
representative member, occurrence count, rule/version/reference, assumptions,
input values, cause and next action. Checks are stored as `review_snapshot` in
project metadata with every revisioned write, inside the same transaction and undo
snapshot. Reads calculate current diagnostics within the model read snapshot
without changing the database. This allows code/rule-version changes to be
identified separately from historical saved assessments.

Settings / Warnings aggregates repeated source messages, shows all checks and
assumptions, and opens the relevant assembly in the inspector. Warning navigation
clears source/isolation filters and reveals its category. The inspector separates
geometry review from outstanding structural capacity/connection checks. Previews
have their own assessment; partial wall/truss previews lack a complete building
datum and cannot establish whole-project applicability.

Before upgrading any result to an independently verified rule, record:

1. Reviewer identity/qualification, date and approval scope.
2. Applicable jurisdiction, standard edition/amendments and manufacturer document.
3. Exact required inputs, units, loads, support/connection assumptions and bounds.
4. Independent worked examples and boundary/out-of-scope regression fixtures.
5. Rule/version change, migration/re-evaluation policy and unresolved conditions.

No qualified sign-off or standards-table reproduction is supplied by this software
change. Continue **R1** with the reviewer, while **U1/U2/M1** software work can
proceed. Run `python -m pytest test_review.py -q` from `backend/` for the current
geometry/source-assumption regression checks.

[FRAMING.md](FRAMING.md) describes the implemented wall/panel rules, each named
truss template, physical-cut versus graph identity, bearing placement, legacy
layouts and the remaining fabrication/support work. It records source behavior
and worked geometry counts, not an independently verified standards design.
