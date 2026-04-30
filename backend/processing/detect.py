"""Geometry detection: lines, circles, arcs, polygons/contours, hatches.

Improvements over naïve Hough pipeline:
  * Lines: Canny + HoughP + two-pass collinear merge + endpoint snapping.
  * Circles: Hough circles validated by perimeter coverage AND
    contour-based RANSAC-style circle fitting for missed partial circles.
  * Arcs: open contours long enough to be arcs → algebraic circle fit
    → arc span estimation. Catches arcs Hough misses entirely.
  * Hatches: groups of parallel equidistant short lines in a bbox
    are collapsed into a single HATCH entity so the canvas isn't spammed.
  * Contours: polygonal approximation after masking out detected shapes.
"""
from __future__ import annotations
import math
import numpy as np
import cv2


# ============================================================
# LINE DETECTION
# ============================================================

def detect_lines(binary: np.ndarray, min_length_px: int = 35) -> list[dict]:
    edges = cv2.Canny(binary, 50, 150, apertureSize=3, L2gradient=True)
    lines = cv2.HoughLinesP(
        edges,
        rho=1,
        theta=np.pi / 360,
        threshold=55,
        minLineLength=min_length_px,
        maxLineGap=10,
    )
    out: list[dict] = []
    if lines is None:
        return out
    for seg in lines:
        x1, y1, x2, y2 = seg[0]
        length = math.hypot(x2 - x1, y2 - y1)
        out.append({
            "kind": "line",
            "data": {"x1": float(x1), "y1": float(y1), "x2": float(x2), "y2": float(y2), "length": length},
            "confidence": min(1.0, 0.55 + length / 400.0),
            "layer": "GEOMETRY",
        })
    return out


def merge_collinear_lines(lines: list[dict], angle_tol_deg: float = 3.0, dist_tol: float = 5.0, gap_tol: float = 18.0) -> list[dict]:
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
        cluster = [ai, bi]
        conf = items[i]["l"]["confidence"]
        used[i] = True
        for j in range(i + 1, len(items)):
            if used[j]:
                continue
            aj, bj = items[j]["a"], items[j]["b"]
            ang_j = math.atan2(bj[1] - aj[1], bj[0] - aj[0])
            diff = abs(((ang_i - ang_j + math.pi / 2) % math.pi) - math.pi / 2)
            if diff > ang_tol:
                continue
            v = bi - ai
            n_len = np.linalg.norm(v)
            if n_len < 1e-5:
                continue
            n = np.array([-v[1], v[0]]) / n_len
            if abs(np.dot(aj - ai, n)) > dist_tol or abs(np.dot(bj - ai, n)) > dist_tol:
                continue
            u = v / n_len
            pi_ = sorted([0.0, np.dot(bi - ai, u)])
            pj_ = sorted([np.dot(aj - ai, u), np.dot(bj - ai, u)])
            gap = max(pj_[0] - pi_[1], pi_[0] - pj_[1])
            if gap > gap_tol:
                continue
            cluster.extend([aj, bj])
            conf = max(conf, items[j]["l"]["confidence"])
            used[j] = True
        arr = np.stack(cluster)
        u = np.array([math.cos(ang_i), math.sin(ang_i)])
        proj = arr @ u
        p1 = arr[int(np.argmin(proj))]
        p2 = arr[int(np.argmax(proj))]
        length = float(np.linalg.norm(p2 - p1))
        merged.append({
            "kind": "line",
            "data": {"x1": float(p1[0]), "y1": float(p1[1]), "x2": float(p2[0]), "y2": float(p2[1]), "length": length},
            "confidence": float(min(1.0, conf + 0.1)),
            "layer": "GEOMETRY",
        })
    return merged


# ============================================================
# HATCH DETECTION
# ============================================================

def detect_hatches(lines: list[dict], min_lines: int = 4, spacing_tol: float = 0.3) -> tuple[list[dict], set[int]]:
    """Detect groups of parallel equidistant short lines and collapse into a HATCH entity.
    Returns (hatch_entities, indexes_of_lines_consumed).
    """
    if len(lines) < min_lines:
        return [], set()

    # Bucket lines by angle (10° bins)
    buckets: dict[int, list[int]] = {}
    meta = []
    for i, l in enumerate(lines):
        d = l["data"]
        ang = math.degrees(math.atan2(d["y2"] - d["y1"], d["x2"] - d["x1"])) % 180
        length = d.get("length") or math.hypot(d["x2"] - d["x1"], d["y2"] - d["y1"])
        meta.append({"ang": ang, "length": length, "mid": ((d["x1"] + d["x2"]) / 2, (d["y1"] + d["y2"]) / 2)})
        b = int(ang // 10)
        buckets.setdefault(b, []).append(i)

    hatches: list[dict] = []
    consumed: set[int] = set()

    for _, idxs in buckets.items():
        if len(idxs) < min_lines:
            continue
        # Compute perpendicular offset of each line from origin along its normal
        # Use mean angle of bucket
        angs = np.array([meta[i]["ang"] for i in idxs])
        mean_ang = np.deg2rad(angs.mean())
        nx, ny = -math.sin(mean_ang), math.cos(mean_ang)
        offsets = []
        for i in idxs:
            mx, my = meta[i]["mid"]
            offsets.append(mx * nx + my * ny)
        order = np.argsort(offsets)
        sorted_offs = [offsets[o] for o in order]
        sorted_idx = [idxs[o] for o in order]
        # Find consecutive runs with near-equal spacing
        run = [sorted_idx[0]]
        for k in range(1, len(sorted_offs)):
            dprev = sorted_offs[k] - sorted_offs[k - 1]
            if dprev < 3:
                continue
            # use median spacing of current run
            if len(run) >= 2:
                # compute previous spacing
                # approximate with dprev comparison against previous gap
                prev_gap = sorted_offs[k - 1] - sorted_offs[k - 2] if len(run) >= 2 else dprev
                if abs(dprev - prev_gap) / max(prev_gap, 1e-3) < spacing_tol and dprev < 50:
                    run.append(sorted_idx[k])
                    continue
            # start new run
            if len(run) >= min_lines:
                # Emit
                xs, ys = [], []
                for ri in run:
                    d = lines[ri]["data"]
                    xs += [d["x1"], d["x2"]]
                    ys += [d["y1"], d["y2"]]
                    consumed.add(ri)
                bbox = [min(xs), min(ys), max(xs), max(ys)]
                hatches.append({
                    "kind": "hatch",
                    "data": {"bbox": bbox, "count": len(run), "angle_deg": float(np.rad2deg(mean_ang))},
                    "confidence": 0.75,
                    "layer": "GEOMETRY",
                })
            run = [sorted_idx[k]]
        if len(run) >= min_lines:
            xs, ys = [], []
            for ri in run:
                d = lines[ri]["data"]
                xs += [d["x1"], d["x2"]]
                ys += [d["y1"], d["y2"]]
                consumed.add(ri)
            bbox = [min(xs), min(ys), max(xs), max(ys)]
            hatches.append({
                "kind": "hatch",
                "data": {"bbox": bbox, "count": len(run), "angle_deg": float(np.rad2deg(mean_ang))},
                "confidence": 0.75,
                "layer": "GEOMETRY",
            })

    return hatches, consumed


# ============================================================
# CIRCLES + ARCS
# ============================================================

def _fit_circle(pts: np.ndarray) -> tuple[float, float, float, float] | None:
    """Algebraic circle fit (Kasa). pts shape (N,2). Returns (cx,cy,r,residual) or None."""
    if len(pts) < 5:
        return None
    x = pts[:, 0].astype(np.float64)
    y = pts[:, 1].astype(np.float64)
    A = np.column_stack([2 * x, 2 * y, np.ones_like(x)])
    b = x ** 2 + y ** 2
    try:
        c, *_ = np.linalg.lstsq(A, b, rcond=None)
    except Exception:
        return None
    cx, cy, k = c
    r2 = k + cx ** 2 + cy ** 2
    if r2 <= 0:
        return None
    r = math.sqrt(r2)
    if r < 5 or r > max(pts[:, 0].max(), pts[:, 1].max()) * 2:
        return None
    residual = float(np.sqrt(np.mean((np.sqrt((x - cx) ** 2 + (y - cy) ** 2) - r) ** 2)))
    return float(cx), float(cy), float(r), residual


def detect_circles_and_arcs(binary: np.ndarray, gray: np.ndarray) -> list[dict]:
    """Robust detector combining Hough circles + contour-based fitting.
    Distinguishes circles vs arcs via perimeter coverage.
    """
    h, w = binary.shape
    out: list[dict] = []

    # --- Pass 1: Hough circles on grayscale ---
    blurred = cv2.medianBlur(gray, 3)
    hough_hits: list[tuple[float, float, float]] = []
    for param2 in (45, 35, 28):
        circles = cv2.HoughCircles(
            blurred, cv2.HOUGH_GRADIENT,
            dp=1.2, minDist=25, param1=120, param2=param2,
            minRadius=8, maxRadius=min(h, w) // 2,
        )
        if circles is not None:
            for c in circles[0]:
                hough_hits.append((float(c[0]), float(c[1]), float(c[2])))
            if hough_hits:
                break

    # --- Pass 2: contour-based arc/circle fits ---
    contours, _ = cv2.findContours(binary, cv2.RETR_LIST, cv2.CHAIN_APPROX_NONE)
    fit_candidates: list[tuple[float, float, float, float]] = []  # cx,cy,r,coverage_guess
    for cnt in contours:
        if len(cnt) < 30:
            continue
        peri = cv2.arcLength(cnt, False)
        if peri < 80:
            continue
        pts = cnt[:, 0, :]
        fit = _fit_circle(pts)
        if fit is None:
            continue
        cx, cy, r, residual = fit
        if residual > max(2.5, 0.08 * r):
            continue
        # estimate coverage as contour length / (2πr)
        coverage = min(1.0, peri / (2 * math.pi * r))
        if 0.35 <= coverage:
            fit_candidates.append((cx, cy, r, coverage))

    # --- Merge Hough + contour hits (dedupe) ---
    all_hits: list[tuple[float, float, float, float]] = []  # cx,cy,r,coverage
    for cx, cy, r in hough_hits:
        all_hits.append((cx, cy, r, -1.0))  # coverage measured later
    for cx, cy, r, cov in fit_candidates:
        dup = False
        for h_ in all_hits:
            if math.hypot(h_[0] - cx, h_[1] - cy) < max(8, 0.2 * r) and abs(h_[2] - r) < max(5, 0.15 * r):
                dup = True
                break
        if not dup:
            all_hits.append((cx, cy, r, cov))

    # --- Validate each hit via perimeter coverage on the binary ---
    for cx, cy, r, cov_hint in all_hits:
        n = max(72, min(720, int(2 * math.pi * r)))
        hits = 0
        start_hit = np.zeros(n, dtype=bool)
        for k in range(n):
            a = 2 * math.pi * k / n
            px = int(round(cx + r * math.cos(a)))
            py = int(round(cy + r * math.sin(a)))
            ok = False
            for dy in (-2, -1, 0, 1, 2):
                for dx in (-2, -1, 0, 1, 2):
                    xx, yy = px + dx, py + dy
                    if 0 <= xx < w and 0 <= yy < h and binary[yy, xx] > 0:
                        ok = True
                        break
                if ok:
                    break
            start_hit[k] = ok
            hits += int(ok)
        frac = hits / n
        if frac < 0.4:
            continue

        # Deduplicate against already-accepted output
        dup = False
        for e in out:
            d = e["data"]
            if math.hypot(d["cx"] - cx, d["cy"] - cy) < max(8, 0.2 * r) and abs(d["r"] - r) < max(5, 0.15 * r):
                dup = True
                break
        if dup:
            continue

        if frac >= 0.85:
            out.append({
                "kind": "circle",
                "data": {"cx": cx, "cy": cy, "r": r, "coverage": float(frac)},
                "confidence": min(1.0, 0.65 + frac * 0.35),
                "layer": "GEOMETRY",
                "uncertain": frac < 0.92,
            })
        else:
            # longest contiguous arc span
            doubled = np.concatenate([start_hit, start_hit])
            best_len = best_start = cur_len = cur_start = 0
            for i_ in range(len(doubled)):
                if doubled[i_]:
                    if cur_len == 0:
                        cur_start = i_
                    cur_len += 1
                    if cur_len > best_len:
                        best_len = cur_len
                        best_start = cur_start
                else:
                    cur_len = 0
            if best_len < n * 0.2:
                continue
            a_start = (best_start % n) * 2 * math.pi / n
            a_end = ((best_start + best_len - 1) % n) * 2 * math.pi / n
            out.append({
                "kind": "arc",
                "data": {"cx": cx, "cy": cy, "r": r,
                         "start_angle": a_start, "end_angle": a_end,
                         "coverage": float(frac)},
                "confidence": max(0.4, 0.35 + frac * 0.55),
                "layer": "GEOMETRY",
                "uncertain": frac < 0.75,
            })
    return out


# ============================================================
# CONTOURS / POLYGONS
# ============================================================

def detect_contours(binary: np.ndarray, min_area: float = 120.0) -> list[dict]:
    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    out: list[dict] = []
    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area < min_area:
            continue
        peri = cv2.arcLength(cnt, True)
        if peri < 50:
            continue
        approx = cv2.approxPolyDP(cnt, 0.012 * peri, True)
        pts = [[float(p[0][0]), float(p[0][1])] for p in approx]
        if len(pts) < 3:
            continue
        circularity = 4 * math.pi * area / (peri ** 2) if peri else 0
        if circularity > 0.85 and len(pts) >= 8:
            continue  # better captured as a circle
        out.append({
            "kind": "polyline",
            "data": {"points": pts, "closed": True, "area": float(area)},
            "confidence": 0.65 if len(pts) <= 8 else 0.5,
            "layer": "GEOMETRY",
            "uncertain": len(pts) > 14,
        })
    return out


# ============================================================
# TOP-LEVEL
# ============================================================

def detect_all(binary: np.ndarray, gray: np.ndarray) -> list[dict]:
    lines_raw = detect_lines(binary)
    lines = merge_collinear_lines(lines_raw)
    # Second merge pass tightens further
    lines = merge_collinear_lines(lines, angle_tol_deg=2.0, dist_tol=4.0, gap_tol=22.0)

    hatches, consumed = detect_hatches(lines)
    lines = [l for i, l in enumerate(lines) if i not in consumed]

    shapes = detect_circles_and_arcs(binary, gray)

    # Mask detected circles/arcs from binary for contour detection
    masked = binary.copy()
    for c in shapes:
        d = c["data"]
        cv2.circle(masked, (int(d["cx"]), int(d["cy"])), int(d["r"] + 6), 0, thickness=-1)
    # Also erase hatch bboxes from the contour pass so hatch fills don't become polygons
    for hv in hatches:
        x0, y0, x1, y1 = hv["data"]["bbox"]
        cv2.rectangle(masked, (int(x0) - 2, int(y0) - 2), (int(x1) + 2, int(y1) + 2), 0, -1)
    polys = detect_contours(masked)

    return lines + shapes + polys + hatches
