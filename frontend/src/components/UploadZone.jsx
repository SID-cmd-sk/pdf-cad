import { useRef, useState } from "react";
import { uploadFile } from "@/lib/api";
import { toast } from "sonner";

export default function UploadZone({ onUploaded }) {
    const [dragOver, setDragOver] = useState(false);
    const [busy, setBusy] = useState(false);
    const [progress, setProgress] = useState(0);
    const inputRef = useRef();

    const handleFiles = async (files) => {
        if (!files || files.length === 0) return;
        for (const f of files) {
            const name = f.name.toLowerCase();
            if (!/\.(pdf|png|jpe?g|bmp|tiff?|webp)$/.test(name)) {
                toast.error(`Unsupported file: ${f.name}`);
                continue;
            }
            setBusy(true);
            setProgress(0);
            try {
                const res = await uploadFile(f, setProgress);
                toast.success(`Queued ${f.name}`);
                onUploaded && onUploaded(res);
            } catch (e) {
                const msg = e?.response?.data?.detail || e.message;
                toast.error(`Upload failed: ${msg}`);
            } finally {
                setBusy(false);
                setProgress(0);
            }
        }
    };

    return (
        <div
            data-testid="upload-zone"
            className={`dropzone ${dragOver ? "active" : ""}`}
            onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
            onDragLeave={() => setDragOver(false)}
            onDrop={(e) => {
                e.preventDefault();
                setDragOver(false);
                handleFiles(Array.from(e.dataTransfer.files));
            }}
            onClick={() => inputRef.current?.click()}
            style={{ cursor: busy ? "wait" : "pointer" }}
        >
            <input
                ref={inputRef}
                data-testid="upload-input"
                type="file"
                accept=".pdf,.png,.jpg,.jpeg,.bmp,.tif,.tiff,.webp"
                multiple
                style={{ display: "none" }}
                onChange={(e) => handleFiles(Array.from(e.target.files))}
            />
            <div style={{ fontFamily: "'IBM Plex Mono', monospace", fontSize: 12, letterSpacing: "0.14em", color: "var(--ink-dim)", textTransform: "uppercase", marginBottom: 14 }}>
                INPUT / RASTER → VECTOR RECONSTRUCTION
            </div>
            <div style={{ fontSize: 24, fontWeight: 500, marginBottom: 8 }}>
                Drop scans, PDFs or images here
            </div>
            <div style={{ color: "var(--ink-dim)", fontSize: 13 }}>
                PDF · PNG · JPG · TIFF · WEBP &nbsp;·&nbsp; Max 60&nbsp;MB
            </div>
            {busy && (
                <div style={{ marginTop: 22 }}>
                    <div className="progress" style={{ maxWidth: 300, margin: "0 auto" }}>
                        <div style={{ width: `${Math.round(progress * 100)}%` }} />
                    </div>
                    <div className="mono-label" style={{ marginTop: 8 }}>Uploading {Math.round(progress * 100)}%</div>
                </div>
            )}
        </div>
    );
}
