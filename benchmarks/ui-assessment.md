# Desktop/mobile UI assessment and resume guide

The v2.16 local assessment uses Chromium 151, a 1440 × 1000 desktop and a
390 × 844 mobile layout, with reduced motion requested. The isolated focused
capture opens the bundled sample home; the full acceptance suite repeats the
audit against its independently saved reusable home. No user project or browser
draft is inspected. [ui-assessment.json](ui-assessment.json) records results,
frontend bundle, accessible control/table names, keyboard counts, modal boundaries,
mobile bounds and measured text colours.

All seven essential pages passed accessible-name and ARIA-reference checks at
both sizes. Real Tab traversal reached all 1,141 enabled targets in this sample's
fourteen page/viewport cases and wrapped without a page trap. Counts depend on the
home, BOM rows and current field readiness; they are observations, not a target.
The audit includes editable CSV cells, dynamic opening controls, custom truss CSV
fields and the definition editor. CSV review, preview and cancellation activate
from the keyboard; cancellation removes commit readiness. The broader suite
covers guided wall/truss preview, error focus/retry, hierarchy paging, exact BOM
row location, orthographic/clipped extents and camera controls.

BOM/Pricing dialogs retain native modal behaviour: background page controls stay
inert and Escape returns focus to the opener. Chromium may yield Tab to browser
chrome at the end of a cycle; this is recorded separately, rather than adding a
custom trap that prevents normal browser navigation. Mobile Close panel returns
focus to its section button. The model and form occupy separate vertical space.

The audit fixed two source-backed findings: Pricing and CSV review tables lacked
accessible names, and the focused rail label covered panel content. Tables now
have names and explicit column headers; the CSV action column is named. Rail
labels stay beside the open desktop panel or above the mobile form sheet.
Browser checks assert that their bounds do not intersect panel content. Existing
options, ranges, native controls and rendering quality remain available.

The measured secondary/error/warning/success text contrast on solid panel
backgrounds ranges from **6.20:1 to 13.54:1**, above the test's 4.5:1 target.
The calculation uses actual computed RGB colours and relative luminance. It
does not measure disabled-control opacity, arbitrary user colours, geometry
materials or every alpha-composited overlay. Reduced-motion CSS transitions are
disabled; automatic model rotation remains an explicit, reversible user choice.
Selected model rows have a checkmark/pressed state; temporary rows and status use
PREVIEW text; form progress names the current stage. These preserve meaning when
colour differences are hard to distinguish.

The captured top/bottom views support manual inspection of the long forms and
tables. The selected desktop wall and mobile imports/pricing/wall captures were
visually inspected for readable field groups, wrapping, scroll reachability,
tooltip placement and remaining canvas space. This is a local software/visual
assessment, not certification across assistive technologies or physical devices.

| Page | Desktop | Mobile | Next expert's focus |
|---|---|---|---|
| Building Specs | [Top](ui-assessment-screenshots/building-specs-desktop-top.png), [bottom](ui-assessment-screenshots/building-specs-desktop-bottom.png) | [Top](ui-assessment-screenshots/building-specs-mobile-top.png), [bottom](ui-assessment-screenshots/building-specs-mobile-bottom.png) | Verify normalized choices and meaningful source assumptions as R1 rules develop. |
| BOM | [Top](ui-assessment-screenshots/bom-desktop-top.png), [bottom](ui-assessment-screenshots/bom-desktop-bottom.png) | [Top](ui-assessment-screenshots/bom-mobile-top.png), [bottom](ui-assessment-screenshots/bom-mobile-bottom.png) | Preserve exact row/assembly identity; assess dense tables on reference devices and supplier cutting workflows. |
| Pricing | [Top](ui-assessment-screenshots/pricing-desktop-top.png), [bottom](ui-assessment-screenshots/pricing-desktop-bottom.png) | [Top](ui-assessment-screenshots/pricing-mobile-top.png), [bottom](ui-assessment-screenshots/pricing-mobile-bottom.png) | Keep historical source/FX and unpriced coverage visible when quote/currency workflows expand. |
| Imports | [Top](ui-assessment-screenshots/imports-drawing-plans-desktop-top.png), [bottom](ui-assessment-screenshots/imports-drawing-plans-desktop-bottom.png) | [Top](ui-assessment-screenshots/imports-drawing-plans-mobile-top.png), [bottom](ui-assessment-screenshots/imports-drawing-plans-mobile-bottom.png) | Resume V1 API/resource acceptance and definition/archive replay. |
| Manual Wall | [Top](ui-assessment-screenshots/manual-wall-frame-input-desktop-top.png), [bottom](ui-assessment-screenshots/manual-wall-frame-input-desktop-bottom.png) | [Top](ui-assessment-screenshots/manual-wall-frame-input-mobile-top.png), [bottom](ui-assessment-screenshots/manual-wall-frame-input-mobile-bottom.png) | Resume W1 joints/laps/detail export and qualified fabrication review. |
| Manual Truss | [Top](ui-assessment-screenshots/manual-truss-input-desktop-top.png), [bottom](ui-assessment-screenshots/manual-truss-input-desktop-bottom.png) | [Top](ui-assessment-screenshots/manual-truss-input-mobile-top.png), [bottom](ui-assessment-screenshots/manual-truss-input-mobile-bottom.png) | Resume T1 template/support/cut documentation and qualified supplier review. |
| Settings / Warnings | [Top](ui-assessment-screenshots/settings-warnings-desktop-top.png), [bottom](ui-assessment-screenshots/settings-warnings-desktop-bottom.png) | [Top](ui-assessment-screenshots/settings-warnings-mobile-top.png), [bottom](ui-assessment-screenshots/settings-warnings-mobile-bottom.png) | Preserve project/revision isolation; continue R1 standards/manufacturer audit. |

From `frontend/`, after building and configuring backend Python/Chromium:

```bash
TIMBERBIM_TEST_ACCESSIBILITY_ONLY=1 \
TIMBERBIM_ACCESSIBILITY_REPORT=../benchmarks/ui-assessment.json npm run test:browser
```

The selected audit is a development convenience. Normal `npm run test:browser`
includes it with all other acceptance flows. Fresh-source verification clears
focused-test flags and external report destinations so it always runs the full
suite with disposable state. The optional report writes JSON and a sibling
`-screenshots` directory; it adds no product dependency.

Remaining review: chosen physical desktop/phone devices, actual screen-reader
combinations, browser zoom/text enlargement, other languages/longer labels and
broader visual/user assessment. Keep U1 view/draft/request identities and V2
field/error recovery while improving these cases. Project scope changes and
framework restrictions still require the owner's confirmation.
