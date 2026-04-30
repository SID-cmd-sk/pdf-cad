"""Export entities to DXF with layered output."""
from __future__ import annotations
from pathlib import Path
from typing import Iterable
import math
import ezdxf


LAYER_COLORS = {
    "GEOMETRY": 7,       # white
    "TEXT": 4,           # cyan
    "DIMENSIONS": 3,     # green
    "UNCERTAIN": 1,      # red
}


def _ensure_layers(doc):
    for name, color in LAYER_COLORS.items():
        if name not in doc.layers:
            doc.layers.add(name=name, color=color)


def entities_to_dxf(entities: list[dict], out_path: str | Path, page_height: float | None = None) -> str:
    """Write entities to a DXF file. Y axis is flipped (image y -> DXF y = page_height - y)."""
    doc = ezdxf.new(setup=True)
    _ensure_layers(doc)
    msp = doc.modelspace()

    def fy(y: float) -> float:
        if page_height is None:
            return float(-y)
        return float(page_height - y)

    for e in entities:
        if e.get("deleted"):
            continue
        layer = e.get("layer", "GEOMETRY")
        if e.get("uncertain"):
            layer = "UNCERTAIN"
        kind = e["kind"]
        d = e.get("data", {})
        try:
            if kind == "line":
                msp.add_line((float(d["x1"]), fy(d["y1"])), (float(d["x2"]), fy(d["y2"])), dxfattribs={"layer": layer})
            elif kind == "circle":
                msp.add_circle((float(d["cx"]), fy(d["cy"])), float(d["r"]), dxfattribs={"layer": layer})
            elif kind == "arc":
                # In DXF arcs go counter-clockwise. Since y is flipped, invert angles.
                sa = math.degrees(float(d["start_angle"]))
                ea = math.degrees(float(d["end_angle"]))
                # After y-flip arc orientation reverses → swap angles
                msp.add_arc(
                    center=(float(d["cx"]), fy(d["cy"])),
                    radius=float(d["r"]),
                    start_angle=-ea,
                    end_angle=-sa,
                    dxfattribs={"layer": layer},
                )
            elif kind == "polyline":
                pts = d.get("points", [])
                xy = [(float(p[0]), fy(float(p[1]))) for p in pts]
                if len(xy) >= 2:
                    close = bool(d.get("closed"))
                    msp.add_lwpolyline(xy, close=close, dxfattribs={"layer": layer})
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
            # Skip malformed entity but keep going
            continue

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    doc.saveas(str(out_path))
    return str(out_path)
