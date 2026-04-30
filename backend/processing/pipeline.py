"""Pipeline orchestrator. Runs synchronous CV work — call from a thread."""
from __future__ import annotations
from pathlib import Path
import traceback
import concurrent.futures
import cv2

from storage import db
from processing import ingest, preprocess, detect, ocr, reconstruct, export_dxf
from learning import engine as learning


def _save_preview(img, out_path: Path, quality: int = 70):
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(out_path), img, [cv2.IMWRITE_JPEG_QUALITY, quality])


def _process_single_page(job_id: str, pi: int, img, preview_dir: Path, vector_entities_for_page: list | None):
    """Process one page — CPU-bound, safe to run in a worker thread."""
    raw_path = preview_dir / f"p{pi}_raw.jpg"
    prev_path = preview_dir / f"p{pi}_preview.jpg"
    _save_preview(img, raw_path, quality=60)
    pp = preprocess.preprocess(img)
    _save_preview(pp["deskewed"], prev_path, quality=70)

    ents: list[dict] = []
    if vector_entities_for_page:
        for v in vector_entities_for_page:
            ents.append(v)
    else:
        ents.extend(detect.detect_all(pp["binary"], pp["gray"]))
        try:
            ents.extend(ocr.extract_text(pp["gray"]))
        except Exception as oe:
            db.log(job_id, "WARN", f"OCR failed page {pi}: {oe}")

    for e in ents:
        e["page_index"] = pi
    ents = reconstruct.reconstruct(ents)
    ents, applied = learning.apply_rules(ents)
    if applied:
        db.log(job_id, "INFO", f"Applied {applied} learned rule(s) on page {pi}")

    return {
        "page_index": pi,
        "width": int(pp["deskewed"].shape[1]),
        "height": int(pp["deskewed"].shape[0]),
        "raw_path": str(raw_path),
        "preview_path": str(prev_path),
        "rotation": pp["rotation"],
        "entities": ents,
    }


def run_job(job_id: str) -> dict:
    """Top-level pipeline for a job id. Updates DB as it goes."""
    job = db.get_job(job_id)
    if not job:
        return {"ok": False, "error": "job not found"}

    try:
        db.update_job(job_id, status="processing", stage="ingest", progress=0.05, error=None)
        db.clear_entities(job_id)
        db.log(job_id, "INFO", "Pipeline started")

        filepath = job["filepath"]
        is_pdf = ingest.is_pdf(filepath)
        is_img = ingest.is_image(filepath)
        if not (is_pdf or is_img):
            raise ValueError(f"Unsupported file type: {filepath}")

        all_entities: list[dict] = []
        pages_info = []
        is_vector = False

        preview_dir = db.PREVIEWS_DIR / job_id
        preview_dir.mkdir(parents=True, exist_ok=True)

        if is_pdf:
            is_vector = ingest.pdf_is_vector(filepath)
            db.update_job(job_id, is_vector=int(is_vector))
            page_iter = list(ingest.pdf_iter_pages(filepath))
            total = len(page_iter)
            db.update_job(job_id, num_pages=total)
            vector_entities = []
            if is_vector:
                vector_entities = ingest.pdf_vector_entities(filepath)

            # Parallelise across pages (2-4 workers is the sweet spot on most laptops)
            max_workers = min(4, max(1, total))
            done = 0
            results: list[dict] = []
            with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as ex:
                futures = {}
                for pi, img in page_iter:
                    vec = vector_entities[pi] if (is_vector and pi < len(vector_entities) and vector_entities[pi]) else None
                    futures[ex.submit(_process_single_page, job_id, pi, img, preview_dir, vec)] = pi
                for fut in concurrent.futures.as_completed(futures):
                    try:
                        r = fut.result()
                        results.append(r)
                    except Exception as pe:
                        db.log(job_id, "ERROR", f"page {futures[fut]} failed: {pe}")
                    done += 1
                    db.update_job(job_id, stage=f"processed {done}/{total}", progress=0.05 + 0.85 * (done / max(1, total)))

            # Sort by page index and persist
            results.sort(key=lambda r: r["page_index"])
            for r in results:
                db.add_page(
                    job_id=job_id,
                    page_index=r["page_index"],
                    width=r["width"],
                    height=r["height"],
                    raw_path=r["raw_path"],
                    preview_path=r["preview_path"],
                    rotation=r["rotation"],
                )
                pages_info.append({"page": r["page_index"], "h": r["height"], "w": r["width"]})
                all_entities.extend(r["entities"])
        else:
            img = ingest.load_image(filepath)
            r = _process_single_page(job_id, 0, img, preview_dir, None)
            db.add_page(
                job_id=job_id,
                page_index=0,
                width=r["width"],
                height=r["height"],
                raw_path=r["raw_path"],
                preview_path=r["preview_path"],
                rotation=r["rotation"],
            )
            pages_info.append({"page": 0, "h": r["height"], "w": r["width"]})
            db.update_job(job_id, num_pages=1)
            all_entities.extend(r["entities"])

        db.update_job(job_id, stage="saving entities", progress=0.9)
        db.add_entities(job_id, all_entities)

        # Export DXF (combine pages by offsetting Y if multiple)
        db.update_job(job_id, stage="export dxf", progress=0.95)
        dxf_path = _export_job_dxf(job_id)
        db.update_job(job_id, status="done", stage="done", progress=1.0, error=None)
        db.log(job_id, "INFO", f"Pipeline done. DXF: {dxf_path}")
        return {"ok": True, "dxf": dxf_path, "pages": pages_info, "entities": len(all_entities)}
    except Exception as ex:
        tb = traceback.format_exc()
        db.log(job_id, "ERROR", tb)
        db.update_job(job_id, status="error", error=str(ex))
        return {"ok": False, "error": str(ex)}


def _export_job_dxf(job_id: str) -> str:
    pages = db.get_pages(job_id)
    entities = db.get_entities(job_id)
    if not pages:
        raise ValueError("no pages")
    # Combine with per-page Y offset
    y_offset = 0
    combined: list[dict] = []
    heights = {p["page_index"]: p["height"] for p in pages}
    # Sort entities by page
    by_page: dict[int, list[dict]] = {}
    for e in entities:
        by_page.setdefault(e["page_index"], []).append(e)
    for p in pages:
        h = p["height"]
        for e in by_page.get(p["page_index"], []):
            ec = {**e, "data": dict(e["data"])}
            # translate y by y_offset AFTER flip: we pass page_height per entity via offset trick
            # Simpler: shift x only for stacked pages; shift in DXF coords
            # Here we append page_height to each entity's data as meta, and let export compute absolute
            ec["_y_offset"] = y_offset
            ec["_page_height"] = h
            combined.append(ec)
        y_offset += h + 40  # gap between pages

    # Custom export: apply y_offset
    out_path = db.OUTPUTS_DIR / f"{job_id}.dxf"
    import ezdxf, math as _math
    doc = ezdxf.new(setup=True)
    from processing.export_dxf import LAYER_COLORS
    for name, color in LAYER_COLORS.items():
        if name not in doc.layers:
            doc.layers.add(name=name, color=color)
    msp = doc.modelspace()

    for e in combined:
        if e.get("deleted"):
            continue
        h = e["_page_height"]
        off = e["_y_offset"]
        def fy(y):
            return (h - y) + (- (h + off))  # stacked: first page top at 0, next below

        layer = e.get("layer", "GEOMETRY")
        if e.get("uncertain"):
            layer = "UNCERTAIN"
        kind = e["kind"]
        d = e["data"]
        try:
            if kind == "line":
                msp.add_line((float(d["x1"]), fy(d["y1"])), (float(d["x2"]), fy(d["y2"])), dxfattribs={"layer": layer})
            elif kind == "circle":
                msp.add_circle((float(d["cx"]), fy(d["cy"])), float(d["r"]), dxfattribs={"layer": layer})
            elif kind == "arc":
                sa = _math.degrees(float(d["start_angle"]))
                ea = _math.degrees(float(d["end_angle"]))
                msp.add_arc(center=(float(d["cx"]), fy(d["cy"])), radius=float(d["r"]), start_angle=-ea, end_angle=-sa, dxfattribs={"layer": layer})
            elif kind == "polyline":
                pts = d.get("points", [])
                xy = [(float(p[0]), fy(float(p[1]))) for p in pts]
                if len(xy) >= 2:
                    msp.add_lwpolyline(xy, close=bool(d.get("closed")), dxfattribs={"layer": layer})
            elif kind in ("text", "dimension"):
                txt = d.get("text", "")
                if not txt:
                    continue
                height = float(d.get("height", 12))
                x = float(d.get("x", 0))
                y = float(d.get("y", 0))
                t = msp.add_text(txt, dxfattribs={"layer": layer, "height": max(2.0, height * 0.8)})
                t.set_placement((x, fy(y)))
            elif kind == "hatch":
                bbox = d.get("bbox")
                if not bbox or len(bbox) != 4:
                    continue
                x0, y0, x1, y1 = [float(v) for v in bbox]
                pts = [(x0, fy(y0)), (x1, fy(y0)), (x1, fy(y1)), (x0, fy(y1))]
                msp.add_lwpolyline(pts, close=True, dxfattribs={"layer": layer})
                angle = float(d.get("angle_deg", 45))
                try:
                    h_ent = msp.add_hatch(dxfattribs={"layer": layer})
                    h_ent.set_pattern_fill("ANSI31", scale=1.5, angle=angle)
                    h_ent.paths.add_polyline_path(pts, is_closed=True)
                except Exception:
                    pass
        except Exception:
            continue

    out_path.parent.mkdir(parents=True, exist_ok=True)
    doc.saveas(str(out_path))
    return str(out_path)
