"""Vector reconstruction: snap endpoints, merge near-duplicates, clean topology."""
from __future__ import annotations
import math
from collections import defaultdict


def snap_endpoints(entities: list[dict], snap_dist: float = 6.0) -> list[dict]:
    """Snap nearby endpoints of lines together to form clean intersections."""
    endpoints: list[tuple[int, str, float, float]] = []
    for i, e in enumerate(entities):
        if e["kind"] == "line":
            d = e["data"]
            endpoints.append((i, "a", d["x1"], d["y1"]))
            endpoints.append((i, "b", d["x2"], d["y2"]))
        elif e["kind"] == "polyline":
            d = e["data"]
            pts = d.get("points", [])
            if pts:
                endpoints.append((i, "first", pts[0][0], pts[0][1]))
                endpoints.append((i, "last", pts[-1][0], pts[-1][1]))

    # Bucket by grid to find clusters fast
    grid = defaultdict(list)
    g = max(1, int(snap_dist))
    for idx, which, x, y in endpoints:
        key = (int(x // g), int(y // g))
        grid[key].append((idx, which, x, y))

    # Build clusters
    visited = [False] * len(endpoints)
    clusters: list[list[int]] = []
    for i in range(len(endpoints)):
        if visited[i]:
            continue
        visited[i] = True
        idx_i, which_i, xi, yi = endpoints[i]
        cluster = [i]
        kx, ky = int(xi // g), int(yi // g)
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for entry in grid.get((kx + dx, ky + dy), []):
                    idx_j, which_j, xj, yj = entry
                    if idx_j == idx_i and which_j == which_i:
                        continue
                    j = None
                    for k, ep in enumerate(endpoints):
                        if ep is entry and not visited[k]:
                            j = k
                            break
                    if j is None:
                        continue
                    if math.hypot(xi - xj, yi - yj) <= snap_dist:
                        visited[j] = True
                        cluster.append(j)
        if len(cluster) > 1:
            clusters.append(cluster)

    # Compute centroids and apply
    for cluster in clusters:
        xs = [endpoints[k][2] for k in cluster]
        ys = [endpoints[k][3] for k in cluster]
        cx, cy = sum(xs) / len(xs), sum(ys) / len(ys)
        for k in cluster:
            idx, which, _, _ = endpoints[k]
            e = entities[idx]
            if e["kind"] == "line":
                if which == "a":
                    e["data"]["x1"] = cx
                    e["data"]["y1"] = cy
                else:
                    e["data"]["x2"] = cx
                    e["data"]["y2"] = cy
                e["modified"] = True
            elif e["kind"] == "polyline":
                pts = e["data"].get("points", [])
                if not pts:
                    continue
                if which == "first":
                    pts[0] = [cx, cy]
                else:
                    pts[-1] = [cx, cy]
                e["data"]["points"] = pts
                e["modified"] = True
    return entities


def remove_duplicate_lines(entities: list[dict], dist_tol: float = 5.0) -> list[dict]:
    out: list[dict] = []
    seen: list[dict] = []
    for e in entities:
        if e["kind"] != "line":
            out.append(e)
            continue
        d = e["data"]
        key = (round(min(d["x1"], d["x2"]) / dist_tol), round(min(d["y1"], d["y2"]) / dist_tol),
               round(max(d["x1"], d["x2"]) / dist_tol), round(max(d["y1"], d["y2"]) / dist_tol))
        dup = False
        for s in seen:
            if s["key"] == key:
                dup = True
                break
        if not dup:
            seen.append({"key": key})
            out.append(e)
    return out


def reconstruct(entities: list[dict]) -> list[dict]:
    entities = remove_duplicate_lines(entities)
    entities = snap_endpoints(entities, snap_dist=6.0)
    return entities
