import { useEffect, useState, useMemo, useCallback } from "react";
import { useParams, Link } from "react-router-dom";
import { getJob, pagePreviewUrl, dxfUrl, reprocessJob } from "@/lib/api";
import GeometryCanvas from "@/components/GeometryCanvas";
import LayerPanel from "@/components/LayerPanel";
import CorrectionPanel from "@/components/CorrectionPanel";
import { Download, RefreshCw, ChevronLeft, AlertCircle } from "lucide-react";
import { toast } from "sonner";

export default function JobView() {
    const { id } = useParams();
    const [data, setData] = useState(null);
    const [pageIdx, setPageIdx] = useState(0);
    const [layers, setLayers] = useState({ GEOMETRY: true, TEXT: true, DIMENSIONS: true, UNCERTAIN: true });
    const [selectedId, setSelectedId] = useState(null);
    const [mode, setMode] = useState("overlay"); // overlay | dxf

    const refresh = useCallback(async () => {
        try {
            const d = await getJob(id);
            setData(d);
        } catch (e) {
            toast.error("Failed to load job");
        }
    }, [id]);

    useEffect(() => {
        refresh();
        const t = setInterval(() => {
            if (data?.job?.status === "processing" || data?.job?.status === "pending" || !data) {
                refresh();
            }
        }, 1500);
        return () => clearInterval(t);
    }, [refresh, data]);

    const pageEntities = useMemo(() => {
        if (!data) return [];
        return (data.entities || []).filter((e) => e.page_index === pageIdx);
    }, [data, pageIdx]);

    const layerCounts = useMemo(() => {
        const c = { GEOMETRY: 0, TEXT: 0, DIMENSIONS: 0, UNCERTAIN: 0 };
        pageEntities.forEach((e) => {
            const k = e.uncertain ? "UNCERTAIN" : (e.layer || "GEOMETRY");
            c[k] = (c[k] || 0) + 1;
        });
        return c;
    }, [pageEntities]);

    const uncertainList = useMemo(() => pageEntities.filter((e) => e.uncertain), [pageEntities]);

    const currentPage = useMemo(() => {
        if (!data?.pages) return null;
        return data.pages.find((p) => p.page_index === pageIdx) || data.pages[0];
    }, [data, pageIdx]);

    const selected = useMemo(() => pageEntities.find((e) => e.id === selectedId), [pageEntities, selectedId]);

    const onReprocess = async () => {
        try { await reprocessJob(id); toast.success("Reprocess started"); refresh(); } catch { toast.error("Reprocess failed"); }
    };

    if (!data) {
        return <div style={{ padding: 32, color: "var(--ink-dim)" }}>Loading…</div>;
    }
    const job = data.job;
    const isProcessing = job.status === "processing" || job.status === "pending";

    return (
        <div style={{ display: "grid", gridTemplateColumns: "260px 1fr 340px", height: "100%", overflow: "hidden" }}>
            {/* LEFT column */}
            <div style={{ borderRight: "1px solid var(--line)", overflow: "auto", padding: 14, display: "flex", flexDirection: "column", gap: 12 }}>
                <Link to="/" className="mono-label" style={{ display: "flex", alignItems: "center", gap: 6, textDecoration: "none" }} data-testid="back-home">
                    <ChevronLeft size={12} /> Back
                </Link>
                <div>
                    <div className="mono-label">File</div>
                    <div style={{ wordBreak: "break-all", fontSize: 14 }} data-testid="job-filename">{job.filename}</div>
                </div>
                <div style={{ display: "flex", gap: 8 }}>
                    <span className={`chip ${job.status === "done" ? "ok" : job.status === "error" ? "danger" : "pending"}`} data-testid="job-status">{job.status}</span>
                    {job.is_vector ? <span className="chip">vector-pdf</span> : null}
                </div>
                {isProcessing && (
                    <div>
                        <div className="mono-label">{job.stage || "processing"}</div>
                        <div className="progress"><div style={{ width: `${Math.round((job.progress || 0) * 100)}%` }} /></div>
                    </div>
                )}
                {job.error && (
                    <div className="panel" style={{ borderColor: "#4a1f23" }}>
                        <div className="panel-body" style={{ color: "var(--danger)", fontSize: 12, display: "flex", gap: 8 }}>
                            <AlertCircle size={14} />
                            <div>{job.error}</div>
                        </div>
                    </div>
                )}

                <div className="panel">
                    <div className="panel-header">Summary</div>
                    <div className="panel-body" style={{ fontSize: 13, color: "var(--ink-dim)" }}>
                        <Row label="Pages" value={job.num_pages || 0} />
                        <Row label="Entities" value={data.summary?.total || 0} />
                        <Row label="Uncertain" value={data.summary?.uncertain || 0} danger={(data.summary?.uncertain || 0) > 0} />
                        {Object.entries(data.summary?.counts || {}).map(([k, v]) => (
                            <Row key={k} label={k} value={v} />
                        ))}
                    </div>
                </div>

                <LayerPanel layers={layers} counts={layerCounts} onToggle={(k) => setLayers({ ...layers, [k]: !(layers[k] !== false) })} />

                {data.pages?.length > 1 && (
                    <div className="panel">
                        <div className="panel-header">Pages</div>
                        <div className="panel-body" style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                            {data.pages.map((p) => (
                                <button
                                    key={p.page_index}
                                    className="btn"
                                    data-testid={`page-${p.page_index}`}
                                    style={{ padding: "4px 10px", borderColor: pageIdx === p.page_index ? "var(--accent)" : "var(--line-2)", color: pageIdx === p.page_index ? "var(--accent)" : "var(--ink)" }}
                                    onClick={() => { setPageIdx(p.page_index); setSelectedId(null); }}
                                >
                                    {p.page_index + 1}
                                </button>
                            ))}
                        </div>
                    </div>
                )}

                <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                    <a
                        className="btn btn-primary"
                        href={dxfUrl(id)}
                        data-testid="download-dxf"
                        style={{ justifyContent: "center", pointerEvents: job.status === "done" ? "auto" : "none", opacity: job.status === "done" ? 1 : 0.4 }}
                    >
                        <Download size={14} /> Download DXF
                    </a>
                    <button className="btn" onClick={onReprocess} data-testid="job-reprocess">
                        <RefreshCw size={14} /> Reprocess with current rules
                    </button>
                </div>
            </div>

            {/* CANVAS */}
            <div style={{ position: "relative", overflow: "hidden" }}>
                {currentPage ? (
                    <>
                        <div style={{ position: "absolute", top: 12, left: 12, zIndex: 5, display: "flex", gap: 6 }}>
                            <button
                                className="btn"
                                onClick={() => setMode("overlay")}
                                data-testid="mode-overlay"
                                style={{ borderColor: mode === "overlay" ? "var(--accent)" : "var(--line-2)", color: mode === "overlay" ? "var(--accent)" : "var(--ink)" }}
                            >
                                Scan + Overlay
                            </button>
                            <button
                                className="btn"
                                onClick={() => setMode("dxf")}
                                data-testid="mode-dxf"
                                style={{ borderColor: mode === "dxf" ? "var(--accent)" : "var(--line-2)", color: mode === "dxf" ? "var(--accent)" : "var(--ink)" }}
                            >
                                DXF Preview
                            </button>
                        </div>
                        <GeometryCanvas
                            width={currentPage.width}
                            height={currentPage.height}
                            imageUrl={`${pagePreviewUrl(id, currentPage.page_index)}`}
                            entities={pageEntities}
                            layers={layers}
                            selectedId={selectedId}
                            onSelect={(e) => setSelectedId(e.id)}
                            mode={mode}
                        />
                    </>
                ) : (
                    <div style={{ padding: 40, color: "var(--ink-dim)" }}>
                        {isProcessing ? "Processing…" : "No pages available"}
                    </div>
                )}
            </div>

            {/* RIGHT column */}
            <div style={{ borderLeft: "1px solid var(--line)", overflow: "auto", padding: 14, display: "flex", flexDirection: "column", gap: 12 }}>
                <CorrectionPanel jobId={id} entity={selected} onChanged={refresh} />

                <div className="panel">
                    <div className="panel-header">
                        <span>Uncertain items</span>
                        <span className="chip danger">{uncertainList.length}</span>
                    </div>
                    <div style={{ maxHeight: 220, overflow: "auto" }}>
                        {uncertainList.length === 0 ? (
                            <div className="panel-body" style={{ color: "var(--ink-dim)", fontSize: 13 }}>None. Everything detected confidently.</div>
                        ) : (
                            uncertainList.map((e) => (
                                <button
                                    key={e.id}
                                    onClick={() => setSelectedId(e.id)}
                                    data-testid={`uncertain-${e.id}`}
                                    style={{
                                        width: "100%",
                                        textAlign: "left",
                                        background: selectedId === e.id ? "var(--bg-3)" : "transparent",
                                        border: "none",
                                        borderBottom: "1px solid var(--line)",
                                        padding: "8px 12px",
                                        color: "var(--ink)",
                                        cursor: "pointer",
                                        fontSize: 12,
                                        fontFamily: "'IBM Plex Mono', monospace",
                                    }}
                                >
                                    <div style={{ display: "flex", justifyContent: "space-between" }}>
                                        <span style={{ color: "var(--danger)" }}>{e.kind}</span>
                                        <span style={{ color: "var(--ink-soft)" }}>{Math.round((e.confidence || 0) * 100)}%</span>
                                    </div>
                                    <div style={{ color: "var(--ink-soft)", fontSize: 10, marginTop: 2 }}>{e.id.slice(0, 12)}</div>
                                </button>
                            ))
                        )}
                    </div>
                </div>
            </div>
        </div>
    );
}

const Row = ({ label, value, danger }) => (
    <div style={{ display: "flex", justifyContent: "space-between", padding: "4px 0" }}>
        <span style={{ textTransform: "capitalize" }}>{label}</span>
        <span className="mono" style={{ color: danger ? "var(--danger)" : "var(--ink)" }}>{value}</span>
    </div>
);
