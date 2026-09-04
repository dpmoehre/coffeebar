// 豆库独立页：打开就一眼看完所有在库豆子还剩多少。
import { useEffect, useMemo, useState } from "react";

import { api } from "../api.js";
import { Plus } from "../icons.jsx";
import { Bar, Btn, Chip, Empty, Field, Input, Modal, Select, g } from "../ui.jsx";

const SORTS = [
  { key: "recent", label: "最近动过" },
  { key: "left", label: "剩得少" },
  { key: "left_desc", label: "剩得多" },
  { key: "roast", label: "烘焙" },
  { key: "origin", label: "产地" },
  { key: "score", label: "评分" },
  { key: "opened", label: "开封日" },
];

export default function Beans({ onOpen, toast, oops }) {
  const [data, setData] = useState(null);
  const [scope, setScope] = useState("stock");
  const [sort, setSort] = useState("recent");
  const [picked, setPicked] = useState([]);
  const [adding, setAdding] = useState(false);

  const load = () => api.beans(scope).then(setData).catch((e) => oops(e.message));
  useEffect(() => {
    setData(null);
    load();
  }, [scope]);

  const allTags = useMemo(() => {
    const set = new Set();
    (data?.beans || []).forEach((b) => b.tags.forEach((t) => set.add(t)));
    return [...set].sort();
  }, [data]);

  const beans = useMemo(() => {
    let list = [...(data?.beans || [])];
    // 多选标签 = 同时带这些标签（越点越少）
    if (picked.length) list = list.filter((b) => picked.every((t) => b.tags.includes(t)));
    const by = {
      recent: (a, b) => b.updated_at.localeCompare(a.updated_at),
      left: (a, b) => a.balance_g - b.balance_g,
      left_desc: (a, b) => b.balance_g - a.balance_g,
      roast: (a, b) => (a.roast || "").localeCompare(b.roast || ""),
      origin: (a, b) => (a.origin || "").localeCompare(b.origin || ""),
      score: (a, b) => (b.scores?.overall || 0) - (a.scores?.overall || 0),
      opened: (a, b) => (b.updated_at || "").localeCompare(a.updated_at || ""),
    };
    return list.sort(by[sort]);
  }, [data, picked, sort]);

  return (
    <>
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="serif m-0 text-3xl font-semibold">豆子</h1>
          <p className="mt-2 mb-0 text-muted">
            {data
              ? `在库 ${data.beans.filter((b) => b.in_stock).length} 支 · 平均一杯 ${
                  data.avg_dose.avg_g
                } g${
                  data.avg_dose.source === "fallback" ? "（还没数据）" : ""
                }`
              : "读取中…"}
          </p>
        </div>
        <Btn onClick={() => setAdding(true)}>
          <Plus className="h-4 w-4" />
          新建豆子
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
        <span className="mx-1 h-5 w-px bg-line" />
        <Select value={sort} onChange={(e) => setSort(e.target.value)} className="py-1.5 text-sm">
          {SORTS.map((s) => (
            <option key={s.key} value={s.key}>
              {s.label}
            </option>
          ))}
        </Select>
        {picked.length > 0 && (
          <button className="text-sm text-amber underline" onClick={() => setPicked([])}>
            清除筛选
          </button>
        )}
      </div>

      {allTags.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-2">
          {allTags.map((t) => (
            <Chip
              key={t}
              on={picked.includes(t)}
              onClick={() =>
                setPicked((p) => (p.includes(t) ? p.filter((x) => x !== t) : [...p, t]))
              }
            >
              {t}
            </Chip>
          ))}
        </div>
      )}

      <div className="mt-6 grid gap-4 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4">
        {beans.map((b) => (
          <Card key={b.id} bean={b} onClick={() => onOpen(b.id)} />
        ))}
      </div>

      {data && beans.length === 0 && (
        <Empty>
          {scope === "history"
            ? "还没有喝完的豆子。用完的豆会留在这里，风味和冲煮记录都不会丢。"
            : picked.length
              ? "没有同时带这些标签的豆子。"
              : "豆库是空的。右上角新建一支，填个名字和袋子上印的克重就行。"}
        </Empty>
      )}

      <NewBean
        open={adding}
        onClose={() => setAdding(false)}
        onDone={(bean) => {
          setAdding(false);
          toast(`已加入豆库：${bean.name}`);
          load();
        }}
        oops={oops}
      />
    </>
  );
}

function Card({ bean, onClick }) {
  const pct = bean.usable_g ? (bean.balance_g / bean.usable_g) * 100 : 0;
  return (
    <article
      onClick={onClick}
      className="rise cursor-pointer overflow-hidden rounded-2xl border border-line
        bg-panel transition hover:border-amber"
    >
      <div
        className="h-28"
        style={{
          background:
            "radial-gradient(circle at 30% 40%, #5a3d28, transparent 42%), linear-gradient(135deg, #3a2618, #1a120e)",
        }}
      />
      <div className="p-5">
        <div className="flex items-baseline justify-between gap-2">
          <div className="serif truncate text-lg">{bean.name}</div>
          {!bean.in_stock && <span className="shrink-0 text-xs text-muted">历史</span>}
        </div>
        <div className="mt-1 truncate text-[13px] text-muted">
          {[bean.origin, bean.roast, bean.water_temp && `${bean.water_temp} °C`]
            .filter(Boolean)
            .join(" · ") || "还没填产地"}
        </div>

        <div className="mt-3">
          <Bar pct={pct} warn={bean.near_empty} />
        </div>
        <div className="mt-2 flex justify-between text-[13px] text-muted">
          <span className={bean.near_empty ? "text-warn" : ""}>{g(bean.balance_g)}</span>
          <span>{bean.cups_left < 1 ? "不够一杯了" : `约 ${bean.cups_left} 杯`}</span>
        </div>

        {bean.tags.length > 0 && (
          <div className="mt-3 flex flex-wrap gap-1.5">
            {bean.tags.slice(0, 4).map((t) => (
              <b
                key={t}
                className="rounded-full border border-line px-2 py-0.5 text-xs font-normal text-muted"
              >
                {t}
              </b>
            ))}
          </div>
        )}
      </div>
    </article>
  );
}

function NewBean({ open, onClose, onDone, oops }) {
  const [f, setF] = useState({});
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });

  useEffect(() => {
    if (open) setF({ roast: "浅烘", nominal_g: 200 });
  }, [open]);

  const submit = async () => {
    try {
      const bean = await api.createBean({
        ...f,
        nominal_g: Number(f.nominal_g) || undefined,
        price: f.price ? Number(f.price) : undefined,
        water_temp: f.water_temp ? Number(f.water_temp) : undefined,
        tags: (f.tags || "").split(/[,，\s]+/).filter(Boolean),
      });
      onDone(bean);
    } catch (e) {
      oops(e.message);
    }
  };

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="新建豆子"
      sub="卡是品种。同样的豆再买一袋，进豆卡点「再入一袋」，不用在这儿重建。"
      footer={
        <>
          <Btn variant="ghost" onClick={onClose}>
            取消
          </Btn>
          <Btn onClick={submit} disabled={!f.name?.trim()}>
            加入豆库
          </Btn>
        </>
      }
    >
      <Field label="名字">
        <Input value={f.name || ""} onChange={set("name")} placeholder="肯尼亚 AA" autoFocus />
      </Field>
      <div className="grid grid-cols-2 gap-3">
        <Field label="产地">
          <Input value={f.origin || ""} onChange={set("origin")} placeholder="肯尼亚" />
        </Field>
        <Field label="处理法">
          <Input value={f.process || ""} onChange={set("process")} placeholder="水洗" />
        </Field>
      </div>
      <div className="grid grid-cols-2 gap-3">
        <Field label="烘焙">
          <Select value={f.roast || "浅烘"} onChange={set("roast")} className="w-full">
            {["浅烘", "中烘", "深烘"].map((r) => (
              <option key={r}>{r}</option>
            ))}
          </Select>
        </Field>
        <Field label="建议水温 °C">
          <Input type="number" value={f.water_temp || ""} onChange={set("water_temp")} placeholder="92" />
        </Field>
      </div>
      <div className="grid grid-cols-2 gap-3">
        <Field label="袋上印的克重" hint="刚拆袋不用称，先按这个扣">
          <Input type="number" value={f.nominal_g ?? ""} onChange={set("nominal_g")} />
        </Field>
        <Field label="这袋多少钱">
          <Input type="number" value={f.price || ""} onChange={set("price")} placeholder="128" />
        </Field>
      </div>
      <Field label="标签" hint="空格或逗号分开，输入即创建">
        <Input value={f.tags || ""} onChange={set("tags")} placeholder="水洗 柑橘 耶加" />
      </Field>
    </Modal>
  );
}
