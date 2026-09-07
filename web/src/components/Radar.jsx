// 杯测雷达：八个维度 1–10。可只看，也可在图上点/拖打分。可叠均分 + 最新。
import { useRef, useState } from "react";

import { axisPoint, dimNum, fmtScore, hasDims, pickScore } from "../radarMath.js";
import { Chip } from "../ui.jsx";

const DIMS = [
  ["dry", "干香"],
  ["flavor", "风味"],
  ["aftertaste", "余韵"],
  ["acidity", "酸质"],
  ["sweetness", "甜感"],
  ["body", "醇厚"],
  ["balance", "平衡"],
  ["overall", "总体"],
];

function polyOf(scores, at, r) {
  return DIMS.map(([k], i) => at(i, (dimNum(scores, k) / 10) * r).join(",")).join(" ");
}

export default function Radar({
  scores,
  base,
  overlay,
  mode = "both",
  editable = false,
  onChange,
}) {
  const svgRef = useRef(null);
  const drag = useRef(false);
  const size = 240;
  const c = size / 2;
  const r = 84;
  const n = DIMS.length;
  const at = (i, radius) => axisPoint(i, radius, c, n);

  const viewBase = editable ? scores : (base ?? scores);
  const viewOverlay = editable ? null : overlay;
  const showBase = Boolean(hasDims(viewBase) && (!viewOverlay || mode === "both" || mode === "base"));
  const showOverlay = Boolean(hasDims(viewOverlay) && (mode === "both" || mode === "overlay"));
  const numbers = mode === "overlay" && hasDims(viewOverlay) ? viewOverlay : viewBase;

  const apply = (e) => {
    if (!editable || !onChange || !svgRef.current) return;
    const ev = e.touches ? e.touches[0] : e;
    if (!ev) return;
    const ctm = svgRef.current.getScreenCTM();
    if (!ctm) return;
    const pt = svgRef.current.createSVGPoint();
    pt.x = ev.clientX;
    pt.y = ev.clientY;
    const p = pt.matrixTransform(ctm.inverse());
    const { i, score } = pickScore(p.x, p.y, c, r, n);
    onChange(DIMS[i][0], score < 1 ? "" : score);
  };

  const down = (e) => {
    if (!editable) return;
    drag.current = true;
    e.currentTarget.setPointerCapture?.(e.pointerId);
    apply(e);
  };
  const move = (e) => {
    if (drag.current) apply(e);
  };
  const up = () => {
    drag.current = false;
  };

  return (
    <svg
      ref={svgRef}
      viewBox={`0 0 ${size} ${size}`}
      className={`w-full ${editable ? "touch-none cursor-crosshair" : ""}`}
      style={{ maxHeight: 260 }}
      onPointerDown={down}
      onPointerMove={move}
      onPointerUp={up}
      onPointerCancel={up}
    >
      {[0.25, 0.5, 0.75, 1].map((f) => (
        <polygon
          key={f}
          points={DIMS.map((_, i) => at(i, r * f).join(",")).join(" ")}
          fill="none"
          stroke="#3a3228"
        />
      ))}
      {DIMS.map((_, i) => {
        const [x, y] = at(i, r);
        return <line key={i} x1={c} y1={c} x2={x} y2={y} stroke="#3a3228" />;
      })}
      {showBase && (
        <polygon
          points={polyOf(viewBase, at, r)}
          fill="rgba(200,141,68,.28)"
          stroke="#c88d44"
          strokeWidth={showOverlay ? 1.5 : 2}
          strokeDasharray={showOverlay ? "4 4" : undefined}
        />
      )}
      {showOverlay && (
        <polygon
          points={polyOf(viewOverlay, at, r)}
          fill="none"
          stroke="#e0a85a"
          strokeWidth="2"
        />
      )}
      {editable &&
        DIMS.map(([k], i) => {
          const v = dimNum(scores, k);
          if (!v) return null;
          const [x, y] = at(i, (v / 10) * r);
          return <circle key={`h-${k}`} cx={x} cy={y} r="5" fill="#e0a85a" stroke="#1a120a" />;
        })}
      {DIMS.map(([k, label], i) => {
        const [x, y] = at(i, r + 22);
        const v = dimNum(numbers, k);
        return (
          <text
            key={k}
            x={x}
            y={y}
            fill={v ? "#e0a85a" : "#9c8b74"}
            fontSize="11"
            textAnchor="middle"
            dominantBaseline="middle"
          >
            {v ? `${label} ${fmtScore(v)}` : label}
          </text>
        );
      })}
      {!hasDims(viewBase) && !hasDims(viewOverlay) && (
        <text x={c} y={c} fill="#9c8b74" fontSize="12" textAnchor="middle">
          {editable ? "点一条轴打分" : "还没杯测"}
        </text>
      )}
    </svg>
  );
}

export function LayeredRadar({
  base,
  overlay,
  baseLabel = "均分",
  overlayLabel = "最新",
  layered = true,
}) {
  const canLayer = Boolean(layered && hasDims(base) && hasDims(overlay));
  const [mode, setMode] = useState("both");
  const view = canLayer ? mode : "base";
  const toggle = (key) => setMode((cur) => (cur === key ? "both" : key));

  return (
    <div>
      {canLayer && (
        <div className="mb-2 flex flex-wrap gap-2">
          <Chip type="button" on={view === "both" || view === "base"} onClick={() => toggle("base")}>
            {baseLabel}
          </Chip>
          <Chip
            type="button"
            on={view === "both" || view === "overlay"}
            onClick={() => toggle("overlay")}
          >
            {overlayLabel}
          </Chip>
        </div>
      )}
      <Radar base={base} overlay={canLayer ? overlay : null} mode={view} />
    </div>
  );
}
