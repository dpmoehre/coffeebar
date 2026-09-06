// 墨卡托 / 等积（Equal Earth）。国界随包，不打外网瓦片。
import { geoEqualEarth, geoGraticule, geoMercator, geoPath } from "d3-geo";
import { useEffect, useMemo, useRef, useState } from "react";

import { spreadScreen } from "../geo/spread.js";
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

function padIso(id) {
  return String(id ?? "").padStart(3, "0");
}

export default function WorldMap2d({
  kind = "mercator",
  pins = [],
  origins = [],
  selectedId,
  placing,
  onOpen,
  onPlace,
}) {
  const wrap = useRef(null);
  const svgRef = useRef(null);
  const layerRef = useRef(null);
  const [size, setSize] = useState({ w: 640, h: 420 });
  const [view, setView] = useState({ k: 1, x: 0, y: 0 });
  const [tip, setTip] = useState(null);
  const drag = useRef(null);

  useEffect(() => {
    const el = wrap.current;
    if (!el) return;
    const ro = new ResizeObserver((entries) => {
      const r = entries[0]?.contentRect;
      if (r?.width && r?.height) setSize({ w: r.width, h: r.height });
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  useEffect(() => {
    setView({ k: 1, x: 0, y: 0 });
  }, [kind, size.w, size.h]);

  const { w, h } = size;
  const projection = useMemo(() => makeProjection(kind, w, h), [kind, w, h]);
  const path = useMemo(() => geoPath(projection), [projection]);
  const graticule = useMemo(() => geoGraticule()(), []);
  const grid = useMemo(() => path(graticule), [path]);

  const coffeeByIso = useMemo(() => {
    const m = new Map();
    for (const o of origins) {
      if (o.iso) m.set(padIso(o.iso), o);
    }
    return m;
  }, [origins]);

  const countryPaths = useMemo(
    () =>
      countries.features
        .map((f) => {
          const d = path(f);
          return d ? { id: padIso(f.id), d, origin: coffeeByIso.get(padIso(f.id)) } : null;
        })
        .filter(Boolean),
    [path, coffeeByIso]
  );

  const regionDots = useMemo(
    () =>
      origins
        .filter((o) => o.kind === "region")
        .map((o) => {
          const xy = projection([o.lng, o.lat]);
          return xy ? { ...o, x: xy[0], y: xy[1] } : null;
        })
        .filter(Boolean),
    [origins, projection]
  );

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

  const spreadDots = useMemo(() => spreadScreen(dots, view.k), [dots, view.k]);
  // 放大时钉子保持屏幕大小；缩小时跟着地图收，免得盖住整块产区。
  const inv = view.k > 1 ? 1 / view.k : 1;

  const localXY = (e) => {
    const el = wrap.current;
    const box = el.getBoundingClientRect();
    return { x: e.clientX - box.left - el.clientLeft, y: e.clientY - box.top - el.clientTop };
  };

  const hoverOrigin = (origin, e) => {
    if (!origin || drag.current?.moved) return;
    setTip({ origin, ...localXY(e) });
  };

  const leaveOrigin = (key) => {
    setTip((t) => (t?.origin?.key === key ? null : t));
  };

  const toLatLng = (clientX, clientY) => {
    const svg = svgRef.current;
    const layer = layerRef.current;
    if (svg && layer) {
      const ctm = layer.getScreenCTM();
      if (ctm) {
        const pt = svg.createSVGPoint();
        pt.x = clientX;
        pt.y = clientY;
        const p = pt.matrixTransform(ctm.inverse());
        return projection.invert([p.x, p.y]);
      }
    }
    const el = wrap.current;
    const rect = el.getBoundingClientRect();
    const px = (clientX - rect.left - el.clientLeft - view.x) / view.k;
    const py = (clientY - rect.top - el.clientTop - view.y) / view.k;
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
    const el = wrap.current;
    const rect = el.getBoundingClientRect();
    const mx = e.clientX - rect.left - el.clientLeft;
    const my = e.clientY - rect.top - el.clientTop;
    const factor = e.deltaY < 0 ? 1.12 : 1 / 1.12;
    setView((v) => {
      const k = Math.min(8, Math.max(0.7, v.k * factor));
      const nx = mx - ((mx - v.x) * k) / v.k;
      const ny = my - ((my - v.y) * k) / v.k;
      return { k, x: nx, y: ny };
    });
  };

  const activeOrigin = tip?.origin?.key;

  return (
    <div
      ref={wrap}
      className={`relative h-full min-h-0 w-full overflow-hidden rounded-2xl border border-line bg-[#0c0a08] ${
        placing ? "cursor-crosshair" : "cursor-grab"
      }`}
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={onPointerUp}
      onWheel={onWheel}
    >
      <svg
        ref={svgRef}
        width={w}
        height={h}
        viewBox={`0 0 ${w} ${h}`}
        className="block h-full w-full"
      >
        <g ref={layerRef} transform={`translate(${view.x},${view.y}) scale(${view.k})`}>
          <path
            d={grid}
            fill="none"
            stroke="#2a231c"
            strokeWidth={0.6 * inv}
            pointerEvents="none"
          />
          {countryPaths.map((c) => {
            const on = c.origin && activeOrigin === c.origin.key;
            return (
              <path
                key={c.id}
                d={c.d}
                fill={c.origin ? (on ? "#4a3828" : "#2a231c") : "#1c1814"}
                stroke={c.origin ? "#6b5438" : "#3a3228"}
                strokeWidth={0.7 * inv}
                className={c.origin && !placing ? "cursor-pointer" : undefined}
                style={{ pointerEvents: c.origin ? "auto" : "none" }}
                onPointerEnter={(e) => hoverOrigin(c.origin, e)}
                onPointerMove={(e) => hoverOrigin(c.origin, e)}
                onPointerLeave={() => c.origin && leaveOrigin(c.origin.key)}
              />
            );
          })}
          {regionDots.map((o) => {
            const on = activeOrigin === o.key;
            return (
              <g
                key={o.key}
                transform={`translate(${o.x},${o.y}) scale(${inv})`}
                className={placing ? undefined : "cursor-pointer"}
                onPointerEnter={(e) => hoverOrigin(o, e)}
                onPointerMove={(e) => hoverOrigin(o, e)}
                onPointerLeave={() => leaveOrigin(o.key)}
              >
                <circle r={12} fill="transparent" />
                <circle
                  r={on ? 5 : 4}
                  fill="none"
                  stroke="#c88d44"
                  strokeWidth={1.3}
                  opacity={0.9}
                />
                <circle r={1.5} fill="#c88d44" />
              </g>
            );
          })}
          {spreadDots.map((p) =>
            Math.hypot(p.sx - p.x, p.sy - p.y) > 0.8 ? (
              <line
                key={`leg-${p.bean_id}-${p.place_id}`}
                x1={p.x}
                y1={p.y}
                x2={p.sx}
                y2={p.sy}
                stroke="#c88d44"
                strokeOpacity={0.35}
                strokeWidth={1.1 * inv}
                pointerEvents="none"
              />
            ) : null
          )}
          {spreadDots.map((p) => {
            const on = p.bean_id === selectedId || tip?.pin?.place_id === p.place_id;
            const r = on ? 6.5 : 4.5;
            return (
              <g
                key={`${p.bean_id}-${p.place_id}`}
                transform={`translate(${p.sx},${p.sy}) scale(${inv})`}
                className="cursor-pointer"
                onPointerEnter={(e) => {
                  if (drag.current?.moved) return;
                  setTip({ pin: p, ...localXY(e) });
                }}
                onPointerMove={(e) => {
                  if (drag.current?.moved) return;
                  setTip({ pin: p, ...localXY(e) });
                }}
                onPointerLeave={() => setTip((t) => (t?.pin?.place_id === p.place_id ? null : t))}
                onPointerUp={(e) => {
                  e.stopPropagation();
                  if (drag.current?.moved) return;
                  if (!placing && onOpen) onOpen(p.bean_id);
                }}
              >
                <circle r={12} fill="transparent" />
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
      <PinTip pin={tip?.pin} origin={tip?.origin} x={tip?.x} y={tip?.y} box={size} />
    </div>
  );
}
