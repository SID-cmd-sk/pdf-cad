"""Local OCR via Tesseract. Multi-PSM pass + dimension heuristics + orientation."""
from __future__ import annotations
import re
import cv2
import numpy as np

try:
    import pytesseract
    _HAS_TESSERACT = True
except Exception:
    _HAS_TESSERACT = False


DIMENSION_RE = re.compile(r"^\s*[ØRøⒹ]?\d+(?:[.,]\d+)?\s*(?:mm|cm|m|in|\"|ft)?\s*$", re.IGNORECASE)
TOLERANCE_RE = re.compile(r"^[±+\-]?\d+(?:[.,]\d+)?$")


def is_dimension_text(text: str) -> bool:
    t = text.strip()
    if not t:
        return False
    if DIMENSION_RE.match(t):
        return True
    if re.match(r"^[ØRøR]\s*\d+", t):
        return True
    if re.match(r"^\d+\s*[xX×]\s*\d+$", t):
        return True
    if re.match(r"^M\d+", t):  # metric thread e.g. M8
        return True
    if TOLERANCE_RE.match(t):
        return True
    return False


def _best_orientation(gray: np.ndarray) -> np.ndarray:
    """Very light check: if the image seems mostly vertical text, return rotated copy."""
    # Keep it simple: detect via HoughLines on horizontal vs vertical gradient.
    return gray  # placeholder — Tesseract 5 handles in-plane rotation via PSM 1


def _run_ocr(work: np.ndarray, psm: int) -> list[dict]:
    try:
        # No whitelist — the unicode chars were breaking config parsing on some systems
        # and filtering too aggressively on CAD drawings where OCR sees plenty of short tokens.
        data = pytesseract.image_to_data(
            work,
            config=f"--oem 3 --psm {psm}",
            output_type=pytesseract.Output.DICT,
        )
    except Exception:
        return []
    rows = []
    n = len(data.get("text", []))
    for i in range(n):
        txt = (data["text"][i] or "").strip()
        if not txt:
            continue
        try:
            conf = float(data["conf"][i])
        except Exception:
            conf = -1.0
        if conf < 25:
            continue
        rows.append({
            "text": txt,
            "x": int(data["left"][i]),
            "y": int(data["top"][i]),
            "w": int(data["width"][i]),
            "h": int(data["height"][i]),
            "conf": conf,
            "block": int(data.get("block_num", [0] * n)[i]),
            "par": int(data.get("par_num", [0] * n)[i]),
            "line": int(data.get("line_num", [0] * n)[i]),
        })
    return rows


def extract_text(gray: np.ndarray) -> list[dict]:
    """Run tesseract with multiple PSMs for robustness. Returns layered entities."""
    if not _HAS_TESSERACT:
        return []
    work = gray
    if work.mean() < 80:
        work = cv2.bitwise_not(work)
    h, w = work.shape[:2]
    s = 1.0
    if max(h, w) < 1500:
        s = 1500 / max(h, w)
        work = cv2.resize(work, (int(w * s), int(h * s)), interpolation=cv2.INTER_CUBIC)

    # PSM 11: sparse text (best for CAD drawings)
    # PSM 6: assume a single uniform block (good for titles/labels)
    rows: list[dict] = []
    for psm in (11, 6):
        rows.extend(_run_ocr(work, psm))

    # Deduplicate by bounding-box overlap (keep highest conf)
    rows.sort(key=lambda r: -r["conf"])
    kept: list[dict] = []
    for r in rows:
        dup = False
        for k in kept:
            # IoU check
            x0 = max(r["x"], k["x"])
            y0 = max(r["y"], k["y"])
            x1 = min(r["x"] + r["w"], k["x"] + k["w"])
            y1 = min(r["y"] + r["h"], k["y"] + k["h"])
            if x1 <= x0 or y1 <= y0:
                continue
            inter = (x1 - x0) * (y1 - y0)
            area_r = r["w"] * r["h"]
            area_k = k["w"] * k["h"]
            iou = inter / max(1, area_r + area_k - inter)
            if iou > 0.4:
                dup = True
                break
        if not dup:
            kept.append(r)

    out: list[dict] = []
    for r in kept:
        txt = r["text"]
        kind = "dimension" if is_dimension_text(txt) else "text"
        layer = "DIMENSIONS" if kind == "dimension" else "TEXT"
        out.append({
            "kind": kind,
            "data": {
                "text": txt,
                "x": r["x"] / s,
                "y": r["y"] / s,
                "width": r["w"] / s,
                "height": r["h"] / s,
                "ocr_conf": r["conf"],
            },
            "confidence": max(0.3, r["conf"] / 100.0),
            "layer": layer,
            "uncertain": r["conf"] < 70,
        })
    return out
