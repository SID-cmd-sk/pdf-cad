import { Eye, EyeOff } from "lucide-react";

const LAYERS = [
    { key: "GEOMETRY", label: "Geometry", color: "#76f7e3" },
    { key: "TEXT", label: "Text", color: "#ffcc66" },
    { key: "DIMENSIONS", label: "Dimensions", color: "#8ef0a0" },
    { key: "UNCERTAIN", label: "Uncertain", color: "#ff4d4f" },
];

export default function LayerPanel({ layers, counts, onToggle }) {
    return (
        <div className="panel" data-testid="layer-panel">
            <div className="panel-header">
                <span>Layers</span>
                <span style={{ color: "var(--ink-soft)" }}>{Object.values(counts || {}).reduce((a, b) => a + b, 0)} items</span>
            </div>
            <div className="panel-body" style={{ padding: 6 }}>
                {LAYERS.map((l) => {
                    const visible = layers[l.key] !== false;
                    const ct = counts?.[l.key] || 0;
                    return (
                        <button
                            key={l.key}
                            onClick={() => onToggle(l.key)}
                            data-testid={`layer-${l.key}`}
                            style={{
                                display: "flex",
                                alignItems: "center",
                                gap: 10,
                                padding: "8px 10px",
                                width: "100%",
                                border: "none",
                                background: "transparent",
                                color: visible ? "var(--ink)" : "var(--ink-soft)",
                                borderRadius: 4,
                                cursor: "pointer",
                                fontSize: 13,
                                textAlign: "left",
                            }}
                        >
                            {visible ? <Eye size={14} /> : <EyeOff size={14} />}
                            <span style={{ width: 10, height: 10, background: l.color, borderRadius: 2, opacity: visible ? 1 : 0.3 }} />
                            <span style={{ flex: 1 }}>{l.label}</span>
                            <span className="mono" style={{ color: "var(--ink-soft)", fontSize: 11 }}>{ct}</span>
                        </button>
                    );
                })}
            </div>
        </div>
    );
}
