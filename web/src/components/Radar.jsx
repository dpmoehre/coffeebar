// 杯测雷达：八个维度 1–10
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

export default function Radar({ scores }) {
  const size = 220;
  const c = size / 2;
  const r = 76;
  const n = DIMS.length;
  const at = (i, radius) => {
    const a = (Math.PI * 2 * i) / n - Math.PI / 2;
    return [c + Math.cos(a) * radius, c + Math.sin(a) * radius];
  };

  const pts = DIMS.map(([k], i) => at(i, ((scores?.[k] || 0) / 10) * r));
  const poly = pts.map((p) => p.join(",")).join(" ");

  return (
    <svg viewBox={`0 0 ${size} ${size}`} className="w-full" style={{ maxHeight: 230 }}>
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
      {scores && (
        <polygon points={poly} fill="rgba(200,141,68,.28)" stroke="#c88d44" strokeWidth="2" />
      )}
      {DIMS.map(([k, label], i) => {
        const [x, y] = at(i, r + 18);
        return (
          <text
            key={k}
            x={x}
            y={y}
            fill="#9c8b74"
            fontSize="11"
            textAnchor="middle"
            dominantBaseline="middle"
          >
            {label}
          </text>
        );
      })}
      {!scores && (
        <text x={c} y={c} fill="#9c8b74" fontSize="12" textAnchor="middle">
          还没杯测
        </text>
      )}
    </svg>
  );
}
