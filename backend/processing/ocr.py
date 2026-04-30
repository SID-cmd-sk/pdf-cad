"""Local OCR via Tesseract. Extracts text blocks with bounding boxes."""
from __future__ import annotations
import re
import cv2
import numpy as np

try:
    import pytesseract
    _HAS_TESSERACT = True
except Exception:
    _HAS_TESSERACT = False


DIMENSION_RE = re.compile(r"^\s*[ØRø]?\d+(?:[.,]\d+)?\s*(?:mm|cm|m|in|\")?\s*$", re.IGNORECASE)


def is_dimension_text(text: str) -> bool:
    t = text.strip()
    if not t:
        return False
    if DIMENSION_RE.match(t):
        return True
    # "12x34", "R5", "Ø20"
    if re.match(r"^[ØRø]\d+", t):
        return True
    if re.match(r"^\d+\s*[xX]\s*\d+$", t):
        return True
    return False


def extract_text(gray: np.ndarray) -> list[dict]:
    """Run tesseract on a grayscale image, return text entities."""
    if not _HAS_TESSERACT:
        return []
    # Invert if the image is mostly white-on-black (binary inv style)
    work = gray
    if work.mean() < 80:
        work = cv2.bitwise_not(work)
    # Upscale tiny images to help OCR
    h, w = work.shape[:2]
    if max(h, w) < 1500:
        scale = 1500 / max(h, w)
        work = cv2.resize(work, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_CUBIC)
        s = scale
    else:
        s = 1.0

    try:
        data = pytesseract.image_to_data(
            work,
            config="--oem 3 --psm 6 -c tessedit_char_whitelist=0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz.,+-xX°ØR\"'/()[]",
            output_type=pytesseract.Output.DICT,
        )
    except Exception:
        return []

    out: list[dict] = []
    n = len(data.get("text", []))
    for i in range(n):
        txt = (data["text"][i] or "").strip()
        if not txt:
            continue
        try:
            conf = float(data["conf"][i])
        except Exception:
            conf = -1.0
        if conf < 30:
            continue
        x = data["left"][i] / s
        y = data["top"][i] / s
        tw = data["width"][i] / s
        th = data["height"][i] / s
        kind = "dimension" if is_dimension_text(txt) else "text"
        layer = "DIMENSIONS" if kind == "dimension" else "TEXT"
        out.append({
            "kind": kind,
            "data": {"text": txt, "x": x, "y": y, "width": tw, "height": th, "ocr_conf": conf},
            "confidence": max(0.3, conf / 100.0),
            "layer": layer,
            "uncertain": conf < 70,
        })
    return out
