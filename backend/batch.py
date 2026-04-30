#!/usr/bin/env python3
"""
Batch processor — run the full CAD Assist pipeline against a directory of drawings.

Use this to test the engine against your own corpus of CAD scans:

    python backend/batch.py /path/to/drawings --out /path/to/dxfs --report report.csv

It produces one DXF per input, writes a CSV report with per-file metrics
(entity counts, OCR hits, uncertain count, elapsed time, errors) and
prints summary statistics at the end. Useful for regression testing the
pipeline against 100s or 1000s of real drawings without touching the UI.
"""
from __future__ import annotations
import argparse
import csv
import json
import sys
import time
from pathlib import Path
from collections import Counter

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import cv2
from storage import db
from processing import ingest, preprocess, detect, ocr, reconstruct, export_dxf
from learning import engine as learning


SUPPORTED = {".pdf", ".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".webp"}


def process_file(path: Path, out_dir: Path) -> dict:
    start = time.time()
    row = {
        "file": str(path),
        "pages": 0,
        "lines": 0,
        "circles": 0,
        "arcs": 0,
        "polylines": 0,
        "hatches": 0,
        "text": 0,
        "dimensions": 0,
        "uncertain": 0,
        "total": 0,
        "elapsed_s": 0.0,
        "dxf": "",
        "error": "",
    }
    all_entities: list[dict] = []
    pages_meta: list[tuple[int, int]] = []  # (width, height)
    try:
        if ingest.is_pdf(path):
            is_vector = ingest.pdf_is_vector(path)
            vec = ingest.pdf_vector_entities(path) if is_vector else []
            for pi, img in ingest.pdf_iter_pages(path):
                pp = preprocess.preprocess(img)
                ents = []
                if is_vector and pi < len(vec) and vec[pi]:
                    ents.extend(vec[pi])
                else:
                    ents.extend(detect.detect_all(pp["binary"], pp["gray"]))
                    ents.extend(ocr.extract_text(pp["gray"]))
                for e in ents:
                    e["page_index"] = pi
                ents = reconstruct.reconstruct(ents)
                ents, _ = learning.apply_rules(ents)
                all_entities.extend(ents)
                pages_meta.append((pp["deskewed"].shape[1], pp["deskewed"].shape[0]))
        else:
            img = ingest.load_image(path)
            pp = preprocess.preprocess(img)
            ents = detect.detect_all(pp["binary"], pp["gray"])
            ents.extend(ocr.extract_text(pp["gray"]))
            for e in ents:
                e["page_index"] = 0
            ents = reconstruct.reconstruct(ents)
            ents, _ = learning.apply_rules(ents)
            all_entities.extend(ents)
            pages_meta.append((pp["deskewed"].shape[1], pp["deskewed"].shape[0]))

        # Export DXF
        out_path = out_dir / (path.stem + ".dxf")
        # Use first page dims for single-page; multi-page export uses the built-in helper logic
        page_h = pages_meta[0][1] if pages_meta else None
        export_dxf.entities_to_dxf([e for e in all_entities if e.get("page_index", 0) == 0], out_path, page_height=page_h)
        row["dxf"] = str(out_path)

        counts = Counter(e["kind"] for e in all_entities if not e.get("deleted"))
        row["pages"] = len(pages_meta)
        row["lines"] = counts.get("line", 0)
        row["circles"] = counts.get("circle", 0)
        row["arcs"] = counts.get("arc", 0)
        row["polylines"] = counts.get("polyline", 0)
        row["hatches"] = counts.get("hatch", 0)
        row["text"] = counts.get("text", 0)
        row["dimensions"] = counts.get("dimension", 0)
        row["uncertain"] = sum(1 for e in all_entities if e.get("uncertain") and not e.get("deleted"))
        row["total"] = sum(1 for e in all_entities if not e.get("deleted"))
    except Exception as ex:
        row["error"] = str(ex)
    row["elapsed_s"] = round(time.time() - start, 3)
    return row


def main():
    ap = argparse.ArgumentParser(description="Batch process CAD drawings → DXF")
    ap.add_argument("input", help="Directory to scan (recursive)")
    ap.add_argument("--out", default="./batch_out", help="Output DXF directory")
    ap.add_argument("--report", default="./batch_report.csv", help="CSV report path")
    ap.add_argument("--limit", type=int, default=0, help="Optional max number of files to process")
    args = ap.parse_args()

    in_dir = Path(args.input)
    if not in_dir.exists():
        print(f"input not found: {in_dir}")
        sys.exit(2)

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    files = sorted([p for p in in_dir.rglob("*") if p.suffix.lower() in SUPPORTED])
    if args.limit > 0:
        files = files[: args.limit]

    learning.seed_default_rules()
    print(f"[batch] {len(files)} files to process")
    rows: list[dict] = []
    ok = 0
    for i, p in enumerate(files, 1):
        r = process_file(p, out_dir)
        rows.append(r)
        if r["error"]:
            print(f"  [{i}/{len(files)}] {p.name}  ERROR: {r['error']}")
        else:
            print(f"  [{i}/{len(files)}] {p.name}  {r['total']} ents ({r['lines']}L/{r['circles']}C/{r['arcs']}A) "
                  f"{r['uncertain']} uncertain  {r['elapsed_s']}s")
            ok += 1

    fieldnames = list(rows[0].keys()) if rows else ["file", "error"]
    with open(args.report, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    if rows:
        total_time = sum(r["elapsed_s"] for r in rows)
        avg = total_time / len(rows)
        avg_ents = sum(r["total"] for r in rows) / len(rows)
        avg_unc = sum(r["uncertain"] for r in rows) / len(rows)
        print()
        print(f"[batch] summary")
        print(f"  files processed:     {ok}/{len(rows)}")
        print(f"  total time:          {total_time:.1f}s")
        print(f"  avg time per file:   {avg:.2f}s")
        print(f"  avg entities/file:   {avg_ents:.1f}")
        print(f"  avg uncertain/file:  {avg_unc:.1f}")
        print(f"  report:              {args.report}")
        print(f"  dxfs:                {out_dir}")


if __name__ == "__main__":
    main()
