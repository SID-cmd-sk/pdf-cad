export default function About() {
    const steps = [
        { n: "01", t: "Ingest", d: "Accepts PDF, PNG, JPG, TIFF, WEBP. Vector PDFs are parsed directly via PyMuPDF; scans are rasterised at 200 DPI." },
        { n: "02", t: "Preprocess", d: "Grayscale, denoise, adaptive/Otsu binarisation, minAreaRect-based deskew." },
        { n: "03", t: "Detect", d: "Hough lines with collinear merging, Hough circles with per-perimeter coverage test to split circles from arcs, contour-based polygons." },
        { n: "04", t: "OCR", d: "Local Tesseract 5 with a CAD-friendly whitelist; dimension-like tokens are routed to the DIMENSIONS layer." },
        { n: "05", t: "Reconstruct", d: "Deduplicate, snap nearby endpoints to clean intersections, separate uncertain geometry onto a dedicated layer." },
        { n: "06", t: "Export", d: "Layered DXF (GEOMETRY · TEXT · DIMENSIONS · UNCERTAIN) via ezdxf." },
        { n: "07", t: "Learn", d: "Every correction can become a rule. Signatures like 'short_line<10' or 'low_coverage_arc<0.6' auto-apply on future jobs." },
    ];
    return (
        <div style={{ overflow: "auto", padding: "28px 32px" }}>
            <div style={{ maxWidth: 1000, margin: "0 auto" }}>
                <div style={{ fontSize: 11, letterSpacing: "0.2em", color: "var(--ink-dim)", fontFamily: "'IBM Plex Mono', monospace", marginBottom: 12 }}>
                    PIPELINE
                </div>
                <div style={{ fontSize: 28, fontWeight: 400, marginBottom: 8 }}>Deterministic. Local. Explainable.</div>
                <div style={{ color: "var(--ink-dim)", marginBottom: 32, maxWidth: 720 }}>
                    Every step of the conversion is a transparent, inspectable transform — no black-box AI. The learning layer
                    is a plain SQLite table of rules you can read, edit or delete.
                </div>

                <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(300px, 1fr))", gap: 14 }}>
                    {steps.map((s) => (
                        <div key={s.n} className="panel" data-testid={`step-${s.n}`}>
                            <div className="panel-body">
                                <div className="mono" style={{ color: "var(--accent)", letterSpacing: "0.18em", fontSize: 11, marginBottom: 6 }}>STAGE {s.n}</div>
                                <div style={{ fontSize: 18, marginBottom: 6 }}>{s.t}</div>
                                <div style={{ color: "var(--ink-dim)", fontSize: 13, lineHeight: 1.5 }}>{s.d}</div>
                            </div>
                        </div>
                    ))}
                </div>

                <div className="panel" style={{ marginTop: 28 }}>
                    <div className="panel-header">Stack</div>
                    <div className="panel-body" style={{ color: "var(--ink-dim)", fontSize: 13, lineHeight: 1.8 }}>
                        <div><span className="mono" style={{ color: "var(--accent)" }}>backend</span> — FastAPI · OpenCV · Tesseract · PyMuPDF · ezdxf · SQLite (WAL)</div>
                        <div><span className="mono" style={{ color: "var(--accent)" }}>frontend</span> — React 19 · SVG pan/zoom · sonner toasts</div>
                        <div><span className="mono" style={{ color: "var(--accent)" }}>storage</span> — single-file SQLite DB, local disk uploads &amp; outputs</div>
                        <div><span className="mono" style={{ color: "var(--accent)" }}>packaging</span> — run <code>./start.sh</code> or wrap in Electron for desktop</div>
                    </div>
                </div>
            </div>
        </div>
    );
}
