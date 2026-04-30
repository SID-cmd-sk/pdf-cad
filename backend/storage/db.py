"""SQLite storage layer. Single-file local DB, WAL enabled, thread-safe helpers."""
from __future__ import annotations
import os
import sqlite3
import json
import uuid
import threading
from pathlib import Path
from datetime import datetime, timezone
from typing import Any, Optional, Iterable

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
UPLOADS_DIR = DATA_DIR / "uploads"
OUTPUTS_DIR = DATA_DIR / "outputs"
PREVIEWS_DIR = DATA_DIR / "previews"
LOGS_DIR = DATA_DIR / "logs"
DB_PATH = DATA_DIR / "cadassist.sqlite3"

for d in (DATA_DIR, UPLOADS_DIR, OUTPUTS_DIR, PREVIEWS_DIR, LOGS_DIR):
    d.mkdir(parents=True, exist_ok=True)

_lock = threading.RLock()


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id() -> str:
    return uuid.uuid4().hex


def _connect() -> sqlite3.Connection:
    con = sqlite3.connect(str(DB_PATH), timeout=30, isolation_level=None, check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL;")
    con.execute("PRAGMA synchronous=NORMAL;")
    con.execute("PRAGMA foreign_keys=ON;")
    return con


SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    filename TEXT NOT NULL,
    filepath TEXT NOT NULL,
    mime TEXT,
    status TEXT NOT NULL,
    stage TEXT,
    progress REAL DEFAULT 0,
    num_pages INTEGER DEFAULT 0,
    is_vector INTEGER DEFAULT 0,
    error TEXT,
    meta TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_jobs_created ON jobs(created_at DESC);

CREATE TABLE IF NOT EXISTS pages (
    id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL,
    page_index INTEGER NOT NULL,
    width INTEGER,
    height INTEGER,
    preview_path TEXT,
    raw_path TEXT,
    rotation REAL DEFAULT 0,
    scale REAL DEFAULT 1.0,
    FOREIGN KEY(job_id) REFERENCES jobs(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_pages_job ON pages(job_id, page_index);

CREATE TABLE IF NOT EXISTS entities (
    id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL,
    page_index INTEGER NOT NULL,
    kind TEXT NOT NULL,
    data TEXT NOT NULL,
    layer TEXT DEFAULT 'GEOMETRY',
    confidence REAL DEFAULT 1.0,
    uncertain INTEGER DEFAULT 0,
    deleted INTEGER DEFAULT 0,
    modified INTEGER DEFAULT 0,
    rule_applied TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY(job_id) REFERENCES jobs(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_entities_job ON entities(job_id, page_index, deleted);

CREATE TABLE IF NOT EXISTS rules (
    id TEXT PRIMARY KEY,
    pattern_signature TEXT NOT NULL,
    pattern_data TEXT,
    action_type TEXT NOT NULL,
    action_data TEXT,
    confidence REAL DEFAULT 0.5,
    uses INTEGER DEFAULT 0,
    successes INTEGER DEFAULT 0,
    active INTEGER DEFAULT 1,
    notes TEXT,
    created_at TEXT NOT NULL,
    last_used TEXT
);
CREATE INDEX IF NOT EXISTS idx_rules_sig ON rules(pattern_signature, active);

CREATE TABLE IF NOT EXISTS corrections (
    id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL,
    entity_id TEXT,
    action_type TEXT NOT NULL,
    old_data TEXT,
    new_data TEXT,
    rule_id TEXT,
    apply_to_similar INTEGER DEFAULT 0,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_corrections_job ON corrections(job_id);

CREATE TABLE IF NOT EXISTS logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT,
    level TEXT,
    message TEXT,
    created_at TEXT NOT NULL
);
"""


def init_db():
    with _lock:
        con = _connect()
        try:
            con.executescript(SCHEMA)
        finally:
            con.close()


def exec_write(query: str, params: Iterable = ()):
    with _lock:
        con = _connect()
        try:
            cur = con.execute(query, tuple(params))
            return cur.lastrowid
        finally:
            con.close()


def exec_many(query: str, seq: Iterable[Iterable]):
    with _lock:
        con = _connect()
        try:
            con.executemany(query, [tuple(p) for p in seq])
        finally:
            con.close()


def query_all(query: str, params: Iterable = ()) -> list[dict]:
    with _lock:
        con = _connect()
        try:
            rows = con.execute(query, tuple(params)).fetchall()
            return [dict(r) for r in rows]
        finally:
            con.close()


def query_one(query: str, params: Iterable = ()) -> Optional[dict]:
    rows = query_all(query, params)
    return rows[0] if rows else None


# ---------- Jobs ----------
def create_job(filename: str, filepath: str, mime: str) -> str:
    jid = new_id()
    ts = now_iso()
    exec_write(
        "INSERT INTO jobs(id,filename,filepath,mime,status,stage,progress,created_at,updated_at) "
        "VALUES(?,?,?,?,?,?,?,?,?)",
        (jid, filename, filepath, mime, "pending", "uploaded", 0.0, ts, ts),
    )
    return jid


def update_job(job_id: str, **fields):
    if not fields:
        return
    fields["updated_at"] = now_iso()
    cols = ", ".join(f"{k}=?" for k in fields.keys())
    exec_write(f"UPDATE jobs SET {cols} WHERE id=?", list(fields.values()) + [job_id])


def get_job(job_id: str) -> Optional[dict]:
    row = query_one("SELECT * FROM jobs WHERE id=?", (job_id,))
    if row and row.get("meta"):
        try:
            row["meta"] = json.loads(row["meta"])
        except Exception:
            pass
    return row


def list_jobs(limit: int = 100) -> list[dict]:
    rows = query_all("SELECT id,filename,status,stage,progress,num_pages,error,created_at,updated_at FROM jobs ORDER BY created_at DESC LIMIT ?", (limit,))
    return rows


def delete_job(job_id: str):
    exec_write("DELETE FROM jobs WHERE id=?", (job_id,))


# ---------- Pages ----------
def add_page(job_id: str, page_index: int, width: int, height: int, raw_path: str, preview_path: str, rotation: float = 0.0, scale: float = 1.0) -> str:
    pid = new_id()
    exec_write(
        "INSERT INTO pages(id,job_id,page_index,width,height,raw_path,preview_path,rotation,scale) VALUES(?,?,?,?,?,?,?,?,?)",
        (pid, job_id, page_index, width, height, raw_path, preview_path, rotation, scale),
    )
    return pid


def get_pages(job_id: str) -> list[dict]:
    return query_all("SELECT * FROM pages WHERE job_id=? ORDER BY page_index", (job_id,))


# ---------- Entities ----------
def add_entities(job_id: str, entities: list[dict]) -> int:
    if not entities:
        return 0
    rows = []
    ts = now_iso()
    for e in entities:
        rows.append((
            e.get("id") or new_id(),
            job_id,
            int(e.get("page_index", 0)),
            e["kind"],
            json.dumps(e.get("data", {})),
            e.get("layer", "GEOMETRY"),
            float(e.get("confidence", 1.0)),
            int(bool(e.get("uncertain", False))),
            0,
            int(bool(e.get("modified", False))),
            e.get("rule_applied"),
            ts,
        ))
    exec_many(
        "INSERT INTO entities(id,job_id,page_index,kind,data,layer,confidence,uncertain,deleted,modified,rule_applied,created_at) "
        "VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
        rows,
    )
    return len(rows)


def get_entities(job_id: str, include_deleted: bool = False) -> list[dict]:
    q = "SELECT * FROM entities WHERE job_id=?"
    if not include_deleted:
        q += " AND deleted=0"
    q += " ORDER BY page_index, kind"
    rows = query_all(q, (job_id,))
    for r in rows:
        try:
            r["data"] = json.loads(r["data"])
        except Exception:
            r["data"] = {}
    return rows


def get_entity(entity_id: str) -> Optional[dict]:
    r = query_one("SELECT * FROM entities WHERE id=?", (entity_id,))
    if r:
        try:
            r["data"] = json.loads(r["data"])
        except Exception:
            r["data"] = {}
    return r


def update_entity(entity_id: str, **fields):
    if "data" in fields and not isinstance(fields["data"], str):
        fields["data"] = json.dumps(fields["data"])
    cols = ", ".join(f"{k}=?" for k in fields.keys())
    exec_write(f"UPDATE entities SET {cols} WHERE id=?", list(fields.values()) + [entity_id])


def soft_delete_entity(entity_id: str):
    exec_write("UPDATE entities SET deleted=1 WHERE id=?", (entity_id,))


def clear_entities(job_id: str):
    exec_write("DELETE FROM entities WHERE job_id=?", (job_id,))


# ---------- Rules ----------
def create_rule(pattern_signature: str, pattern_data: dict, action_type: str, action_data: dict, confidence: float = 0.6, notes: str = "") -> str:
    rid = new_id()
    exec_write(
        "INSERT INTO rules(id,pattern_signature,pattern_data,action_type,action_data,confidence,notes,created_at) "
        "VALUES(?,?,?,?,?,?,?,?)",
        (rid, pattern_signature, json.dumps(pattern_data or {}), action_type, json.dumps(action_data or {}), confidence, notes, now_iso()),
    )
    return rid


def list_rules(active_only: bool = False) -> list[dict]:
    q = "SELECT * FROM rules"
    if active_only:
        q += " WHERE active=1"
    q += " ORDER BY created_at DESC"
    rows = query_all(q)
    for r in rows:
        try:
            r["pattern_data"] = json.loads(r.get("pattern_data") or "{}")
        except Exception:
            r["pattern_data"] = {}
        try:
            r["action_data"] = json.loads(r.get("action_data") or "{}")
        except Exception:
            r["action_data"] = {}
    return rows


def get_rule(rule_id: str) -> Optional[dict]:
    r = query_one("SELECT * FROM rules WHERE id=?", (rule_id,))
    if r:
        try:
            r["pattern_data"] = json.loads(r.get("pattern_data") or "{}")
            r["action_data"] = json.loads(r.get("action_data") or "{}")
        except Exception:
            pass
    return r


def update_rule(rule_id: str, **fields):
    for k in ("pattern_data", "action_data"):
        if k in fields and not isinstance(fields[k], str):
            fields[k] = json.dumps(fields[k])
    cols = ", ".join(f"{k}=?" for k in fields.keys())
    exec_write(f"UPDATE rules SET {cols} WHERE id=?", list(fields.values()) + [rule_id])


def bump_rule(rule_id: str, success: bool = True):
    field = "successes" if success else "uses"
    # We always bump uses; successes optionally
    exec_write("UPDATE rules SET uses=uses+1, last_used=? WHERE id=?", (now_iso(), rule_id))
    if success:
        exec_write("UPDATE rules SET successes=successes+1 WHERE id=?", (rule_id,))


def delete_rule(rule_id: str):
    exec_write("DELETE FROM rules WHERE id=?", (rule_id,))


# ---------- Corrections ----------
def add_correction(job_id: str, entity_id: Optional[str], action_type: str, old_data: Any, new_data: Any, rule_id: Optional[str], apply_to_similar: bool) -> str:
    cid = new_id()
    exec_write(
        "INSERT INTO corrections(id,job_id,entity_id,action_type,old_data,new_data,rule_id,apply_to_similar,created_at) "
        "VALUES(?,?,?,?,?,?,?,?,?)",
        (cid, job_id, entity_id, action_type,
         json.dumps(old_data) if old_data is not None else None,
         json.dumps(new_data) if new_data is not None else None,
         rule_id, int(bool(apply_to_similar)), now_iso()),
    )
    return cid


# ---------- Logs ----------
def log(job_id: Optional[str], level: str, message: str):
    exec_write("INSERT INTO logs(job_id,level,message,created_at) VALUES(?,?,?,?)", (job_id, level, message, now_iso()))


def get_logs(job_id: str, limit: int = 200) -> list[dict]:
    return query_all("SELECT * FROM logs WHERE job_id=? ORDER BY id DESC LIMIT ?", (job_id, limit))


# Initialize on import
init_db()
