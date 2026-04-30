import { useEffect, useState } from "react";
import UploadZone from "@/components/UploadZone";
import JobList from "@/components/JobList";
import { listJobs, health } from "@/lib/api";
import { Activity, Cpu, Database, FileCode } from "lucide-react";

export default function Home() {
    const [jobs, setJobs] = useState([]);
    const [h, setH] = useState(null);

    const refresh = async () => {
        try {
            const list = await listJobs();
            setJobs(list);
        } catch (e) {
            /* ignore */
        }
    };

    useEffect(() => {
        refresh();
        health().then(setH).catch(() => setH({ ok: false }));
        const t = setInterval(refresh, 2000);
        return () => clearInterval(t);
    }, []);

    return (
        <div style={{ overflow: "auto", padding: "28px 32px" }}>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 340px", gap: 24, maxWidth: 1500, margin: "0 auto" }}>
                <div>
                    <div style={{ fontSize: 11, letterSpacing: "0.2em", color: "var(--ink-dim)", fontFamily: "'IBM Plex Mono', monospace", marginBottom: 12 }}>
                        01 / UPLOAD
                    </div>
                    <div style={{ fontSize: 32, fontWeight: 400, marginBottom: 8, letterSpacing: "-0.01em" }}>
                        Convert scans to editable <span style={{ color: "var(--accent)" }}>DXF</span>.
                    </div>
                    <div style={{ color: "var(--ink-dim)", marginBottom: 28, maxWidth: 640 }}>
                        Local-first pipeline: ingest → preprocess → detect geometry → OCR → reconstruct → export.
                        Every correction you make trains the engine's rule library.
                    </div>
                    <UploadZone onUploaded={refresh} />

                    <div style={{ marginTop: 36 }}>
                        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 12 }}>
                            <div style={{ fontSize: 11, letterSpacing: "0.2em", color: "var(--ink-dim)", fontFamily: "'IBM Plex Mono', monospace" }}>
                                02 / JOBS
                            </div>
                            <span className="mono" style={{ fontSize: 11, color: "var(--ink-soft)" }}>{jobs.length} total</span>
                        </div>
                        <div className="panel">
                            <JobList jobs={jobs} onMutate={refresh} />
                        </div>
                    </div>
                </div>

                <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
                    <div className="panel">
                        <div className="panel-header">System</div>
                        <div className="panel-body" style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                            <Stat icon={<Activity size={14} />} label="Backend" value={h?.ok ? "online" : "offline"} status={h?.ok ? "ok" : "danger"} />
                            <Stat icon={<Cpu size={14} />} label="Tesseract OCR" value={h?.tesseract ? "ready" : "missing"} status={h?.tesseract ? "ok" : "warn"} />
                            <Stat icon={<FileCode size={14} />} label="PDF engine" value={h?.fitz ? "ready" : "missing"} status={h?.fitz ? "ok" : "warn"} />
                            <Stat icon={<Database size={14} />} label="Storage" value="SQLite · local" status="ok" />
                        </div>
                    </div>

                    <div className="panel">
                        <div className="panel-header">How it works</div>
                        <div className="panel-body" style={{ fontSize: 13, color: "var(--ink-dim)", lineHeight: 1.7 }}>
                            <div style={{ marginBottom: 10 }}>
                                1. Drop a drawing. Vector PDFs are parsed directly; scans go through deskew, threshold, Hough detection and OCR.
                            </div>
                            <div style={{ marginBottom: 10 }}>
                                2. Review detected geometry. Red lines are flagged uncertain.
                            </div>
                            <div style={{ marginBottom: 10 }}>
                                3. Click an entity to convert, edit, delete, or mark correct. Tick <em>Apply to similar</em> to teach a rule.
                            </div>
                            <div>
                                4. Download the cleaned DXF. Rules auto-apply to future jobs.
                            </div>
                        </div>
                    </div>

                    <div className="panel">
                        <div className="panel-header">Samples</div>
                        <div className="panel-body" style={{ fontSize: 12, color: "var(--ink-dim)" }}>
                            Sample drawings live in <code className="mono" style={{ color: "var(--accent)" }}>/app/samples/</code>. Drag one into the drop zone to try the pipeline end-to-end.
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
}

const Stat = ({ icon, label, value, status }) => (
    <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
        <span style={{ color: "var(--ink-soft)" }}>{icon}</span>
        <span style={{ flex: 1, fontSize: 13 }}>{label}</span>
        <span className={`chip ${status || ""}`} style={{ textTransform: "none" }}>{value}</span>
    </div>
);
