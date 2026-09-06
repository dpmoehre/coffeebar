// 补货：见底的豆和酒会出现在这里。豆可以挂货架/包装对照图。
import { useEffect, useRef, useState } from "react";

import { api } from "../api.js";
import { Empty, Panel, g, ml, money } from "../ui.jsx";

export default function Restock({ onOpen, onOpenSpirit, onOpenGear, toast, oops }) {
  const [items, setItems] = useState(null);
  const [spirits, setSpirits] = useState([]);
  const [filters, setFilters] = useState([]);
  const fileRef = useRef({});

  const load = () =>
    api.restock().then((d) => {
      setItems(d.items || []);
      setSpirits(d.spirits || []);
      setFilters(d.filters || []);
    });

  useEffect(() => {
    load();
  }, []);

  const addPhoto = async (beanId, files) => {
    if (!files?.length) return;
    try {
      for (const f of files) await api.addRestockPhoto(beanId, f);
      toast?.(files.length > 1 ? `加了 ${files.length} 张` : "对照图挂上了");
      await load();
    } catch (e) {
      oops?.(e.message);
    } finally {
      if (fileRef.current[beanId]) fileRef.current[beanId].value = "";
    }
  };

  if (!items) {
    return <p className="mt-6 text-muted">读取中…</p>;
  }

  const empty = items.length === 0 && spirits.length === 0 && filters.length === 0;

  return (
    <>
      <header>
        <h1 className="serif m-0 text-2xl font-semibold md:text-3xl">补货</h1>
        <p className="mt-2 mb-0 text-muted">
          账面不够一杯、瓶子空了、滤纸用完或只剩不多，会出现在这里。豆子能挂货架对照图。
        </p>
      </header>

      {empty ? (
        <Empty>豆、酒和滤纸都还够。</Empty>
      ) : (
        <>
          {items.length > 0 && (
            <section className="mt-6">
              <h2 className="serif m-0 text-lg">豆子</h2>
              <Panel className="mt-3">
                {items.map((it) => (
                  <div
                    key={`bean-${it.id}`}
                    className="flex items-center gap-4 border-b border-line py-3.5 last:border-0"
                  >
                    <button
                      type="button"
                      onClick={() => onOpen(it.id)}
                      className="flex min-w-0 flex-1 cursor-pointer items-center gap-4 text-left hover:opacity-80"
                    >
                      {it.photos?.[0] ? (
                        <img
                          src={it.photos[0].thumb || it.photos[0].url}
                          alt=""
                          className="h-11 w-11 shrink-0 rounded-full object-cover"
                        />
                      ) : (
                        <div
                          className="h-11 w-11 shrink-0 rounded-full"
                          style={{
                            background: "radial-gradient(circle at 35% 35%, #7a5333, #2a1c14)",
                          }}
                        />
                      )}
                      <div className="min-w-0 flex-1">
                        <div className="truncate">
                          {it.name}
                          <span className="ml-2 text-[13px] text-muted">还剩 {g(it.balance_g)}</span>
                        </div>
                        <div className="mt-0.5 text-xs text-muted">
                          {it.reasons.join(" · ")}
                          {it.last_price ? ` · 上次 ${money(it.last_price)}` : ""}
                        </div>
                      </div>
                      <div className="whitespace-nowrap text-sm text-amber">
                        {it.cups_left < 1 ? "不够一杯" : `约 ${it.cups_left} 杯`}
                        {it.days_left != null ? ` · ${it.days_left} 天` : ""}
                      </div>
                    </button>
                    <label
                      className="shrink-0 cursor-pointer rounded-full border border-line px-3 py-1 text-xs
                        text-muted hover:border-amber hover:text-amber"
                    >
                      对照图
                      <input
                        ref={(el) => (fileRef.current[it.id] = el)}
                        type="file"
                        accept="image/*,.heic,.heif"
                        className="hidden"
                        onChange={(e) => addPhoto(it.id, [...e.target.files])}
                      />
                    </label>
                  </div>
                ))}
              </Panel>
            </section>
          )}

          {filters.length > 0 && (
            <section className="mt-6">
              <h2 className="serif m-0 text-lg">滤纸</h2>
              <Panel className="mt-3">
                {filters.map((it) => (
                  <button
                    type="button"
                    key={`filter-${it.id}`}
                    onClick={() => onOpenGear?.(it.id)}
                    className="flex w-full cursor-pointer items-center gap-4 border-b border-line py-3.5
                      text-left last:border-0 hover:opacity-80"
                  >
                    {it.cover ? (
                      <img
                        src={it.cover.thumb || it.cover.url}
                        alt=""
                        className="h-11 w-11 shrink-0 rounded-full object-cover"
                      />
                    ) : (
                      <div
                        className="h-11 w-11 shrink-0 rounded-full"
                        style={{
                          background: "radial-gradient(circle at 35% 35%, #7a5333, #2a1c14)",
                        }}
                      />
                    )}
                    <div className="min-w-0 flex-1">
                      <div className="truncate">
                        {it.name}
                        <span className="ml-2 text-[13px] text-muted">还剩 {it.sheets_left} 张</span>
                      </div>
                      <div className="mt-0.5 text-xs text-muted">
                        {it.reasons.join(" · ")}
                        {it.last_price ? ` · 上次 ${money(it.last_price)}` : ""}
                      </div>
                    </div>
                  </button>
                ))}
              </Panel>
            </section>
          )}

          {spirits.length > 0 && (
            <section className="mt-6">
              <h2 className="serif m-0 text-lg">酒水</h2>
              <Panel className="mt-3">
                {spirits.map((it) => (
                  <button
                    type="button"
                    key={`spirit-${it.id}`}
                    onClick={() => onOpenSpirit?.(it.id)}
                    className="flex w-full cursor-pointer items-center gap-4 border-b border-line py-3.5
                      text-left last:border-0 hover:opacity-80"
                  >
                    <div
                      className="h-11 w-11 shrink-0 rounded-full"
                      style={{
                        background: "radial-gradient(circle at 35% 35%, #c4a574, #2a1c14)",
                      }}
                    />
                    <div className="min-w-0 flex-1">
                      <div className="truncate">
                        {it.name}
                        <span className="ml-2 text-[13px] text-muted">还剩 {ml(it.balance_ml)}</span>
                      </div>
                      <div className="mt-0.5 text-xs text-muted">
                        {it.reasons.join(" · ")}
                        {it.last_price ? ` · 上次 ${money(it.last_price)}` : ""}
                      </div>
                    </div>
                    <div className="whitespace-nowrap text-sm text-amber">
                      {it.pours_left < 1 ? "不够一杯" : `约 ${it.pours_left} 杯`}
                      {it.days_left != null ? ` · ${it.days_left} 天` : ""}
                    </div>
                  </button>
                ))}
              </Panel>
            </section>
          )}
        </>
      )}
    </>
  );
}
