/** 把挤在一起的地图钉散开，让每一颗都能点到。 */

export function clusterBy(items, limit, dist) {
  const n = items.length;
  const parent = Array.from({ length: n }, (_, i) => i);
  const find = (i) => (parent[i] === i ? i : (parent[i] = find(parent[i])));
  for (let i = 0; i < n; i++) {
    for (let j = i + 1; j < n; j++) {
      if (dist(items[i], items[j]) > limit) continue;
      const a = find(i);
      const b = find(j);
      if (a !== b) parent[a] = b;
    }
  }
  const groups = new Map();
  items.forEach((it, i) => {
    const r = find(i);
    if (!groups.has(r)) groups.set(r, []);
    groups.get(r).push(it);
  });
  return [...groups.values()];
}

function pinKey(p) {
  return `${p.bean_id ?? p.key ?? ""}:${p.place_id ?? ""}`;
}

function sortGroup(group) {
  return [...group].sort((a, b) => pinKey(a).localeCompare(pinKey(b)));
}

export function ringOffsets(n, radius) {
  if (n <= 1) return [{ dx: 0, dy: 0 }];
  return Array.from({ length: n }, (_, i) => {
    const a = -Math.PI / 2 + (2 * Math.PI * i) / n;
    return { dx: radius * Math.cos(a), dy: radius * Math.sin(a) };
  });
}

function ringRadius(n, gap) {
  if (n <= 1) return 0;
  if (n === 2) return gap / 2;
  return gap / (2 * Math.sin(Math.PI / n));
}

/** 平面图：只有几乎叠在同一像素上的钉才散开。
 * 邻产区不要并成一圈，否则换缩放会看起来像换了落点。 */
export function spreadScreen(items, k = 1, gap = 26, stackPx = 10) {
  if (!items.length) return [];
  const zoom = Math.max(Number(k) || 1, 1);
  const mapGap = gap / zoom;
  const mapLimit = stackPx / zoom;
  const groups = clusterBy(items, mapLimit, (a, b) => Math.hypot(a.x - b.x, a.y - b.y));
  const out = [];
  for (const raw of groups) {
    const group = sortGroup(raw);
    if (group.length === 1) {
      out.push({ ...group[0], sx: group[0].x, sy: group[0].y });
      continue;
    }
    const cx = group.reduce((s, p) => s + p.x, 0) / group.length;
    const cy = group.reduce((s, p) => s + p.y, 0) / group.length;
    const offs = ringOffsets(group.length, ringRadius(group.length, mapGap));
    group.forEach((p, i) => {
      out.push({ ...p, sx: cx + offs[i].dx, sy: cy + offs[i].dy });
    });
  }
  return out;
}

export function degreeDist(a, b) {
  const dlat = a.lat - b.lat;
  const dlng = (a.lng - b.lng) * Math.cos(((a.lat + b.lat) * Math.PI) / 360);
  return Math.hypot(dlat, dlng);
}

/** 地球：同一产区多钉绕真点散开，卡片仍用原来的经纬度。 */
export function spreadLatLng(items, limitDeg = 0.35, ringDeg = 0.55) {
  if (!items.length) return [];
  const groups = clusterBy(items, limitDeg, degreeDist);
  const out = [];
  for (const raw of groups) {
    const group = sortGroup(raw);
    if (group.length === 1) {
      out.push({ ...group[0], plat: group[0].lat, plng: group[0].lng });
      continue;
    }
    const clat = group.reduce((s, p) => s + p.lat, 0) / group.length;
    const clng = group.reduce((s, p) => s + p.lng, 0) / group.length;
    const cos = Math.cos((clat * Math.PI) / 180) || 0.2;
    const offs = ringOffsets(group.length, ringRadius(group.length, ringDeg));
    group.forEach((p, i) => {
      out.push({
        ...p,
        plat: clat + offs[i].dy,
        plng: clng + offs[i].dx / cos,
      });
    });
  }
  return out;
}
