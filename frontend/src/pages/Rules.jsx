import { useEffect, useState } from "react";
import { listRules, updateRule, deleteRule } from "@/lib/api";
import { Trash2, ToggleLeft, ToggleRight, Brain } from "lucide-react";
import { toast } from "sonner";

export default function Rules() {
    const [rules, setRules] = useState([]);

    const refresh = async () => {
        try { setRules(await listRules()); } catch { toast.error("Load rules failed"); }
    };
    useEffect(() => { refresh(); }, []);

    const toggle = async (r) => {
        try { await updateRule(r.id, { active: !r.active }); refresh(); }
        catch { toast.error("Toggle failed"); }
    };
    const remove = async (r) => {
        if (!window.confirm("Delete this rule?")) return;
        try { await deleteRule(r.id); toast.success("Deleted"); refresh(); }
        catch { toast.error("Delete failed"); }
    };

    return (
        <div style={{ overflow: "auto", padding: "28px 32px" }}>
            <div style={{ maxWidth: 1200, margin: "0 auto" }}>
                <div style={{ fontSize: 11, letterSpacing: "0.2em", color: "var(--ink-dim)", fontFamily: "'IBM Plex Mono', monospace", marginBottom: 12 }}>
                    LEARNING LIBRARY
                </div>
                <div style={{ fontSize: 28, fontWeight: 400, marginBottom: 8 }}>
                    Rules the engine has learned
                </div>
                <div style={{ color: "var(--ink-dim)", marginBottom: 28, maxWidth: 780 }}>
                    Every time you correct an entity with <em>Apply to similar</em>, a rule is added here.
                    New jobs will auto-apply these during reconstruction.
                </div>

                <div className="panel" data-testid="rules-panel">
                    <div className="panel-header">
                        <span><Brain size={12} style={{ verticalAlign: "middle", marginRight: 6 }} /> {rules.length} rules</span>
                    </div>
                    {rules.length === 0 ? (
                        <div className="panel-body" style={{ color: "var(--ink-dim)" }}>No rules yet. Make a correction inside a job to teach the system.</div>
                    ) : (
                        <table className="table" data-testid="rules-table">
                            <thead>
                                <tr>
                                    <th>Pattern</th>
                                    <th>Action</th>
                                    <th>Confidence</th>
                                    <th>Uses</th>
                                    <th>Notes</th>
                                    <th>Active</th>
                                    <th></th>
                                </tr>
                            </thead>
                            <tbody>
                                {rules.map((r) => (
                                    <tr key={r.id} data-testid={`rule-row-${r.id}`}>
                                        <td className="mono" style={{ fontSize: 12 }}>{r.pattern_signature}</td>
                                        <td>
                                            <span className="chip" style={{ textTransform: "none" }}>{r.action_type}</span>
                                            {r.action_data?.to_kind && <span className="mono" style={{ fontSize: 11, marginLeft: 6, color: "var(--ink-dim)" }}>→ {r.action_data.to_kind}</span>}
                                            {r.action_data?.text && <span className="mono" style={{ fontSize: 11, marginLeft: 6, color: "var(--ink-dim)" }}>"{r.action_data.text}"</span>}
                                        </td>
                                        <td className="mono" style={{ color: "var(--ink-dim)" }}>{Math.round((r.confidence || 0) * 100)}%</td>
                                        <td className="mono" style={{ color: "var(--ink-dim)" }}>{r.successes}/{r.uses}</td>
                                        <td style={{ fontSize: 12, color: "var(--ink-dim)" }}>{r.notes || ""}</td>
                                        <td>
                                            <button
                                                className="btn btn-ghost"
                                                onClick={() => toggle(r)}
                                                data-testid={`rule-toggle-${r.id}`}
                                                style={{ color: r.active ? "var(--accent)" : "var(--ink-soft)" }}
                                            >
                                                {r.active ? <ToggleRight size={16} /> : <ToggleLeft size={16} />}
                                                {r.active ? "On" : "Off"}
                                            </button>
                                        </td>
                                        <td style={{ textAlign: "right" }}>
                                            <button className="btn btn-danger" onClick={() => remove(r)} data-testid={`rule-delete-${r.id}`}>
                                                <Trash2 size={14} />
                                            </button>
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    )}
                </div>
            </div>
        </div>
    );
}
