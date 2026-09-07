// 杯测雷达：八个维度 1–10。可只看，也可在图上点/拖打分。
import { useRef } from "react";

import { axisPoint, pickScore } from "../radarMath.js";

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

function num(scores, k) {
  const v = scores?.[k];
  if (v === "" || v == null) return 0;
  const n = Number(v);
  return Number.isFinite(n) ? n : 0;
}

function hasScore(scores) {
  return Boolean(scores && DIMS.some(([k]) => num(scores, k) > 0));
}

export default function Radar({ scores, editable = false, onChange }) {
  const svgRef = useRef(null);
  const drag = useRef(false);
  const size = 240;
  const c = size / 2;
  const r = 84;
  const n = DIMS.length;
  const at = (i, radius) => axisPoint(i, radius, c, n);

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

  const pts = DIMS.map(([k], i) => at(i, (num(scores, k) / 10) * r));
  const poly = pts.map((p) => p.join(",")).join(" ");

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
      {hasScore(scores) && (
        <polygon points={poly} fill="rgba(200,141,68,.28)" stroke="#c88d44" strokeWidth="2" />
      )}
      {editable &&
        DIMS.map(([k], i) => {
          const v = num(scores, k);
          if (!v) return null;
          const [x, y] = at(i, (v / 10) * r);
          return <circle key={`h-${k}`} cx={x} cy={y} r="5" fill="#e0a85a" stroke="#1a120a" />;
        })}
      {DIMS.map(([k, label], i) => {
        const [x, y] = at(i, r + 22);
        const v = num(scores, k);
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
            {v ? `${label} ${v}` : label}
          </text>
        );
      })}
      {!hasScore(scores) && (
        <text x={c} y={c} fill="#9c8b74" fontSize="12" textAnchor="middle">
          {editable ? "点一条轴打分" : "还没杯测"}
        </text>
      )}
    </svg>
  );
}
