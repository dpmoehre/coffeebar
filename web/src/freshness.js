export const PHASE_LABEL = {
  unknown: "没填烘焙日",
  resting: "养豆中",
  peak: "正当时",
  fading: "过了高峰",
  stale: "老了",
};

export const SCORE_DIMS = [
  ["dry", "干香"],
  ["flavor", "风味"],
  ["aftertaste", "余韵"],
  ["acidity", "酸质"],
  ["sweetness", "甜感"],
  ["body", "醇厚"],
  ["balance", "平衡"],
  ["overall", "总体"],
];

export function freshnessLine(f) {
  if (!f) return "";
  const bits = [];
  if (f.phase && f.phase !== "unknown" && f.days_after_roast != null) {
    bits.push(`烘后第 ${f.days_after_roast} 天 · ${f.label || PHASE_LABEL[f.phase] || ""}`);
  }
  if (f.opened_long) bits.push("开封已久");
  return bits.join(" · ");
}

export function scoreFreshnessLine(s) {
  if (!s || s.days_after_roast == null) return "";
  const label = PHASE_LABEL[s.window_phase] || s.window_phase || "";
  return label ? `烘后第 ${s.days_after_roast} 天 · ${label}` : `烘后第 ${s.days_after_roast} 天`;
}