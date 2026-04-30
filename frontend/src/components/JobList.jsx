import { Link } from "react-router-dom";
import { Trash2, RefreshCw } from "lucide-react";
import { deleteJob, reprocessJob } from "@/lib/api";
import { toast } from "sonner";

const statusChip = (s) => {
    if (s === "done") return <span className="chip ok" data-testid={`status-${s}`}>Done</span>;
    if (s === "error") return <span className="chip danger" data-testid={`status-${s}`}>Error</span>;
    if (s === "processing") return <span className="chip pending" data-testid={`status-${s}`}>Processing</span>;
    return <span className="chip" data-testid={`status-${s}`}>{s}</span>;
};

const fmtDate = (d) => {
    if (!d) return "";
    try { return new Date(d).toLocaleString(); } catch { return d; }
};

export default function JobList({ jobs, onMutate }) {
    const onDelete = async (id) => {
        if (!window.confirm("Delete this job and all its data?")) return;
        try {
            await deleteJob(id);
            toast.success("Job deleted");
            onMutate && onMutate();
        } catch (e) {
            toast.error("Delete failed");
        }
    };
    const onReprocess = async (id) => {
        try {
            await reprocessJob(id);
            toast.success("Reprocessing started");
            onMutate && onMutate();
        } catch (e) {
            toast.error("Reprocess failed");
        }
    };

    if (!jobs || jobs.length === 0) {
        return (
            <div className="panel-body" style={{ textAlign: "center", color: "var(--ink-dim)" }} data-testid="jobs-empty">
                No jobs yet. Upload a drawing above to begin.
            </div>
        );
    }

    return (
        <table className="table" data-testid="jobs-table">
            <thead>
                <tr>
                    <th>File</th>
                    <th>Status</th>
                    <th>Pages</th>
                    <th>Stage</th>
                    <th>Created</th>
                    <th style={{ textAlign: "right" }}>Actions</th>
                </tr>
            </thead>
            <tbody>
                {jobs.map((j) => (
                    <tr key={j.id} data-testid={`job-row-${j.id}`}>
                        <td>
                            <Link
                                to={`/job/${j.id}`}
                                className="mono"
                                style={{ color: "var(--accent)", textDecoration: "none" }}
                                data-testid={`job-link-${j.id}`}
                            >
                                {j.filename}
                            </Link>
                            {j.error && <div style={{ color: "var(--danger)", fontSize: 12, marginTop: 4 }}>{j.error}</div>}
                        </td>
                        <td>
                            {statusChip(j.status)}
                            {j.status === "processing" && (
                                <div className="progress" style={{ marginTop: 6 }}>
                                    <div style={{ width: `${Math.round((j.progress || 0) * 100)}%` }} />
                                </div>
                            )}
                        </td>
                        <td className="mono" style={{ color: "var(--ink-dim)" }}>{j.num_pages || "-"}</td>
                        <td className="mono" style={{ color: "var(--ink-dim)", fontSize: 12 }}>{j.stage || ""}</td>
                        <td className="mono" style={{ color: "var(--ink-dim)", fontSize: 12 }}>{fmtDate(j.created_at)}</td>
                        <td style={{ textAlign: "right" }}>
                            <button
                                className="btn btn-ghost"
                                onClick={() => onReprocess(j.id)}
                                data-testid={`reprocess-${j.id}`}
                                title="Reprocess"
                            >
                                <RefreshCw size={14} /> Reprocess
                            </button>
                            <button
                                className="btn btn-danger"
                                onClick={() => onDelete(j.id)}
                                data-testid={`delete-${j.id}`}
                                title="Delete"
                                style={{ marginLeft: 8 }}
                            >
                                <Trash2 size={14} />
                            </button>
                        </td>
                    </tr>
                ))}
            </tbody>
        </table>
    );
}
