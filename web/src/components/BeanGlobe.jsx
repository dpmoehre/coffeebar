// 真 3D 地球。贴图和国界都在本地，不拉 CDN。
import { useEffect, useMemo, useRef, useState } from "react";
import Globe from "react-globe.gl";

import { spreadLatLng } from "../geo/spread.js";
import { countries } from "../geo/world.js";
import PinTip from "./PinTip.jsx";

function padIso(id) {
  return String(id ?? "").padStart(3, "0");
}

export default function BeanGlobe({
  pins = [],
  origins = [],
  selectedId,
  placing,
  onOpen,
  onPlace,
}) {
  const wrap = useRef(null);
  const globe = useRef(null);
  const hover = useRef(null);
  const mouse = useRef({ x: 24, y: 24 });
  const [size, setSize] = useState({ w: 640, h: 420 });
  const [tip, setTip] = useState(null);

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

  const coffeeByIso = useMemo(() => {
    const m = new Map();
    for (const o of origins) {
      if (o.iso) m.set(padIso(o.iso), o);
    }
    return m;
  }, [origins]);

  const points = useMemo(() => {
    const regs = origins
      .filter((o) => o.kind === "region")
      .map((o) => ({
        ...o,
        _kind: "origin",
        size: tip?.origin?.key === o.key ? 0.28 : 0.16,
        color: "#c88d44",
        alt: 0.006,
      }));
    const beans = spreadLatLng(pins).map((p) => ({
      ...p,
      _kind: "pin",
      size: p.bean_id === selectedId || tip?.pin?.place_id === p.place_id ? 0.42 : 0.24,
      color: p.in_stock ? "#c88d44" : "#9c8b74",
      alt: 0.012,
    }));
    return [...regs, ...beans];
  }, [origins, pins, selectedId, tip?.origin?.key, tip?.pin?.place_id]);

  useEffect(() => {
    const hit = pins.find((p) => p.bean_id === selectedId);
    if (hit && globe.current) {
      globe.current.pointOfView({ lat: hit.lat, lng: hit.lng, altitude: 1.7 }, 600);
    }
  }, [selectedId, pins]);

  const activeIso = tip?.origin?.iso ? padIso(tip.origin.iso) : "";

  return (
    <div
      ref={wrap}
      className={`relative h-full min-h-0 w-full overflow-hidden rounded-2xl border border-line bg-[#0c0a08] ${
        placing ? "cursor-crosshair" : ""
      }`}
      onMouseMove={(e) => {
        const box = wrap.current.getBoundingClientRect();
        mouse.current = { x: e.clientX - box.left, y: e.clientY - box.top };
        if (!hover.current) return;
        if (hover.current._kind === "origin") {
          setTip({ origin: hover.current, ...mouse.current });
        } else {
          setTip({ pin: hover.current, ...mouse.current });
        }
      }}
    >
      <Globe
        ref={globe}
        width={size.w}
        height={size.h}
        backgroundColor="#0c0a08"
        globeImageUrl="/globe-dark.jpg"
        bumpImageUrl={null}
        backgroundImageUrl={null}
        atmosphereColor="#c88d44"
        atmosphereAltitude={0.12}
        polygonsData={countries.features}
        polygonCapColor={(d) => {
          const iso = padIso(d.id);
          if (!coffeeByIso.has(iso)) return "rgba(28,24,20,0.25)";
          return iso === activeIso ? "rgba(74,56,40,0.72)" : "rgba(42,35,28,0.55)";
        }}
        polygonSideColor={() => "rgba(58,50,40,0.35)"}
        polygonStrokeColor={(d) => (coffeeByIso.has(padIso(d.id)) ? "#8a6a40" : "#6b5438")}
        polygonAltitude={(d) => {
          const iso = padIso(d.id);
          if (!coffeeByIso.has(iso)) return 0.004;
          return iso === activeIso ? 0.012 : 0.007;
        }}
        polygonsTransitionDuration={0}
        pointsData={points}
        pointLat={(d) => (d._kind === "pin" ? d.plat : d.lat)}
        pointLng={(d) => (d._kind === "pin" ? d.plng : d.lng)}
        pointAltitude="alt"
        pointRadius="size"
        pointColor="color"
        pointLabel={() => ""}
        onPointHover={(d) => {
          hover.current = d || null;
          if (!d) {
            setTip(null);
            return;
          }
          if (d._kind === "origin") setTip({ origin: d, ...mouse.current });
          else setTip({ pin: d, ...mouse.current });
        }}
        onPointClick={(d) => {
          if (!placing && d?._kind === "pin" && onOpen) onOpen(d.bean_id);
        }}
        onPolygonHover={(feat) => {
          if (hover.current) return;
          const origin = feat && coffeeByIso.get(padIso(feat.id));
          setTip(origin ? { origin, ...mouse.current } : null);
        }}
        onGlobeClick={(pos) => {
          if (placing && onPlace && pos) onPlace(pos.lat, pos.lng);
        }}
      />
      <PinTip pin={tip?.pin} origin={tip?.origin} x={tip?.x} y={tip?.y} box={size} />
    </div>
  );
}
