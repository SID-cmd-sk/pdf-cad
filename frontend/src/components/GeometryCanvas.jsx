import { useEffect, useRef, useState, useMemo } from "react";

/**
 * GeometryCanvas: pan/zoom viewer showing the background scan + interactive
 * SVG overlay of detected entities. Click an entity to select.
 */
export default function GeometryCanvas({ width, height, imageUrl, entities, layers, selectedId, onSelect, mode = "overlay" }) {
    const wrapRef = useRef();
    const [view, setView] = useState({ x: 0, y: 0, scale: 1 });
    const [grab, setGrab] = useState(false);
    const [dragStart, setDragStart] = useState(null);

    // Fit on mount / size change
    useEffect(() => {
        if (!wrapRef.current || !width || !height) return;
        const rect = wrapRef.current.getBoundingClientRect();
        const s = Math.min(rect.width / width, rect.height / height) * 0.95;
        const x = (rect.width - width * s) / 2;
        const y = (rect.height - height * s) / 2;
        setView({ x, y, scale: s });
    }, [width, height, imageUrl]);

    const onWheel = (e) => {
        e.preventDefault();
        const rect = wrapRef.current.getBoundingClientRect();
        const mx = e.clientX - rect.left;
        const my = e.clientY - rect.top;
        const delta = e.deltaY < 0 ? 1.12 : 0.89;
        setView((v) => {
            const ns = Math.max(0.05, Math.min(20, v.scale * delta));
            const nx = mx - ((mx - v.x) / v.scale) * ns;
            const ny = my - ((my - v.y) / v.scale) * ns;
            return { x: nx, y: ny, scale: ns };
        });
    };

    const onMouseDown = (e) => {
        if (e.button !== 0) return;
        if (e.target.closest("[data-entity-id], [data-entity-hit]")) return;
        setGrab(true);
        setDragStart({ x: e.clientX - view.x, y: e.clientY - view.y });
    };
    const onMouseMove = (e) => {
        if (!grab || !dragStart) return;
        setView((v) => ({ ...v, x: e.clientX - dragStart.x, y: e.clientY - dragStart.y }));
    };
    const onMouseUp = () => { setGrab(false); setDragStart(null); };

    const resetView = () => {
        if (!wrapRef.current || !width || !height) return;
        const rect = wrapRef.current.getBoundingClientRect();
        const s = Math.min(rect.width / width, rect.height / height) * 0.95;
        setView({ x: (rect.width - width * s) / 2, y: (rect.height - height * s) / 2, scale: s });
    };

    const filtered = useMemo(() => {
        const activeLayers = layers || {};
        return (entities || []).filter((e) => {
            if (e.deleted) return false;
            const layer = e.uncertain ? "UNCERTAIN" : (e.layer || "GEOMETRY");
            return activeLayers[layer] !== false;
        });
    }, [entities, layers]);

    const renderEntity = (e) => {
        const layer = e.uncertain ? "UNCERTAIN" : (e.layer || "GEOMETRY");
        const isSel = selectedId === e.id;
        const onClick = (ev) => { ev.stopPropagation(); onSelect && onSelect(e); };
        const hitWidth = Math.max(10, 12 / view.scale);
        const strokeW = 2 / view.scale;
        const common = {
            className: `entity layer-${layer}`,
            "data-uncertain": e.uncertain ? "1" : "0",
            "data-selected": isSel ? "1" : "0",
            "data-entity-id": e.id,
            onClick,
            style: { cursor: "pointer", vectorEffect: "non-scaling-stroke" },
        };
        const hit = {
            "data-entity-hit": e.id,
            onClick,
            style: { cursor: "pointer", pointerEvents: "stroke" },
            stroke: "transparent",
            fill: "none",
            strokeWidth: hitWidth,
        };
        const d = e.data || {};
        if (e.kind === "line") {
            return (
                <g key={e.id}>
                    <line {...hit} x1={d.x1} y1={d.y1} x2={d.x2} y2={d.y2} />
                    <line {...common} x1={d.x1} y1={d.y1} x2={d.x2} y2={d.y2} strokeWidth={strokeW} />
                </g>
            );
        }
        if (e.kind === "circle") {
            return (
                <g key={e.id}>
                    <circle {...hit} cx={d.cx} cy={d.cy} r={d.r} />
                    <circle {...common} cx={d.cx} cy={d.cy} r={d.r} fill="none" strokeWidth={strokeW} />
                </g>
            );
        }
        if (e.kind === "arc") {
            const sa = d.start_angle || 0;
            const ea = d.end_angle || Math.PI;
            const x1 = d.cx + d.r * Math.cos(sa);
            const y1 = d.cy + d.r * Math.sin(sa);
            const x2 = d.cx + d.r * Math.cos(ea);
            const y2 = d.cy + d.r * Math.sin(ea);
            const large = (ea - sa) > Math.PI ? 1 : 0;
            const dp = `M ${x1} ${y1} A ${d.r} ${d.r} 0 ${large} 1 ${x2} ${y2}`;
            return (
                <g key={e.id}>
                    <path {...hit} d={dp} />
                    <path {...common} d={dp} fill="none" strokeWidth={strokeW} />
                </g>
            );
        }
        if (e.kind === "polyline") {
            const pts = d.points || [];
            const str = pts.map((p) => `${p[0]},${p[1]}`).join(" ");
            if (d.closed) {
                return (
                    <g key={e.id}>
                        <polygon {...hit} points={str} />
                        <polygon {...common} points={str} fill="none" strokeWidth={strokeW} />
                    </g>
                );
            }
            return (
                <g key={e.id}>
                    <polyline {...hit} points={str} />
                    <polyline {...common} points={str} fill="none" strokeWidth={strokeW} />
                </g>
            );
        }
        if (e.kind === "text" || e.kind === "dimension") {
            const size = Math.max(8, (d.height || 16) * 0.9);
            return (
                <g key={e.id} {...common}>
                    <rect
                        x={d.x - 2}
                        y={d.y - 2}
                        width={(d.width || 80) + 4}
                        height={(d.height || 16) + 4}
                        fill="rgba(245, 165, 36, 0.08)"
                        stroke={isSel ? "#f5a524" : "rgba(245, 165, 36, 0.4)"}
                        strokeWidth={1 / view.scale}
                    />
                    <text
                        x={d.x}
                        y={d.y + (d.height || 16) * 0.85}
                        fontSize={size}
                        fill={e.kind === "dimension" ? "#8ef0a0" : "#ffcc66"}
                        fontFamily="'IBM Plex Mono', monospace"
                    >
                        {d.text}
                    </text>
                </g>
            );
        }
        if (e.kind === "hatch") {
            const bb = d.bbox || [0, 0, 0, 0];
            const [x0, y0, x1, y1] = bb;
            const patternId = `hatch-${e.id}`;
            const angle = d.angle_deg || 45;
            return (
                <g key={e.id}>
                    <defs>
                        <pattern id={patternId} width="8" height="8" patternUnits="userSpaceOnUse" patternTransform={`rotate(${angle})`}>
                            <line x1="0" y1="0" x2="0" y2="8" stroke="#76f7e3" strokeWidth="1" opacity="0.6" />
                        </pattern>
                    </defs>
                    <rect {...hit} x={x0} y={y0} width={x1 - x0} height={y1 - y0} />
                    <rect
                        {...common}
                        x={x0}
                        y={y0}
                        width={x1 - x0}
                        height={y1 - y0}
                        fill={`url(#${patternId})`}
                        stroke="#76f7e3"
                        strokeDasharray="4 2"
                        strokeWidth={strokeW}
                        opacity="0.7"
                    />
                </g>
            );
        }
        return null;
    };

    return (
        <div style={{ position: "relative", height: "100%" }}>
            <div
                ref={wrapRef}
                className={`canvas-wrap ${grab ? "grabbing" : ""}`}
                style={{ height: "100%" }}
                onWheel={onWheel}
                onMouseDown={onMouseDown}
                onMouseMove={onMouseMove}
                onMouseUp={onMouseUp}
                onMouseLeave={onMouseUp}
                data-testid="geometry-canvas"
            >
                <div
                    style={{
                        position: "absolute",
                        left: view.x,
                        top: view.y,
                        transform: `scale(${view.scale})`,
                        transformOrigin: "0 0",
                        width,
                        height,
                        background: mode === "dxf" ? "#05080c" : "transparent",
                    }}
                >
                    {imageUrl && mode !== "dxf" && (
                        <img
                            src={imageUrl}
                            alt="scan"
                            style={{ width, height, opacity: 0.5, filter: "invert(1) grayscale(1) brightness(1.1)", display: "block" }}
                            draggable={false}
                        />
                    )}
                    <svg
                        width={width}
                        height={height}
                        style={{ position: "absolute", top: 0, left: 0, pointerEvents: "auto" }}
                        viewBox={`0 0 ${width} ${height}`}
                    >
                        {filtered.map(renderEntity)}
                    </svg>
                </div>
            </div>
            <div style={{ position: "absolute", top: 12, right: 12, display: "flex", gap: 8 }}>
                <span className="chip" data-testid="zoom-indicator">{(view.scale * 100).toFixed(0)}%</span>
                <button className="btn" onClick={resetView} data-testid="zoom-fit">Fit</button>
            </div>
        </div>
    );
}
