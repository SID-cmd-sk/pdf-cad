"""Rule-based learning engine.

Pattern signatures are deterministic and human-readable:
  - "short_line<10"          lines shorter than a given length
  - "low_coverage_arc<0.6"   arcs with coverage fraction below threshold
  - "many_vertex_poly>12"    noisy polygons with > N vertices
  - "low_conf_text<0.5"      low-confidence text
  - "dim_text_value:<normalised>"  specific dimension text substitution
  - "entity:line->arc"        explicit conversion seen before

Action types:
  - delete
  - convert      (change kind; e.g., line -> arc)
  - edit_text    (replace text)
  - snap         (set params)
  - merge
  - close_shape
"""
from __future__ import annotations
import math
from typing import Any

from storage import db


# ---------- Pattern signatures ----------

def line_signature(d: dict) -> list[str]:
    length = d.get("length") or math.hypot(d["x2"] - d["x1"], d["y2"] - d["y1"])
    sigs = []
    if length < 10:
        sigs.append("short_line<10")
    elif length < 25:
        sigs.append("short_line<25")
    return sigs


def arc_signature(d: dict) -> list[str]:
    cov = d.get("coverage", 1.0)
    sigs = []
    if cov < 0.6:
        sigs.append("low_coverage_arc<0.6")
    if cov < 0.4:
        sigs.append("low_coverage_arc<0.4")
    return sigs


def circle_signature(d: dict) -> list[str]:
    cov = d.get("coverage", 1.0)
    sigs = []
    if cov < 0.9:
        sigs.append("broken_circle<0.9")
    if cov < 0.8:
        sigs.append("broken_circle<0.8")
    return sigs


def poly_signature(d: dict) -> list[str]:
    pts = d.get("points", [])
    sigs = []
    if len(pts) > 12:
        sigs.append("many_vertex_poly>12")
    if len(pts) > 20:
        sigs.append("many_vertex_poly>20")
    return sigs


def text_signature(e: dict) -> list[str]:
    d = e["data"]
    sigs = []
    if e.get("confidence", 1.0) < 0.5:
        sigs.append("low_conf_text<0.5")
    t = (d.get("text") or "").strip()
    if t:
        sigs.append(f"text_value:{t.lower()}")
    return sigs


def entity_signatures(e: dict) -> list[str]:
    kind = e["kind"]
    d = e.get("data", {})
    if kind == "line":
        return line_signature(d)
    if kind == "circle":
        return circle_signature(d)
    if kind == "arc":
        return arc_signature(d)
    if kind == "polyline":
        return poly_signature(d)
    if kind in ("text", "dimension"):
        return text_signature(e)
    return []


# ---------- Applying rules ----------

def apply_rules(entities: list[dict]) -> tuple[list[dict], int]:
    """Apply active rules to entities. Returns (entities, num_applied)."""
    rules = db.list_rules(active_only=True)
    if not rules:
        return entities, 0

    # Index rules by signature
    by_sig: dict[str, list[dict]] = {}
    for r in rules:
        by_sig.setdefault(r["pattern_signature"], []).append(r)

    count = 0
    result: list[dict] = []
    for e in entities:
        sigs = entity_signatures(e)
        applied_rule = None
        for sig in sigs:
            matches = by_sig.get(sig, [])
            if not matches:
                continue
            # Pick best rule (highest confidence * success_ratio)
            matches.sort(key=lambda r: (r["confidence"], (r["successes"] + 1) / (r["uses"] + 1)), reverse=True)
            rule = matches[0]
            action = rule["action_type"]
            data = rule.get("action_data") or {}
            if action == "delete":
                e["deleted"] = True
                e["modified"] = True
            elif action == "convert":
                target = data.get("to_kind")
                if target == "arc" and e["kind"] == "circle":
                    # convert full circle to arc with given coverage (default 0.6 half)
                    e["kind"] = "arc"
                    e["data"]["start_angle"] = data.get("start_angle", 0.0)
                    e["data"]["end_angle"] = data.get("end_angle", math.pi)
                    e["modified"] = True
                elif target == "circle" and e["kind"] == "arc":
                    e["kind"] = "circle"
                    # clean arc-specific fields
                    e["data"].pop("start_angle", None)
                    e["data"].pop("end_angle", None)
                    e["modified"] = True
                elif target == "line" and e["kind"] == "polyline":
                    pts = e["data"].get("points", [])
                    if len(pts) >= 2:
                        e["kind"] = "line"
                        e["data"] = {"x1": pts[0][0], "y1": pts[0][1], "x2": pts[-1][0], "y2": pts[-1][1]}
                        e["modified"] = True
            elif action == "edit_text":
                new_text = data.get("text")
                if new_text and e["kind"] in ("text", "dimension"):
                    e["data"]["text"] = new_text
                    e["uncertain"] = False
                    e["modified"] = True
            elif action == "close_shape" and e["kind"] == "polyline":
                e["data"]["closed"] = True
                e["modified"] = True
            elif action == "mark_certain":
                e["uncertain"] = False
                e["modified"] = True
            applied_rule = rule["id"]
            db.bump_rule(rule["id"], success=True)
            count += 1
            break
        if applied_rule:
            e["rule_applied"] = applied_rule
        result.append(e)
    return result, count


# ---------- Learning from correction ----------

def record_correction(job_id: str, entity_before: dict | None, action_type: str, new_data: dict | None, apply_to_similar: bool, notes: str = "") -> str | None:
    """Store a correction. Optionally create/strengthen a rule from it.
    Returns the created/updated rule_id, or None if no rule generated.
    """
    old_data = entity_before.get("data") if entity_before else None
    entity_id = entity_before.get("id") if entity_before else None
    rule_id: str | None = None

    if apply_to_similar and entity_before is not None:
        sigs = entity_signatures(entity_before)
        # pick the most specific signature
        if sigs:
            sig = sigs[0]
            # Build action_data
            action_data: dict[str, Any] = {}
            if action_type == "convert" and new_data:
                action_data["to_kind"] = new_data.get("to_kind")
                if action_data["to_kind"] == "arc":
                    action_data["start_angle"] = new_data.get("start_angle", 0.0)
                    action_data["end_angle"] = new_data.get("end_angle", math.pi)
            elif action_type == "edit_text" and new_data:
                action_data["text"] = new_data.get("text", "")
            elif action_type == "delete":
                action_data = {}
            elif action_type == "close_shape":
                action_data = {}
            elif action_type == "mark_certain":
                action_data = {}
            # Check if rule already exists
            existing = db.list_rules()
            match = None
            for r in existing:
                if r["pattern_signature"] == sig and r["action_type"] == action_type and r.get("action_data") == action_data:
                    match = r
                    break
            if match:
                rule_id = match["id"]
                db.update_rule(rule_id, confidence=min(1.0, match["confidence"] + 0.1))
            else:
                rule_id = db.create_rule(
                    pattern_signature=sig,
                    pattern_data={"from_kind": entity_before.get("kind")},
                    action_type=action_type,
                    action_data=action_data,
                    confidence=0.6,
                    notes=notes or "",
                )

    db.add_correction(job_id, entity_id, action_type, old_data, new_data, rule_id, apply_to_similar)
    return rule_id


def seed_default_rules():
    """Seed a pragmatic library of rules common to CAD drawings."""
    existing = db.list_rules()
    if existing:
        return
    seeds = [
        # noise cleanup
        ("short_line<10", "line", "delete", {}, 0.6, "Delete tiny line fragments under 10 px (noise)."),
        ("short_line<25", "line", "mark_certain", {}, 0.4, "Short lines are usually fine; keep but de-flag."),
        ("many_vertex_poly>20", "polyline", "delete", {}, 0.55, "Very noisy polygons (>20 vertices)."),
        ("many_vertex_poly>12", "polyline", "mark_certain", {}, 0.3, "Moderately jagged polygons — keep."),
        # arc/circle disambiguation
        ("low_coverage_arc<0.4", "arc", "delete", {}, 0.5, "Arcs with <40% support are usually detection noise."),
        ("low_coverage_arc<0.6", "arc", "mark_certain", {}, 0.4, "Low-coverage arcs — likely real but approximate."),
        ("broken_circle<0.9", "circle", "mark_certain", {}, 0.5, "Mostly complete circles, typical of scans."),
        ("broken_circle<0.8", "circle", "convert", {"to_kind": "arc", "start_angle": 0.0, "end_angle": 3.14159}, 0.4, "Heavily broken circles likely want to be arcs."),
        # OCR fixes (common Tesseract confusions on CAD)
        ("text_value:o", "text", "edit_text", {"text": "0"}, 0.7, "Lone O → 0 (dim numeric context)."),
        ("text_value:l", "text", "edit_text", {"text": "1"}, 0.65, "Lone l → 1."),
        ("text_value:s", "text", "edit_text", {"text": "5"}, 0.5, "Lone S → 5 (dim)."),
        ("text_value:b", "text", "edit_text", {"text": "8"}, 0.45, "Lone B → 8 (dim)."),
        ("low_conf_text<0.5", "text", "mark_certain", {}, 0.3, "Low-confidence text — keep but de-flag."),
    ]
    for sig, from_kind, act, act_data, conf, notes in seeds:
        db.create_rule(
            pattern_signature=sig,
            pattern_data={"from_kind": from_kind},
            action_type=act,
            action_data=act_data,
            confidence=conf,
            notes=notes,
        )
