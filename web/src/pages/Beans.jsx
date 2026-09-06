// 豆库独立页：打开就一眼看完所有在库豆子还剩多少。
import { useEffect, useMemo, useState } from "react";

import { api } from "../api.js";
import { recall, remember } from "../listCache.js";
import { freshnessLine } from "../freshness.js";
import { Plus } from "../icons.jsx";
import TodayBar from "../components/TodayBar.jsx";
import { Bar, Btn, Chip, Cover, Empty, Field, Input, Modal, Select, coverSrc, g, perG } from "../ui.jsx";

const SORTS = [
  { key: "recent", label: "最近动过" },
  { key: "fresh", label: "新鲜" },
  { key: "left", label: "剩得少" },
  { key: "left_desc", label: "剩得多" },
  { key: "cost", label: "克价低" },
  { key: "cost_desc", label: "克价高" },
  { key: "roast", label: "烘焙" },
  { key: "origin", label: "产地" },
  { key: "score", label: "评分" },
  { key: "opened", label: "开封日" },
];

const PHASE_CHIPS = [
  { key: "resting", label: "养豆中" },
  { key: "peak", label: "正当时" },
  { key: "past", label: "过了" },
  { key: "unknown", label: "没填烘焙日" },
];

function byFresh(a, b) {
  const da = a.freshness?.days_after_roast;
  const db = b.freshness?.days_after_roast;
  if (da == null && db == null) return 0;
  if (da == null) return 1;
  if (db == null) return -1;
  return da - db;
}

function phaseMatch(bean, filter) {
  const p = bean.freshness?.phase;
  if (filter === "past") return p === "fading" || p === "stale";
  return p === filter;
}

// 没填价钱的垫底，别因为 null 被当成最便宜或最贵
function byCost(a, b, desc) {
  if (a.unit_cost == null && b.unit_cost == null) return 0;
  if (a.unit_cost == null) return 1;
  if (b.unit_cost == null) return -1;
  return desc ? b.unit_cost - a.unit_cost : a.unit_cost - b.unit_cost;
}

export default function Beans({ onOpen, onOpenRestock, onOpenPerson, toast, oops }) {
  const [scope, setScope] = useState("stock");
  const [data, setData] = useState(() => recall(`beans:${scope}`) ?? null);
  const [sort, setSort] = useState("recent");
  const [picked, setPicked] = useState([]);
  const [phase, setPhase] = useState("");
  const [q, setQ] = useState("");
  const [adding, setAdding] = useState(false);

  const load = () =>
    api
      .beans(scope)
      .then((d) => {
        remember(`beans:${scope}`, d);
        setData(d);
      })
      .catch((e) => oops(e.message));
  useEffect(() => {
    const hit = recall(`beans:${scope}`);
    setData(hit === undefined ? null : hit);
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
    if (phase) list = list.filter((b) => phaseMatch(b, phase));
    const needle = q.trim().toLowerCase();
    if (needle) {
      list = list.filter((b) =>
        [b.name, b.origin, b.varietal, b.producer, ...(b.tags || [])]
          .filter(Boolean)
          .some((x) => String(x).toLowerCase().includes(needle)),
      );
    }
    const by = {
      recent: (a, b) => b.updated_at.localeCompare(a.updated_at),
      left: (a, b) => a.balance_g - b.balance_g,
      left_desc: (a, b) => b.balance_g - a.balance_g,
      roast: (a, b) => (a.roast || "").localeCompare(b.roast || ""),
      origin: (a, b) => (a.origin || "").localeCompare(b.origin || ""),
      score: (a, b) => (b.scores?.overall || 0) - (a.scores?.overall || 0),
      opened: (a, b) => (b.updated_at || "").localeCompare(a.updated_at || ""),
      cost: (a, b) => byCost(a, b, false),
      cost_desc: (a, b) => byCost(a, b, true),
      fresh: byFresh,
    };
    return list.sort(by[sort]);
  }, [data, picked, phase, sort, q]);

  return (
    <>
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="serif m-0 text-2xl font-semibold md:text-3xl">豆子</h1>
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

      <TodayBar
        onOpen={onOpen}
        onOpenRestock={onOpenRestock}
        onOpenPerson={onOpenPerson}
        oops={oops}
      />

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
          placeholder="搜名字、产地…"
          className="w-44 py-1.5 text-sm"
        />
        <Select value={sort} onChange={(e) => setSort(e.target.value)} className="py-1.5 text-sm">
          {SORTS.map((s) => (
            <option key={s.key} value={s.key}>
              {s.label}
            </option>
          ))}
        </Select>
        {(picked.length > 0 || phase) && (
          <button
            className="text-sm text-amber underline"
            onClick={() => {
              setPicked([]);
              setPhase("");
            }}
          >
            清除筛选
          </button>
        )}
      </div>

      <div className="mt-3 flex flex-wrap gap-2">
        {PHASE_CHIPS.map((c) => (
          <Chip key={c.key} on={phase === c.key} onClick={() => setPhase((p) => (p === c.key ? "" : c.key))}>
            {c.label}
          </Chip>
        ))}
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
        {!data
          ? [0, 1, 2, 3].map((i) => <CardSkeleton key={i} delay={i} />)
          : beans.map((b, i) => (
              <Card key={b.id} bean={b} delay={i} onClick={() => onOpen(b.id)} />
            ))}
      </div>

      {data && beans.length === 0 && (
        <Empty>
          {scope === "history"
            ? "还没有喝完的豆子。用完的豆会留在这里，风味和冲煮记录都不会丢。"
            : picked.length || q.trim()
              ? "没有对得上的豆子。"
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

function CardSkeleton({ delay = 0 }) {
  return (
    <div
      className="rise overflow-hidden rounded-2xl border border-line bg-panel"
      style={{ animationDelay: `${Math.min(delay, 12) * 45}ms` }}
    >
      <Cover className="h-48 w-full" />
      <div className="p-5">
        <div className="h-5 w-2/3 rounded bg-line" />
        <div className="mt-3 h-3 w-1/2 rounded bg-line" />
      </div>
    </div>
  );
}

function Card({ bean, delay = 0, onClick }) {
  const pct = bean.usable_g ? (bean.balance_g / bean.usable_g) * 100 : 0;
  return (
    <article
      onClick={onClick}
      className="rise cursor-pointer overflow-hidden rounded-2xl border border-line
        bg-panel transition hover:border-amber"
      style={{ animationDelay: `${Math.min(delay, 12) * 45}ms` }}
    >
      <Cover src={coverSrc(bean.cover)} className="h-48 w-full" />
      <div className="p-5">
        <div className="flex items-baseline justify-between gap-2">
          <div className="serif truncate text-lg">{bean.name}</div>
          <span className="shrink-0 text-xs text-muted">
            {bean.certified
              ? "已认证"
              : bean.visibility === "public"
                ? "公开"
                : bean.pending
                  ? "待入袋"
                  : !bean.in_stock
                    ? "历史"
                    : ""}
          </span>
        </div>
        <div className="mt-1 truncate text-[13px] text-muted">
          {[bean.origin, bean.varietal, bean.roast].filter(Boolean).join(" · ") || "还没填产地"}
        </div>
        {freshnessLine(bean.freshness) && (
          <div className="mt-1 truncate text-[13px] text-amber">{freshnessLine(bean.freshness)}</div>
        )}

        {/* 还没入袋就没有克重可言，别拿 0 g 的空进度条糊弄 */}
        {bean.pending ? (
          <div className="mt-3 text-[13px] text-muted">称一下净含量就能开始扣豆</div>
        ) : (
          <>
            <div className="mt-3">
              <Bar pct={pct} warn={bean.near_empty} />
            </div>
            <div className="mt-2 flex justify-between text-[13px] text-muted">
              <span className={bean.near_empty ? "text-warn" : ""}>
                {g(bean.balance_g)}
                {/* 一支豆多袋只出一张卡，袋数在这儿点一下，明细在豆卡页 */}
                {bean.open_lots > 1 && <span className="ml-1.5">共 {bean.open_lots} 袋</span>}
              </span>
              <span>{bean.cups_left < 1 ? "不够一杯了" : `约 ${bean.cups_left} 杯`}</span>
            </div>
            {perG(bean.unit_cost) && (
              <div className="mt-1 text-[13px] text-amber">{perG(bean.unit_cost)}</div>
            )}
          </>
        )}

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
    if (open) setF({ roast: "浅烘", nominal_g: 200, visibility: "private" });
  }, [open]);

  const submit = async () => {
    try {
      const bean = await api.createBean({
        ...f,
        nominal_g: Number(f.nominal_g) || undefined,
        price: f.price ? Number(f.price) : undefined,
        water_temp: f.water_temp ? Number(f.water_temp) : undefined,
        bought_on: f.bought_on || undefined,
        roasted_on: f.roasted_on || undefined,
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
        <Field label="豆种" hint="包装上的 Varietal">
          <Input value={f.varietal || ""} onChange={set("varietal")} placeholder="黄波旁" />
        </Field>
      </div>
      <div className="grid grid-cols-2 gap-3">
        <Field label="处理厂 / 庄园">
          <Input value={f.producer || ""} onChange={set("producer")} placeholder="Matyazo CWS 处理厂" />
        </Field>
        <Field label="海拔">
          <Input value={f.altitude || ""} onChange={set("altitude")} placeholder="1500-2200m" />
        </Field>
      </div>
      <div className="grid grid-cols-2 gap-3">
        <Field label="处理法">
          <Input value={f.process || ""} onChange={set("process")} placeholder="水洗" />
        </Field>
        <Field label="建议水温 °C">
          <Input type="number" value={f.water_temp || ""} onChange={set("water_temp")} placeholder="92" />
        </Field>
      </div>
      <div className="grid grid-cols-2 gap-3">
        <Field label="烘焙">
          <Select value={f.roast || "浅烘"} onChange={set("roast")} className="w-full">
            {["浅烘", "中浅烘", "中烘", "中深烘", "深烘"].map((r) => (
              <option key={r}>{r}</option>
            ))}
          </Select>
        </Field>
        <Field label="袋上印的克重" hint="刚拆袋不用称，先按这个扣">
          <Input type="number" value={f.nominal_g ?? ""} onChange={set("nominal_g")} />
        </Field>
      </div>
      <div className="grid grid-cols-2 gap-3">
        <Field label="这袋多少钱">
          <Input type="number" value={f.price || ""} onChange={set("price")} placeholder="128" />
        </Field>
        <Field label="购入日" hint="不填按今天">
          <Input type="date" value={f.bought_on || ""} onChange={set("bought_on")} />
        </Field>
      </div>
      <Field label="烘焙日" hint="袋上印的 Roast Date，可空">
        <Input type="date" value={f.roasted_on || ""} onChange={set("roasted_on")} />
      </Field>
      <Field label="标签" hint="空格或逗号分开，输入即创建">
        <Input value={f.tags || ""} onChange={set("tags")} placeholder="水洗 柑橘 耶加" />
      </Field>
      <Field label="备注" hint="品牌、坐标这类写这里">
        <Input value={f.note || ""} onChange={set("note")} placeholder='61" coffee · 7°N 40°W' />
      </Field>
      <label className="mt-1 flex items-start gap-2 text-sm text-cream">
        <input
          type="checkbox"
          className="mt-0.5"
          checked={f.visibility === "public"}
          onChange={(e) => setF({ ...f, visibility: e.target.checked ? "public" : "private" })}
        />
        <span>
          建完就公开
          <span className="mt-0.5 block text-[13px] text-muted">
            别人能在广场看见产地和照片，看不见价钱和还剩多少。认证要等管理员审。
          </span>
        </span>
      </label>
      <Field label="店家推荐冲法" hint="豆卡上印的滤器、研磨、水质、目标时长">
        <Input
          value={f.brew_note || ""}
          onChange={set("brew_note")}
          placeholder="KONO 法兰绒 · 富士 #7 · TDS 10-15 · 2'15&quot;"
        />
      </Field>
    </Modal>
  );
}
