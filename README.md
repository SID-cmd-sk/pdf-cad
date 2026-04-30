# CAD / Assist

**Local-first** system that converts scanned drawings (PDF / PNG / JPG / TIFF) into editable **DXF** CAD files and **learns from every correction you make**.

No paid APIs. No cloud vision. All processing runs on the user's machine.

---

## Quick start (one command)

```bash
./start.sh
```
or (cross-platform / double-click friendly):
```bash
python launch.py
```

This script automatically:

1. Creates a Python virtual environment (`.venv`)
2. Installs backend dependencies (OpenCV, Tesseract wrapper, PyMuPDF, ezdxf, FastAPI)
3. Installs frontend dependencies (React)
4. Generates three sample drawings in `samples/`
5. Starts the FastAPI backend on `:8001` and the React UI on `:3000`

Open <http://localhost:3000> and drop a file on the upload zone.

### Practical assumptions

- Best results are obtained from scans at **200+ DPI**.
- OCR and dimension extraction run locally via Tesseract when installed; if missing, geometry export still works.
- DXF output units are inferred from detected dimension tokens (`mm`, `cm`, `in`) when possible, otherwise exported in drawing units.

### Requirements

- Python 3.10+
- Node.js 18+ with yarn or npm
- Tesseract OCR 5+ (optional but strongly recommended)
  - macOS: `brew install tesseract`
  - Debian/Ubuntu: `sudo apt install -y tesseract-ocr`
  - Windows: <https://github.com/UB-Mannheim/tesseract/wiki>

---

## Architecture

```
ui/                          React 19 SPA (drop zone, canvas, inspector)
backend/
├── server.py                FastAPI (all endpoints under /api)
├── processing/
│   ├── ingest.py            PDF/image loader, vector PDF extraction
│   ├── preprocess.py        grayscale · denoise · threshold · deskew
│   ├── detect.py            Hough lines + circle/arc + contours
│   ├── ocr.py               local Tesseract with dimension heuristics
│   ├── reconstruct.py       dedupe + snap endpoints
│   ├── export_dxf.py        layered DXF writer
│   └── pipeline.py          orchestrator
├── learning/engine.py       rule-based learning (signatures + actions)
└── storage/db.py            single-file SQLite (WAL)
samples/                     generated sample drawings
```

- **Storage**: one SQLite file in `backend/data/cadassist.sqlite3`.
- **Uploads**: `backend/data/uploads/<job_id>/`
- **Previews**: `backend/data/previews/<job_id>/pN_preview.jpg`
- **DXF output**: `backend/data/outputs/<job_id>.dxf`

No cloud services are contacted for core processing.

---

## Pipeline

1. **Ingest** — PDFs are inspected; if they contain drawings (vector) the paths are extracted directly. Otherwise each page is rasterised at 200 DPI with PyMuPDF. Large images are capped at 3500 px on the longest side.
2. **Preprocess** — grayscale → fastNlMeans or bilateral denoise → adaptive/Otsu binarisation (whichever yields a saner ink ratio) → minAreaRect-based skew correction.
3. **Detect geometry** — probabilistic Hough line segments are merged into clean long lines by angle + perpendicular distance + gap. Hough circles are validated against the binary image: perimeter coverage tells us whether we have a circle or an arc, and the longest hit arc becomes the arc's angle span. Contours are approximated as polygons.
4. **OCR** — Tesseract 5 with a CAD whitelist. Anything matching dimension patterns (`Ø20`, `120mm`, `R5`) is routed to the DIMENSIONS layer and the rest to TEXT.
5. **Reconstruct** — duplicate lines are removed, near endpoints are snapped to a shared centroid.
6. **Learning rules** — matching active rules auto-apply before export (delete noise, upgrade arcs to circles, edit known OCR mistakes, etc.).
7. **Export** — `ezdxf` writes a layered DXF with `GEOMETRY`, `TEXT`, `DIMENSIONS`, `UNCERTAIN` layers. Uncertain items stay on their own layer so CAD software can colour them red.

---

## Self-learning

The learning layer is **rule-based and explainable**. Every correction stores:

- a **pattern signature** (e.g. `short_line<10`, `low_coverage_arc<0.6`, `many_vertex_poly>20`, `text_value:d12`),
- an **action** (`delete` · `convert` · `edit_text` · `close_shape` · `mark_certain`) with optional payload,
- confidence, use count, success count, notes and timestamps.

When you tick **"Apply this fix to similar cases"** in the inspector, the system records a rule; on every future job the matching rule is auto-applied in stage 6 of the pipeline. You can view, disable or delete any rule under **Learning** in the UI.

Two sensible defaults are seeded on first run:
- delete lines shorter than 10 px (noise),
- delete polygons with more than 20 vertices (OCR edge artefacts).

---

## API (all under `/api`)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | backend + tesseract + fitz status |
| POST | `/jobs/upload` | multipart upload, auto-starts pipeline |
| GET | `/jobs` | list jobs |
| GET | `/jobs/{id}` | job + pages + entities + summary |
| DELETE | `/jobs/{id}` | remove job + files |
| POST | `/jobs/{id}/reprocess` | re-run pipeline |
| GET | `/jobs/{id}/preview/{page}` | JPEG preview of a page |
| GET | `/jobs/{id}/dxf` | download final DXF |
| GET | `/jobs/{id}/logs` | per-job log lines |
| POST | `/jobs/{id}/correct` | apply + optionally learn a correction |
| PATCH | `/entities/{id}` | raw entity edit |
| POST | `/jobs/{id}/entities` | add a new entity |
| GET | `/rules` | list learned rules |
| PATCH | `/rules/{id}` | toggle active / edit notes |
| DELETE | `/rules/{id}` | delete rule |

---

## Desktop packaging (optional)

The backend is a single Python app and the UI is a static React bundle, so wrapping in Electron / Tauri is straightforward:

1. `cd frontend && yarn build` — produces `frontend/build/`.
2. Bundle the Python backend with PyInstaller: `pyinstaller --onefile backend/server.py` (on Windows make sure `tesseract.exe` is on the PATH or ship it alongside).
3. Create a thin Electron main process that spawns the backend binary, waits until `:8001/api/health` is reachable, and loads the React build from disk.

For Windows local/CI builds, use one command from repo root:

```powershell
python scripts/build_exe.py
```

This produces an installer in `desktop/dist/`.

---

## Robustness

- Uploads capped at 60 MB.
- Vector + raster PDF paths are handled separately; broken pages are skipped but the rest continues.
- Every pipeline stage writes to the `logs` table so failures are debuggable from the UI.
- Supervisor / reloader friendly: the DB uses WAL and is safe across processes.
- Deskew, threshold, Hough, OCR and contour stages each fail gracefully and continue with fewer entities if one step errors.

---

## License

MIT.
