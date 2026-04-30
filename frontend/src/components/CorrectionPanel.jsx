import { useState } from "react";
import { Trash2, Type, Shuffle, CheckCircle2, Link as LinkIcon, AlertCircle } from "lucide-react";
import { correctEntity } from "@/lib/api";
import { toast } from "sonner";

export default function CorrectionPanel({ jobId, entity, onChanged }) {
    const [busy, setBusy] = useState(false);
    const [applyAll, setApplyAll] = useState(true);
    const [textEdit, setTextEdit] = useState(entity?.data?.text || "");

    if (!entity) {
        return (
            <div className="panel" data-testid="correction-panel-empty">
                <div className="panel-header">Inspector</div>
                <div className="panel-body" style={{ color: "var(--ink-dim)", fontSize: 13 }}>
                    Click any entity on the canvas to inspect, correct, or teach the system.
                </div>
            </div>
        );
    }

    const submit = async (action_type, new_data) => {
        setBusy(true);
        try {
            const res = await correctEntity(jobId, {
                entity_id: entity.id,
                action_type,
                new_data: new_data || null,
                apply_to_similar: applyAll,
            });
            if (res.rule_id) toast.success("Fix saved · rule learned");
            else toast.success("Fix applied");
            onChanged && onChanged();
        } catch (e) {
            toast.error("Correction failed");
        } finally {
            setBusy(false);
        }
    };

    const kind = entity.kind;
    const d = entity.data || {};

    return (
        <div className="panel fade-in" data-testid="correction-panel">
            <div className="panel-header">
                <span>Inspector</span>
                <span className="chip" style={{ textTransform: "none" }}>{kind}</span>
            </div>
            <div className="panel-body" style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                <div>
                    <div className="mono-label">ID</div>
                    <div className="mono" style={{ fontSize: 11, color: "var(--ink-dim)", wordBreak: "break-all" }}>{entity.id}</div>
                </div>
                <div>
                    <div className="mono-label">Confidence</div>
                    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                        <div style={{ flex: 1, height: 4, background: "var(--line)", borderRadius: 2, overflow: "hidden" }}>
                            <div style={{ height: "100%", width: `${Math.round((entity.confidence || 0) * 100)}%`, background: entity.uncertain ? "var(--danger)" : "var(--accent)" }} />
                        </div>
                        <span className="mono" style={{ fontSize: 12 }}>{Math.round((entity.confidence || 0) * 100)}%</span>
                    </div>
                    {entity.uncertain ? (
                        <div style={{ fontSize: 11, color: "var(--danger)", marginTop: 6, display: "flex", alignItems: "center", gap: 6 }}>
                            <AlertCircle size={12} /> Flagged as uncertain
                        </div>
                    ) : null}
                </div>

                <div>
                    <div className="mono-label">Data</div>
                    <pre className="mono" style={{ fontSize: 11, background: "var(--bg-0)", padding: 8, borderRadius: 4, border: "1px solid var(--line)", maxHeight: 120, overflow: "auto" }}>
{JSON.stringify(d, null, 2)}
                    </pre>
                </div>

                <label style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 12, color: "var(--ink-dim)" }}>
                    <input
                        type="checkbox"
                        data-testid="apply-similar-toggle"
                        checked={applyAll}
                        onChange={(e) => setApplyAll(e.target.checked)}
                    />
                    Apply this fix to similar cases (teach the system)
                </label>

                <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                    <div className="mono-label">Actions</div>

                    {kind === "circle" && (
                        <button className="btn" disabled={busy} onClick={() => submit("convert", { to_kind: "arc", start_angle: 0, end_angle: Math.PI })} data-testid="action-to-arc">
                            <Shuffle size={14} /> Convert to Arc
                        </button>
                    )}
                    {kind === "arc" && (
                        <button className="btn" disabled={busy} onClick={() => submit("convert", { to_kind: "circle" })} data-testid="action-to-circle">
                            <Shuffle size={14} /> Convert to Circle
                        </button>
                    )}
                    {kind === "polyline" && (
                        <>
                            <button className="btn" disabled={busy} onClick={() => submit("convert", { to_kind: "line" })} data-testid="action-to-line">
                                <Shuffle size={14} /> Convert to Line
                            </button>
                            {!d.closed && (
                                <button className="btn" disabled={busy} onClick={() => submit("close_shape", null)} data-testid="action-close-shape">
                                    <LinkIcon size={14} /> Close Shape
                                </button>
                            )}
                        </>
                    )}
                    {(kind === "text" || kind === "dimension") && (
                        <div style={{ display: "flex", gap: 6 }}>
                            <input
                                className="input"
                                value={textEdit}
                                onChange={(e) => setTextEdit(e.target.value)}
                                data-testid="action-text-input"
                                placeholder="Corrected text"
                            />
                            <button className="btn btn-primary" disabled={busy || !textEdit} onClick={() => submit("edit_text", { text: textEdit })} data-testid="action-edit-text">
                                <Type size={14} /> Save
                            </button>
                        </div>
                    )}
                    {entity.uncertain && (
                        <button className="btn" disabled={busy} onClick={() => submit("mark_certain", null)} data-testid="action-mark-certain">
                            <CheckCircle2 size={14} /> Mark as Correct
                        </button>
                    )}
                    <button className="btn btn-danger" disabled={busy} onClick={() => submit("delete", null)} data-testid="action-delete">
                        <Trash2 size={14} /> Delete Entity
                    </button>
                </div>
            </div>
        </div>
    );
}
