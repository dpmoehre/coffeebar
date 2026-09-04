// 豆卡：库存（多袋）+ 雷达在上，冲煮指导整行在下，最近消耗可撤回。
import { useCallback, useEffect, useState } from "react";

import { api } from "../api.js";
import BrewPlan from "../components/BrewPlan.jsx";
import Radar from "../components/Radar.jsx";
import { Plus, Undo } from "../icons.jsx";
import { Bar, Btn, Chip, Field, Input, Modal, Panel, g, money } from "../ui.jsx";

export default function BeanCard({ id, onBack, toast, oops }) {
  const [bean, setBean] = useState(null);
  const [people, setPeople] = useState([]);
  const [brewOpen, setBrewOpen] = useState(false);
  const [prefill, setPrefill] = useState(null);
  const [lotOpen, setLotOpen] = useState(false);
  const [lockInfo, setLockInfo] = useState(null);

  const load = useCallback(
    () => api.bean(id).then(setBean).catch((e) => oops(e.message)),
    [id, oops]
  );

  useEffect(() => {
    setBean(null);
    load();
    api.people().then((d) => setPeople(d.people));
  }, [id, load]);

  // 编辑期间每 60 秒续锁；被接管会被明确告知
  useEffect(() => {
    if (!bean) return;
    const res = `bean:${bean.id}`;
    const t = setInterval(async () => {
      try {
        await api.heartbeat(res);
      } catch (e) {
        if (e.status === 409) oops(e.message);
      }
    }, 60000);
    return () => {
      clearInterval(t);
      api.unlock(res).catch(() => {});
    };
  }, [bean?.id, oops]);

  const guarded = async (fn) => {
    try {
      await api.lock(`bean:${id}`);
      await fn();
    } catch (e) {
      if (e.isLocked && e.body.can_take_over) {
        setLockInfo({ ...e.body, retry: fn });
      } else {
        oops(e.message);
      }
    }
  };

  if (!bean) return <p className="text-muted">读取中…</p>;

  const openLots = bean.lots.filter((l) => !l.closed_at);
  const current = openLots[0];
  const dose = bean.avg_dose;

  return (
    <>
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <button onClick={onBack} className="mb-1.5 text-sm text-muted hover:text-amber">
            ‹ 回豆库
          </button>
          <h1 className="serif m-0 truncate text-3xl font-semibold">{bean.name}</h1>
          <p className="mt-2 mb-0 text-muted">
            {[
              bean.origin,
              bean.process,
              bean.roast,
              current?.opened_on && `开封 ${current.opened_on}`,
              current?.unit_cost && `这杯约 ${money(dose.avg_g * current.unit_cost)}`,
            ]
              .filter(Boolean)
              .join(" · ")}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Btn
            onClick={() =>
              guarded(async () => {
                setPrefill(null);
                setBrewOpen(true);
              })
            }
            disabled={openLots.length === 0}
          >
            冲一次
          </Btn>
          <Btn variant="ghost" onClick={() => setLotOpen(true)}>
            <Plus className="h-4 w-4" />
            再入一袋
          </Btn>
        </div>
      </header>

      <div className="mt-6 grid gap-4 lg:grid-cols-2">
        <Panel>
          <div className="flex items-baseline justify-between">
            <div className="serif text-lg">库存</div>
            <div className="text-[13px] text-muted">
              {openLots.length ? `${openLots.length} 袋在库` : "在库没有了"}
            </div>
          </div>

          <div className="serif mt-3 text-4xl">
            {Math.round(bean.balance_g)}
            <span className="ml-1 text-lg text-amber">g</span>
          </div>
          <p className="mt-1 text-[13px] text-muted">
            {bean.cups_left < 1 ? "不够一杯了" : `还能冲约 ${bean.cups_left} 杯`}（按你平均一杯{" "}
            {dose.avg_g} g
            {dose.lo_g != null && dose.lo_g !== dose.hi_g ? `，${dose.lo_g}–${dose.hi_g}` : ""}
            {dose.source === "fallback" ? "，还没数据" : ""}）
          </p>

          <div className="mt-4 space-y-3">
            {bean.lots.map((lot) => (
              <LotRow key={lot.id} lot={lot} onDone={load} guarded={guarded} toast={toast} oops={oops} />
            ))}
          </div>

          {bean.tags.length > 0 && (
            <div className="mt-4 flex flex-wrap gap-1.5">
              {bean.tags.map((t) => (
                <b
                  key={t}
                  className="rounded-full border border-line px-2 py-0.5 text-xs font-normal text-muted"
                >
                  {t}
                </b>
              ))}
            </div>
          )}
        </Panel>

        <Panel>
          <div className="serif text-lg">杯测雷达</div>
          <Radar scores={bean.scores} />
        </Panel>
      </div>

      <BrewPlan
        bean={bean}
        toast={toast}
        oops={oops}
        onRecord={(info) => {
          setPrefill(info);
          setBrewOpen(true);
        }}
      />

      <Panel className="mt-5">
        <div className="serif text-lg">最近消耗</div>
        <p className="mt-1 mb-3 text-[13px] text-muted">记错了可以撤回，撤回只划掉、不删记录。</p>
        {bean.log.length === 0 ? (
          <p className="text-muted">还没冲过。</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full border-collapse text-sm">
              <thead>
                <tr className="text-muted">
                  {["时间", "谁喝的", "哪一袋", "粉量", "这杯钱", ""].map((h, i) => (
                    <th key={i} className="border-b border-line px-2 py-2 text-left font-normal">
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {bean.log.map((r) => (
                  <tr key={r.id} className={r.voided_at ? "opacity-45 line-through" : ""}>
                    <td className="border-b border-line px-2 py-2 whitespace-nowrap">
                      {r.at.slice(5, 16)}
                    </td>
                    <td className="border-b border-line px-2 py-2">{r.person_name || "没记"}</td>
                    <td className="border-b border-line px-2 py-2 text-muted whitespace-nowrap">
                      {r.bought_on || `#${r.lot_id}`}
                      {r.lot_closed_at ? "（已关）" : ""}
                    </td>
                    <td className="border-b border-line px-2 py-2 text-amber whitespace-nowrap">
                      {r.amount_g} g
                    </td>
                    <td className="border-b border-line px-2 py-2 text-amber whitespace-nowrap">
                      {r.unit_cost ? money(r.cost) : "—"}
                    </td>
                    <td className="border-b border-line px-2 py-2 text-right whitespace-nowrap">
                      <button
                        className="inline-flex items-center gap-1 text-xs text-muted underline
                          hover:text-amber no-underline"
                        onClick={async () => {
                          try {
                            if (r.voided_at) {
                              await api.unvoidBrew(r.id);
                              toast("已恢复这一笔");
                            } else {
                              const out = await api.voidBrew(r.id, "记错了");
                              toast(
                                out.closed_lot_adjusted
                                  ? `已撤回，${r.amount_g} g 记成今天的调整（那袋已关）`
                                  : `已撤回，${r.amount_g} g 加回库存`
                              );
                            }
                            load();
                          } catch (e) {
                            oops(e.message);
                          }
                        }}
                      >
                        <Undo className="h-3.5 w-3.5" />
                        {r.voided_at ? "恢复" : "撤回"}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>

      <BrewOnce
        open={brewOpen}
        onClose={() => setBrewOpen(false)}
        lots={openLots}
        people={people}
        dose={dose}
        prefill={prefill}
        onDone={(msg) => {
          setBrewOpen(false);
          toast(msg);
          load();
          api.people().then((d) => setPeople(d.people));
        }}
        oops={oops}
      />

      <AddLot
        open={lotOpen}
        onClose={() => setLotOpen(false)}
        beanId={bean.id}
        onDone={() => {
          setLotOpen(false);
          toast("又入一袋，没有新建豆卡");
          load();
        }}
        oops={oops}
      />

      <Modal
        open={!!lockInfo}
        onClose={() => setLockInfo(null)}
        title="另一处正在编辑"
        footer={
          <>
            <Btn variant="ghost" onClick={() => setLockInfo(null)}>
              先不动
            </Btn>
            <Btn
              onClick={async () => {
                const retry = lockInfo.retry;
                setLockInfo(null);
                try {
                  await api.lock(`bean:${id}`, true);
                  await retry();
                } catch (e) {
                  oops(e.message);
                }
              }}
            >
              接管
            </Btn>
          </>
        }
      >
        <p className="text-muted">{lockInfo?.message}</p>
      </Modal>
    </>
  );
}

function LotRow({ lot, onDone, guarded, toast, oops }) {
  const [busy, setBusy] = useState(null);
  const pct = lot.usable_g ? (lot.balance_g / lot.usable_g) * 100 : 0;

  const ask = async (kind) => {
    const label = kind === "measure" ? "开袋称出来是多少克" : "现在实际还剩多少克";
    const raw = window.prompt(label, Math.round(lot.balance_g));
    if (raw == null) return;
    const val = Number(raw);
    if (!Number.isFinite(val) || val < 0) return oops("要填个数");
    try {
      if (kind === "measure") {
        await api.measure(lot.id, val);
        toast("补了开袋实称");
      } else {
        const out = await api.adjust(lot.id, val);
        toast(`盘点记下 ${out.delta_g > 0 ? "+" : ""}${out.delta_g} g`);
      }
      onDone();
    } catch (e) {
      oops(e.message);
    }
  };

  return (
    <div className={`rounded-xl border border-line p-3 ${lot.closed_at ? "opacity-50" : ""}`}>
      <div className="flex items-baseline justify-between gap-2 text-sm">
        <div>
          {lot.closed_at ? "已关袋" : lot.opened_on ? "在喝这袋" : "未开封"}
          <span className="ml-2 text-[13px] text-muted">
            标称 {lot.nominal_g}
            {lot.measured_g ? ` · 实称 ${lot.measured_g}` : "（没称）"}
            {lot.price ? ` · ${money(lot.price)}` : ""}
          </span>
        </div>
        <div className="whitespace-nowrap text-amber">{g(lot.balance_g)}</div>
      </div>
      {!lot.closed_at && (
        <>
          <div className="mt-2">
            <Bar pct={pct} warn={pct < 8} />
          </div>
          <div className="mt-2 flex flex-wrap gap-2 text-xs">
            {!lot.measured_g && (
              <button className="text-muted underline hover:text-amber" onClick={() => ask("measure")}>
                补开袋实称
              </button>
            )}
            <button className="text-muted underline hover:text-amber" onClick={() => ask("adjust")}>
              盘点
            </button>
            <button
              className="text-muted underline hover:text-warn"
              onClick={() =>
                guarded(async () => {
                  if (!window.confirm("这袋真的冲完了吗？余数会记成偏差。")) return;
                  const out = await api.closeLot(lot.id);
                  toast(`关袋，偏差 ${out.deviation_g > 0 ? "+" : ""}${out.deviation_g} g`);
                  onDone();
                })
              }
            >
              这袋用完
            </button>
          </div>
        </>
      )}
      {lot.closed_at && (
        <div className="mt-1 text-xs text-muted">
          用掉 {Math.round(lot.used_g ?? 0)} g · 关于 {lot.closed_at.slice(5, 10)}
        </div>
      )}
    </div>
  );
}

function BrewOnce({ open, onClose, lots, people, dose, prefill, onDone, oops }) {
  const [lotId, setLotId] = useState(null);
  const [amount, setAmount] = useState("");
  const [who, setWho] = useState("");

  useEffect(() => {
    if (!open) return;
    // 默认选上次冲用的那袋（后端按开封与创建排序，第一条就是在喝的）
    setLotId(lots[0]?.id ?? null);
    setAmount(String(prefill?.dose ?? dose.avg_g ?? 15));
    setWho(localStorage.getItem("coffeebar-last-person") || "");
  }, [open, lots, prefill, dose]);

  const lot = lots.find((l) => l.id === lotId);
  const amt = Number(amount);
  const short = lot && amt > lot.balance_g;

  const submit = async () => {
    try {
      const res = await api.recordBrew({
        lot_id: lotId,
        amount_g: amt,
        person: who.trim() || undefined,
        brew_method: prefill?.method,
        brew_ratio: prefill?.ratio,
        brew_total_s: prefill?.total_s,
        brew_stages: prefill?.stages,
      });
      if (who.trim()) localStorage.setItem("coffeebar-last-person", who.trim());
      onDone(
        `${who.trim() || "没记谁"} · 扣 ${amt} g${
          res.cost ? ` · ${money(res.cost)}` : ""
        }${res.near_empty ? " · 这袋快见底了" : ""}`
      );
    } catch (e) {
      oops(e.message);
    }
  };

  return (
    <Modal
      open={open}
      onClose={onClose}
      wide
      title="冲一次"
      sub="袋子由你选，粉量填这次实际用了多少。"
      footer={
        <>
          <Btn variant="ghost" onClick={onClose}>
            取消
          </Btn>
          <Btn onClick={submit} disabled={!lotId || !(amt > 0) || short}>
            记下并扣库存
          </Btn>
        </>
      }
    >
      <div>
        <span className="mb-2 block text-[13px] text-muted">
          用哪一袋（默认上次那袋，可改；不自动挑）
        </span>
        <div className="space-y-2">
          {lots.map((l) => (
            <button
              key={l.id}
              onClick={() => setLotId(l.id)}
              className={`flex w-full items-center gap-3 rounded-xl border px-3 py-2.5 text-left
                text-[13px] transition ${
                  l.id === lotId ? "border-amber bg-amber/10" : "border-line hover:border-[#6b5438]"
                }`}
            >
              <span
                className={`h-3.5 w-3.5 shrink-0 rounded-full border ${
                  l.id === lotId ? "border-amber bg-amber" : "border-[#6b5438]"
                }`}
              />
              <span className="min-w-0 flex-1">
                {l.opened_on ? "在喝这袋" : "未开封"}
                <span className="text-muted">
                  {" · "}
                  {l.bought_on ? `${l.bought_on} 入 · ` : ""}标称 {l.nominal_g}
                  {l.measured_g ? ` / 实称 ${l.measured_g}` : ""}
                </span>
              </span>
              <span className="whitespace-nowrap text-amber">
                {g(l.balance_g)}
                {l.price ? ` · ${money(l.price)}` : ""}
              </span>
            </button>
          ))}
        </div>
      </div>

      <Field label="这次实际用了多少粉（克）">
        <Input
          type="number"
          step="0.1"
          value={amount}
          onChange={(e) => setAmount(e.target.value)}
          autoFocus
        />
      </Field>
      <p className={`text-[13px] ${short ? "text-warn" : "text-muted"}`}>
        {!lot
          ? "先选一袋"
          : short
            ? `这袋只剩 ${Math.round(lot.balance_g)} g，不够 ${amt} g。换一袋、改粉量，或先盘点补重。`
            : `这袋账面 ${Math.round(lot.balance_g)} g，按你平均 ${dose.avg_g} g 还能冲约 ${Math.floor(
                lot.balance_g / dose.avg_g
              )} 杯${lot.unit_cost ? ` · 这杯约 ${money(amt * lot.unit_cost)}` : ""}`}
      </p>

      <Field label="谁喝的" hint="打个新名字就有这个人；留空表示没记">
        <Input value={who} onChange={(e) => setWho(e.target.value)} placeholder="我" />
      </Field>
      {people.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {people.map((p) => (
            <Chip key={p.id} on={who === p.name} onClick={() => setWho(p.name)}>
              {p.name}
            </Chip>
          ))}
        </div>
      )}

      {prefill && (
        <p className="text-xs text-muted">
          带上这次冲煮记录：{prefill.method} · 1:{prefill.ratio} · 实际用了{" "}
          {Math.floor(prefill.total_s / 60)}:{String(prefill.total_s % 60).padStart(2, "0")}
        </p>
      )}
    </Modal>
  );
}

function AddLot({ open, onClose, beanId, onDone, oops }) {
  const [f, setF] = useState({});
  useEffect(() => {
    if (open) setF({ nominal_g: 200 });
  }, [open]);

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="再入一袋"
      sub="同样的豆只加批次，产地、风味、冲煮方案都不用重填。"
      footer={
        <>
          <Btn variant="ghost" onClick={onClose}>
            取消
          </Btn>
          <Btn
            onClick={async () => {
              try {
                await api.addLot(beanId, {
                  nominal_g: Number(f.nominal_g),
                  price: f.price ? Number(f.price) : undefined,
                  bought_on: f.bought_on || undefined,
                });
                onDone();
              } catch (e) {
                oops(e.message);
              }
            }}
            disabled={!(Number(f.nominal_g) > 0)}
          >
            入库
          </Btn>
        </>
      }
    >
      <div className="grid grid-cols-2 gap-3">
        <Field label="袋上印的克重">
          <Input
            type="number"
            value={f.nominal_g ?? ""}
            onChange={(e) => setF({ ...f, nominal_g: e.target.value })}
            autoFocus
          />
        </Field>
        <Field label="这袋多少钱">
          <Input
            type="number"
            value={f.price ?? ""}
            onChange={(e) => setF({ ...f, price: e.target.value })}
            placeholder="128"
          />
        </Field>
      </div>
      <Field label="购入日" hint="不填就按今天记">
        <Input type="date" value={f.bought_on ?? ""} onChange={(e) => setF({ ...f, bought_on: e.target.value })} />
      </Field>
    </Modal>
  );
}
