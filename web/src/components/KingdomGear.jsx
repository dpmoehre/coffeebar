// 王国器具：目录里的同一件，大家打总体分、写一句、收藏。不是八维杯测。
import { useEffect, useMemo, useState } from "react";

import { api } from "../api.js";
import { recall, remember } from "../listCache.js";
import { Plus } from "../icons.jsx";
import { Btn, Chip, Cover, Empty, Field, Input, Panel, coverSrc } from "../ui.jsx";

export function KingdomGearList({ onOpen, oops }) {
  const [saved, setSaved] = useState(false);
  const [items, setItems] = useState(() => recall("kingdom-gear:false") ?? null);
  const [q, setQ] = useState("");

  const load = () =>
    api
      .kingdomGear(saved)
      .then((d) => {
        remember(`kingdom-gear:${saved}`, d.gear);
        setItems(d.gear);
      })
      .catch((e) => oops(e.message));

  useEffect(() => {
    const hit = recall(`kingdom-gear:${saved}`);
    setItems(hit === undefined ? null : hit);
    load();
  }, [saved]);

  const shown = useMemo(() => {
    const list = [...(items || [])];
    const needle = q.trim().toLowerCase();
    if (!needle) return list;
    return list.filter((g) =>
      [g.name, g.kind_label, g.family_label, g.brand, g.model, g.method_label]
        .filter(Boolean)
        .some((x) => String(x).toLowerCase().includes(needle)),
    );
  }, [items, q]);

  return (
    <>
      <div className="mt-5 flex flex-wrap items-center gap-2">
        <Chip on={saved} onClick={() => setSaved((v) => !v)}>
          只看收藏
        </Chip>
        <Input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="搜名字、型号…"
          className="w-44 py-1.5 text-sm"
        />
      </div>
      {!items ? (
        <p className="mt-6 text-muted">读取中…</p>
      ) : (
        <>
          <div className="mt-6 grid gap-4 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4">
            {shown.map((g, i) => (
              <article
                key={g.id}
                onClick={() => onOpen(g.id)}
                className="rise cursor-pointer overflow-hidden rounded-2xl border border-line
                  bg-panel transition hover:border-amber"
                style={{ animationDelay: `${Math.min(i, 12) * 45}ms` }}
              >
                <Cover src={coverSrc(g.cover)} className="h-40 w-full" />
                <div className="p-5">
                  <div className="flex items-baseline justify-between gap-2">
                    <div className="serif truncate text-lg">{g.name}</div>
                    {g.favorited ? <span className="shrink-0 text-xs text-amber">已收藏</span> : null}
                  </div>
                  <div className="mt-1 truncate text-[13px] text-muted">
                    {[g.kind_label, g.family_label, g.brand, g.model].filter(Boolean).join(" · ") ||
                      "还没填型号"}
                  </div>
                  <div className="mt-3 text-sm text-amber">
                    {g.avg?.overall != null ? `总体 ${g.avg.overall}` : "还没人评"}
                    <span className="ml-2 text-xs text-muted">
                      {g.reviews} 评价 · {g.favorites} 收藏
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
                : "王国还没有器具。管理员在后台「收器具」之后，大家就能一起评。"}
            </Empty>
          )}
        </>
      )}
    </>
  );
}

export function KingdomGearCard({ id, onBack, onOpenPlaza, onOpenMineGear, toast, oops }) {
  const [item, setItem] = useState(null);
  const [busy, setBusy] = useState(false);

  const load = () =>
    api
      .kingdomGearItem(id)
      .then(setItem)
      .catch((e) => oops(e.message));

  useEffect(() => {
    setItem(null);
    load();
  }, [id]);

  if (!item) return <p className="text-muted">读取中…</p>;

  const fav = async () => {
    try {
      setItem(await api.kingdomGearFavorite(id));
      toast(item.favorited ? "已取消收藏" : "已收藏");
    } catch (e) {
      oops(e.message);
    }
  };

  const claim = async () => {
    setBusy(true);
    try {
      const mine = await api.gearFromCatalog(id);
      toast("已领到你的台面");
      setItem(await api.kingdomGearItem(id));
      if (onOpenMineGear) onOpenMineGear(mine.id);
    } catch (e) {
      oops(e.message);
    } finally {
      setBusy(false);
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
            <h1 className="serif m-0 truncate text-2xl font-semibold md:text-3xl">{item.name}</h1>
            <p className="mt-2 mb-0 text-muted">
              {[item.kind_label, item.family_label, item.brand, item.model, item.method_label]
                .filter(Boolean)
                .join(" · ") || "还没填型号"}
            </p>
            {item.note ? <p className="mt-1 mb-0 text-[13px] text-muted">{item.note}</p> : null}
          </div>
          <div className="flex flex-wrap gap-2">
            <Btn variant={item.favorited ? "solid" : "ghost"} onClick={fav}>
              {item.favorited ? "已收藏" : "收藏"}
            </Btn>
            {item.mine_gear_id && onOpenMineGear ? (
              <Btn variant="ghost" onClick={() => onOpenMineGear(item.mine_gear_id)}>
                已在台面
              </Btn>
            ) : (
              <Btn variant="ghost" onClick={claim} disabled={busy}>
                领到台面
              </Btn>
            )}
          </div>
        </div>
        <p className="mt-2 mb-0 text-[13px] text-muted">
          {item.reviews} 人评价 · {item.favorites} 人收藏
          {item.avg?.overall != null ? ` · 总体均分 ${item.avg.overall}` : ""}
        </p>
      </header>

      <Panel className="mt-6">
        <div className="serif text-lg">照片</div>
        {item.photos?.length ? (
          <div className="mt-3 grid grid-cols-2 gap-2">
            {item.photos.map((p) => (
              <img key={p.id} src={p.thumb || p.url} alt="" className="h-40 w-full rounded-xl object-cover" />
            ))}
          </div>
        ) : (
          <p className="mt-3 mb-0 text-sm text-muted">还没有照片。</p>
        )}
        {item.plaza?.length > 0 && onOpenPlaza && (
          <div className="mt-4">
            <div className="text-[13px] text-muted">广场上挂过来的件</div>
            {item.plaza.map((c) => (
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

      <GearScoreForm item={item} onDone={setItem} toast={toast} oops={oops} />

      <Panel className="mt-5">
        <div className="serif text-lg">评价</div>
        {item.scores?.length ? (
          <div className="mt-4 space-y-4">
            {item.scores.map((s) => (
              <div key={s.id} className="border-b border-line pb-4 last:border-0 last:pb-0">
                <div className="flex flex-wrap items-baseline justify-between gap-2">
                  <span className="text-cream">{s.author}</span>
                  <span className="text-sm text-amber">
                    {s.overall != null ? `总体 ${s.overall}` : "没打分"}
                  </span>
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
          <p className="mt-3 mb-0 text-sm text-muted">还没人评。下面写一句就是第一条。</p>
        )}
      </Panel>
    </>
  );
}

function GearScoreForm({ item, onDone, toast, oops }) {
  const mine = item.mine || {};
  const [form, setForm] = useState({
    overall: mine.overall == null ? "" : mine.overall,
    comment: mine.comment || "",
  });
  const [busy, setBusy] = useState(false);
  const [pending, setPending] = useState([]);

  useEffect(() => {
    setForm({
      overall: item.mine?.overall == null ? "" : item.mine.overall,
      comment: item.mine?.comment || "",
    });
    setPending([]);
  }, [item.id, item.mine?.at]);

  const save = async () => {
    setBusy(true);
    try {
      const payload = {
        comment: form.comment,
        overall: form.overall === "" ? null : Number(form.overall),
      };
      let next = await api.kingdomGearScore(item.id, payload);
      for (const f of pending) {
        next = await api.addKingdomGearScorePhoto(item.id, f);
      }
      setPending([]);
      onDone(next);
      toast(pending.length ? "评价和照片都记下了" : "评价已记下。再改会覆盖你上次的");
    } catch (e) {
      oops(e.message);
    } finally {
      setBusy(false);
    }
  };

  const drop = async () => {
    if (!window.confirm("撤回你在这件器具上的评价？")) return;
    setBusy(true);
    try {
      onDone(await api.kingdomGearUnscore(item.id));
      toast("已撤回");
    } catch (e) {
      oops(e.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Panel className="mt-5">
      <div className="serif text-lg">{item.mine ? "改我的评价" : "我也评一句"}</div>
      <p className="mt-1 mb-0 text-[13px] text-muted">
        一人一件一条，可改。器具只打总体 1–10，不要套豆子的八维。
      </p>
      <div className="mt-4 max-w-40">
        <Field label="总体">
          <Input
            type="number"
            min="1"
            max="10"
            step="0.5"
            value={form.overall}
            onChange={(e) => setForm({ ...form, overall: e.target.value })}
          />
        </Field>
      </div>
      <div className="mt-3">
        <Field label="一句话">
          <Input
            value={form.comment}
            onChange={(e) => setForm({ ...form, comment: e.target.value })}
            placeholder="水流稳、好闷蒸…"
          />
        </Field>
      </div>
      <div className="mt-4">
        <div className="text-[13px] text-muted">照片</div>
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
              if (!item.mine) {
                setPending((cur) => [...cur, ...files].slice(0, 8));
                return;
              }
              setBusy(true);
              try {
                let next = item;
                for (const f of files) next = await api.addKingdomGearScorePhoto(item.id, f);
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
        {(item.mine?.photos?.length || pending.length) > 0 && (
          <div className="mt-3 grid grid-cols-3 gap-2">
            {(item.mine?.photos || []).map((p) => (
              <figure key={p.id} className="group relative m-0">
                <img src={p.thumb || p.url} alt="" className="h-24 w-full rounded-lg object-cover" />
                <button
                  type="button"
                  className="absolute top-1.5 right-1.5 hidden rounded-full bg-black/60 px-2 py-0.5 text-xs text-cream group-hover:block"
                  onClick={async () => {
                    try {
                      onDone(await api.delKingdomGearScorePhoto(p.id));
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
          {item.mine ? "改好了" : "记下"}
        </Btn>
        {item.mine && (
          <Btn variant="ghost" onClick={drop} disabled={busy}>
            撤回我的
          </Btn>
        )}
      </div>
    </Panel>
  );
}
