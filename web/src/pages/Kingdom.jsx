// 咖啡王国：大家对同一支公共豆种杯测、评价、收藏。看不见任何人的进价和库存。
import { useEffect, useMemo, useState } from "react";

import { api } from "../api.js";
import { recall, remember } from "../listCache.js";
import Radar from "../components/Radar.jsx";
import { Plus } from "../icons.jsx";
import { KingdomGearCard, KingdomGearList } from "../components/KingdomGear.jsx";
import { Btn, Chip, Cover, Empty, Field, Input, Panel, coverSrc } from "../ui.jsx";

const DIMS = [
  ["dry", "干香"],
  ["flavor", "风味"],
  ["aftertaste", "余韵"],
  ["acidity", "酸质"],
  ["sweetness", "甜感"],
  ["body", "醇厚"],
  ["balance", "平衡"],
  ["overall", "总体"],
];

export default function Kingdom({
  openId,
  openGearId,
  tab = "beans",
  onTab,
  onOpen,
  onOpenGear,
  onBack,
  onOpenPlaza,
  onOpenPlazaGear,
  onOpenMineGear,
  toast,
  oops,
}) {
  if (openId) {
    return (
      <KingdomCard
        id={openId}
        onBack={onBack}
        onOpenPlaza={onOpenPlaza}
        toast={toast}
        oops={oops}
      />
    );
  }
  if (openGearId) {
    return (
      <KingdomGearCard
        id={openGearId}
        onBack={onBack}
        onOpenPlaza={onOpenPlazaGear}
        onOpenMineGear={onOpenMineGear}
        toast={toast}
        oops={oops}
      />
    );
  }
  return (
    <>
      <header>
        <h1 className="serif m-0 text-2xl font-semibold md:text-3xl">咖啡王国</h1>
        <p className="mt-2 mb-0 text-muted">
          {tab === "gear"
            ? "大家一起评同一件器具。管理员收到目录的才会出现；只打总体分和一句话，看不见谁的台面。"
            : "大家一起评同一支豆。杯测、评价、收藏都挂在这里，看不见别人的进价和还剩多少。"}
        </p>
      </header>
      <div className="mt-5 flex flex-wrap gap-2">
        <Chip on={tab === "beans"} onClick={() => onTab?.("beans")}>
          豆子
        </Chip>
        <Chip on={tab === "gear"} onClick={() => onTab?.("gear")}>
          器具
        </Chip>
      </div>
      {tab === "gear" ? (
        <KingdomGearList onOpen={onOpenGear} oops={oops} />
      ) : (
        <KingdomList onOpen={onOpen} oops={oops} />
      )}
    </>
  );
}

function KingdomList({ onOpen, oops }) {
  const [saved, setSaved] = useState(false);
  const [beans, setBeans] = useState(() => recall("kingdom:false") ?? null);
  const [q, setQ] = useState("");

  const load = () =>
    api
      .kingdom(saved)
      .then((d) => {
        remember(`kingdom:${saved}`, d.beans);
        setBeans(d.beans);
      })
      .catch((e) => oops(e.message));

  useEffect(() => {
    const hit = recall(`kingdom:${saved}`);
    setBeans(hit === undefined ? null : hit);
    load();
  }, [saved]);

  const shown = useMemo(() => {
    const list = [...(beans || [])];
    const needle = q.trim().toLowerCase();
    if (!needle) return list;
    return list.filter((b) =>
      [b.name, b.origin, b.varietal, b.producer].filter(Boolean).some((x) => String(x).toLowerCase().includes(needle)),
    );
  }, [beans, q]);

  return (
    <>
      <div className="mt-5 flex flex-wrap items-center gap-2">
        <Chip on={saved} onClick={() => setSaved((v) => !v)}>
          只看收藏
        </Chip>
        <Input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="搜名字、产地…"
          className="w-44 py-1.5 text-sm"
        />
      </div>

      {!beans ? (
        <p className="mt-6 text-muted">读取中…</p>
      ) : (
        <>
          <div className="mt-6 grid gap-4 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4">
            {shown.map((b, i) => (
              <article
                key={b.id}
                onClick={() => onOpen(b.id)}
                className="rise cursor-pointer overflow-hidden rounded-2xl border border-line
                  bg-panel transition hover:border-amber"
                style={{ animationDelay: `${Math.min(i, 12) * 45}ms` }}
              >
                <Cover src={coverSrc(b.cover)} className="h-48 w-full" />
                <div className="p-5">
                  <div className="flex items-baseline justify-between gap-2">
                    <div className="serif truncate text-lg">{b.name}</div>
                    {b.favorited ? <span className="shrink-0 text-xs text-amber">已收藏</span> : null}
                  </div>
                  <div className="mt-1 truncate text-[13px] text-muted">
                    {[b.origin, b.varietal, b.roast].filter(Boolean).join(" · ") || "还没填产地"}
                  </div>
                  <div className="mt-3 text-sm text-amber">
                    {b.avg?.overall != null ? `总体 ${b.avg.overall}` : "还没人评"}
                    <span className="ml-2 text-xs text-muted">
                      {b.cups} 杯测 · {b.favorites} 收藏
                      {b.plaza_cards ? ` · 广场 ${b.plaza_cards} 张` : ""}
                    </span>
                  </div>
                </div>
              </article>
            ))}
          </div>
          {shown.length === 0 && (
            <Empty>
              {saved || q.trim()
                ? "没有对得上的。"
                : "王国还是空的。管理员把广场上的公开卡收进来之后，大家就能一起评。"}
            </Empty>
          )}
        </>
      )}
    </>
  );
}

function KingdomCard({ id, onBack, onOpenPlaza, toast, oops }) {
  const [bean, setBean] = useState(null);

  const load = () =>
    api
      .kingdomItem(id)
      .then(setBean)
      .catch((e) => oops(e.message));

  useEffect(() => {
    setBean(null);
    load();
  }, [id]);

  if (!bean) return <p className="text-muted">读取中…</p>;

  const fav = async () => {
    try {
      setBean(await api.kingdomFavorite(id));
      toast(bean.favorited ? "已取消收藏" : "已收藏");
    } catch (e) {
      oops(e.message);
    }
  };

  return (
    <>
      <header>
        <button onClick={onBack} className="mb-1.5 text-sm text-muted hover:text-amber">
          ‹ 回王国
        </button>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h1 className="serif m-0 truncate text-2xl font-semibold md:text-3xl">{bean.name}</h1>
            <p className="mt-2 mb-0 text-muted">
              {[bean.origin, bean.varietal, bean.process, bean.roast, bean.altitude]
                .filter(Boolean)
                .join(" · ") || "还没填产地"}
            </p>
            {bean.producer || bean.note ? (
              <p className="mt-1 mb-0 text-[13px] text-muted">
                {[bean.producer, bean.note].filter(Boolean).join(" · ")}
              </p>
            ) : null}
          </div>
          <Btn variant={bean.favorited ? "solid" : "ghost"} onClick={fav}>
            {bean.favorited ? "已收藏" : "收藏"}
          </Btn>
        </div>
        <p className="mt-2 mb-0 text-[13px] text-muted">
          {bean.cups} 人杯测 · {bean.favorites} 人收藏
          {bean.avg?.overall != null ? ` · 总体均分 ${bean.avg.overall}` : ""}
        </p>
      </header>

      <div className="mt-6 grid gap-4 lg:grid-cols-2">
        <Panel>
          <div className="serif text-lg">照片</div>
          {bean.photos?.length ? (
            <div className="mt-3 grid grid-cols-2 gap-2">
              {bean.photos.map((p) => (
                <img key={p.id} src={p.thumb || p.url} alt="" className="h-40 w-full rounded-xl object-cover" />
              ))}
            </div>
          ) : (
            <p className="mt-3 mb-0 text-sm text-muted">还没有照片。</p>
          )}
          {bean.cards?.length > 0 && onOpenPlaza && (
            <div className="mt-4">
              <div className="text-[13px] text-muted">
                广场上挂过来的卡（各人自己的袋子，进价库存仍只主人看得见）
              </div>
              {bean.cards.map((c) => (
                <button
                  key={c.id}
                  type="button"
                  className="mt-1 block text-sm text-amber underline"
                  onClick={() => onOpenPlaza(c.id)}
                >
                  {c.name}
                </button>
              ))}
            </div>
          )}
        </Panel>
        <Panel>
          <div className="serif text-lg">大家的平均</div>
          <Radar scores={bean.avg} />
        </Panel>
      </div>

      <ScoreForm bean={bean} onDone={setBean} toast={toast} oops={oops} />

      <Panel className="mt-5">
        <div className="serif text-lg">杯测与评价</div>
        {bean.scores?.length ? (
          <div className="mt-4 space-y-4">
            {bean.scores.map((s, i) => (
              <div key={i} className="border-b border-line pb-4 last:border-0 last:pb-0">
                <div className="flex flex-wrap items-baseline justify-between gap-2">
                  <span className="text-cream">{s.author}</span>
                  <span className="text-sm text-amber">
                    {s.overall != null ? `总体 ${s.overall}` : "没打总体"}
                  </span>
                </div>
                <div className="mt-1 text-[13px] text-muted">
                  {DIMS.filter(([k]) => k !== "overall" && s[k] != null)
                    .map(([k, label]) => `${label} ${s[k]}`)
                    .join(" · ")}
                </div>
                {s.comment ? (
                  <p className="serif mt-2 mb-0 text-[15px] leading-relaxed">{s.comment}</p>
                ) : null}
                {s.photos?.length ? (
                  <div className="mt-3 grid grid-cols-3 gap-2">
                    {s.photos.map((p) => (
                      <img
                        key={p.id}
                        src={p.thumb || p.url}
                        alt=""
                        className="h-24 w-full rounded-lg object-cover"
                      />
                    ))}
                  </div>
                ) : null}
              </div>
            ))}
          </div>
        ) : (
          <p className="mt-3 mb-0 text-sm text-muted">还没人评。下面打一份就是第一条。</p>
        )}
      </Panel>
    </>
  );
}

function ScoreForm({ bean, onDone, toast, oops }) {
  const mine = bean.mine || {};
  const [form, setForm] = useState(blank(mine));
  const [busy, setBusy] = useState(false);
  const [pending, setPending] = useState([]);

  useEffect(() => {
    setForm(blank(bean.mine || {}));
    setPending([]);
  }, [bean.id, bean.mine?.at]);

  const save = async () => {
    setBusy(true);
    try {
      const payload = { comment: form.comment };
      for (const [k] of DIMS) payload[k] = form[k] === "" ? null : Number(form[k]);
      let next = await api.kingdomScore(bean.id, payload);
      for (const f of pending) {
        next = await api.addKingdomScorePhoto(bean.id, f);
      }
      setPending([]);
      onDone(next);
      toast(pending.length ? "杯测和照片都记下了" : "杯测已记下。再改会覆盖你上次的");
    } catch (e) {
      oops(e.message);
    } finally {
      setBusy(false);
    }
  };

  const drop = async () => {
    if (!window.confirm("撤回你在这支豆上的杯测？")) return;
    setBusy(true);
    try {
      onDone(await api.kingdomUnscore(bean.id));
      toast("已撤回");
    } catch (e) {
      oops(e.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Panel className="mt-5">
      <div className="serif text-lg">{bean.mine ? "改我的杯测" : "我也评一杯"}</div>
      <p className="mt-1 mb-0 text-[13px] text-muted">一人一豆一条，可改。分 1–10，可空；至少打一个分或写一句。</p>
      <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
        {DIMS.map(([k, label]) => (
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
        <Field label="一句话评价">
          <Input
            value={form.comment}
            onChange={(e) => setForm({ ...form, comment: e.target.value })}
            placeholder="明亮的柠檬、尾段有可可…"
          />
        </Field>
      </div>
      <div className="mt-4">
        <div className="text-[13px] text-muted">杯测照片</div>
        <p className="mt-1 mb-0 text-xs text-muted">豆干、粉床、成品都行。一杯最多 8 张。先记下杯测也能再补。</p>
        <label className="mt-2 inline-flex cursor-pointer items-center gap-1.5 rounded-full border border-line px-3.5 py-1.5 text-sm hover:border-amber">
          <Plus className="h-3.5 w-3.5" />
          {busy ? "上传中…" : "传照片"}
          <input
            type="file"
            accept="image/*,.heic,.heif"
            multiple
            className="hidden"
            onChange={async (e) => {
              const files = [...(e.target.files || [])];
              e.target.value = "";
              if (!files.length) return;
              if (!bean.mine) {
                setPending((cur) => [...cur, ...files].slice(0, 8));
                return;
              }
              setBusy(true);
              try {
                let next = bean;
                for (const f of files) next = await api.addKingdomScorePhoto(bean.id, f);
                onDone(next);
                toast(files.length > 1 ? `加了 ${files.length} 张` : "照片挂上了");
              } catch (err) {
                oops(err.message);
              } finally {
                setBusy(false);
              }
            }}
          />
        </label>
        {(bean.mine?.photos?.length || pending.length) > 0 && (
          <div className="mt-3 grid grid-cols-3 gap-2">
            {(bean.mine?.photos || []).map((p) => (
              <figure key={p.id} className="group relative m-0">
                <img src={p.thumb || p.url} alt="" className="h-24 w-full rounded-lg object-cover" />
                <button
                  type="button"
                  className="absolute top-1.5 right-1.5 hidden rounded-full bg-black/60 px-2 py-0.5 text-xs text-cream group-hover:block"
                  onClick={async () => {
                    try {
                      onDone(await api.delKingdomScorePhoto(p.id));
                      toast("删掉了");
                    } catch (err) {
                      oops(err.message);
                    }
                  }}
                >
                  删
                </button>
              </figure>
            ))}
            {pending.map((f, i) => (
              <div
                key={`${f.name}-${i}`}
                className="flex h-24 items-center justify-center rounded-lg border border-dashed border-line text-xs text-muted"
              >
                待上传 {i + 1}
              </div>
            ))}
          </div>
        )}
      </div>
      <div className="mt-4 flex flex-wrap gap-2">
        <Btn onClick={save} disabled={busy}>
          {bean.mine ? "改好了" : "记下"}
        </Btn>
        {bean.mine && (
          <Btn variant="ghost" onClick={drop} disabled={busy}>
            撤回我的
          </Btn>
        )}
      </div>
    </Panel>
  );
}

function blank(mine) {
  const out = { comment: mine.comment || "" };
  for (const [k] of DIMS) out[k] = mine[k] == null ? "" : mine[k];
  return out;
}
