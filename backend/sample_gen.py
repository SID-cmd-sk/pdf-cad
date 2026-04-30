"""Generate a few synthetic scanned drawings to demonstrate the pipeline end-to-end."""
from __future__ import annotations
import math
import random
from pathlib import Path
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont


OUT_DIR = Path(__file__).resolve().parent.parent / "samples"
OUT_DIR.mkdir(parents=True, exist_ok=True)


def _font(size: int):
    # Try a few common fonts, fallback to default
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
    ]
    for f in candidates:
        if Path(f).exists():
            try:
                return ImageFont.truetype(f, size)
            except Exception:
                pass
    return ImageFont.load_default()


def _add_noise(img: np.ndarray, amount: float = 10) -> np.ndarray:
    noise = np.random.normal(0, amount, img.shape).astype(np.int16)
    out = np.clip(img.astype(np.int16) + noise, 0, 255).astype(np.uint8)
    return out


def _rotate(img: np.ndarray, angle: float) -> np.ndarray:
    h, w = img.shape[:2]
    M = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
    return cv2.warpAffine(img, M, (w, h), borderValue=(255, 255, 255))


def mechanical_part(path: Path):
    """A simple mechanical part with circles, lines, dimensions."""
    W, H = 1400, 1000
    im = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(im)
    font = _font(22)

    # Outer rectangle
    d.rectangle([220, 220, 1180, 780], outline="black", width=3)

    # Two circles (bolt holes)
    d.ellipse([260, 260, 340, 340], outline="black", width=3)
    d.ellipse([1060, 260, 1140, 340], outline="black", width=3)
    d.ellipse([260, 660, 340, 740], outline="black", width=3)
    d.ellipse([1060, 660, 1140, 740], outline="black", width=3)

    # Big center circle
    d.ellipse([600, 400, 800, 600], outline="black", width=3)
    # Small inner circle
    d.ellipse([670, 470, 730, 530], outline="black", width=3)

    # Arc / slot
    d.arc([400, 450, 560, 550], 0, 180, fill="black", width=3)
    d.line([400, 500, 560, 500], fill="white", width=0)  # open arc

    # Dimension lines (with arrowheads drawn as small triangles)
    d.line([220, 160, 1180, 160], fill="black", width=2)
    d.line([220, 150, 220, 170], fill="black", width=2)
    d.line([1180, 150, 1180, 170], fill="black", width=2)
    d.text((670, 120), "960mm", fill="black", font=font)

    d.line([170, 220, 170, 780], fill="black", width=2)
    d.line([160, 220, 180, 220], fill="black", width=2)
    d.line([160, 780, 180, 780], fill="black", width=2)
    d.text((80, 490), "560mm", fill="black", font=font)

    # Labels
    d.text((680, 610), "Ø200", fill="black", font=font)
    d.text((640, 830), "BRACKET PLATE", fill="black", font=_font(28))
    d.text((640, 870), "PART-001 / REV A", fill="black", font=font)

    arr = np.array(im)
    arr = _rotate(arr, angle=random.uniform(-1.2, 1.2))
    arr = _add_noise(arr, amount=6)
    cv2.imwrite(str(path), cv2.cvtColor(arr, cv2.COLOR_RGB2BGR))


def floor_plan(path: Path):
    W, H = 1600, 1100
    im = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(im)
    font = _font(20)

    # Outer walls
    d.rectangle([120, 120, 1480, 980], outline="black", width=4)
    # Inner walls
    d.line([700, 120, 700, 600], fill="black", width=3)
    d.line([120, 600, 1480, 600], fill="black", width=3)
    d.line([1000, 600, 1000, 980], fill="black", width=3)
    # Doors (arcs)
    d.arc([660, 560, 760, 660], 180, 270, fill="black", width=2)
    d.arc([960, 560, 1060, 660], 180, 270, fill="black", width=2)
    # Windows (double lines)
    d.line([200, 120, 400, 120], fill="black", width=2)
    d.line([200, 130, 400, 130], fill="black", width=2)
    d.line([900, 120, 1100, 120], fill="black", width=2)
    d.line([900, 130, 1100, 130], fill="black", width=2)

    # Labels
    d.text((380, 340), "LIVING ROOM", fill="black", font=font)
    d.text((1080, 340), "BEDROOM 1", fill="black", font=font)
    d.text((380, 770), "KITCHEN", fill="black", font=font)
    d.text((1160, 770), "BATH", fill="black", font=font)
    d.text((640, 1020), "FLOOR PLAN — SCALE 1:50", fill="black", font=_font(24))

    # Dimensions
    d.line([120, 80, 1480, 80], fill="black", width=2)
    d.line([120, 70, 120, 90], fill="black", width=2)
    d.line([1480, 70, 1480, 90], fill="black", width=2)
    d.text((720, 40), "13600mm", fill="black", font=font)

    arr = np.array(im)
    arr = _rotate(arr, angle=random.uniform(-0.8, 0.8))
    arr = _add_noise(arr, amount=5)
    cv2.imwrite(str(path), cv2.cvtColor(arr, cv2.COLOR_RGB2BGR))


def geometry_demo(path: Path):
    W, H = 1200, 900
    im = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(im)
    font = _font(18)
    # grid of shapes
    d.line([100, 200, 400, 200], fill="black", width=3)
    d.line([500, 150, 500, 500], fill="black", width=3)
    d.line([600, 150, 900, 450], fill="black", width=3)
    d.ellipse([150, 350, 350, 550], outline="black", width=3)
    d.arc([500, 550, 700, 750], 0, 180, fill="black", width=3)
    d.polygon([(850, 600), (1050, 600), (1100, 750), (800, 750)], outline="black", width=3)
    d.text((100, 100), "GEOMETRY SAMPLE", fill="black", font=_font(26))
    d.text((100, 820), "Ø200  L=300  R=100", fill="black", font=font)

    arr = np.array(im)
    arr = _add_noise(arr, amount=3)
    cv2.imwrite(str(path), cv2.cvtColor(arr, cv2.COLOR_RGB2BGR))


def build_all():
    mechanical_part(OUT_DIR / "mechanical_part.png")
    floor_plan(OUT_DIR / "floor_plan.png")
    geometry_demo(OUT_DIR / "geometry_demo.png")
    print(f"Samples written to {OUT_DIR}")


if __name__ == "__main__":
    build_all()
