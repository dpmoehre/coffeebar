// 墨卡托 / 等积（Equal Earth）。国界随包，不打外网瓦片。
import { geoEqualEarth, geoGraticule, geoMercator, geoPath } from "d3-geo";
import { useEffect, useMemo, useRef, useState } from "react";

import { countries } from "../geo/world.js";
import PinTip from "./PinTip.jsx";

function makeProjection(kind, w, h) {
  const proj = kind === "mercator" ? geoMercator() : geoEqualEarth();
  return proj.fitExtent(
    [
      [16, 16],
      [w - 16, h - 16],
    ],
    countries
  );
}

export default function WorldMap2d({
  kind = "mercator",
  pins = [],
  selectedId,
  placing,
  onOpen,
  onPlace,
}) {
  const wrap = useRef(null);
  const [size, setSize] = useState({ w: 640, h: 420 });
  const [view, setView] = useState({ k: 1, x: 0, y: 0 });
  const [tip, setTip] = useState(null);
  const drag = useRef(null);

  useEffect(() => {
    const el = wrap.current;
    if (!el) return;
    const ro = new ResizeObserver(() => {
      const r = el.getBoundingClientRect();
      if (r.width && r.height) setSize({ w: r.width, h: r.height });
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  useEffect(() => {
    setView({ k: 1, x: 0, y: 0 });
  }, [kind]);

  const { w, h } = size;
  const projection = useMemo(() => makeProjection(kind, w, h), [kind, w, h]);
  const path = useMemo(() => geoPath(projection), [projection]);
  const graticule = useMemo(() => geoGraticule()(), []);
  const land = useMemo(() => path(countries), [path]);
  const grid = useMemo(() => path(graticule), [path]);

  const dots = useMemo(
    () =>
      pins
        .map((p) => {
          const xy = projection([p.lng, p.lat]);
          return xy ? { ...p, x: xy[0], y: xy[1] } : null;
        })
        .filter(Boolean),
    [pins, projection]
  );

  const toLatLng = (clientX, clientY) => {
    const rect = wrap.current.getBoundingClientRect();
    const px = (clientX - rect.left - view.x) / view.k;
    const py = (clientY - rect.top - view.y) / view.k;
    return projection.invert([px, py]);
  };

  const onPointerDown = (e) => {
    if (e.button !== 0) return;
    drag.current = {
      id: e.pointerId,
      x: e.clientX,
      y: e.clientY,
      ox: view.x,
      oy: view.y,
      moved: false,
    };
    e.currentTarget.setPointerCapture(e.pointerId);
  };

  const onPointerMove = (e) => {
    const d = drag.current;
    if (!d || d.id !== e.pointerId) return;
    const dx = e.clientX - d.x;
    const dy = e.clientY - d.y;
    if (Math.hypot(dx, dy) > 5) d.moved = true;
    if (d.moved) {
      setTip(null);
      setView((v) => ({ ...v, x: d.ox + dx, y: d.oy + dy }));
    }
  };

  const onPointerUp = (e) => {
    const d = drag.current;
    drag.current = null;
    if (!d || d.moved) return;
    const ll = toLatLng(e.clientX, e.clientY);
    if (!ll) return;
    if (placing && onPlace) onPlace(ll[1], ll[0]);
  };

  const onWheel = (e) => {
    e.preventDefault();
    const rect = wrap.current.getBoundingClientRect();
    const mx = e.clientX - rect.left;
    const my = e.clientY - rect.top;
    const factor = e.deltaY < 0 ? 1.12 : 1 / 1.12;
    setView((v) => {
      const k = Math.min(8, Math.max(0.7, v.k * factor));
      const nx = mx - ((mx - v.x) * k) / v.k;
      const ny = my - ((my - v.y) * k) / v.k;
      return { k, x: nx, y: ny };
    });
  };

  return (
    <div
      ref={wrap}
      className={`relative h-full min-h-[280px] w-full overflow-hidden rounded-2xl border border-line bg-[#0c0a08] ${
        placing ? "cursor-crosshair" : "cursor-grab"
      }`}
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={onPointerUp}
      onWheel={onWheel}
    >
      <svg width={w} height={h} className="block">
        <g transform={`translate(${view.x},${view.y}) scale(${view.k})`}>
          <path d={grid} fill="none" stroke="#2a231c" strokeWidth={0.6} />
          <path d={land} fill="#1c1814" stroke="#3a3228" strokeWidth={0.7} />
          {dots.map((p) => {
            const on = p.bean_id === selectedId || tip?.pin?.place_id === p.place_id;
            const r = on ? 6.5 : 4.5;
            return (
              <g
                key={`${p.bean_id}-${p.place_id}`}
                transform={`translate(${p.x},${p.y})`}
                className="cursor-pointer"
                onPointerEnter={(e) => {
                  if (drag.current?.moved) return;
                  const box = wrap.current.getBoundingClientRect();
                  setTip({ pin: p, x: e.clientX - box.left, y: e.clientY - box.top });
                }}
                onPointerMove={(e) => {
                  if (drag.current?.moved) return;
                  const box = wrap.current.getBoundingClientRect();
                  setTip({ pin: p, x: e.clientX - box.left, y: e.clientY - box.top });
                }}
                onPointerLeave={() => setTip(null)}
                onPointerUp={(e) => {
                  e.stopPropagation();
                  if (drag.current?.moved) return;
                  if (!placing && onOpen) onOpen(p.bean_id);
                }}
              >
                <circle r={14} fill="transparent" />
                <circle
                  r={r + 3}
                  fill={p.in_stock ? "#c88d44" : "transparent"}
                  fillOpacity={p.in_stock ? 0.22 : 0}
                  stroke={p.in_stock ? "#c88d44" : "#9c8b74"}
                  strokeWidth={p.in_stock ? 0 : 1.4}
                />
                <circle
                  r={r}
                  fill={p.in_stock ? "#c88d44" : "#12100e"}
                  stroke={p.in_stock ? "#e0a85a" : "#9c8b74"}
                  strokeWidth={1.4}
                />
                {on && <circle r={r + 6} fill="none" stroke="#e0a85a" strokeWidth={1} />}
              </g>
            );
          })}
        </g>
      </svg>
      <PinTip pin={tip?.pin} x={tip?.x} y={tip?.y} box={size} />
    </div>
  );
}
