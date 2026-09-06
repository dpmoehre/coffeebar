// 酒卡：库存（多瓶）+ 倒一杯 + 照片。
import { useCallback, useEffect, useState } from "react";

import { api } from "../api.js";
import Photos from "../components/Photos.jsx";
import { Plus, Trash, Undo } from "../icons.jsx";
import { Bar, Btn, Field, Input, Modal, Panel, money } from "../ui.jsx";

export default function SpiritCard({ id, onBack, toast, oops }) {
  const [spirit, setSpirit] = useState(null);
  const [people, setPeople] = useState([]);
  const [pourOpen, setPourOpen] = useState(false);
  const [lotOpen, setLotOpen] = useState(false);
  const [wipe, setWipe] = useState(null);
  const [killCard, setKillCard] = useState(false);

  const load = useCallback(
    () => api.spirit(id).then(setSpirit).catch((e) => oops(e.message)),
    [id, oops]
  );

  useEffect(() => {
    let cancelled = false;
    setSpirit(null);
    api
      .spirit(id)
      .then((s) => {
        if (!cancelled) setSpirit(s);
      })
      .catch((e) => oops(e.message));
    api.people().then((d) => {
      if (!cancelled) setPeople(d.people);
    });
    return () => {
      cancelled = true;
    };
  }, [id, oops]);

  if (!spirit) return <p className="text-muted">读取中…</p>;

  const openLots = spirit.lots.filter((l) => !l.closed_at);
  const current = openLots[0];
  const liveDrinks = (spirit.log || []).filter((r) => !r.voided_at).length;
  const removeCard = async (mode, done) => {
    setKillCard(false);
    try {
      await api.deleteSpirit(id, mode);
      toast(done);
      onBack();
    } catch (e) {
      oops(e.message);
    }
  };

  return (
    <>
      <button className="mb-4 text-sm text-muted underline hover:text-amber" onClick={onBack}>
        ← 酒水
      </button>

      <header className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="serif m-0 text-2xl font-semibold md:text-3xl">{spirit.name}</h1>
          <p className="mt-2 mb-0 text-muted">
            {[
              spirit.kind,
              spirit.category && spirit.category !== spirit.kind ? spirit.category : null,
              spirit.origin,
              spirit.flavor,
              spirit.abv != null && `${spirit.abv}% vol`,
              current?.opened_on ? `开瓶 ${current.opened_on}` : current ? "未开瓶" : "待入瓶",
            ]
              .filter(Boolean)
              .join(" · ")}
          </p>
          {spirit.note && <p className="mt-1 mb-0 text-[13px] text-muted">{spirit.note}</p>}
        </div>
        <div className="flex flex-wrap gap-2">
          <Btn onClick={() => setPourOpen(true)} disabled={openLots.length === 0}>
            倒一杯
          </Btn>
          <Btn variant="ghost" onClick={() => setLotOpen(true)}>
            <Plus className="h-4 w-4" />
            再入一瓶
          </Btn>
          <Btn variant="danger" onClick={() => setKillCard(true)}>
            <Trash className="h-4 w-4" />
            删除酒卡
          </Btn>
        </div>
      </header>

      <Panel className="mt-6">
        <div className="flex items-baseline justify-between">
          <div className="serif text-lg">库存</div>
          <div className="text-[13px] text-muted">
            {openLots.length ? `${openLots.length} 瓶在库` : "在库没有了"}
          </div>
        </div>
        <div className="serif mt-3 text-4xl">
          {Math.round(spirit.balance_ml)}
          <span className="ml-1 text-lg text-amber">ml</span>
        </div>
        {spirit.unit_cost != null && (
          <p className="mt-1 text-[13px] text-muted">
            {spirit.unit_cost.toFixed(2)} 元/ml
            {current?.price != null && ` · 这瓶 ${money(current.price)}`}
          </p>
        )}
        <div className="mt-4 space-y-3">
          {spirit.lots.map((lot) => (
            <LotRow key={lot.id} lot={lot} onDone={load} toast={toast} oops={oops} />
          ))}
        </div>
      </Panel>

      <Photos
        photos={spirit.photos}
        onDone={load}
        toast={toast}
        oops={oops}
        kinds={[
          ["pack", "瓶盒"],
          ["label", "酒标"],
        ]}
        upload={(file, kind) => api.addBottlePhoto(id, file, kind)}
      />

      <Panel className="mt-5">
        <div className="serif text-lg">最近倒过</div>
        {spirit.log.length === 0 ? (
          <p className="text-muted">还没倒过。</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full border-collapse text-sm">
              <thead>
                <tr className="text-muted">
                  {["时间", "谁喝的", "毫升", "这杯钱", ""].map((h, i) => (
                    <th key={i} className="border-b border-line px-2 py-2 text-left font-normal">
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {spirit.log.map((r) => (
                  <tr key={r.id} className={r.voided_at ? "opacity-45 line-through" : ""}>
                    <td className="border-b border-line px-2 py-2 whitespace-nowrap">
                      {r.at.slice(5, 16)}
                    </td>
                    <td className="border-b border-line px-2 py-2">{r.person_name || "没记"}</td>
                    <td className="border-b border-line px-2 py-2 text-amber whitespace-nowrap">
                      {r.amount_ml} ml
                    </td>
                    <td className="border-b border-line px-2 py-2 text-amber whitespace-nowrap">
                      {r.unit_cost ? money(r.cost) : "—"}
                    </td>
                    <td className="border-b border-line px-2 py-2 text-right">
                      <div className="flex flex-col items-end gap-1">
                        <button
                          className="inline-flex items-center gap-1 text-xs text-muted hover:text-amber"
                          onClick={async () => {
                            try {
                              if (r.voided_at) {
                                await api.unvoidBrew(r.id);
                                toast("已恢复这一笔");
                              } else {
                                await api.voidBrew(r.id, "记错了");
                                toast(`已撤回，${r.amount_ml} ml 加回库存`);
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
                            className="inline-flex items-center gap-1 text-xs text-muted hover:text-warn"
                            onClick={() => setWipe(r)}
                          >
                            <Trash className="h-3.5 w-3.5" />
                            彻底删除
                          </button>
                        ) : null}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>

      <Modal
        open={killCard}
        onClose={() => setKillCard(false)}
        title={`删掉「${spirit.name}」这张酒卡？`}
        wide={liveDrinks > 0}
        footer={
          <>
            <Btn variant="ghost" onClick={() => setKillCard(false)}>
              不删了
            </Btn>
            {liveDrinks > 0 ? (
              <>
                <Btn
                  onClick={() =>
                    removeCard("keep", `已从酒库收起「${spirit.name}」，花掉的钱还在统计里`)
                  }
                >
                  留下花掉的钱
                </Btn>
                <Btn
                  variant="danger"
                  onClick={() =>
                    removeCard("wipe", `已删掉「${spirit.name}」，记录和钱也一起抹了`)
                  }
                >
                  连记录一起抹
                </Btn>
              </>
            ) : (
              <Btn variant="danger" onClick={() => removeCard(null, `已删掉「${spirit.name}」`)}>
                删掉酒卡
              </Btn>
            )}
          </>
        }
      >
        {liveDrinks > 0 ? (
          <p className="text-muted">
            这张卡还有 {liveDrinks} 笔没撤回的倒酒，不用先去撤回。
            真喝过就选「留下花掉的钱」：酒库里没这张卡了，统计里杯数和钱还在。
            建错的测试卡选「连记录一起抹」，那几笔也不进账。
          </p>
        ) : (
          <p className="text-muted">
            瓶子、库存事件、照片和酒单里这支酒的条目一起删，恢复不了。
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
          撤回时毫升已经加回去了，删除不会再改库存和钱。恢复不了。
        </p>
      </Modal>

      <PourOnce
        open={pourOpen}
        onClose={() => setPourOpen(false)}
        lots={openLots}
        people={people}
        onDone={(msg) => {
          setPourOpen(false);
          toast(msg);
          load();
          api.people().then((d) => setPeople(d.people));
        }}
        oops={oops}
      />

      <AddBottle
        open={lotOpen}
        onClose={() => setLotOpen(false)}
        bottleId={spirit.id}
        onDone={() => {
          setLotOpen(false);
          toast("又入一瓶，没有新建酒卡");
          load();
        }}
        oops={oops}
      />
    </>
  );
}

function LotRow({ lot, onDone, toast, oops }) {
  const pct = lot.usable_ml ? (lot.balance_ml / lot.usable_ml) * 100 : 0;

  return (
    <div className={`rounded-xl border border-line p-3 ${lot.closed_at ? "opacity-50" : ""}`}>
      <div className="flex items-baseline justify-between gap-2 text-sm">
        <div>
          <span className="text-muted">第 {lot.seq} 瓶</span>
          <span className="ml-2">
            {lot.closed_at ? "已关瓶" : lot.opened_on ? "在喝这瓶" : "未开瓶"}
          </span>
          <span className="ml-2 text-[13px] text-muted">
            标称 {lot.nominal_ml} ml
            {lot.price ? ` · ${money(lot.price)}` : ""}
          </span>
        </div>
        <div className="whitespace-nowrap text-amber">{Math.round(lot.balance_ml)} ml</div>
      </div>
      {!lot.closed_at && (
        <>
          <div className="mt-2">
            <Bar pct={pct} warn={pct < 8} />
          </div>
          <div className="mt-2 flex flex-wrap gap-2 text-xs">
            {!lot.opened_on && (
              <button
                className="font-semibold text-amber underline"
                onClick={async () => {
                  try {
                    await api.openBottle(lot.id);
                    toast("开瓶了");
                    onDone();
                  } catch (e) {
                    oops(e.message);
                  }
                }}
              >
                开瓶
              </button>
            )}
            <button
              className="text-muted underline hover:text-amber"
              onClick={async () => {
                const raw = window.prompt("现在实际还剩多少毫升", Math.round(lot.balance_ml));
                if (raw == null) return;
                try {
                  const out = await api.adjustBottle(lot.id, Number(raw));
                  toast(`盘点记下 ${out.delta_ml > 0 ? "+" : ""}${out.delta_ml} ml`);
                  onDone();
                } catch (e) {
                  oops(e.message);
                }
              }}
            >
              盘点
            </button>
            <button
              className="text-muted underline hover:text-warn"
              onClick={async () => {
                if (!window.confirm("这瓶真的倒完了吗？余数会记成偏差。")) return;
                try {
                  const out = await api.closeBottle(lot.id);
                  toast(`关瓶，偏差 ${out.deviation_ml > 0 ? "+" : ""}${out.deviation_ml} ml`);
                  onDone();
                } catch (e) {
                  oops(e.message);
                }
              }}
            >
              这瓶倒完
            </button>
          </div>
        </>
      )}
    </div>
  );
}

function PourOnce({ open, onClose, lots, people, onDone, oops }) {
  const [lotId, setLotId] = useState(null);
  const [amount, setAmount] = useState("30");
  const [who, setWho] = useState("");

  useEffect(() => {
    if (!open) return;
    setLotId(lots[0]?.id ?? null);
    setAmount("30");
    setWho(localStorage.getItem("coffeebar-last-person") || "");
  }, [open, lots]);

  const lot = lots.find((l) => l.id === lotId);
  const amt = Number(amount);
  const short = lot && amt > lot.balance_ml;

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="倒一杯"
      sub="瓶子由你选，毫升填这次实际倒了多少。"
      footer={
        <>
          <Btn variant="ghost" onClick={onClose}>
            取消
          </Btn>
          <Btn
            disabled={!lotId || !(amt > 0) || short}
            onClick={async () => {
              try {
                const res = await api.recordDrink({
                  lot_id: lotId,
                  amount_ml: amt,
                  person: who.trim() || undefined,
                });
                if (who.trim()) localStorage.setItem("coffeebar-last-person", who.trim());
                onDone(
                  `${who.trim() || "没记谁"} · 倒 ${amt} ml${
                    res.cost ? ` · ${money(res.cost)}` : ""
                  }${res.alcohol_g ? ` · 酒精约 ${res.alcohol_g} g` : ""}`
                );
              } catch (e) {
                oops(e.message);
              }
            }}
          >
            记下并扣库存
          </Btn>
        </>
      }
    >
      <div className="space-y-2">
        {lots.map((l) => (
          <button
            key={l.id}
            onClick={() => setLotId(l.id)}
            className={`flex w-full items-center gap-3 rounded-xl border px-3 py-2.5 text-left
              text-[13px] ${l.id === lotId ? "border-amber bg-amber/10" : "border-line"}`}
          >
            <span>
              第 {l.seq} 瓶 · {l.opened_on ? "在喝这瓶" : "未开瓶"}
            </span>
            <span className="ml-auto text-amber">{Math.round(l.balance_ml)} ml</span>
          </button>
        ))}
      </div>
      <Field label="这次倒了多少（ml）">
        <Input type="number" step="1" value={amount} onChange={(e) => setAmount(e.target.value)} />
      </Field>
      {short && <p className="text-sm text-warn">这瓶不够了。</p>}
      <Field label="谁喝的" hint="不填就记成没记">
        <Input
          value={who}
          onChange={(e) => setWho(e.target.value)}
          list="people-list"
          placeholder="戚浩辰"
        />
        <datalist id="people-list">
          {people.map((p) => (
            <option key={p.id} value={p.name} />
          ))}
        </datalist>
      </Field>
    </Modal>
  );
}

function AddBottle({ open, onClose, bottleId, onDone, oops }) {
  const [f, setF] = useState({ nominal_ml: 1000, price: "" });

  useEffect(() => {
    if (open) setF({ nominal_ml: 1000, price: "" });
  }, [open]);

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="再入一瓶"
      footer={
        <>
          <Btn variant="ghost" onClick={onClose}>
            取消
          </Btn>
          <Btn
            onClick={async () => {
              try {
                await api.addBottleLot(bottleId, {
                  nominal_ml: Number(f.nominal_ml),
                  price: f.price ? Number(f.price) : undefined,
                });
                onDone();
              } catch (e) {
                oops(e.message);
              }
            }}
          >
            入库
          </Btn>
        </>
      }
    >
      <div className="grid grid-cols-2 gap-3">
        <Field label="标称容量 ml">
          <Input
            type="number"
            value={f.nominal_ml}
            onChange={(e) => setF({ ...f, nominal_ml: e.target.value })}
          />
        </Field>
        <Field label="这瓶多少钱">
          <Input
            type="number"
            value={f.price}
            onChange={(e) => setF({ ...f, price: e.target.value })}
          />
        </Field>
      </div>
    </Modal>
  );
}
