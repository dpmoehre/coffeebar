// 别人公开的豆卡。看得见产地、照片、杯测、买袋价和袋上克重，看不见还剩多少。
import { useEffect, useMemo, useState } from "react";

import { api } from "../api.js";
import Radar from "../components/Radar.jsx";
import { Btn, Chip, Empty, Input, Panel, g, money } from "../ui.jsx";

function offerLine(offer) {
  if (!offer) return "";
  return [offer.nominal_g != null ? g(offer.nominal_g) : null, offer.price != null ? money(offer.price) : null]
    .filter(Boolean)
    .join(" · ");
}

export default function Plaza({
  openId,
  onOpen,
  onBack,
  onOpenMine,
  onOpenKingdom,
  admin,
  toast,
  oops,
}) {
  if (openId) {
    return (
      <PublicCard
        id={openId}
        onBack={onBack}
        onOpenMine={onOpenMine}
        onOpenKingdom={onOpenKingdom}
        admin={admin}
        toast={toast}
        oops={oops}
      />
    );
  }
  return <PlazaList onOpen={onOpen} oops={oops} />;
}

const ROAST_ORDER = ["浅烘", "中浅烘", "中浅", "中烘", "中深烘", "深烘"];

function sortRoasts(values) {
  return [...values].sort((a, b) => {
    const ia = ROAST_ORDER.indexOf(a);
    const ib = ROAST_ORDER.indexOf(b);
    if (ia === -1 && ib === -1) return a.localeCompare(b, "zh");
    if (ia === -1) return 1;
    if (ib === -1) return -1;
    return ia - ib;
  });
}

function toggleItem(list, value) {
  return list.includes(value) ? list.filter((x) => x !== value) : [...list, value];
}

function matchesPlaza(card, { q, roast, process, tags, inKingdom }) {
  if (roast.length && !roast.some((r) => (card.roast || "").toLowerCase() === r.toLowerCase())) {
    return false;
  }
  if (process.length && !process.some((p) => (card.process || "").toLowerCase() === p.toLowerCase())) {
    return false;
  }
  if (tags.length) {
    const have = (card.tags || []).map((t) => t.toLowerCase());
    if (!tags.every((t) => have.includes(t.toLowerCase()))) return false;
  }
  const needle = q.trim().toLowerCase();
  if (needle) {
    const hay = [card.name, card.origin, card.varietal, card.producer, ...(card.tags || [])].filter(
      Boolean,
    );
    if (!hay.some((x) => String(x).toLowerCase().includes(needle))) return false;
  }
  if (inKingdom && !card.kingdom_id) return false;
  return true;
}

function PlazaList({ onOpen, oops }) {
  const [beans, setBeans] = useState(null);
  const [certifiedOnly, setCertifiedOnly] = useState(false);
  const [inKingdom, setInKingdom] = useState(false);
  const [q, setQ] = useState("");
  const [roast, setRoast] = useState([]);
  const [process, setProcess] = useState([]);
  const [tags, setTags] = useState([]);

  const load = () =>
    api
      .publicBeans(certifiedOnly)
      .then((d) => setBeans(d.beans))
      .catch((e) => oops(e.message));

  useEffect(() => {
    setBeans(null);
    load();
  }, [certifiedOnly]);

  const facets = useMemo(() => {
    const roastSet = new Set();
    const processSet = new Set();
    const tagSet = new Set();
    (beans || []).forEach((b) => {
      if (b.roast) roastSet.add(b.roast);
      if (b.process) processSet.add(b.process);
      (b.tags || []).forEach((t) => tagSet.add(t));
    });
    return {
      roast: sortRoasts([...roastSet]),
      process: [...processSet].sort((a, b) => a.localeCompare(b, "zh")),
      tags: [...tagSet].sort((a, b) => a.localeCompare(b, "zh")),
    };
  }, [beans]);

  const shown = useMemo(
    () => (beans || []).filter((b) => matchesPlaza(b, { q, roast, process, tags, inKingdom })),
    [beans, q, roast, process, tags, inKingdom],
  );

  const filtered = roast.length || process.length || tags.length || q.trim() || inKingdom;
  const clearFilters = () => {
    setQ("");
    setRoast([]);
    setProcess([]);
    setTags([]);
    setInKingdom(false);
  };

  return (
    <>
      <header>
        <h1 className="serif m-0 text-3xl font-semibold">广场</h1>
        <p className="mt-2 mb-0 text-muted">
          {beans
            ? `${shown.length} 张公开卡。认证过的是管理员对过产地和地图钉。收进王国之后，这里能跳过去看大家的杯测。`
            : "别人公开的豆卡。认证过的是管理员对过产地和地图钉。收进王国之后，这里能跳过去看大家的杯测。"}
        </p>
      </header>

      <div className="mt-5 flex flex-wrap items-center gap-2">
        <Chip on={certifiedOnly} onClick={() => setCertifiedOnly((v) => !v)}>
          不看未认证
        </Chip>
        <Chip on={inKingdom} onClick={() => setInKingdom((v) => !v)}>
          已进王国
        </Chip>
        <Input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="搜名字、产地…"
          className="w-44 py-1.5 text-sm"
        />
        {filtered ? (
          <button type="button" className="text-sm text-amber underline" onClick={clearFilters}>
            清除筛选
          </button>
        ) : null}
      </div>

      <FilterRow
        label="烘焙"
        items={facets.roast}
        picked={roast}
        onToggle={(v) => setRoast((cur) => toggleItem(cur, v))}
      />
      <FilterRow
        label="处理"
        items={facets.process}
        picked={process}
        onToggle={(v) => setProcess((cur) => toggleItem(cur, v))}
      />
      <FilterRow
        label="标签"
        items={facets.tags}
        picked={tags}
        onToggle={(v) => setTags((cur) => toggleItem(cur, v))}
      />

      {!beans ? (
        <p className="mt-6 text-muted">读取中…</p>
      ) : (
        <>
          <div className="mt-6 grid gap-4 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4">
            {shown.map((b) => (
              <article
                key={b.id}
                onClick={() => onOpen(b.id)}
                className="rise cursor-pointer overflow-hidden rounded-2xl border border-line
                  bg-panel transition hover:border-amber"
              >
                {b.cover ? (
                  <img src={b.cover.thumb || b.cover.url} alt="" className="h-48 w-full object-cover" />
                ) : (
                  <div
                    className="h-48"
                    style={{
                      background:
                        "radial-gradient(circle at 30% 40%, #5a3d28, transparent 42%), linear-gradient(135deg, #3a2618, #1a120e)",
                    }}
                  />
                )}
                <div className="p-5">
                  <div className="flex items-baseline justify-between gap-2">
                    <div className="serif truncate text-lg">{b.name}</div>
                    <Badge certified={b.certified} />
                  </div>
                  <div className="mt-1 truncate text-[13px] text-muted">
                    {[b.origin, b.varietal, b.roast].filter(Boolean).join(" · ") || "还没填产地"}
                  </div>
                  {offerLine(b.offer) ? (
                    <div className="mt-2 text-sm text-amber">{offerLine(b.offer)}</div>
                  ) : null}
                  {b.kingdom ? (
                    <div className="mt-3 text-sm text-amber">
                      王国
                      {b.kingdom.avg?.overall != null ? ` · 总体 ${b.kingdom.avg.overall}` : " · 还没人评"}
                      <span className="ml-2 text-xs text-muted">{b.kingdom.cups} 杯测</span>
                    </div>
                  ) : null}
                  {b.tags?.length > 0 && (
                    <div className="mt-3 flex flex-wrap gap-1.5">
                      {b.tags.slice(0, 4).map((t) => (
                        <b
                          key={t}
                          onClick={(e) => {
                            e.stopPropagation();
                            setTags((cur) => toggleItem(cur, t));
                          }}
                          className={`rounded-full border px-2 py-0.5 text-xs font-normal ${
                            tags.includes(t)
                              ? "border-amber bg-amber text-[#1a120a]"
                              : "border-line text-muted"
                          }`}
                        >
                          {t}
                        </b>
                      ))}
                    </div>
                  )}
                </div>
              </article>
            ))}
          </div>
          {shown.length === 0 && (
            <Empty>
              {certifiedOnly || filtered
                ? "没有对得上的公开豆卡。少点几个芯片，或点「清除筛选」。"
                : "还没有人把豆卡公开。自己的卡在豆库里打开，选「公开」。"}
            </Empty>
          )}
        </>
      )}
    </>
  );
}

function FilterRow({ label, items, picked, onToggle }) {
  if (!items.length) return null;
  return (
    <div className="mt-3 flex flex-wrap items-center gap-2">
      <span className="text-xs text-muted">{label}</span>
      {items.map((item) => (
        <Chip key={item} on={picked.includes(item)} onClick={() => onToggle(item)}>
          {item}
        </Chip>
      ))}
    </div>
  );
}

function PublicCard({ id, onBack, onOpenMine, onOpenKingdom, admin, toast, oops }) {
  const [bean, setBean] = useState(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    setBean(null);
    api
      .publicBean(id)
      .then(setBean)
      .catch((e) => oops(e.message));
  }, [id, oops]);

  if (!bean) return <p className="text-muted">读取中…</p>;

  const collect = async () => {
    setBusy(true);
    try {
      const card = await api.adminCollectKingdom(bean.id, { name: bean.name });
      toast("已收进王国，大家可以一起评了");
      if (onOpenKingdom) onOpenKingdom(card.id);
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
          ‹ 回广场
        </button>
        <div className="flex flex-wrap items-baseline gap-3">
          <h1 className="serif m-0 truncate text-3xl font-semibold">{bean.name}</h1>
          <Badge certified={bean.certified} />
        </div>
        <p className="mt-2 mb-0 text-muted">
          {[bean.origin, bean.varietal, bean.process, bean.roast, bean.altitude].filter(Boolean).join(" · ") ||
            "还没填产地"}
        </p>
        {offerLine(bean.offer) ? (
          <p className="mt-1 mb-0 text-sm text-amber">
            最近一袋 {offerLine(bean.offer)}
            <span className="ml-2 text-xs text-muted">袋上的买价和克重，不是还剩多少</span>
          </p>
        ) : (
          <p className="mt-1 mb-0 text-[13px] text-muted">还没填这袋多少钱、袋上克重。</p>
        )}
        {(bean.producer || bean.note) && (
          <p className="mt-1 mb-0 text-[13px] text-muted">
            {[bean.producer, bean.note].filter(Boolean).join(" · ")}
          </p>
        )}
        {bean.places?.length > 0 && (
          <p className="mt-1 mb-0 text-[13px] text-muted">
            地图上：{bean.places.map((p) => p.label).join("、")}
          </p>
        )}
        {bean.mine && onOpenMine && (
          <button
            type="button"
            className="mt-2 mr-4 text-sm text-amber underline"
            onClick={() => onOpenMine(bean.id)}
          >
            这是你的卡，去豆库改
          </button>
        )}
      </header>

      {bean.kingdom && onOpenKingdom ? (
        <Panel className="mt-5">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <div className="serif text-lg">王国里的同一支</div>
              <p className="mt-1 mb-0 text-sm text-muted">
                {bean.kingdom.name}
                {bean.kingdom.avg?.overall != null ? ` · 大家总体 ${bean.kingdom.avg.overall}` : " · 还没人评"}
                <span className="ml-2 text-xs">
                  {bean.kingdom.cups} 杯测 · {bean.kingdom.favorites} 收藏
                </span>
              </p>
            </div>
            <Btn onClick={() => onOpenKingdom(bean.kingdom.id)}>去杯测</Btn>
          </div>
        </Panel>
      ) : admin ? (
        <Panel className="mt-5">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <div className="serif text-lg">还没进王国</div>
              <p className="mt-1 mb-0 text-sm text-muted">收进去之后，大家就评同一支，不评这张私卡。</p>
            </div>
            <Btn onClick={collect} disabled={busy}>
              收入王国
            </Btn>
          </div>
        </Panel>
      ) : (
        <p className="mt-4 mb-0 text-[13px] text-muted">这张卡还没被收进王国。收进去之后才能和大家一起评。</p>
      )}

      <div className="mt-6 grid gap-4 lg:grid-cols-2">
        <Panel>
          <div className="serif text-lg">照片</div>
          {bean.photos?.length ? (
            <div className="mt-3 grid grid-cols-2 gap-2">
              {bean.photos.map((p) => (
                <img
                  key={p.id}
                  src={p.thumb || p.url}
                  alt=""
                  className="h-40 w-full rounded-xl object-cover"
                />
              ))}
            </div>
          ) : (
            <p className="mt-3 mb-0 text-sm text-muted">还没有包装或豆盘照片。</p>
          )}
          {bean.tags?.length > 0 && (
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
          <div className="serif text-lg">这张卡主人的杯测</div>
          <p className="mt-1 mb-0 text-[13px] text-muted">只代表这袋的主人，不是王国里大家的分。</p>
          <Radar scores={bean.scores} />
          {bean.scores?.comment && (
            <p className="serif mt-3 mb-0 text-[15px] leading-relaxed text-cream">{bean.scores.comment}</p>
          )}
        </Panel>
      </div>
    </>
  );
}

function Badge({ certified }) {
  return certified ? (
    <span className="shrink-0 text-xs text-amber">已认证</span>
  ) : (
    <span className="shrink-0 text-xs text-muted">未认证</span>
  );
}
