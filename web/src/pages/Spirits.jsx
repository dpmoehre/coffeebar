// 基酒库：一行看见酒名、买入价、风味、酒精度。
import { useEffect, useState } from "react";

import { api } from "../api.js";
import { Plus } from "../icons.jsx";
import { Btn, Chip, Empty, Field, Input, Modal, money } from "../ui.jsx";

export default function Spirits({ onOpen, toast, oops }) {
  const [data, setData] = useState(null);
  const [scope, setScope] = useState("stock");
  const [adding, setAdding] = useState(false);

  const load = () => api.spirits(scope).then(setData).catch((e) => oops(e.message));
  useEffect(() => {
    setData(null);
    load();
  }, [scope]);

  const items = data?.spirits || [];

  return (
    <>
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="serif m-0 text-3xl font-semibold">酒水</h1>
          <p className="mt-2 mb-0 text-muted">
            {data
              ? `在库 ${items.filter((s) => s.in_stock).length} 支基酒。同样的酒再买一瓶，进酒卡点「再入一瓶」。`
              : "读取中…"}
          </p>
        </div>
        <Btn onClick={() => setAdding(true)}>
          <Plus className="h-4 w-4" />
          新建基酒
        </Btn>
      </header>

      <div className="mt-5 flex flex-wrap items-center gap-2">
        {[
          ["stock", "在库"],
          ["history", "历史"],
          ["all", "全部"],
        ].map(([k, label]) => (
          <Chip key={k} on={scope === k} onClick={() => setScope(k)}>
            {label}
          </Chip>
        ))}
      </div>

      <div className="mt-6 space-y-3">
        {items.map((s) => (
          <article
            key={s.id}
            onClick={() => onOpen(s.id)}
            className="rise flex cursor-pointer items-center gap-4 rounded-2xl border border-line
              bg-panel p-4 transition hover:border-amber"
          >
            {s.cover ? (
              <img src={s.cover.thumb} alt="" className="h-16 w-16 shrink-0 rounded-xl object-cover" />
            ) : (
              <div className="h-16 w-16 shrink-0 rounded-xl bg-[#3a2618]" />
            )}
            <div className="min-w-0 flex-1">
              <div className="serif truncate text-lg">{s.name}</div>
              <div className="mt-1 truncate text-[13px] text-muted">
                {[
                  s.category,
                  s.flavor,
                  s.abv != null && `${s.abv}% vol`,
                  s.last_ml && `${Math.round(s.last_ml)} ml`,
                  s.pending
                    ? "待入瓶"
                    : s.in_stock
                      ? s.balance_ml > 0
                        ? `剩 ${Math.round(s.balance_ml)} ml`
                        : "见底了"
                      : "已喝完",
                ]
                  .filter(Boolean)
                  .join(" · ")}
              </div>
            </div>
            <div className="shrink-0 text-right">
              <div className="text-amber">{s.last_price != null ? money(s.last_price) : "—"}</div>
              {s.unit_cost != null && (
                <div className="mt-0.5 text-xs text-muted">{s.unit_cost.toFixed(2)} 元/ml</div>
              )}
            </div>
          </article>
        ))}
      </div>

      {data && items.length === 0 && (
        <Empty>
          {scope === "history"
            ? "还没有喝完的基酒。"
            : "酒库是空的。右上角新建一支，填酒名、买入价和酒精度。"}
        </Empty>
      )}

      <NewSpirit
        open={adding}
        onClose={() => setAdding(false)}
        onDone={(s) => {
          setAdding(false);
          toast(`已加入酒库：${s.name}`);
          load();
        }}
        oops={oops}
      />
    </>
  );
}

function NewSpirit({ open, onClose, onDone, oops }) {
  const [f, setF] = useState({});
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });

  useEffect(() => {
    if (open) setF({ category: "威士忌", nominal_ml: 700, abv: 40 });
  }, [open]);

  const submit = async () => {
    try {
      const spirit = await api.createSpirit({
        ...f,
        nominal_ml: Number(f.nominal_ml) || undefined,
        price: f.price ? Number(f.price) : undefined,
        abv: f.abv ? Number(f.abv) : undefined,
        tags: (f.tags || "").split(/[,，\s]+/).filter(Boolean),
      });
      onDone(spirit);
    } catch (e) {
      oops(e.message);
    }
  };

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="新建基酒"
      sub="卡是酒名。同样的酒再买一瓶，进酒卡点「再入一瓶」，不用在这儿重建。"
      footer={
        <>
          <Btn variant="ghost" onClick={onClose}>
            取消
          </Btn>
          <Btn onClick={submit} disabled={!f.name?.trim()}>
            加入酒库
          </Btn>
        </>
      }
    >
      <Field label="酒名">
        <Input value={f.name || ""} onChange={set("name")} placeholder="格兰杰 谜 16年" autoFocus />
      </Field>
      <div className="grid grid-cols-2 gap-3">
        <Field label="品类">
          <Input value={f.category || ""} onChange={set("category")} placeholder="单一麦芽威士忌" />
        </Field>
        <Field label="产地">
          <Input value={f.origin || ""} onChange={set("origin")} placeholder="苏格兰高地" />
        </Field>
      </div>
      <div className="grid grid-cols-2 gap-3">
        <Field label="酒精度 % vol">
          <Input type="number" step="0.1" value={f.abv ?? ""} onChange={set("abv")} />
        </Field>
        <Field label="风味类型">
          <Input value={f.flavor || ""} onChange={set("flavor")} placeholder="柑橘甜、圆润" />
        </Field>
      </div>
      <div className="grid grid-cols-2 gap-3">
        <Field label="这瓶多少钱">
          <Input type="number" value={f.price || ""} onChange={set("price")} placeholder="399" />
        </Field>
        <Field label="标称容量 ml">
          <Input type="number" value={f.nominal_ml ?? ""} onChange={set("nominal_ml")} />
        </Field>
      </div>
      <Field label="标签" hint="空格或逗号分开">
        <Input value={f.tags || ""} onChange={set("tags")} placeholder="波本桶 高地 旅行零售" />
      </Field>
      <Field label="备注">
        <Input value={f.note || ""} onChange={set("note")} placeholder="Traveller's Exclusive" />
      </Field>
    </Modal>
  );
}
