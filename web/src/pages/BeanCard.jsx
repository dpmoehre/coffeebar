// 豆卡：库存（多袋）+ 雷达在上，冲煮指导整行在下，冲煮记录可撤回、可挂过程照。
import { useCallback, useEffect, useRef, useState } from "react";

import { api } from "../api.js";
import BrewPlan from "../components/BrewPlan.jsx";
import OpenBag from "../components/OpenBag.jsx";
import Photos from "../components/Photos.jsx";
import Radar from "../components/Radar.jsx";
import { SCORE_DIMS, freshnessLine, scoreFreshnessLine } from "../freshness.js";
import { Plus, Trash, Undo } from "../icons.jsx";
import { Bar, Btn, Chip, Field, Input, Modal, Panel, Select, g, money } from "../ui.jsx";

export default function BeanCard({ id, onBack, onOpenMap, toast, oops }) {
  const [bean, setBean] = useState(null);
  const [people, setPeople] = useState([]);
  const [brewOpen, setBrewOpen] = useState(false);
  const [prefill, setPrefill] = useState(null);
  const [lotOpen, setLotOpen] = useState(false);
  const [opening, setOpening] = useState(null);
  const [lockInfo, setLockInfo] = useState(null);
  const [wipe, setWipe] = useState(null);
  const [killCard, setKillCard] = useState(false);
  const [editing, setEditing] = useState(false);
  const holding = useRef(false);

  const load = useCallback(
    () => api.bean(id).then(setBean).catch((e) => oops(e.message)),
    [id, oops]
  );

  useEffect(() => {
    let cancelled = false;
    setBean(null);
    api
      .bean(id)
      .then((b) => {
        if (!cancelled) setBean(b);
      })
      .catch((e) => oops(e.message));
    api.people().then((d) => {
      if (!cancelled) setPeople(d.people);
    });
    return () => {
      cancelled = true;
    };
  }, [id, oops]);

  // 只有自己拿到写锁才续；光看着不占锁，也不对空锁心跳（否则会误报被接管、整页闪）。
  useEffect(() => {
    const res = `bean:${id}`;
    const t = setInterval(async () => {
      if (!holding.current) return;
      try {
        await api.heartbeat(res);
      } catch (e) {
        holding.current = false;
        if (e.status === 409) oops(e.message);
      }
    }, 60000);
    return () => {
      clearInterval(t);
      if (holding.current) {
        holding.current = false;
        api.unlock(res).catch(() => {});
      }
    };
  }, [id, oops]);

  const guarded = async (fn) => {
    try {
      await api.lock(`bean:${id}`);
      holding.current = true;
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
  const liveBrews = (bean.log || []).filter((r) => !r.voided_at).length;
  const removeCard = async (mode, done) => {
    setKillCard(false);
    try {
      await api.deleteBean(id, mode);
      toast(done);
      onBack();
    } catch (e) {
      oops(e.message);
    }
  };

  return (
    <>
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <button onClick={onBack} className="mb-1.5 text-sm text-muted hover:text-amber">
            ‹ 回豆库
          </button>
          <div className="flex flex-wrap items-baseline gap-3">
            <h1 className="serif m-0 truncate text-2xl font-semibold md:text-3xl">{bean.name}</h1>
            {bean.certified ? (
              <span className="text-xs text-amber">已认证</span>
            ) : bean.visibility === "public" ? (
              <span className="text-xs text-muted">公开 · 未认证</span>
            ) : (
              <span className="text-xs text-muted">只自己看</span>
            )}
          </div>
          <p className="mt-2 mb-0 text-muted">
            {[
              bean.origin,
              bean.varietal,
              bean.process,
              bean.roast,
              bean.altitude,
              bean.water_temp && `${bean.water_temp} °C`,
              current?.opened_on ? `开封 ${current.opened_on}` : "未开封",
              freshnessLine(bean.freshness),
              current?.unit_cost && `这杯约 ${money(dose.avg_g * current.unit_cost)}`,
            ]
              .filter(Boolean)
              .join(" · ")}
          </p>
          {(bean.producer || bean.note) && (
            <p className="mt-1 mb-0 text-[13px] text-muted">
              {[bean.producer, bean.note].filter(Boolean).join(" · ")}
            </p>
          )}
          {onOpenMap && (
            <p className="mt-1 mb-0 text-[13px] text-muted">
              {bean.places?.length
                ? `地图上：${bean.places.map((p) => p.label).join("、")}`
                : "地图上还没定点"}
              <button
                type="button"
                className="ml-2 text-amber underline hover:text-amber2"
                onClick={() => onOpenMap(bean.id)}
              >
                去地图上点
              </button>
            </p>
          )}
        </div>
        <div className="flex flex-wrap gap-2">
          <Btn
            variant="ghost"
            onClick={() =>
              guarded(async () => {
                const next = bean.visibility === "public" ? "private" : "public";
                const out = await api.updateBean(id, { visibility: next });
                toast(
                  next === "public"
                    ? "已公开。别人能在广场看见，认证要等管理员审"
                    : "已改回只自己看",
                );
                if (out.certification_dropped) toast("认证掉了，要重新审");
                await load();
              })
            }
          >
            {bean.visibility === "public" ? "改回只自己看" : "公开这张卡"}
          </Btn>
          <Btn variant="ghost" onClick={() => setEditing(true)}>
            改资料
          </Btn>
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
          <Btn variant="danger" onClick={() => setKillCard(true)}>
            <Trash className="h-4 w-4" />
            删除豆卡
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
              <LotRow
                key={lot.id}
                lot={lot}
                onDone={load}
                onOpenBag={() => setOpening(lot)}
                guarded={guarded}
                toast={toast}
                oops={oops}
              />
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
          {scoreFreshnessLine(bean.scores) && (
            <p className="mt-2 mb-0 text-[13px] text-amber">{scoreFreshnessLine(bean.scores)}</p>
          )}
          {bean.scores?.comment && (
            <p className="serif mt-3 mb-0 text-[15px] leading-relaxed text-cream">
              {bean.scores.comment}
            </p>
          )}
          {(bean.score_log || []).length > 1 && (
            <div className="mt-4 space-y-1.5">
              {(bean.score_log || []).map((s) => (
                <div key={s.id} className="flex flex-wrap justify-between gap-2 text-[13px] text-muted">
                  <span>
                    {s.at?.slice(0, 10)}
                    {s.lot_seq ? ` · 第 ${s.lot_seq} 袋` : ""}
                    {s.overall != null ? ` · 总体 ${s.overall}` : ""}
                  </span>
                  <span className="text-amber">{scoreFreshnessLine(s) || "没填烘焙日"}</span>
                </div>
              ))}
            </div>
          )}
          <ScoreForm bean={bean} onDone={load} toast={toast} oops={oops} />
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

      <Photos
        beanId={bean.id}
        photos={bean.photos || []}
        onDone={load}
        toast={toast}
        oops={oops}
      />

      <Panel className="mt-5">
        <div className="serif text-lg">冲煮记录</div>
        {bean.grind_hint?.sentence && (
          <p className="mt-1 mb-0 text-[13px] text-amber">{bean.grind_hint.sentence}</p>
        )}
        <p className="mt-1 mb-3 text-[13px] text-muted">
          每次怎么冲都留在这支豆上，称豆、粉床、冲完、器具（称盘、壶、滤杯）的照片也可以挂上。记错了先撤回（只划掉、库存加回去）；划掉的那笔可以再点彻底删除。
        </p>
        {bean.log.length === 0 ? (
          <p className="text-muted">还没冲过。</p>
        ) : (
          <div className="space-y-3">
            {bean.log.map((r) => (
              <div
                key={r.id}
                className={`rounded-xl border border-line px-3 py-3 ${
                  r.voided_at ? "opacity-45" : ""
                }`}
              >
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div>
                    <div className={r.voided_at ? "line-through" : ""}>
                      <span className="text-cream">
                        {r.as_cup === 0 ? "整袋补录" : r.person_name || "没记"}
                      </span>
                      <span className="mx-2 text-muted">·</span>
                      <span className="text-amber">{r.amount_g} g</span>
                      {r.cost != null && (r.unit_cost != null || r.filter_unit_cost != null) ? (
                        <span className="ml-2 text-amber">
                          {money(r.cost)}
                          {r.filter_sheets ? " · 含滤纸" : ""}
                        </span>
                      ) : null}
                    </div>
                    <div className="mt-1 text-[13px] text-muted">
                      {r.at.slice(5, 16)} · 第 {r.lot_seq} 袋
                      {r.lot_closed_at ? "（已关）" : ""}
                      {brewHeadline(r) ? ` · ${brewHeadline(r)}` : ""}
                    </div>
                    {r.note ? <div className="mt-1 text-[13px] text-muted">{r.note}</div> : null}
                  </div>
                  <div className="flex shrink-0 flex-col items-end gap-1">
                    <button
                      className="inline-flex items-center gap-1 text-xs text-muted underline
                        hover:text-amber"
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
                    {r.voided_at ? (
                      <button
                        className="inline-flex items-center gap-1 text-xs text-muted underline
                          hover:text-warn"
                        onClick={() => setWipe(r)}
                      >
                        <Trash className="h-3.5 w-3.5" />
                        彻底删除
                      </button>
                    ) : null}
                  </div>
                </div>
                <BrewHistory stages={parseStages(r.brew_stages)} />
                <BrewPhotos
                  consId={r.id}
                  photos={r.photos || []}
                  onDone={load}
                  toast={toast}
                  oops={oops}
                />
              </div>
            ))}
          </div>
        )}
      </Panel>

      <Modal
        open={killCard}
        onClose={() => setKillCard(false)}
        title={`删掉「${bean.name}」这张豆卡？`}
        wide={liveBrews > 0}
        footer={
          <>
            <Btn variant="ghost" onClick={() => setKillCard(false)}>
              不删了
            </Btn>
            {liveBrews > 0 ? (
              <>
                <Btn
                  onClick={() =>
                    removeCard("keep", `已从豆库收起「${bean.name}」，花掉的钱还在统计里`)
                  }
                >
                  留下花掉的钱
                </Btn>
                <Btn
                  variant="danger"
                  onClick={() =>
                    removeCard("wipe", `已删掉「${bean.name}」，记录和钱也一起抹了`)
                  }
                >
                  连记录一起抹
                </Btn>
              </>
            ) : (
              <Btn variant="danger" onClick={() => removeCard(null, `已删掉「${bean.name}」`)}>
                删掉豆卡
              </Btn>
            )}
          </>
        }
      >
        {liveBrews > 0 ? (
          <p className="text-muted">
            这张卡还有 {liveBrews} 笔没撤回的冲煮，不用先去撤回。
            真喝过就选「留下花掉的钱」：豆库里没这张卡了，统计里杯数和钱还在。
            建错的测试卡选「连记录一起抹」，那几笔也不进账。
          </p>
        ) : (
          <p className="text-muted">
            袋子、库存事件、照片、评分和冲煮默认值一起删，恢复不了。
          </p>
        )}
      </Modal>

      <Modal
        open={!!wipe}
        onClose={() => setWipe(null)}
        title="彻底删掉这笔划掉的记录？"
        footer={
          <>
            <Btn variant="ghost" onClick={() => setWipe(null)}>
              不删了
            </Btn>
            <Btn
              variant="danger"
              onClick={async () => {
                const row = wipe;
                setWipe(null);
                try {
                  await api.deleteBrew(row.id);
                  toast("已彻底删除");
                  load();
                } catch (e) {
                  oops(e.message);
                }
              }}
            >
              彻底删除
            </Btn>
          </>
        }
      >
        <p className="text-muted">
          撤回时库存已经加回去了，删除不会再改克重和钱。过程照会一起从盘上清掉，恢复不了。
        </p>
      </Modal>

      <EditBean
        open={editing}
        bean={bean}
        onClose={() => setEditing(false)}
        onSave={(patch) =>
          guarded(async () => {
            const out = await api.updateBean(id, patch);
            setEditing(false);
            setBean({ ...bean, ...out });
            toast("资料已改");
            if (out.certification_dropped) toast("改了认证相关字段，认证掉了，要重新审");
            load();
          })
        }
      />

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

      <OpenBag
        open={!!opening}
        lot={opening}
        onClose={() => setOpening(null)}
        onDone={(msg) => {
          setOpening(null);
          toast(msg);
          load();
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
                  holding.current = true;
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

function ScoreForm({ bean, onDone, toast, oops }) {
  const lots = bean.lots || [];
  const current = lots.find((l) => !l.closed_at) || lots[0];
  const [lotId, setLotId] = useState(current?.id ?? "");
  const [roastedOn, setRoastedOn] = useState(current?.roasted_on || "");
  const [form, setForm] = useState(() => blankScore());
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    const lot = (bean.lots || []).find((l) => l.id === lotId);
    setRoastedOn(lot?.roasted_on || "");
  }, [lotId, bean.id]);

  const save = async () => {
    const payload = { comment: form.comment || undefined, roasted_on: roastedOn || null };
    if (lotId) payload.lot_id = Number(lotId);
    let filled = Boolean(form.comment);
    for (const [k] of SCORE_DIMS) {
      if (form[k] !== "") {
        payload[k] = Number(form[k]);
        filled = true;
      }
    }
    if (!filled) return oops("先打一个分，或写一句");
    setBusy(true);
    try {
      await api.addScore(bean.id, payload);
      setForm(blankScore());
      toast("杯测记下了");
      onDone();
    } catch (e) {
      oops(e.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="mt-5 border-t border-line pt-4">
      <div className="serif text-base">新打一杯</div>
      <p className="mt-1 mb-0 text-[13px] text-muted">选袋、八维、评语。烘焙日有就带出，可改；袋上还空着会写回这袋。</p>
      {lots.length > 0 && (
        <div className="mt-3 space-y-2">
          {lots.map((l) => (
            <button
              key={l.id}
              type="button"
              onClick={() => setLotId(l.id)}
              className={`flex w-full items-center gap-3 rounded-xl border px-3 py-2 text-left text-[13px] transition ${
                l.id === lotId ? "border-amber bg-amber/10" : "border-line hover:border-[#6b5438]"
              }`}
            >
              <span>
                第 {l.seq} 袋 · {l.closed_at ? "已关袋" : l.opened_on ? "在喝这袋" : "未开封"}
                {l.roasted_on ? ` · 烘于 ${l.roasted_on}` : ""}
              </span>
            </button>
          ))}
        </div>
      )}
      <div className="mt-3">
        <Field label="烘焙日" hint="袋上印的 Roast Date，可空">
          <Input type="date" value={roastedOn} onChange={(e) => setRoastedOn(e.target.value)} />
        </Field>
      </div>
      <div className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-4">
        {SCORE_DIMS.map(([k, label]) => (
          <Field key={k} label={label}>
            <Input
              type="number"
              min="1"
              max="10"
              step="0.5"
              value={form[k]}
              onChange={(e) => setForm({ ...form, [k]: e.target.value })}
            />
          </Field>
        ))}
      </div>
      <div className="mt-3">
        <Field label="一句评语">
          <Input
            value={form.comment}
            onChange={(e) => setForm({ ...form, comment: e.target.value })}
            placeholder="明亮的柠檬、尾段有可可…"
          />
        </Field>
      </div>
      <div className="mt-3">
        <Btn onClick={save} disabled={busy}>
          记下这杯
        </Btn>
      </div>
    </div>
  );
}

function blankScore() {
  const out = { comment: "" };
  for (const [k] of SCORE_DIMS) out[k] = "";
  return out;
}

function LotRow({ lot, onDone, onOpenBag, guarded, toast, oops }) {
  const [busy, setBusy] = useState(null);
  const [roastOn, setRoastOn] = useState(lot.roasted_on || "");
  const pct = lot.usable_g ? (lot.balance_g / lot.usable_g) * 100 : 0;

  useEffect(() => {
    setRoastOn(lot.roasted_on || "");
  }, [lot.roasted_on]);

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
          <span className="text-muted">第 {lot.seq} 袋</span>
          <span className="ml-2">
            {lot.closed_at ? "已关袋" : lot.opened_on ? "在喝这袋" : "未开封"}
          </span>
          <span className="ml-2 text-[13px] text-muted">
            标称 {lot.nominal_g}
            {lot.measured_g ? ` · 实称 ${lot.measured_g}` : "（没称）"}
            {lot.price ? ` · ${money(lot.price)}` : ""}
          </span>
          {freshnessLine(lot.freshness) && (
            <span className="ml-2 text-[13px] text-amber">{freshnessLine(lot.freshness)}</span>
          )}
        </div>
        <div className="whitespace-nowrap text-amber">{g(lot.balance_g)}</div>
      </div>
      <div className="mt-2 flex flex-wrap items-center gap-2 text-xs">
        <span className="text-muted">烘焙日</span>
        <Input
          type="date"
          className="w-auto py-1 text-xs"
          value={roastOn}
          onChange={(e) => setRoastOn(e.target.value)}
        />
        <button
          className="text-amber underline"
          disabled={busy === "roast"}
          onClick={async () => {
            setBusy("roast");
            try {
              await api.setLotRoast(lot.id, roastOn || null);
              toast(roastOn ? "烘焙日记下了" : "已去掉烘焙日");
              onDone();
            } catch (e) {
              oops(e.message);
            } finally {
              setBusy(null);
            }
          }}
        >
          记下
        </button>
      </div>
      {!lot.closed_at && (
        <>
          <div className="mt-2">
            <Bar pct={pct} warn={pct < 8} />
          </div>
          <div className="mt-2 flex flex-wrap gap-2 text-xs">
            {!lot.opened_on && (
              <button className="font-semibold text-amber underline" onClick={onOpenBag}>
                开封
              </button>
            )}
            {lot.opened_on && !lot.measured_g && (
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
  const [totalS, setTotalS] = useState("");
  const [paper, setPaper] = useState(null);
  const [packId, setPackId] = useState(null);

  useEffect(() => {
    if (!open) return;
    // 默认选上次冲用的那袋（后端按开封与创建排序，第一条就是在喝的）
    setLotId(lots[0]?.id ?? null);
    setAmount(String(prefill?.dose ?? dose.avg_g ?? 15));
    setWho(localStorage.getItem("coffeebar-last-person") || "");
    setTotalS(prefill?.total_s != null ? String(prefill.total_s) : "");
    setPaper(undefined);
    setPackId(null);
    api.brewMethods().then((d) => {
      const f = d.filter || null;
      setPaper(f);
      if (f?.pack_id) setPackId(f.pack_id);
    });
  }, [open, lots, prefill, dose]);

  const lot = lots.find((l) => l.id === lotId);
  const amt = Number(amount);
  const short = lot && amt > lot.balance_g;
  const pickedPack = paper?.need_pick
    ? (paper.packs || []).find((p) => p.pack_id === packId)
    : paper;
  const paperUnit = pickedPack?.unit_cost;
  const beanUnit = lot?.unit_cost;
  const cupCost =
    beanUnit != null || paperUnit != null
      ? (amt > 0 && beanUnit != null ? amt * beanUnit : 0) + (paperUnit || 0)
      : null;

  const submit = async () => {
    try {
      const res = await api.recordBrew({
        lot_id: lotId,
        amount_g: amt,
        person: who.trim() || undefined,
        brew_method: prefill?.method,
        brew_ratio: prefill?.ratio,
        brew_total_s: totalS ? Number(totalS) : undefined,
        brew_stages: prefill?.stages,
        filter_pack_id: packId || undefined,
      });
      if (who.trim()) localStorage.setItem("coffeebar-last-person", who.trim());
      const paperBit =
        res.filter_cost != null ? ` · 滤纸 ${money(res.filter_cost)}` : "";
      onDone(
        `${who.trim() || "没记谁"} · 扣 ${amt} g${
          res.cost ? ` · ${money(res.cost)}` : ""
        }${paperBit}${res.near_empty ? " · 这袋快见底了" : ""}`
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
                第 {l.seq} 袋 · {l.opened_on ? "在喝这袋" : "未开封"}
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
      <Field label="实际总秒" hint="可空。播完会带上；手填也能对照方案给研磨建议">
        <Input
          type="number"
          value={totalS}
          onChange={(e) => setTotalS(e.target.value)}
          placeholder="例如 168"
        />
      </Field>
      <p className={`text-[13px] ${short ? "text-warn" : "text-muted"}`}>
        {!lot
          ? "先选一袋"
          : short
            ? `这袋只剩 ${Math.round(lot.balance_g)} g，不够 ${amt} g。换一袋、改粉量，或先盘点补重。`
            : `这袋账面 ${Math.round(lot.balance_g)} g，按你平均 ${dose.avg_g} g 还能冲约 ${Math.floor(
                lot.balance_g / dose.avg_g
              )} 杯${cupCost != null ? ` · 这杯约 ${money(cupCost)}` : ""}`}
      </p>
      {paper === undefined ? null : paper?.need_pick ? (
        <div>
          <span className="mb-2 block text-[13px] text-muted">
            开着好几包滤纸，选一包才扣纸；不选这杯不加纸钱
          </span>
          <div className="flex flex-wrap gap-2">
            {(paper.packs || []).map((p) => (
              <Chip key={p.pack_id} on={packId === p.pack_id} onClick={() => setPackId(p.pack_id)}>
                {p.name || "滤纸"} · 还剩 {p.remaining} 张
                {p.unit_cost != null ? ` · ${money(p.unit_cost)} / 张` : ""}
              </Chip>
            ))}
          </div>
        </div>
      ) : paper?.remaining != null ? (
        <p className="text-[13px] text-muted">
          滤纸还剩 {paper.remaining} 张
          {paper.unit_cost != null ? `，这杯加 ${money(paper.unit_cost)}` : "，这包没记价钱"}
        </p>
      ) : (
        <p className="text-[13px] text-muted">还没开包计张，这杯不加纸钱。</p>
      )}

      <Field label="谁喝的" hint="打个新名字就有这个人；留空表示没记">
        <Input value={who} onChange={(e) => setWho(e.target.value)} placeholder="丁瀚舟" />
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
                  roasted_on: f.roasted_on || undefined,
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
      <Field label="烘焙日" hint="袋上印的 Roast Date，可空">
        <Input type="date" value={f.roasted_on ?? ""} onChange={(e) => setF({ ...f, roasted_on: e.target.value })} />
      </Field>
    </Modal>
  );
}

const METHOD = {
  v60: "V60 四段",
  hoffmann: "Hoffmann 一杯",
  kasuya: "4:6 粕谷",
  kalita: "Kalita",
  volcano: "多段式火山冲",
};

function wr(n) {
  if (n == null || n === 0) return "";
  return `1:${Number(n).toFixed(2)}`;
}

function fmtSec(s) {
  if (s == null) return "";
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

function parseStages(raw) {
  if (!raw) return [];
  if (Array.isArray(raw)) return raw;
  try {
    const v = JSON.parse(raw);
    return Array.isArray(v) ? v : [];
  } catch {
    return [];
  }
}

function brewHeadline(r) {
  const bits = [];
  if (r.brew_method) bits.push(METHOD[r.brew_method] || r.brew_method);
  if (r.brew_ratio) bits.push(wr(r.brew_ratio));
  if (r.brew_total_s) bits.push(fmtSec(r.brew_total_s));
  if (r.brew_compare) {
    bits.push(`方案 ${fmtSec(r.brew_compare.planned_s)}`);
    if (r.brew_compare.key === "hold") bits.push("对上了");
    else bits.push(r.brew_compare.delta_s > 0 ? "偏慢" : "偏快");
  }
  return bits.join(" · ");
}

const BREW_PHOTO_KINDS = [
  ["beans", "称豆"],
  ["bed", "粉床"],
  ["finish", "冲完"],
  ["gear", "器具"],
];

function BrewPhotos({ consId, photos, onDone, toast, oops }) {
  const [busy, setBusy] = useState(null);
  const [zoom, setZoom] = useState(null);
  const inputs = useRef({});
  const label = Object.fromEntries(BREW_PHOTO_KINDS);

  const pick = async (kind, files) => {
    if (!files?.length) return;
    setBusy(kind);
    try {
      for (const f of files) await api.addBrewPhoto(consId, f, kind);
      toast(files.length > 1 ? `加了 ${files.length} 张` : "照片挂上了");
      onDone();
    } catch (e) {
      oops(e.message);
    } finally {
      setBusy(null);
      if (inputs.current[kind]) inputs.current[kind].value = "";
    }
  };

  return (
    <div className="mt-3">
      <div className="flex flex-wrap gap-2">
        {BREW_PHOTO_KINDS.map(([kind, name]) => (
          <label
            key={kind}
            className="inline-flex cursor-pointer items-center gap-1 rounded-full border
              border-line px-2.5 py-1 text-xs hover:border-amber"
          >
            <Plus className="h-3 w-3" />
            {busy === kind ? "上传中…" : name}
            <input
              ref={(el) => (inputs.current[kind] = el)}
              type="file"
              accept="image/*,.heic,.heif"
              multiple
              className="hidden"
              onChange={(e) => pick(kind, [...e.target.files])}
            />
          </label>
        ))}
      </div>
      {photos.length > 0 ? (
        <div className="mt-2 grid grid-cols-3 gap-2">
          {photos.map((p) => (
            <figure key={p.id} className="group relative m-0">
              <img
                src={p.thumb}
                alt={label[p.kind] || p.kind}
                onClick={() => setZoom(p)}
                className="aspect-square w-full cursor-zoom-in rounded-lg border border-line
                  object-cover transition hover:border-amber"
              />
              <figcaption
                className="absolute bottom-1.5 left-1.5 rounded-full bg-black/65 px-2 py-0.5
                  text-[11px] text-cream"
              >
                {label[p.kind] || p.kind}
              </figcaption>
              <button
                title="删掉这张"
                className="absolute right-1.5 top-1.5 hidden h-6 w-6 rounded-full bg-black/70
                  text-cream hover:bg-warn group-hover:block"
                onClick={async () => {
                  try {
                    await api.delBrewPhoto(p.id);
                    toast("删掉了");
                    onDone();
                  } catch (e) {
                    oops(e.message);
                  }
                }}
              >
                ×
              </button>
            </figure>
          ))}
        </div>
      ) : null}
      {zoom ? (
        <div
          onClick={() => setZoom(null)}
          className="fixed inset-0 z-50 grid cursor-zoom-out place-items-center bg-black/80 p-6"
        >
          <img src={zoom.url} alt="" className="max-h-full max-w-full rounded-xl" />
        </div>
      ) : null}
    </div>
  );
}

function EditBean({ open, bean, onClose, onSave }) {
  const [f, setF] = useState({});
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });

  useEffect(() => {
    if (open && bean) {
      setF({
        name: bean.name || "",
        origin: bean.origin || "",
        varietal: bean.varietal || "",
        producer: bean.producer || "",
        altitude: bean.altitude || "",
        process: bean.process || "",
        roast: bean.roast || "浅烘",
        note: bean.note || "",
        tags: (bean.tags || []).join(" "),
      });
    }
  }, [open, bean]);

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="改资料"
      sub="改名字、产地、豆种、处理厂、处理法、烘焙或海拔后，已有的认证会掉，要重新审。"
      footer={
        <>
          <Btn variant="ghost" onClick={onClose}>
            取消
          </Btn>
          <Btn
            onClick={() =>
              onSave({
                name: f.name,
                origin: f.origin,
                varietal: f.varietal,
                producer: f.producer,
                altitude: f.altitude,
                process: f.process,
                roast: f.roast,
                note: f.note,
                tags: (f.tags || "").split(/[,，\s]+/).filter(Boolean),
              })
            }
            disabled={!f.name?.trim()}
          >
            保存
          </Btn>
        </>
      }
    >
      <Field label="名字">
        <Input value={f.name || ""} onChange={set("name")} />
      </Field>
      <div className="grid grid-cols-2 gap-3">
        <Field label="产地">
          <Input value={f.origin || ""} onChange={set("origin")} />
        </Field>
        <Field label="豆种">
          <Input value={f.varietal || ""} onChange={set("varietal")} />
        </Field>
      </div>
      <div className="grid grid-cols-2 gap-3">
        <Field label="处理厂 / 庄园">
          <Input value={f.producer || ""} onChange={set("producer")} />
        </Field>
        <Field label="海拔">
          <Input value={f.altitude || ""} onChange={set("altitude")} />
        </Field>
      </div>
      <div className="grid grid-cols-2 gap-3">
        <Field label="处理法">
          <Input value={f.process || ""} onChange={set("process")} />
        </Field>
        <Field label="烘焙">
          <Select value={f.roast || "浅烘"} onChange={set("roast")} className="w-full">
            {["浅烘", "中浅烘", "中烘", "中深烘", "深烘"].map((r) => (
              <option key={r}>{r}</option>
            ))}
          </Select>
        </Field>
      </div>
      <Field label="标签">
        <Input value={f.tags || ""} onChange={set("tags")} />
      </Field>
      <Field label="备注">
        <Input value={f.note || ""} onChange={set("note")} />
      </Field>
    </Modal>
  );
}

function BrewHistory({ stages }) {
  if (!stages.length) return null;
  const objects = stages.filter((s) => s && typeof s === "object");
  if (!objects.length) return null;
  return (
    <div className="mt-2 overflow-x-auto text-[13px] text-muted">
      {objects.map((s, i) => (
        <div key={i}>
          {s.name}
          {s.add_g ? ` +${s.add_g} g` : " 停手"}
          {s.add_ratio ? ` ${wr(s.add_ratio)}` : ""}
          {s.target_g != null ? ` → 秤到 ${s.target_g} g` : ""}
          {s.target_ratio ? ` ${wr(s.target_ratio)}` : ""}
        </div>
      ))}
    </div>
  );
}
