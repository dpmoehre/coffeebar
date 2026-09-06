// 基酒库：一行看见酒名、买入价、风味、酒精度。可按大类筛，按含量 / 酒精度排。
import { useEffect, useMemo, useState } from "react";

import { api } from "../api.js";
import { Plus } from "../icons.jsx";
import { Btn, Chip, Empty, Field, Input, Modal, Select, money } from "../ui.jsx";

const KINDS = ["威士忌", "金酒", "朗姆", "伏特加", "龙舌兰", "白兰地", "利口酒", "其他"];

const SORTS = [
  { key: "recent", label: "最近动过" },
  { key: "size_desc", label: "含量大" },
  { key: "size", label: "含量小" },
  { key: "abv_desc", label: "酒精度高" },
  { key: "abv", label: "酒精度低" },
  { key: "left_desc", label: "剩得多" },
  { key: "left", label: "剩得少" },
  { key: "cost", label: "克价低" },
  { key: "cost_desc", label: "克价高" },
];

// 没填的垫底，别把空值当成最大或最小
function byNum(a, b, key, desc) {
  if (a[key] == null && b[key] == null) return 0;
  if (a[key] == null) return 1;
  if (b[key] == null) return -1;
  return desc ? b[key] - a[key] : a[key] - b[key];
}

function lineOf(s) {
  const cat = s.category && s.category !== s.kind ? s.category : null;
  return [
    s.kind,
    cat,
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
    .join(" · ");
}

function SpiritRow({ s, onOpen }) {
  return (
    <article
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
        <div className="mt-1 truncate text-[13px] text-muted">{lineOf(s)}</div>
      </div>
      <div className="shrink-0 text-right">
        <div className="text-amber">{s.last_price != null ? money(s.last_price) : "—"}</div>
        {s.unit_cost != null && (
          <div className="mt-0.5 text-xs text-muted">{s.unit_cost.toFixed(2)} 元/ml</div>
        )}
      </div>
    </article>
  );
}

export default function Spirits({ onOpen, toast, oops }) {
  const [data, setData] = useState(null);
  const [scope, setScope] = useState("stock");
  const [kind, setKind] = useState("");
  const [sort, setSort] = useState("recent");
  const [q, setQ] = useState("");
  const [picked, setPicked] = useState([]);
  const [adding, setAdding] = useState(false);

  const load = () => api.spirits(scope).then(setData).catch((e) => oops(e.message));
  useEffect(() => {
    setData(null);
    load();
  }, [scope]);

  const kinds = data?.kinds || KINDS;
  const allTags = useMemo(() => {
    const set = new Set();
    (data?.spirits || []).forEach((s) => (s.tags || []).forEach((t) => set.add(t)));
    return [...set].sort();
  }, [data]);
  const items = useMemo(() => {
    let list = [...(data?.spirits || [])];
    if (kind) list = list.filter((s) => (s.kind || "其他") === kind);
    if (picked.length) list = list.filter((s) => picked.every((t) => (s.tags || []).includes(t)));
    const needle = q.trim().toLowerCase();
    if (needle) {
      list = list.filter((s) =>
        [s.name, s.kind, s.category, s.flavor, ...(s.tags || [])]
          .filter(Boolean)
          .some((x) => String(x).toLowerCase().includes(needle)),
      );
    }
    const by = {
      recent: (a, b) => (b.updated_at || "").localeCompare(a.updated_at || ""),
      size: (a, b) => byNum(a, b, "last_ml", false),
      size_desc: (a, b) => byNum(a, b, "last_ml", true),
      abv: (a, b) => byNum(a, b, "abv", false),
      abv_desc: (a, b) => byNum(a, b, "abv", true),
      left: (a, b) => byNum(a, b, "balance_ml", false),
      left_desc: (a, b) => byNum(a, b, "balance_ml", true),
      cost: (a, b) => byNum(a, b, "unit_cost", false),
      cost_desc: (a, b) => byNum(a, b, "unit_cost", true),
    };
    return list.sort(by[sort] || by.recent);
  }, [data, kind, sort, q, picked]);

  // 没选大类、又是默认排序时按威士忌 / 金酒分组，一眼能分开
  const groups = useMemo(() => {
    if (kind || sort !== "recent") return null;
    const map = new Map();
    for (const s of items) {
      const k = s.kind || "其他";
      if (!map.has(k)) map.set(k, []);
      map.get(k).push(s);
    }
    const order = [...kinds, ...[...map.keys()].filter((k) => !kinds.includes(k))];
    return order.filter((k) => map.has(k)).map((k) => [k, map.get(k)]);
  }, [items, kind, sort, kinds]);

  return (
    <>
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="serif m-0 text-3xl font-semibold">酒水</h1>
          <p className="mt-2 mb-0 text-muted">
            {data
              ? `在库 ${(data.spirits || []).filter((s) => s.in_stock).length} 支基酒。同样的酒再买一瓶，进酒卡点「再入一瓶」。`
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
        <span className="mx-1 h-5 w-px bg-line" />
        <Input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="搜酒名、风味…"
          className="w-44 py-1.5 text-sm"
        />
        <Select value={sort} onChange={(e) => setSort(e.target.value)} className="py-1.5 text-sm">
          {SORTS.map((s) => (
            <option key={s.key} value={s.key}>
              {s.label}
            </option>
          ))}
        </Select>
        {(kind || picked.length > 0) && (
          <button
            className="text-sm text-amber underline"
            onClick={() => {
              setKind("");
              setPicked([]);
            }}
          >
            清除筛选
          </button>
        )}
      </div>

      <div className="mt-3 flex flex-wrap gap-2">
        {kinds.map((k) => (
          <Chip key={k} on={kind === k} onClick={() => setKind((cur) => (cur === k ? "" : k))}>
            {k}
          </Chip>
        ))}
      </div>
      {allTags.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-2">
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

      <div className="mt-6 space-y-3">
        {groups
          ? groups.map(([k, rows]) => (
              <section key={k} className="space-y-3">
                <h2 className="serif m-0 text-sm text-muted">{k}</h2>
                {rows.map((s) => (
                  <SpiritRow key={s.id} s={s} onOpen={onOpen} />
                ))}
              </section>
            ))
          : items.map((s) => <SpiritRow key={s.id} s={s} onOpen={onOpen} />)}
      </div>

      {data && items.length === 0 && (
        <Empty>
          {scope === "history"
            ? "还没有喝完的基酒。"
            : q.trim()
              ? "没有对得上的酒。"
              : kind
                ? `还没有「${kind}」。`
                : "酒库是空的。右上角新建一支，填酒名、买入价和酒精度。"}
        </Empty>
      )}

      <NewSpirit
        open={adding}
        onClose={() => setAdding(false)}
        kinds={kinds}
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

function NewSpirit({ open, onClose, onDone, oops, kinds }) {
  const [f, setF] = useState({});
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });

  useEffect(() => {
    if (open) setF({ kind: "威士忌", category: "", nominal_ml: 700, abv: 40 });
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
        <Field label="大类">
          <Select value={f.kind || "威士忌"} onChange={set("kind")} className="w-full">
            {kinds.map((k) => (
              <option key={k} value={k}>
                {k}
              </option>
            ))}
          </Select>
        </Field>
        <Field label="细类" hint="单一麦芽 / 伦敦干金">
          <Input value={f.category || ""} onChange={set("category")} placeholder="单一麦芽" />
        </Field>
      </div>
      <div className="grid grid-cols-2 gap-3">
        <Field label="产地">
          <Input value={f.origin || ""} onChange={set("origin")} placeholder="苏格兰高地" />
        </Field>
        <Field label="风味类型">
          <Input value={f.flavor || ""} onChange={set("flavor")} placeholder="柑橘甜、圆润" />
        </Field>
      </div>
      <div className="grid grid-cols-2 gap-3">
        <Field label="酒精度 % vol">
          <Input type="number" step="0.1" value={f.abv ?? ""} onChange={set("abv")} />
        </Field>
        <Field label="标称容量 ml">
          <Input type="number" value={f.nominal_ml ?? ""} onChange={set("nominal_ml")} />
        </Field>
      </div>
      <div className="grid grid-cols-2 gap-3">
        <Field label="这瓶多少钱">
          <Input type="number" value={f.price || ""} onChange={set("price")} placeholder="399" />
        </Field>
        <Field label="标签" hint="空格或逗号分开">
          <Input value={f.tags || ""} onChange={set("tags")} placeholder="波本桶 高地" />
        </Field>
      </div>
      <Field label="备注">
        <Input value={f.note || ""} onChange={set("note")} placeholder="Traveller's Exclusive" />
      </Field>
    </Modal>
  );
}
