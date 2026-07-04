---
name: verify
description: Build, launch and drive TimberBIM Lite end-to-end (FastAPI + Vite/three.js).
---

# Verify TimberBIM Lite

## Build & launch

```bash
cd frontend && npm run build          # emits dist/ served by the backend
cd ../backend && python -m uvicorn server:app --port 8123
# app at http://localhost:8123 (API + built frontend on one port)
```

`backend/model.db` is git-ignored but is the user's dev database — back it
up before driving commits/regenerate, restore after.

## Drive (headless browser)

Playwright is available via the npx cache; chromium needs two locally
extracted libs (no sudo):

```bash
cd <scratch>/libs && apt-get download libnspr4 libnss3 libasound2t64
for f in *.deb; do dpkg-deb -x "$f" extracted/; done
LD_LIBRARY_PATH=<scratch>/libs/extracted/usr/lib/x86_64-linux-gnu node script.mjs
# import { chromium } from "<npx-cache>/node_modules/playwright/index.mjs"
```

Gotchas:
- The collapsed sidebar rail's buttons overhang the 3D canvas, so
  Playwright's actionability check blocks `page.click` on nav items.
  Instead move the mouse onto the rail (x≈25) to expand it, then
  `page.mouse.click` at the button's bounding box (+20 px from left).
  Pin the sidebar first (`#sidebar-pin`) so panels stay open.
- 3D picking: click a probe grid on the canvas and read `#info`
  textContent for "Selected wall frame" / "Selected truss". The default
  camera targets (10.7, 1.5, −9.1) scene-metres; commit a manual truss at
  start_x≈10700 / start_z≈9100 mm to guarantee an in-frame truss.
- Manual forms: fill `#wall-form [name=…]`, click `#wall-preview`, read
  `#wall-result` (errors surface there).

## Flows worth driving

- Wall click → whole segment metadata; empty-sky click clears; rafter
  (no segment/truss) → single-member detail.
- Manual wall > 6 m → rejection message in `#wall-result`; 2.5 m × 5.5 m
  passes (envelope is orientation-interchangeable).
- `/?wall_treatment=H3.1` URL round-trip → `#wall-treatment` reflects it.
- Settings → Regenerate model (preserves manual/imported members).
