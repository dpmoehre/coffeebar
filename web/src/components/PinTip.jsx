// 地图悬停卡片：豆子钉看这袋，国家 / 产区看百科。
export function fmtLatLng(lat, lng) {
  if (lat == null || lng == null || Number.isNaN(Number(lat))) return "—";
  const ns = lat >= 0 ? "N" : "S";
  const ew = lng >= 0 ? "E" : "W";
  return `${Math.abs(Number(lat)).toFixed(2)}°${ns} · ${Math.abs(Number(lng)).toFixed(2)}°${ew}`;
}

export function pinStyle(pin) {
  return [pin.roast, pin.process, ...(pin.tags || [])].filter(Boolean).join(" · ") || "还没填";
}

export function pinGrams(pin) {
  if (pin.pending) return "待入袋";
  if (!pin.in_stock) return "已关袋";
  const n = Number(pin.balance_g);
  return Number.isFinite(n) ? `${Math.round(n)} g` : "—";
}

function Row({ k, v }) {
  return (
    <div className="flex gap-2">
      <dt className="w-12 shrink-0 text-muted">{k}</dt>
      <dd className="m-0 min-w-0 text-cream">{v || "—"}</dd>
    </div>
  );
}

function placeBox(x, y, box, w, h) {
  let left = x + 16;
  let top = y + 16;
  if (left + w > box.w - 8) left = x - w - 12;
  if (top + h > box.h - 8) top = y - h - 12;
  return { left: Math.max(8, left), top: Math.max(8, top) };
}

export default function PinTip({ pin, origin, x = 0, y = 0, box = { w: 400, h: 300 } }) {
  if (origin) {
    const { left, top } = placeBox(x, y, box, 288, 248);
    return (
      <div
        className="pointer-events-none absolute z-20 w-[288px] rounded-xl border border-line
          bg-[#1c1814]/95 p-3 shadow-[0_12px_40px_rgba(0,0,0,0.45)]"
        style={{ left, top }}
      >
        <div className="serif text-[17px] leading-snug text-amber">{origin.label}</div>
        <div className="mt-0.5 text-[12px] text-muted">
          {origin.kind === "country" ? "国家" : "产区"} · 产地百科
        </div>
        <dl className="mt-2 mb-0 space-y-1 text-[13px] leading-relaxed">
          <Row k="海拔" v={origin.altitude} />
          <Row k="豆种" v={origin.beans} />
          <Row k="风味" v={origin.flavors} />
          <Row k="名产" v={origin.famous} />
        </dl>
      </div>
    );
  }
  if (!pin) return null;
  const { left, top } = placeBox(x, y, box, 272, 188);
  return (
    <div
      className="pointer-events-none absolute z-20 w-[272px] rounded-xl border border-line
        bg-[#1c1814]/95 p-3 shadow-[0_12px_40px_rgba(0,0,0,0.45)]"
      style={{ left, top }}
    >
      <div className="serif text-[17px] leading-snug text-amber">{pin.label || "未命名产地"}</div>
      <dl className="mt-2 mb-0 space-y-1 text-[13px] leading-relaxed">
        <Row k="经纬度" v={fmtLatLng(pin.lat, pin.lng)} />
        <Row k="产区" v={pin.origin} />
        <Row k="豆子" v={pin.name} />
        <Row k="克重" v={pinGrams(pin)} />
        <Row k="风格" v={pinStyle(pin)} />
      </dl>
    </div>
  );
}
