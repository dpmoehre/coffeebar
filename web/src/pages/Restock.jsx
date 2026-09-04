// 补货：见底或撑不了几天的豆会出现在这里。
import { useEffect, useState } from "react";

import { api } from "../api.js";
import { Empty, Panel, g, money } from "../ui.jsx";

export default function Restock({ onOpen }) {
  const [items, setItems] = useState(null);

  useEffect(() => {
    api.restock().then((d) => setItems(d.items));
  }, []);

  return (
    <>
      <header>
        <h1 className="serif m-0 text-3xl font-semibold">补货</h1>
        <p className="mt-2 mb-0 text-muted">
          账面不够一杯、低于安全库存，或照这个喝法撑不了几天的，会出现在这里。
        </p>
      </header>

      {!items ? (
        <p className="mt-6 text-muted">读取中…</p>
      ) : items.length === 0 ? (
        <Empty>都还够喝。</Empty>
      ) : (
        <Panel className="mt-6">
          {items.map((it) => (
            <div
              key={it.id}
              onClick={() => onOpen(it.id)}
              className="flex cursor-pointer items-center gap-4 border-b border-line py-3.5
                last:border-0 hover:opacity-80"
            >
              <div
                className="h-11 w-11 shrink-0 rounded-full"
                style={{ background: "radial-gradient(circle at 35% 35%, #7a5333, #2a1c14)" }}
              />
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
            </div>
          ))}
        </Panel>
      )}
    </>
  );
}
