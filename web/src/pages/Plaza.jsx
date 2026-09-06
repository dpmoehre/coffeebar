// 别人公开的豆卡。看得见产地、照片、杯测和落点，看不见钱和库存。
import { useEffect, useMemo, useState } from "react";

import { api } from "../api.js";
import Radar from "../components/Radar.jsx";
import { Chip, Empty, Input, Panel } from "../ui.jsx";

export default function Plaza({ openId, onOpen, onBack, onOpenMine, toast, oops }) {
  if (openId) {
    return <PublicCard id={openId} onBack={onBack} onOpenMine={onOpenMine} oops={oops} />;
  }
  return <PlazaList onOpen={onOpen} oops={oops} />;
}

function PlazaList({ onOpen, oops }) {
  const [beans, setBeans] = useState(null);
  const [certifiedOnly, setCertifiedOnly] = useState(false);
  const [q, setQ] = useState("");

  const load = () =>
    api
      .publicBeans(certifiedOnly)
      .then((d) => setBeans(d.beans))
      .catch((e) => oops(e.message));

  useEffect(() => {
    setBeans(null);
    load();
  }, [certifiedOnly]);

  const shown = useMemo(() => {
    const list = [...(beans || [])];
    const needle = q.trim().toLowerCase();
    if (!needle) return list;
    return list.filter((b) =>
      [b.name, b.origin, b.varietal, b.producer, ...(b.tags || [])]
        .filter(Boolean)
        .some((x) => String(x).toLowerCase().includes(needle)),
    );
  }, [beans, q]);

  return (
    <>
      <header>
        <h1 className="serif m-0 text-3xl font-semibold">广场</h1>
        <p className="mt-2 mb-0 text-muted">
          别人公开的豆卡。认证过的是管理员对过产地和地图钉；没认证也能公开，不想看就筛掉。
        </p>
      </header>

      <div className="mt-5 flex flex-wrap items-center gap-2">
        <Chip on={certifiedOnly} onClick={() => setCertifiedOnly((v) => !v)}>
          不看未认证
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
                  {b.tags?.length > 0 && (
                    <div className="mt-3 flex flex-wrap gap-1.5">
                      {b.tags.slice(0, 4).map((t) => (
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
            ))}
          </div>
          {shown.length === 0 && (
            <Empty>
              {certifiedOnly || q.trim()
                ? "没有对得上的公开豆卡。"
                : "还没有人把豆卡公开。自己的卡在豆库里打开，选「公开」。"}
            </Empty>
          )}
        </>
      )}
    </>
  );
}

function PublicCard({ id, onBack, onOpenMine, oops }) {
  const [bean, setBean] = useState(null);

  useEffect(() => {
    setBean(null);
    api
      .publicBean(id)
      .then(setBean)
      .catch((e) => oops(e.message));
  }, [id, oops]);

  if (!bean) return <p className="text-muted">读取中…</p>;

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
            className="mt-2 text-sm text-amber underline"
            onClick={() => onOpenMine(bean.id)}
          >
            这是你的卡，去豆库改
          </button>
        )}
      </header>

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
          <div className="serif text-lg">杯测</div>
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
