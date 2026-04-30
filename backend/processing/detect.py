"""Geometry detection: lines, circles, arcs, polygons/contours."""
from __future__ import annotations
import math
import numpy as np
import cv2


# --------- LINES ---------

def detect_lines(binary: np.ndarray, min_length_px: int = 40) -> list[dict]:
    """Probabilistic Hough Transform on binary image. Returns line dicts."""
    edges = cv2.Canny(binary, 50, 150, apertureSize=3, L2gradient=True)
    # LineSegmentDetector is deprecated; use HoughLinesP
    lines = cv2.HoughLinesP(
        edges,
        rho=1,
        theta=np.pi / 360,
        threshold=60,
        minLineLength=min_length_px,
        maxLineGap=8,
    )
    out: list[dict] = []
    if lines is None:
        return out
    for l in lines:
        x1, y1, x2, y2 = l[0]
        length = math.hypot(x2 - x1, y2 - y1)
        out.append({
            "kind": "line",
            "data": {"x1": float(x1), "y1": float(y1), "x2": float(x2), "y2": float(y2), "length": length},
            "confidence": min(1.0, 0.5 + length / 400.0),
            "layer": "GEOMETRY",
        })
    return out


def _angle_of(l: dict) -> float:
    d = l["data"]
    return math.atan2(d["y2"] - d["y1"], d["x2"] - d["x1"])


def merge_collinear_lines(lines: list[dict], angle_tol_deg: float = 3.0, dist_tol: float = 6.0, gap_tol: float = 15.0) -> list[dict]:
    """Merge line segments that are nearly collinear and close."""
    if not lines:
        return lines
    items = []
    for l in lines:
        d = l["data"]
        items.append({"a": np.array([d["x1"], d["y1"]]), "b": np.array([d["x2"], d["y2"]]), "l": l})

    used = [False] * len(items)
    merged = []
    ang_tol = math.radians(angle_tol_deg)

    for i in range(len(items)):
        if used[i]:
            continue
        ai, bi = items[i]["a"], items[i]["b"]
        ang_i = math.atan2(bi[1] - ai[1], bi[0] - ai[0])
        cluster_pts = [ai, bi]
        conf_best = items[i]["l"]["confidence"]
        used[i] = True
        for j in range(i + 1, len(items)):
            if used[j]:
                continue
            aj, bj = items[j]["a"], items[j]["b"]
            ang_j = math.atan2(bj[1] - aj[1], bj[0] - aj[0])
            dang = abs(((ang_i - ang_j + math.pi) % math.pi) - math.pi / 2) - math.pi / 2
            dang = abs(dang)
            if dang > ang_tol and abs(math.pi - dang) > ang_tol:
                continue
            # Perpendicular distance from j to line i
            v = bi - ai
            n = np.array([-v[1], v[0]])
            nn = np.linalg.norm(n)
            if nn < 1e-5:
                continue
            n = n / nn
            if abs(np.dot(aj - ai, n)) > dist_tol:
                continue
            if abs(np.dot(bj - ai, n)) > dist_tol:
                continue
            # Gap check along direction
            u = v / max(np.linalg.norm(v), 1e-5)
            proj_i = sorted([np.dot(ai - ai, u), np.dot(bi - ai, u)])
            proj_j = sorted([np.dot(aj - ai, u), np.dot(bj - ai, u)])
            gap = max(proj_j[0] - proj_i[1], proj_i[0] - proj_j[1])
            if gap > gap_tol:
                continue
            cluster_pts.extend([aj, bj])
            conf_best = max(conf_best, items[j]["l"]["confidence"])
            used[j] = True
        # Build the merged line as endpoints farthest along principal direction
        cluster = np.stack(cluster_pts)
        u = np.array([math.cos(ang_i), math.sin(ang_i)])
        proj = cluster @ u
        lo_idx = int(np.argmin(proj))
        hi_idx = int(np.argmax(proj))
        p1 = cluster[lo_idx].tolist()
        p2 = cluster[hi_idx].tolist()
        length = math.hypot(p2[0] - p1[0], p2[1] - p1[1])
        merged.append({
            "kind": "line",
            "data": {"x1": p1[0], "y1": p1[1], "x2": p2[0], "y2": p2[1], "length": length},
            "confidence": float(min(1.0, conf_best + 0.1)),
            "layer": "GEOMETRY",
        })
    return merged


# --------- CIRCLES / ARCS ---------

def detect_circles(gray: np.ndarray) -> list[dict]:
    """Hough circle transform. Accepts a grayscale image (not binary)."""
    blurred = cv2.medianBlur(gray, 3)
    out: list[dict] = []
    # Try a couple of parameter sets for robustness
    for param2 in (45, 35, 28):
        circles = cv2.HoughCircles(
            blurred,
            cv2.HOUGH_GRADIENT,
            dp=1.2,
            minDist=25,
            param1=120,
            param2=param2,
            minRadius=8,
            maxRadius=min(gray.shape) // 2,
        )
        if circles is not None:
            for c in circles[0]:
                x, y, r = float(c[0]), float(c[1]), float(c[2])
                # Avoid duplicates
                dup = False
                for e in out:
                    d = e["data"]
                    if math.hypot(d["cx"] - x, d["cy"] - y) < max(8, 0.2 * r) and abs(d["r"] - r) < max(5, 0.15 * r):
                        dup = True
                        break
                if not dup:
                    out.append({
                        "kind": "circle",
                        "data": {"cx": x, "cy": y, "r": r},
                        "confidence": 0.7 if param2 == 45 else (0.55 if param2 == 35 else 0.4),
                        "layer": "GEOMETRY",
                    })
            if out:
                break
    return out


def classify_arc_vs_circle(binary: np.ndarray, circles: list[dict]) -> list[dict]:
    """For each 'circle', estimate what fraction of its perimeter is actually drawn.
    If fraction < 0.85 → arc, else circle. Arc carries start/end angles approx."""
    h, w = binary.shape
    out: list[dict] = []
    for c in circles:
        d = c["data"]
        cx, cy, r = d["cx"], d["cy"], d["r"]
        n = max(72, int(2 * math.pi * r))
        n = min(n, 720)
        hits = np.zeros(n, dtype=bool)
        for k in range(n):
            a = 2 * math.pi * k / n
            px = int(round(cx + r * math.cos(a)))
            py = int(round(cy + r * math.sin(a)))
            ok = False
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    xx = px + dx
                    yy = py + dy
                    if 0 <= xx < w and 0 <= yy < h and binary[yy, xx] > 0:
                        ok = True
                        break
                if ok:
                    break
            hits[k] = ok
        frac = float(hits.sum()) / n
        if frac < 0.5:
            # Too little support — discard
            continue
        if frac >= 0.85:
            out.append({
                "kind": "circle",
                "data": {"cx": cx, "cy": cy, "r": r, "coverage": frac},
                "confidence": min(1.0, 0.6 + frac * 0.4),
                "layer": "GEOMETRY",
                "uncertain": frac < 0.9,
            })
        else:
            # Find longest contiguous arc
            best_len = 0
            best_start = 0
            # Double the array to handle wrap-around
            doubled = np.concatenate([hits, hits])
            cur_len = 0
            cur_start = 0
            for i in range(len(doubled)):
                if doubled[i]:
                    if cur_len == 0:
                        cur_start = i
                    cur_len += 1
                    if cur_len > best_len:
                        best_len = cur_len
                        best_start = cur_start
                else:
                    cur_len = 0
            a_start = (best_start % n) * 2 * math.pi / n
            a_end = ((best_start + best_len - 1) % n) * 2 * math.pi / n
            out.append({
                "kind": "arc",
                "data": {
                    "cx": cx, "cy": cy, "r": r,
                    "start_angle": a_start, "end_angle": a_end,
                    "coverage": frac,
                },
                "confidence": max(0.35, 0.3 + frac * 0.5),
                "layer": "GEOMETRY",
                "uncertain": True,  # arcs are often misclassified — mark uncertain
            })
    return out


# --------- CONTOURS / POLYGONS ---------

def detect_contours(binary: np.ndarray, min_area: float = 80.0) -> list[dict]:
    """Find closed contours and approximate as polylines/polygons."""
    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    out: list[dict] = []
    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area < min_area:
            continue
        peri = cv2.arcLength(cnt, True)
        if peri < 40:
            continue
        approx = cv2.approxPolyDP(cnt, 0.01 * peri, True)
        pts = [[float(p[0][0]), float(p[0][1])] for p in approx]
        if len(pts) < 3:
            continue
        # Skip if it's basically a circle (keep circle detection instead)
        (x, y), rr = cv2.minEnclosingCircle(cnt)
        circularity = 4 * math.pi * area / (peri ** 2) if peri else 0
        if circularity > 0.85 and len(pts) >= 8:
            continue
        out.append({
            "kind": "polyline",
            "data": {"points": pts, "closed": True, "area": area},
            "confidence": 0.6,
            "layer": "GEOMETRY",
            "uncertain": len(pts) > 12,  # too-many-vertex polys often noisy
        })
    return out


def detect_all(binary: np.ndarray, gray: np.ndarray) -> list[dict]:
    lines = detect_lines(binary)
    lines = merge_collinear_lines(lines)
    circles_raw = detect_circles(gray)
    circles_and_arcs = classify_arc_vs_circle(binary, circles_raw)
    # Mask out circles/arcs from binary so contours don't re-detect them
    masked = binary.copy()
    for c in circles_and_arcs:
        d = c["data"]
        cv2.circle(masked, (int(d["cx"]), int(d["cy"])), int(d["r"] + 6), 0, thickness=-1)
    contours = detect_contours(masked)
    return lines + circles_and_arcs + contours
