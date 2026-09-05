// 真 3D 地球。贴图和国界都在本地，不拉 CDN。
import { useEffect, useMemo, useRef, useState } from "react";
import Globe from "react-globe.gl";

import { countries } from "../geo/world.js";

export default function BeanGlobe({ pins = [], selectedId, placing, onOpen, onPlace }) {
  const wrap = useRef(null);
  const globe = useRef(null);
  const [size, setSize] = useState({ w: 640, h: 420 });

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

  const points = useMemo(
    () =>
      pins.map((p) => ({
        ...p,
        size: p.bean_id === selectedId ? 0.55 : 0.32,
        color: p.in_stock ? "#c88d44" : "#9c8b74",
      })),
    [pins, selectedId]
  );

  useEffect(() => {
    const hit = pins.find((p) => p.bean_id === selectedId);
    if (hit && globe.current) {
      globe.current.pointOfView({ lat: hit.lat, lng: hit.lng, altitude: 1.7 }, 600);
    }
  }, [selectedId, pins]);

  return (
    <div
      ref={wrap}
      className={`relative h-full min-h-[280px] w-full overflow-hidden rounded-2xl border border-line bg-[#0c0a08] ${
        placing ? "cursor-crosshair" : ""
      }`}
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
        polygonCapColor={() => "rgba(28,24,20,0.25)"}
        polygonSideColor={() => "rgba(58,50,40,0.35)"}
        polygonStrokeColor={() => "#6b5438"}
        polygonAltitude={0.004}
        polygonsTransitionDuration={0}
        pointsData={points}
        pointLat="lat"
        pointLng="lng"
        pointAltitude={0.012}
        pointRadius="size"
        pointColor="color"
        onPointClick={(d) => {
          if (!placing && onOpen) onOpen(d.bean_id);
        }}
        onGlobeClick={(pos) => {
          if (placing && onPlace && pos) onPlace(pos.lat, pos.lng);
        }}
      />
    </div>
  );
}
