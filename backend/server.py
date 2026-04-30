"""FastAPI server for CAD Assist. Local-first, SQLite storage."""
from __future__ import annotations
import asyncio
import shutil
import sys
import os
from pathlib import Path
from typing import Optional, Any
import logging

from fastapi import FastAPI, APIRouter, UploadFile, File, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse, JSONResponse
from starlette.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent
load_dotenv(ROOT_DIR / ".env")

sys.path.insert(0, str(ROOT_DIR))

from storage import db
from processing import pipeline
from learning import engine as learning

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("cadassist")

learning.seed_default_rules()

app = FastAPI(title="CAD Assist", version="1.0.0")
api = APIRouter(prefix="/api")

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------- Pydantic models ----------
class HealthOut(BaseModel):
    ok: bool
    version: str
    tesseract: bool
    fitz: bool


class CorrectionIn(BaseModel):
    entity_id: Optional[str] = None
    action_type: str
    new_data: Optional[dict] = None
    apply_to_similar: bool = False
    notes: Optional[str] = None


class EntityUpdateIn(BaseModel):
    kind: Optional[str] = None
    data: Optional[dict] = None
    layer: Optional[str] = None
    uncertain: Optional[bool] = None
    deleted: Optional[bool] = None


class RuleUpdateIn(BaseModel):
    active: Optional[bool] = None
    confidence: Optional[float] = None
    notes: Optional[str] = None


# ---------- Health ----------
@api.get("/health", response_model=HealthOut)
async def health():
    try:
        import pytesseract  # noqa
        has_tess = True
    except Exception:
        has_tess = False
    try:
        import fitz  # noqa
        has_fitz = True
    except Exception:
        has_fitz = False
    return HealthOut(ok=True, version="1.0.0", tesseract=has_tess, fitz=has_fitz)


# ---------- Jobs ----------
@api.post("/jobs/upload")
async def upload(file: UploadFile = File(...)):
    if not file.filename:
        raise HTTPException(400, "missing filename")
    name_lower = file.filename.lower()
    if not name_lower.endswith((".pdf", ".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".webp")):
        raise HTTPException(400, f"unsupported file type: {file.filename}")

    job_id = db.new_id()
    job_dir = db.UPLOADS_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    dest = job_dir / file.filename
    total = 0
    max_size = 60 * 1024 * 1024
    with dest.open("wb") as f:
        while True:
            chunk = await file.read(1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > max_size:
                f.close()
                dest.unlink(missing_ok=True)
                raise HTTPException(413, "file too large (max 60MB)")
            f.write(chunk)

    ts = db.now_iso()
    db.exec_write(
        "INSERT INTO jobs(id,filename,filepath,mime,status,stage,progress,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)",
        (job_id, file.filename, str(dest), file.content_type or "", "pending", "uploaded", 0.0, ts, ts),
    )

    loop = asyncio.get_event_loop()
    loop.run_in_executor(None, pipeline.run_job, job_id)

    return {"job_id": job_id, "filename": file.filename}


@api.post("/jobs/{job_id}/reprocess")
async def reprocess(job_id: str):
    job = db.get_job(job_id)
    if not job:
        raise HTTPException(404, "job not found")
    loop = asyncio.get_event_loop()
    loop.run_in_executor(None, pipeline.run_job, job_id)
    return {"ok": True, "job_id": job_id}


@api.get("/jobs")
async def list_jobs(limit: int = 100):
    return {"jobs": db.list_jobs(limit=limit)}


@api.get("/jobs/{job_id}")
async def get_job(job_id: str):
    job = db.get_job(job_id)
    if not job:
        raise HTTPException(404, "job not found")
    pages = db.get_pages(job_id)
    entities = db.get_entities(job_id)
    counts: dict[str, int] = {}
    uncertain = 0
    for e in entities:
        counts[e["kind"]] = counts.get(e["kind"], 0) + 1
        if e["uncertain"]:
            uncertain += 1
    return {
        "job": job,
        "pages": pages,
        "entities": entities,
        "summary": {"counts": counts, "uncertain": uncertain, "total": len(entities)},
    }


@api.delete("/jobs/{job_id}")
async def delete_job(job_id: str):
    job = db.get_job(job_id)
    if not job:
        raise HTTPException(404, "job not found")
    db.delete_job(job_id)
    try:
        shutil.rmtree(db.UPLOADS_DIR / job_id, ignore_errors=True)
        shutil.rmtree(db.PREVIEWS_DIR / job_id, ignore_errors=True)
        (db.OUTPUTS_DIR / f"{job_id}.dxf").unlink(missing_ok=True)
    except Exception:
        pass
    return {"ok": True}


@api.get("/jobs/{job_id}/logs")
async def job_logs(job_id: str):
    return {"logs": db.get_logs(job_id)}


@api.get("/jobs/{job_id}/preview/{page_index}")
async def page_preview(job_id: str, page_index: int):
    pages = db.get_pages(job_id)
    page = next((p for p in pages if p["page_index"] == page_index), None)
    if not page:
        raise HTTPException(404, "page not found")
    path = page["preview_path"]
    if not path or not Path(path).exists():
        raise HTTPException(404, "preview missing")
    return FileResponse(path, media_type="image/jpeg")


@api.get("/jobs/{job_id}/dxf")
async def job_dxf(job_id: str):
    path = db.OUTPUTS_DIR / f"{job_id}.dxf"
    if not path.exists():
        raise HTTPException(404, "dxf not available")
    job = db.get_job(job_id)
    fname = (job["filename"].rsplit(".", 1)[0] if job else job_id) + ".dxf"
    return FileResponse(str(path), filename=fname, media_type="application/dxf")


# ---------- Entities & Corrections ----------
@api.patch("/entities/{entity_id}")
async def update_entity(entity_id: str, body: EntityUpdateIn):
    e = db.get_entity(entity_id)
    if not e:
        raise HTTPException(404, "entity not found")
    fields = {k: v for k, v in body.model_dump().items() if v is not None}
    if "uncertain" in fields:
        fields["uncertain"] = int(bool(fields["uncertain"]))
    if "deleted" in fields:
        fields["deleted"] = int(bool(fields["deleted"]))
    fields["modified"] = 1
    db.update_entity(entity_id, **fields)
    return {"ok": True, "entity": db.get_entity(entity_id)}


@api.post("/jobs/{job_id}/correct")
async def correct(job_id: str, body: CorrectionIn):
    job = db.get_job(job_id)
    if not job:
        raise HTTPException(404, "job not found")
    entity_before = db.get_entity(body.entity_id) if body.entity_id else None

    action = body.action_type
    new_data = body.new_data or {}

    if entity_before is not None:
        if action == "delete":
            db.update_entity(entity_before["id"], deleted=1, modified=1)
        elif action == "convert":
            to_kind = new_data.get("to_kind")
            if to_kind == "arc" and entity_before["kind"] == "circle":
                d = dict(entity_before["data"])
                d["start_angle"] = new_data.get("start_angle", 0.0)
                d["end_angle"] = new_data.get("end_angle", 3.14159)
                db.update_entity(entity_before["id"], kind="arc", data=d, modified=1)
            elif to_kind == "circle" and entity_before["kind"] == "arc":
                d = dict(entity_before["data"])
                d.pop("start_angle", None)
                d.pop("end_angle", None)
                db.update_entity(entity_before["id"], kind="circle", data=d, modified=1)
            elif to_kind == "line" and entity_before["kind"] == "polyline":
                pts = entity_before["data"].get("points", [])
                if len(pts) >= 2:
                    nd = {"x1": pts[0][0], "y1": pts[0][1], "x2": pts[-1][0], "y2": pts[-1][1]}
                    db.update_entity(entity_before["id"], kind="line", data=nd, modified=1)
        elif action == "edit_text":
            d = dict(entity_before["data"])
            d["text"] = new_data.get("text", d.get("text", ""))
            db.update_entity(entity_before["id"], data=d, uncertain=0, modified=1)
        elif action == "close_shape" and entity_before["kind"] == "polyline":
            d = dict(entity_before["data"])
            d["closed"] = True
            db.update_entity(entity_before["id"], data=d, modified=1)
        elif action == "mark_certain":
            db.update_entity(entity_before["id"], uncertain=0, modified=1)
        elif action == "update":
            d = {**entity_before["data"], **(new_data or {})}
            db.update_entity(entity_before["id"], data=d, modified=1)

    rule_id = learning.record_correction(
        job_id=job_id,
        entity_before=entity_before,
        action_type=action,
        new_data=new_data,
        apply_to_similar=body.apply_to_similar,
        notes=body.notes or "",
    )
    try:
        pipeline._export_job_dxf(job_id)
    except Exception as e:
        logger.warning(f"dxf regen failed: {e}")

    return {"ok": True, "rule_id": rule_id}


@api.post("/jobs/{job_id}/entities")
async def add_entity(job_id: str, body: dict):
    job = db.get_job(job_id)
    if not job:
        raise HTTPException(404, "job not found")
    body.setdefault("modified", True)
    db.add_entities(job_id, [body])
    try:
        pipeline._export_job_dxf(job_id)
    except Exception:
        pass
    return {"ok": True}


# ---------- Rules ----------
@api.get("/rules")
async def list_rules():
    return {"rules": db.list_rules()}


@api.patch("/rules/{rule_id}")
async def update_rule(rule_id: str, body: RuleUpdateIn):
    r = db.get_rule(rule_id)
    if not r:
        raise HTTPException(404, "rule not found")
    fields = {k: v for k, v in body.model_dump().items() if v is not None}
    if "active" in fields:
        fields["active"] = int(bool(fields["active"]))
    db.update_rule(rule_id, **fields)
    return {"ok": True, "rule": db.get_rule(rule_id)}


@api.delete("/rules/{rule_id}")
async def delete_rule(rule_id: str):
    r = db.get_rule(rule_id)
    if not r:
        raise HTTPException(404, "rule not found")
    db.delete_rule(rule_id)
    return {"ok": True}


app.include_router(api)


@app.get("/")
async def root_redirect():
    return {"ok": True, "name": "CAD Assist API", "docs": "/docs"}
