# CAD/Assist — Product Requirements & Build Log

## Original Problem Statement (verbatim)

Build a complete, working, local-first CAD conversion system that converts scanned
drawings and documents into editable DXF CAD files, with a self-improving
correction memory.

NON-NEGOTIABLE GOAL:
1. Convert PDF → CAD (DXF)
2. Convert PNG/JPG → CAD (DXF)
3. Learn from human corrections over time
4. Run locally on the user's machine
5. Simple setup experience (1-command)
6. No paid APIs / no cloud OCR / no MongoDB

## Architecture (chosen)

- **UI**: React 19 SPA (dark CAD aesthetic, IBM Plex Mono/Sans)
- **Backend**: FastAPI (Python 3.11), sync CV pipeline dispatched via `loop.run_in_executor`
- **Storage**: SQLite with WAL (`/app/backend/data/cadassist.sqlite3`)
- **Image / geometry**: OpenCV 4 + scikit-image + scipy
- **PDF**: PyMuPDF (`fitz`) with vector-path extraction + 200 DPI rasterisation
- **OCR**: Tesseract 5 via pytesseract, CAD whitelist, dimension heuristics
- **DXF**: `ezdxf` with layered output (GEOMETRY · TEXT · DIMENSIONS · UNCERTAIN)
- **Launcher**: `start.sh` (one command, auto-venv, auto-install, auto-start)

## Users / Personas

1. **CAD operator** digitising legacy paper drawings into editable DXF.
2. **Engineer** who wants a local, offline, zero-API-cost pipeline to clean scans.
3. **Power user** who wants the system to learn specific corrections (OCR typos, arc vs circle) and auto-apply them to the next job.

## Core Requirements (static)

- Drag-drop upload PDF / PNG / JPG / TIFF / WEBP (≤60 MB).
- Automatic pipeline: ingest → preprocess → detect → OCR → reconstruct → learning → DXF.
- Every detected entity has confidence; low-confidence entities are flagged as `uncertain` and rendered red.
- Human corrections stored in SQLite; with "apply to similar" they become rules auto-applied on future jobs.
- Rule library fully inspectable: view, disable, delete.
- No cloud dependencies for core processing.

## Implemented (2026-02-xx, Feb 2026 build)

- [x] SQLite schema (jobs, pages, entities, rules, corrections, logs) with indexes + WAL.
- [x] Backend endpoints: `/api/health`, `/api/jobs` (CRUD + upload + reprocess + dxf + preview + logs), `/api/entities/{id}`, `/api/jobs/{id}/correct`, `/api/rules` (CRUD + toggle).
- [x] Pipeline modules: `ingest.py`, `preprocess.py`, `detect.py`, `ocr.py`, `reconstruct.py`, `export_dxf.py`, `pipeline.py`.
- [x] Learning engine with pattern signatures (`short_line<10`, `low_coverage_arc<0.6`, `many_vertex_poly>20`, `low_conf_text<0.5`, `text_value:<val>`, `broken_circle<X>`) and actions (`delete`, `convert`, `edit_text`, `close_shape`, `mark_certain`). Two defaults seeded on startup.
- [x] React UI: Home (upload + jobs + system status), JobView (left meta+layers, SVG canvas with pan/zoom, right inspector + uncertain list), Rules, About.
- [x] GeometryCanvas renders geometry overlay on top of the scan with invisible thicker hit overlays for click-ability.
- [x] Sample drawings auto-generated (`sample_gen.py`): mechanical part, floor plan, geometry demo.
- [x] `start.sh` local one-command launcher.
- [x] Complete README with architecture, API, packaging notes.

## Backlog / Next Steps

### P0 (near-term polish)
- Native desktop packaging: Electron wrapper spawning a PyInstaller-bundled backend.
- Per-entity raw geometry editor (handle drag on endpoints) so users can move without converting.

### P1
- Arc start/end angle manual editing in the Inspector.
- Multi-select + bulk actions (delete, mark-certain, convert).
- DXF re-import to iteratively re-clean a previously exported file.
- Per-layer export options (e.g., text off).

### P2
- Scale inference from detected dimension text (1:50, 1:100…) and store to Page.scale.
- Preview DXF viewer on-screen after export.
- Export alternate formats: SVG, PDF (vector).

## Deferred

- Authentication: not required for a local tool.
- Cloud sync: explicitly forbidden by problem statement.

## Known limitations

- Hough-based arc detection is inherently approximate — hence the "uncertain" layer. Learning fixes this over time per drawing style.
- OCR on hand-written or very stylised fonts is limited; dedicated handwriting model out-of-scope here.
- Very large multi-page PDFs are processed sequentially; parallelism deferred.

## Testing

Iteration 1 — full stack tested by `testing_agent_v3`:
- Backend: 15/15 pytest cases pass (upload, process, DXF, preview, rules CRUD, correction→rule, negative cases).
- Frontend: all flows and testids work (upload, navigate to job, layer toggles, inspector for uncertain items, rules toggle/delete, about page).
- One UX concern (SVG thin-stroke hit areas) was fixed post-test via invisible hit overlays in `GeometryCanvas.jsx`.
