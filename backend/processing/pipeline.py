"""Pipeline orchestrator. Runs synchronous CV work — call from a thread."""
from __future__ import annotations
from pathlib import Path
import traceback
import cv2

from storage import db
from processing import ingest, preprocess, detect, ocr, reconstruct, export_dxf
from learning import engine as learning


def _save_preview(img, out_path: Path):
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(out_path), img, [cv2.IMWRITE_JPEG_QUALITY, 85])


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

            for pi, img in page_iter:
                db.update_job(job_id, stage=f"page {pi+1}/{total} preprocess", progress=0.05 + 0.85 * (pi / max(1, total)))
                raw_path = preview_dir / f"p{pi}_raw.jpg"
                prev_path = preview_dir / f"p{pi}_preview.jpg"
                _save_preview(img, raw_path)

                pp = preprocess.preprocess(img)
                _save_preview(pp["deskewed"], prev_path)

                ents = []
                if is_vector and pi < len(vector_entities) and vector_entities[pi]:
                    # Use vector extraction when available
                    for v in vector_entities[pi]:
                        v["page_index"] = pi
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

                db.add_page(
                    job_id=job_id,
                    page_index=pi,
                    width=int(pp["deskewed"].shape[1]),
                    height=int(pp["deskewed"].shape[0]),
                    raw_path=str(raw_path),
                    preview_path=str(prev_path),
                    rotation=pp["rotation"],
                )
                pages_info.append({"page": pi, "h": pp["deskewed"].shape[0], "w": pp["deskewed"].shape[1]})
                all_entities.extend(ents)
        else:
            img = ingest.load_image(filepath)
            pi = 0
            raw_path = preview_dir / f"p{pi}_raw.jpg"
            prev_path = preview_dir / f"p{pi}_preview.jpg"
            _save_preview(img, raw_path)
            pp = preprocess.preprocess(img)
            _save_preview(pp["deskewed"], prev_path)

            ents = detect.detect_all(pp["binary"], pp["gray"])
            try:
                ents.extend(ocr.extract_text(pp["gray"]))
            except Exception as oe:
                db.log(job_id, "WARN", f"OCR failed: {oe}")
            for e in ents:
                e["page_index"] = pi
            ents = reconstruct.reconstruct(ents)
            ents, applied = learning.apply_rules(ents)
            if applied:
                db.log(job_id, "INFO", f"Applied {applied} learned rule(s)")

            db.add_page(
                job_id=job_id,
                page_index=pi,
                width=int(pp["deskewed"].shape[1]),
                height=int(pp["deskewed"].shape[0]),
                raw_path=str(raw_path),
                preview_path=str(prev_path),
                rotation=pp["rotation"],
            )
            pages_info.append({"page": pi, "h": pp["deskewed"].shape[0], "w": pp["deskewed"].shape[1]})
            db.update_job(job_id, num_pages=1)
            all_entities.extend(ents)

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
        except Exception:
            continue

    out_path.parent.mkdir(parents=True, exist_ok=True)
    doc.saveas(str(out_path))
    return str(out_path)
