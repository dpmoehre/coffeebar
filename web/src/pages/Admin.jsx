// 管理员看所有人的私库。普通人侧栏不会出现这一页。
import { useEffect, useState } from "react";

import { api } from "../api.js";
import Radar from "../components/Radar.jsx";
import { Btn, Chip, Empty, Panel, g, ml, money } from "../ui.jsx";

function clock(at) {
  return at ? at.slice(0, 16).replace("T", " ") : "";
}

export default function Admin({ toast, oops }) {
  const [view, setView] = useState("accounts");
  const [accounts, setAccounts] = useState(null);
  const [picked, setPicked] = useState(null);
  const [dossier, setDossier] = useState(null);
  const [tab, setTab] = useState("beans");
  const [detail, setDetail] = useState(null);
  const [q, setQ] = useState("");

  const loadList = () =>
    api
      .adminAccounts()
      .then((d) => setAccounts(d.accounts))
      .catch((e) => oops(e.message));

  useEffect(() => {
    loadList();
  }, []);

  const openAccount = (id) => {
    setPicked(id);
    setDossier(null);
    setDetail(null);
    setTab("beans");
    api
      .adminAccount(id)
      .then(setDossier)
      .catch((e) => oops(e.message));
  };

  const openBean = async (beanId) => {
    try {
      setDetail(await api.adminBean(picked, beanId));
    } catch (e) {
      oops(e.message);
    }
  };

  const openSpirit = async (bottleId) => {
    try {
      setDetail(await api.adminSpirit(picked, bottleId));
    } catch (e) {
      oops(e.message);
    }
  };

  const patchStatus = async (status) => {
    try {
      await api.adminSetStatus(picked, status);
      toast(status === "disabled" ? "已停用，对方会被踢出" : "已重新启用");
      loadList();
      openAccount(picked);
    } catch (e) {
      oops(e.message);
    }
  };

  const kick = async () => {
    try {
      await api.adminKick(picked);
      toast("已踢下线，对方刷新要重新登录");
    } catch (e) {
      oops(e.message);
    }
  };

  const shown = (accounts || []).filter((a) => {
    const needle = q.trim().toLowerCase();
    if (!needle) return true;
    return String(a.email || "").toLowerCase().includes(needle);
  });

  return (
    <>
      <header>
        <h1 className="serif m-0 text-3xl font-semibold">后台</h1>
        <p className="mt-2 mb-0 text-muted">
          只有管理员看得见。能看每个人的豆卡、酒卡和消耗，也能审公开豆卡。普通人仍然只能看自己的。
        </p>
        <div className="mt-4 flex flex-wrap gap-2">
          <Chip on={view === "accounts"} onClick={() => setView("accounts")}>
            账号
          </Chip>
          <Chip on={view === "review"} onClick={() => setView("review")}>
            审豆卡
          </Chip>
        </div>
      </header>

      {view === "review" ? (
        <ReviewPane toast={toast} oops={oops} />
      ) : !accounts ? (
        <p className="mt-6 text-muted">读取中…</p>
      ) : (
        <div className="mt-6 grid gap-6 lg:grid-cols-[minmax(0,280px)_minmax(0,1fr)]">
          <Panel className="h-fit">
            <input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="搜邮箱…"
              className="w-full rounded-lg border border-line bg-bg px-3 py-2 text-sm text-cream
                outline-none focus:border-amber"
            />
            <div className="mt-3 space-y-1">
              {shown.map((a) => (
                <button
                  key={a.id}
                  type="button"
                  onClick={() => openAccount(a.id)}
                  className={`flex w-full flex-col rounded-xl px-3 py-2.5 text-left text-sm ${
                    picked === a.id ? "bg-chip text-cream" : "text-muted hover:bg-chip/60"
                  }`}
                >
                  <span className="truncate text-cream">
                    {a.email}
                    {a.admin ? <span className="ml-2 text-xs text-amber">管理员</span> : null}
                    {a.status !== "active" ? (
                      <span className="ml-2 text-xs text-warn">已停用</span>
                    ) : null}
                  </span>
                  <span className="mt-0.5 text-xs">
                    豆 {a.beans} · 酒 {a.spirits} · 花掉 {money(a.spent)}
                  </span>
                </button>
              ))}
              {shown.length === 0 && <p className="text-sm text-muted">没有对得上的账号。</p>}
            </div>
          </Panel>

          <div>
            {!dossier ? (
              <Empty>左边点一个账号，看他的豆、酒和流水。</Empty>
            ) : (
              <AccountView
                dossier={dossier}
                tab={tab}
                setTab={setTab}
                detail={detail}
                setDetail={setDetail}
                openBean={openBean}
                openSpirit={openSpirit}
                patchStatus={patchStatus}
                kick={kick}
              />
            )}
          </div>
        </div>
      )}
    </>
  );
}

function AccountView({
  dossier,
  tab,
  setTab,
  detail,
  setDetail,
  openBean,
  openSpirit,
  patchStatus,
  kick,
}) {
  const a = dossier.account;
  const s = dossier.summary || {};
  return (
    <>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="serif m-0 text-2xl">{a.email}</h2>
          <p className="mt-1 mb-0 text-sm text-muted">
            {a.admin ? "管理员 · " : ""}
            {a.status === "active" ? "使用中" : "已停用"}
            {a.created_at ? ` · 注册 ${clock(a.created_at)}` : ""}
          </p>
        </div>
        {!a.admin && (
          <div className="flex flex-wrap gap-2">
            <Btn variant="ghost" onClick={kick}>
              踢下线
            </Btn>
            {a.status === "active" ? (
              <Btn variant="danger" onClick={() => patchStatus("disabled")}>
                停用
              </Btn>
            ) : (
              <Btn onClick={() => patchStatus("active")}>启用</Btn>
            )}
          </div>
        )}
      </div>

      <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Stat label="喝掉的钱" value={money(s.spent)} />
        <Stat label="买进来" value={money(s.bought)} />
        <Stat label="咖啡杯" value={s.cups ?? 0} />
        <Stat label="酒杯" value={s.drink_cups ?? 0} />
      </div>

      <div className="mt-5 flex flex-wrap gap-2">
        {[
          ["beans", `豆子 ${dossier.beans.length}`],
          ["spirits", `酒水 ${dossier.spirits.length}`],
          ["log", `流水 ${dossier.consumption.length}`],
          ["people", `谁喝的 ${dossier.people.length}`],
        ].map(([k, label]) => (
          <Chip
            key={k}
            on={tab === k}
            onClick={() => {
              setTab(k);
              setDetail(null);
            }}
          >
            {label}
          </Chip>
        ))}
      </div>

      {tab === "beans" && (
        <Panel className="mt-4">
          {dossier.beans.length === 0 ? (
            <p className="m-0 text-muted">没有豆卡。</p>
          ) : (
            dossier.beans.map((b) => (
              <button
                key={b.id}
                type="button"
                onClick={() => openBean(b.id)}
                className="flex w-full items-center justify-between gap-3 border-b border-line py-3
                  text-left last:border-0 hover:opacity-80"
              >
                <span>
                  {b.name}
                  <span className="ml-2 text-xs text-muted">{b.origin || ""}</span>
                </span>
                <span className="text-sm text-amber">{g(b.balance_g)}</span>
              </button>
            ))
          )}
        </Panel>
      )}

      {tab === "spirits" && (
        <Panel className="mt-4">
          {dossier.spirits.length === 0 ? (
            <p className="m-0 text-muted">没有酒卡。</p>
          ) : (
            dossier.spirits.map((b) => (
              <button
                key={b.id}
                type="button"
                onClick={() => openSpirit(b.id)}
                className="flex w-full items-center justify-between gap-3 border-b border-line py-3
                  text-left last:border-0 hover:opacity-80"
              >
                <span>
                  {b.name}
                  <span className="ml-2 text-xs text-muted">{b.kind || ""}</span>
                </span>
                <span className="text-sm text-amber">{ml(b.balance_ml)}</span>
              </button>
            ))
          )}
        </Panel>
      )}

      {tab === "log" && (
        <Panel className="mt-4 overflow-x-auto">
          {dossier.consumption.length === 0 ? (
            <p className="m-0 text-muted">还没有流水。</p>
          ) : (
            <table className="w-full text-left text-sm">
              <thead className="text-xs text-muted">
                <tr>
                  <th className="pb-2 font-normal">时间</th>
                  <th className="pb-2 font-normal">什么</th>
                  <th className="pb-2 font-normal">谁</th>
                  <th className="pb-2 font-normal">量</th>
                  <th className="pb-2 font-normal">钱</th>
                </tr>
              </thead>
              <tbody>
                {dossier.consumption.map((c) => (
                  <tr key={c.id} className={c.voided_at ? "text-muted line-through" : ""}>
                    <td className="py-1.5 pr-3 whitespace-nowrap">{clock(c.at)}</td>
                    <td className="py-1.5 pr-3">{c.bean_name || c.spirit_name || "—"}</td>
                    <td className="py-1.5 pr-3">{c.person_name || "没记"}</td>
                    <td className="py-1.5 pr-3">
                      {c.kind === "drink" ? ml(c.amount_ml) : g(c.amount_g)}
                    </td>
                    <td className="py-1.5">{money(c.cost)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Panel>
      )}

      {tab === "people" && (
        <Panel className="mt-4">
          {dossier.people.length === 0 ? (
            <p className="m-0 text-muted">还没记过谁喝的。</p>
          ) : (
            dossier.people.map((p) => (
              <div key={p.id} className="border-b border-line py-2 last:border-0">
                {p.name}
                {!p.active ? <span className="ml-2 text-xs text-muted">停用</span> : null}
              </div>
            ))
          )}
        </Panel>
      )}

      {detail && (
        <Panel className="mt-4">
          <div className="flex items-start justify-between gap-3">
            <h3 className="serif m-0 text-xl">{detail.name}</h3>
            <button className="text-sm text-muted underline" onClick={() => setDetail(null)}>
              收起
            </button>
          </div>
          <p className="mt-2 mb-0 text-sm text-muted">
            {[detail.origin, detail.varietal, detail.roast, detail.kind, detail.flavor]
              .filter(Boolean)
              .join(" · ") || "没有更多字段"}
          </p>
          {detail.lots?.length > 0 && (
            <ul className="mt-3 mb-0 list-none p-0 text-sm">
              {detail.lots.map((l) => (
                <li key={l.id} className="text-muted">
                  {l.nominal_g != null
                    ? `第 ${l.seq || "?"} 袋 ${g(l.balance_g)} / 标称 ${g(l.nominal_g)}`
                    : `${ml(l.balance_ml)} / 标称 ${ml(l.nominal_ml)}`}
                  {l.price != null ? ` · ${money(l.price)}` : ""}
                  {l.closed_at ? " · 已关" : ""}
                </li>
              ))}
            </ul>
          )}
          {detail.log?.length > 0 && (
            <div className="mt-3 text-sm">
              {detail.log.slice(0, 12).map((c) => (
                <div key={c.id} className={c.voided_at ? "text-muted line-through" : "text-muted"}>
                  {clock(c.at)} · {c.person_name || "没记"} ·{" "}
                  {c.kind === "drink" ? ml(c.amount_ml) : g(c.amount_g)} · {money(c.cost)}
                </div>
              ))}
            </div>
          )}
        </Panel>
      )}
    </>
  );
}

function ReviewPane({ toast, oops }) {
  const [status, setStatus] = useState("pending");
  const [beans, setBeans] = useState(null);
  const [picked, setPicked] = useState(null);
  const [note, setNote] = useState("");

  const load = () =>
    api
      .reviewQueue(status)
      .then((d) => setBeans(d.beans))
      .catch((e) => oops(e.message));

  useEffect(() => {
    setBeans(null);
    setPicked(null);
    load();
  }, [status]);

  const open = async (id) => {
    try {
      setPicked(await api.reviewBean(id));
    } catch (e) {
      oops(e.message);
    }
  };

  const certify = async (force) => {
    if (!picked) return;
    try {
      const out = await api.certifyBean(picked.id, {
        note,
        force_places: force,
      });
      setPicked(out);
      setNote("");
      toast("已认证");
      load();
    } catch (e) {
      oops(e.message);
    }
  };

  const uncertify = async () => {
    if (!picked) return;
    try {
      const out = await api.uncertifyBean(picked.id, { note });
      setPicked(out);
      setNote("");
      toast("已取消认证");
      load();
    } catch (e) {
      oops(e.message);
    }
  };

  const guess = async () => {
    if (!picked) return;
    try {
      setPicked(await api.reviewGuessPlaces(picked.id));
      toast("已按词典重钉");
    } catch (e) {
      oops(e.message);
    }
  };

  return (
    <div className="mt-6 grid gap-6 lg:grid-cols-[minmax(0,320px)_minmax(0,1fr)]">
      <Panel className="h-fit">
        <div className="flex flex-wrap gap-2">
          {[
            ["pending", "待审"],
            ["certified", "已认证"],
            ["public", "全部公开"],
          ].map(([k, label]) => (
            <Chip key={k} on={status === k} onClick={() => setStatus(k)}>
              {label}
            </Chip>
          ))}
        </div>
        <div className="mt-3 space-y-1">
          {(beans || []).map((b) => (
            <button
              key={b.id}
              type="button"
              onClick={() => open(b.id)}
              className={`flex w-full flex-col rounded-xl px-3 py-2.5 text-left text-sm ${
                picked?.id === b.id ? "bg-chip text-cream" : "text-muted hover:bg-chip/60"
              }`}
            >
              <span className="truncate text-cream">
                {b.name}
                {b.certified ? <span className="ml-2 text-xs text-amber">已认证</span> : null}
              </span>
              <span className="mt-0.5 text-xs">
                {b.origin || "没填产地"} · {b.owner_email || "无名氏"}
              </span>
              {gaps(b.checklist).length > 0 && (
                <span className="mt-0.5 text-xs text-warn">{gaps(b.checklist).join(" · ")}</span>
              )}
            </button>
          ))}
          {beans && beans.length === 0 && <p className="text-sm text-muted">这一栏是空的。</p>}
          {!beans && <p className="text-sm text-muted">读取中…</p>}
        </div>
      </Panel>

      <div>
        {!picked ? (
          <Empty>
            左边点一张卡。认证是看这张是不是正常的豆子档案：产地、描述、照片、杯测、进价、地图钉。空卡或乱钉不要过。
          </Empty>
        ) : (
          <ReviewDossier
            picked={picked}
            note={note}
            setNote={setNote}
            guess={guess}
            certify={certify}
            uncertify={uncertify}
          />
        )}
      </div>
    </div>
  );
}

const CHECK_LABELS = [
  ["photos", "照片"],
  ["scores", "杯测"],
  ["note", "描述"],
  ["price", "进价"],
  ["origin", "产地"],
  ["places", "落点"],
];

const ARCHIVE_FIELDS = [
  ["origin", "产地"],
  ["varietal", "豆种"],
  ["producer", "处理厂"],
  ["process", "处理法"],
  ["roast", "烘焙"],
  ["altitude", "海拔"],
  ["water_temp", "水温"],
];

function gaps(checklist) {
  return CHECK_LABELS.filter(([k]) => !checklist?.[k]).map(([, label]) => `没${label}`);
}

function ReviewDossier({ picked, note, setNote, guess, certify, uncertify }) {
  const checks = picked.checklist || {};
  return (
    <div className="space-y-4">
      <Panel>
        <h2 className="serif m-0 text-2xl">{picked.name}</h2>
        <p className="mt-1 mb-0 text-sm text-muted">
          {picked.owner?.email || "无名氏"}
          {picked.certified ? " · 已认证" : " · 未认证"}
        </p>
        <div className="mt-3 flex flex-wrap gap-1.5">
          {CHECK_LABELS.map(([k, label]) => (
            <span
              key={k}
              className={`rounded-full border px-2 py-0.5 text-xs ${
                checks[k] ? "border-amber/40 text-amber" : "border-line text-muted"
              }`}
            >
              {checks[k] ? `有${label}` : `没${label}`}
            </span>
          ))}
        </div>
        <dl className="mt-4 grid gap-2 sm:grid-cols-2">
          {ARCHIVE_FIELDS.map(([k, label]) => (
            <div key={k}>
              <dt className="text-xs text-muted">{label}</dt>
              <dd className="m-0 text-sm text-cream">{picked[k] || "没填"}</dd>
            </div>
          ))}
        </dl>
        {picked.tags?.length > 0 && (
          <div className="mt-3 flex flex-wrap gap-1.5">
            {picked.tags.map((t) => (
              <b
                key={t}
                className="rounded-full border border-line px-2 py-0.5 text-xs font-normal text-muted"
              >
                {t}
              </b>
            ))}
          </div>
        )}
        <div className="mt-4">
          <div className="text-xs text-muted">豆卡描述</div>
          <p className="mt-1 mb-0 text-sm leading-relaxed text-cream">
            {picked.note?.trim() || "没写描述"}
          </p>
        </div>
        <div className="mt-4">
          <div className="text-xs text-muted">进价</div>
          <p className="mt-1 mb-0 text-sm text-cream">
            {picked.price
              ? `${money(picked.price.price)} / ${g(picked.price.nominal_g)}${
                  picked.price.unit_cost != null ? ` · 合 ${money(picked.price.unit_cost)}/g` : ""
                }${picked.price.bags > 1 ? ` · ${picked.price.bags} 袋有价` : ""}`
              : "没填进价"}
          </p>
        </div>
      </Panel>

      <div className="grid gap-4 lg:grid-cols-2">
        <Panel>
          <div className="serif text-lg">照片</div>
          {picked.photos?.length ? (
            <div className="mt-3 grid grid-cols-2 gap-2">
              {picked.photos.map((p) => (
                <img
                  key={p.id}
                  src={p.thumb || p.url}
                  alt=""
                  className="h-36 w-full rounded-xl object-cover"
                />
              ))}
            </div>
          ) : (
            <p className="mt-3 mb-0 text-sm text-muted">没有包装或豆盘照片。</p>
          )}
        </Panel>
        <Panel>
          <div className="serif text-lg">杯测</div>
          <Radar scores={picked.scores} />
          {picked.scores?.comment ? (
            <p className="serif mt-3 mb-0 text-[15px] leading-relaxed text-cream">
              {picked.scores.comment}
            </p>
          ) : (
            <p className="mt-3 mb-0 text-sm text-muted">主人还没写杯测评语。</p>
          )}
        </Panel>
      </div>

      <Panel>
        {picked.places?.warnings?.length > 0 ? (
          <p className="mt-0 mb-0 text-sm text-warn">{picked.places.warnings.join("；")}</p>
        ) : (
          <p className="mt-0 mb-0 text-sm text-amber">地图钉和词典对得上</p>
        )}
        {picked.places?.current?.length > 0 && (
          <p className="mt-2 mb-0 text-[13px] text-muted">
            现在：{picked.places.current.map((p) => p.label).join("、")}
          </p>
        )}
        {picked.places?.gazetteer?.length > 0 && (
          <p className="mt-1 mb-0 text-[13px] text-muted">
            词典：{picked.places.gazetteer.map((p) => p.label).join("、")}
          </p>
        )}
        <input
          value={note}
          onChange={(e) => setNote(e.target.value)}
          placeholder="审核备注，可空"
          className="mt-4 w-full rounded-lg border border-line bg-bg px-3 py-2 text-sm text-cream
            outline-none focus:border-amber"
        />
        <div className="mt-3 flex flex-wrap gap-2">
          <Btn variant="ghost" onClick={guess}>
            按词典重钉
          </Btn>
          {picked.certified ? (
            <Btn variant="danger" onClick={uncertify}>
              取消认证
            </Btn>
          ) : (
            <>
              <Btn onClick={() => certify(false)}>认证</Btn>
              {picked.places?.warnings?.length > 0 && (
                <Btn variant="ghost" onClick={() => certify(true)}>
                  钉不对也认证
                </Btn>
              )}
            </>
          )}
        </div>
      </Panel>
    </div>
  );
}

function Stat({ label, value }) {
  return (
    <div className="rounded-2xl border border-line bg-panel px-4 py-3">
      <div className="text-xs text-muted">{label}</div>
      <div className="mt-1 text-lg text-amber">{value}</div>
    </div>
  );
}
