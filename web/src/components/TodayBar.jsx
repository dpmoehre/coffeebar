// 豆库顶上「今天」条。有才画，不跟在库/历史走。
import { useEffect, useState } from "react";

import { api } from "../api.js";
import { recall, remember } from "../listCache.js";
import { Chip } from "../ui.jsx";

function fmtSec(s) {
  if (s == null) return "";
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

function hasToday(d) {
  if (!d) return false;
  return Boolean(
    d.people?.length ||
      d.peak?.length ||
      d.stale ||
      d.opened_long ||
      d.restock?.n ||
      d.last_cup,
  );
}

function personLabel(p) {
  if (p.coffee && p.drink) return `${p.name} ${p.coffee}（酒 ${p.drink}）`;
  if (p.coffee) return `${p.name} ${p.coffee}`;
  if (p.drink) return `${p.name}（酒 ${p.drink}）`;
  return p.name;
}

function restockLabel(r) {
  if (!r?.n) return "";
  if (r.n === r.beans) return `${r.n} 支见底`;
  return `${r.n} 条要补`;
}

function lastLine(c) {
  const who = c.person_name ? ` · ${c.person_name}` : "";
  if (c.actual_s != null && c.planned_s != null) {
    const hint = c.label ? ` · ${c.label}` : "";
    return `${fmtSec(c.actual_s)} / ${fmtSec(c.planned_s)}${hint}${who}`;
  }
  return who ? c.person_name : "上一杯";
}

function Block({ title, children, onClick }) {
  const cls =
    "min-w-[13.5rem] shrink-0 rounded-2xl border border-line bg-panel px-4 py-3 text-left md:min-w-0 md:flex-1 " +
    (onClick ? "cursor-pointer transition hover:border-amber" : "");
  const inner = (
    <>
      <div className="text-[12px] tracking-wide text-muted">{title}</div>
      <div className="mt-2">{children}</div>
    </>
  );
  if (onClick) {
    return (
      <button type="button" className={cls} onClick={onClick}>
        {inner}
      </button>
    );
  }
  return <div className={cls}>{inner}</div>;
}

export default function TodayBar({ onOpen, onOpenRestock, onOpenPerson, oops }) {
  const [data, setData] = useState(() => recall("today") ?? null);

  useEffect(() => {
    api
      .today()
      .then((d) => {
        remember("today", d);
        setData(d);
      })
      .catch((e) => {
        if (recall("today") === undefined) oops(e.message);
      });
  }, [oops]);

  if (!hasToday(data)) return null;

  const taste = data.peak?.length || data.stale || data.opened_long;

  return (
    <div className="-mx-1 mt-5 flex gap-3 overflow-x-auto pb-1 md:mx-0 md:overflow-visible">
      {data.people?.length > 0 && (
        <Block title="今天谁喝了">
          <div className="flex flex-wrap gap-1.5">
            {data.people.map((p) => (
              <Chip
                key={p.person_id ?? "anon"}
                onClick={() => onOpenPerson?.(p.person_id)}
              >
                {personLabel(p)}
              </Chip>
            ))}
          </div>
        </Block>
      )}
      {taste ? (
        <Block title="赏味">
          <div className="flex flex-wrap gap-1.5">
            {data.peak.map((b) => (
              <Chip key={`peak-${b.id}`} onClick={() => onOpen(b.id)}>
                正当时 · {b.name}
              </Chip>
            ))}
            {data.stale && (
              <Chip onClick={() => onOpen(data.stale.id)}>老了 · {data.stale.name}</Chip>
            )}
            {data.opened_long && (
              <Chip onClick={() => onOpen(data.opened_long.id)}>
                开封已久 · {data.opened_long.name}
              </Chip>
            )}
          </div>
        </Block>
      ) : null}
      {data.restock?.n > 0 && (
        <Block title="补货" onClick={() => onOpenRestock?.()}>
          <div className="serif text-lg font-semibold">{restockLabel(data.restock)}</div>
        </Block>
      )}
      {data.last_cup && (
        <Block title="上一杯" onClick={() => onOpen(data.last_cup.bean_id)}>
          <div className="text-sm leading-snug">{data.last_cup.name}</div>
          <div className="mt-1 text-[13px] text-muted">{lastLine(data.last_cup)}</div>
        </Block>
      )}
    </div>
  );
}
