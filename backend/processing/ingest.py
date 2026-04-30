"""Ingest PDFs/images. Detects vector vs raster PDFs and rasterizes pages."""
from __future__ import annotations
from pathlib import Path
from typing import Iterator
import mimetypes
import numpy as np
import cv2
from PIL import Image

try:
    import fitz  # PyMuPDF
except Exception:
    fitz = None


TARGET_DPI = 200
MAX_DIM = 3500  # cap to avoid memory blowup


def is_pdf(path: str | Path) -> bool:
    return str(path).lower().endswith(".pdf")


def is_image(path: str | Path) -> bool:
    p = str(path).lower()
    return p.endswith((".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".webp"))


def load_image(path: str | Path) -> np.ndarray:
    """Load one image (PNG/JPG) into BGR numpy array."""
    img = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if img is None:
        # Fallback via Pillow (handles more formats / EXIF)
        with Image.open(path) as im:
            im = im.convert("RGB")
            img = cv2.cvtColor(np.array(im), cv2.COLOR_RGB2BGR)
    return _cap_size(img)


def _cap_size(img: np.ndarray) -> np.ndarray:
    h, w = img.shape[:2]
    m = max(h, w)
    if m > MAX_DIM:
        scale = MAX_DIM / m
        img = cv2.resize(img, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
    return img


def pdf_is_vector(path: str | Path) -> bool:
    """Heuristic: consider a PDF vector if any page contains drawings (paths) with stroke/fill."""
    if fitz is None:
        return False
    try:
        with fitz.open(str(path)) as doc:
            for page in doc:
                d = page.get_drawings()
                if d and len(d) > 5:
                    return True
        return False
    except Exception:
        return False


def pdf_iter_pages(path: str | Path) -> Iterator[tuple[int, np.ndarray]]:
    """Rasterize every page of a PDF at TARGET_DPI."""
    if fitz is None:
        raise RuntimeError("PyMuPDF (fitz) not installed")
    with fitz.open(str(path)) as doc:
        for i, page in enumerate(doc):
            # Use a matrix corresponding to TARGET_DPI (default is 72 dpi)
            zoom = TARGET_DPI / 72.0
            mat = fitz.Matrix(zoom, zoom)
            pix = page.get_pixmap(matrix=mat, alpha=False)
            img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
            if pix.n == 4:
                img = cv2.cvtColor(img, cv2.COLOR_RGBA2BGR)
            elif pix.n == 1:
                img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
            else:
                img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
            yield i, _cap_size(img)


def pdf_vector_entities(path: str | Path) -> list[list[dict]]:
    """Extract vector drawings from a PDF, returns list-per-page of primitive dicts (in pixel space of rendering).
    Coordinates are in PDF user space (points). Caller should scale if it combined with rasterized images.
    """
    out: list[list[dict]] = []
    if fitz is None:
        return out
    with fitz.open(str(path)) as doc:
        for page in doc:
            entities: list[dict] = []
            zoom = TARGET_DPI / 72.0
            page_h = page.rect.height * zoom
            for d in page.get_drawings():
                for item in d.get("items", []):
                    op = item[0]
                    if op == "l":  # line
                        p1, p2 = item[1], item[2]
                        entities.append({
                            "kind": "line",
                            "data": {
                                "x1": p1.x * zoom, "y1": page_h - p1.y * zoom,
                                "x2": p2.x * zoom, "y2": page_h - p2.y * zoom,
                            },
                            "confidence": 1.0,
                            "layer": "GEOMETRY",
                        })
                    elif op == "c":  # bezier curve -> approximate as polyline
                        pts = [(p.x * zoom, page_h - p.y * zoom) for p in item[1:]]
                        entities.append({
                            "kind": "polyline",
                            "data": {"points": pts},
                            "confidence": 1.0,
                            "layer": "GEOMETRY",
                        })
                    elif op == "re":  # rectangle
                        r = item[1]
                        x, y, w, h = r.x0 * zoom, page_h - r.y1 * zoom, (r.x1 - r.x0) * zoom, (r.y1 - r.y0) * zoom
                        entities.append({
                            "kind": "polyline",
                            "data": {"points": [(x, y), (x + w, y), (x + w, y + h), (x, y + h), (x, y)], "closed": True},
                            "confidence": 1.0,
                            "layer": "GEOMETRY",
                        })
                    elif op == "qu":  # quad
                        pts = [(p.x * zoom, page_h - p.y * zoom) for p in item[1]]
                        entities.append({
                            "kind": "polyline",
                            "data": {"points": pts + [pts[0]], "closed": True},
                            "confidence": 1.0,
                            "layer": "GEOMETRY",
                        })
            # Text
            try:
                for block in page.get_text("dict").get("blocks", []):
                    for line in block.get("lines", []):
                        for span in line.get("spans", []):
                            bbox = span.get("bbox")
                            text = span.get("text", "").strip()
                            if not text or not bbox:
                                continue
                            x0, y0, x1, y1 = bbox
                            entities.append({
                                "kind": "text",
                                "data": {
                                    "text": text,
                                    "x": x0 * zoom,
                                    "y": page_h - y1 * zoom,
                                    "height": (y1 - y0) * zoom,
                                },
                                "confidence": 1.0,
                                "layer": "TEXT",
                            })
            except Exception:
                pass
            out.append(entities)
    return out


def mime_of(path: str | Path) -> str:
    t, _ = mimetypes.guess_type(str(path))
    return t or "application/octet-stream"
