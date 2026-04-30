# CAD/Assist — Product Requirements & Build Log

## Original Problem Statement
Local-first scan → DXF conversion system with self-improving rule library. No paid APIs, no MongoDB, no cloud vision. One-command setup.

## Architecture
- **UI** React 19 SPA (dark CAD aesthetic, IBM Plex Mono/Sans)
- **Backend** FastAPI + OpenCV + Tesseract 5 + PyMuPDF + ezdxf
- **Storage** SQLite WAL in `backend/data/cadassist.sqlite3`
- **Desktop shell** Electron + PyInstaller (in `/app/desktop/`)
- **Launchers** `start.sh` (unix), `run_windows.bat` (windows), `desktop/` (native binaries)

## Iterations

### Iteration 1 (2026-02-xx)
- Initial MVP: upload → pipeline → DXF → rules UI. Two default rules. Detection via Hough + contours. Tested 15/15 backend + full frontend. One UX fix (SVG hit overlays).

### Iteration 2 (2026-02-xx) — user feedback pass
User reported: (1) weak detection (arcs, text, hatches), (2) cloud preview slow, (3) server setup friction, (4) wanted scale to 1000s of drawings.

**Shipped**:
- **Detection rewrite**: contour-based arc fitting (Kasa algebraic circle fit) catches arcs Hough misses; two-pass collinear line merge; hatch pattern detection (parallel equidistant line groups collapse to a single HATCH entity with ANSI31 pattern in the DXF).
- **OCR fix**: removed unicode-char whitelist that was breaking tesseract config and filtering everything out. PSM 11 + PSM 6 multi-pass with IoU dedup. Now detects labels and dimensions reliably ("960mm", "BRACKET PLATE", "Ø200").
- **DXF preview mode**: toggle in JobView between "Scan + Overlay" and "DXF Preview" (pure entity rendering on dark background, no raster).
- **Parallel page processing**: ThreadPoolExecutor (4 workers) for multi-page PDFs in `pipeline.py`.
- **13 pre-seeded rules** (up from 2): noise cleanup, arc/circle disambiguation, common OCR fixes (O→0, l→1, S→5, B→8).
- **Batch CLI** `backend/batch.py`: run pipeline against a directory of drawings, write DXFs + per-file CSV report with entity counts, timings, uncertain counts. Lets user validate on their 1000s of CAD files from terminal.
- **Windows one-shot `run_windows.bat`**: double-click → creates venv, installs deps, generates samples, starts backend+frontend, opens browser.
- **Electron + PyInstaller desktop scaffolding** in `/app/desktop/` with `main.js` (spawns bundled backend as subprocess, waits for `/api/health`, loads React build), `preload.js`, `package.json` with electron-builder config for .exe/.dmg/.AppImage, full per-OS build README.
- **Health check fix**: `/api/health` now actually invokes `pytesseract.get_tesseract_version()` instead of just checking module import.

**Batch benchmark** (3 sample drawings):
```
floor_plan.png      54 entities  4 uncertain  2.4s
geometry_demo.png   15 entities  0 uncertain  1.4s
mechanical_part.png 21 entities  5 uncertain  1.8s
avg 1.86s/file
```

## Backlog

### P0 (next)
- Per-endpoint drag to manually move detected line endpoints on canvas.
- Vector PDF full path mode (stroke-width + color preservation).
- Bundle a Tesseract Windows binary into `desktop/bin/` for truly keyless setup.

### P1
- Scale inference from detected dimension text (1:50, 1:100…).
- Multi-select + bulk corrections.
- On-disk undo history per job.

### P2
- Shareable rule-pack export/import (JSON) so teams can exchange knowledge bases.
- Per-layer DXF export options.

## Not done (out of scope)
- Deep-learning detection (problem statement requires rule-based, explainable, no cloud AI).
- Cross-platform binary build from one machine (intrinsically impossible — users build on their target OS).

## Known limitations
- Handwritten text / stylised fonts: limited OCR accuracy (fundamental Tesseract limit).
- Very large drawings are capped at 3500 px on the longest side.
