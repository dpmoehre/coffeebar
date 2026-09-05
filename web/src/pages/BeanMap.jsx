// 豆子产地地图：墨卡托 / 等积 / 地球。钉来自词典或人手点，不调外网地理编码。
import { lazy, Suspense, useEffect, useMemo, useState } from "react";

import { api } from "../api.js";
import WorldMap2d from "../components/WorldMap2d.jsx";
import { Btn, Chip, Empty } from "../ui.jsx";

const BeanGlobe = lazy(() => import("../components/BeanGlobe.jsx"));

const VIEWS = [
  ["mercator", "墨卡托"],
  ["equal", "等积"],
  ["globe", "地球"],
];

function hasWebGL() {
  try {
    const c = document.createElement("canvas");
    return !!(c.getContext("webgl2") || c.getContext("webgl"));
  } catch {
    return false;
  }
}

function collectBeans(data) {
  const byId = new Map();
  for (const u of data.unplaced || []) {
    byId.set(u.id, { ...u, places: [] });
  }
  for (const p of data.pins || []) {
    if (!byId.has(p.bean_id)) {
      byId.set(p.bean_id, {
        id: p.bean_id,
        name: p.name,
        origin: p.origin,
        in_stock: p.in_stock,
        pending: p.pending,
        cover: p.cover,
        places: [],
      });
    }
    byId.get(p.bean_id).places.push(p);
  }
  return [...byId.values()];
}

export default function BeanMap({ focusId, onOpen, toast, oops }) {
  const [data, setData] = useState(null);
  const [view, setView] = useState("mercator");
  const [scope, setScope] = useState("all");
  const [selected, setSelected] = useState(focusId || null);
  const [placing, setPlacing] = useState(false);
  const [webgl, setWebgl] = useState(true);

  const load = () => api.map().then(setData).catch((e) => oops(e.message));

  useEffect(() => {
    load();
    setWebgl(hasWebGL());
  }, []);

  useEffect(() => {
    if (focusId) {
      setSelected(focusId);
      setPlacing(true);
    }
  }, [focusId]);

  useEffect(() => {
    if (view === "globe" && !webgl) {
      setView("mercator");
      oops("这台设备画不了 3D 地球，先用平面图");
    }
  }, [view, webgl, oops]);

  const beans = useMemo(() => collectBeans(data || {}), [data]);
  const visible = useMemo(() => {
    return beans.filter((b) => {
      if (scope === "stock") return b.in_stock || b.pending;
      if (scope === "history") return !b.in_stock && !b.pending;
      return true;
    });
  }, [beans, scope]);

  const pins = useMemo(() => {
    const ids = new Set(visible.map((b) => b.id));
    return (data?.pins || []).filter((p) => ids.has(p.bean_id));
  }, [data, visible]);

  const current = beans.find((b) => b.id === selected);
  const canPlace = placing && selected;

  const placeAt = async (lat, lng) => {
    if (!selected) return;
    try {
      await api.lock(`bean:${selected}`);
      await api.setPlaces(selected, [{ lat, lng, label: current?.name || "手点" }]);
      toast(`已记下「${current?.name || ""}」的位置`);
      setPlacing(false);
      await load();
    } catch (e) {
      if (e.isLocked && e.body?.can_take_over) {
        try {
          await api.lock(`bean:${selected}`, true);
          await api.setPlaces(selected, [{ lat, lng, label: current?.name || "手点" }]);
          toast(`已记下「${current?.name || ""}」的位置`);
          setPlacing(false);
          await load();
        } catch (err) {
          oops(err.message);
        }
      } else {
        oops(e.message);
      }
    }
  };

  const guess = async () => {
    if (!selected) return;
    try {
      await api.lock(`bean:${selected}`);
      await api.guessPlaces(selected);
      toast("已按产地词典重猜");
      setPlacing(false);
      await load();
    } catch (e) {
      oops(e.message);
    }
  };

  const pick = (id) => {
    setSelected(id);
    const b = beans.find((x) => x.id === id);
    setPlacing(!!b && b.places.length === 0);
  };

  return (
    <>
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="serif m-0 text-3xl font-semibold">地图</h1>
          <p className="mt-2 mb-0 text-muted">
            {data
              ? `${beans.length} 支豆 · ${pins.length} 个落点 · ${data.unplaced.length} 支还没定点`
              : "读取中…"}
          </p>
        </div>
      </header>

      <div className="mt-5 flex flex-wrap items-center gap-2">
        {VIEWS.map(([k, label]) => (
          <Chip
            key={k}
            on={view === k}
            onClick={() => setView(k)}
            disabled={k === "globe" && !webgl}
          >
            {label}
          </Chip>
        ))}
        <span className="mx-1 text-line">|</span>
        {[
          ["all", "全部"],
          ["stock", "在库"],
          ["history", "历史"],
        ].map(([k, label]) => (
          <Chip key={k} on={scope === k} onClick={() => setScope(k)}>
            {label}
          </Chip>
        ))}
      </div>

      {canPlace && (
        <p className="mt-3 mb-0 text-[13px] text-amber">
          正在给「{current?.name}」定点：在图上点一下就记下。点错了可以再点，或用词典重猜。
        </p>
      )}

      <div className="mt-4 grid gap-4 lg:grid-cols-[minmax(0,1fr)_280px]">
        <div className="h-[min(62vh,640px)] min-h-[300px]">
          {view === "globe" && webgl ? (
            <Suspense fallback={<p className="text-muted">地球载入中…</p>}>
              <BeanGlobe
                pins={pins}
                selectedId={selected}
                placing={canPlace}
                onOpen={onOpen}
                onPlace={placeAt}
              />
            </Suspense>
          ) : (
            <WorldMap2d
              kind={view === "equal" ? "equal" : "mercator"}
              pins={pins}
              selectedId={selected}
              placing={canPlace}
              onOpen={onOpen}
              onPlace={placeAt}
            />
          )}
        </div>

        <div className="max-h-[min(62vh,640px)] overflow-auto rounded-2xl border border-line bg-panel p-3">
          {current && (
            <div className="mb-3 border-b border-line pb-3">
              <div className="serif text-base">{current.name}</div>
              <p className="mt-1 mb-2 text-[13px] text-muted">
                {current.origin || "还没填产地"}
                {current.places.length
                  ? ` · ${current.places.map((p) => p.label).join("、")}`
                  : " · 还没定点"}
              </p>
              <div className="flex flex-wrap gap-2">
                <Btn variant="ghost" onClick={() => onOpen(current.id)}>
                  打开豆卡
                </Btn>
                <Btn variant="ghost" onClick={() => setPlacing(true)}>
                  在图上纠正
                </Btn>
                <Btn variant="ghost" onClick={guess}>
                  用词典重猜
                </Btn>
              </div>
            </div>
          )}
          {!visible.length ? (
            <Empty>这个范围里没有豆子。</Empty>
          ) : (
            <ul className="m-0 list-none space-y-1 p-0">
              {visible.map((b) => (
                <li key={b.id}>
                  <button
                    type="button"
                    onClick={() => pick(b.id)}
                    className={`w-full rounded-xl px-3 py-2 text-left text-sm ${
                      selected === b.id ? "bg-chip text-cream" : "text-muted hover:bg-chip/60"
                    }`}
                  >
                    <span className="text-cream">{b.name}</span>
                    <span className="mt-0.5 block text-[12px]">
                      {b.places.length
                        ? b.places.map((p) => p.label).join(" · ")
                        : "还没定点"}
                      {b.in_stock ? "" : b.pending ? " · 待入袋" : " · 历史"}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </>
  );
}
