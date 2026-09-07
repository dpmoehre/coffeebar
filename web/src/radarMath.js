/** 杯测雷达：中心在 (c,c)，第一维朝上，顺时针。 */

export function axisPoint(i, radius, c, n = 8) {
  const a = (Math.PI * 2 * i) / n - Math.PI / 2;
  return [c + Math.cos(a) * radius, c + Math.sin(a) * radius];
}

export function pickScore(x, y, c, r, n = 8) {
  const dx = x - c;
  const dy = y - c;
  const dist = Math.hypot(dx, dy);
  let a = Math.atan2(dx, -dy);
  if (a < 0) a += Math.PI * 2;
  const i = Math.round(a / ((Math.PI * 2) / n)) % n;
  const score = Math.min(10, Math.max(0, Math.round((dist / r) * 10)));
  return { i, score };
}
