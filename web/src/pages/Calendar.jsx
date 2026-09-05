// 月历：上点咖啡、下点酒。一天从凌晨 4 点算起。不占写锁。
import { useEffect, useMemo, useState } from "react";

import { api } from "../api.js";
import { Download } from "../icons.jsx";
import { Btn, Chip, Empty, Panel, money } from "../ui.jsx";

const WEEK = ["一", "二", "三", "四", "五", "六", "日"];

function pad(n) {
  return String(n).padStart(2, "0");
}

function businessToday() {
  const d = new Date();
  d.setHours(d.getHours() - 4);
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

function monthCells(year, month) {
  const first = new Date(year, month - 1, 1);
  let padDays = first.getDay() - 1;
  if (padDays < 0) padDays = 6;
  const last = new Date(year, month, 0).getDate();
  const cells = Array.from({ length: padDays }, () => null);
  for (let d = 1; d <= last; d++) {
    cells.push({ day: d, iso: `${year}-${pad(month)}-${pad(d)}` });
  }
  return cells;
}

function coffeeDot(n) {
  if (!n) return "bg-line";
  if (n >= 3) return "bg-amber2";
  if (n === 2) return "bg-amber";
  return "bg-[#c9a06a]";
}

function drinkDot(n) {
  return n ? "bg-[#7a64c8]" : "bg-line";
}

function clock(at) {
  return at?.slice(11, 16) || "";
}

export default function Calendar({ personId: initialPerson, toast, oops }) {
  const now = new Date();
  const [year, setYear] = useState(now.getFullYear());
  const [month, setMonth] = useState(now.getMonth() + 1);
  const [personId, setPersonId] = useState(initialPerson ?? null);
  const [data, setData] = useState(null);
  const [picked, setPicked] = useState(null);
  const [detail, setDetail] = useState(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    setPersonId(initialPerson ?? null);
  }, [initialPerson]);

  useEffect(() => {
    setData(null);
    api
      .calendar(year, month, personId)
      .then(setData)
      .catch((e) => oops(e.message));
  }, [year, month, personId, oops]);

  useEffect(() => {
    if (!picked) {
      setDetail(null);
      return;
    }
    setDetail(null);
    api
      .calendarDay(picked, personId)
      .then(setDetail)
      .catch((e) => oops(e.message));
  }, [picked, personId, oops]);

  const byDay = useMemo(() => {
    const m = new Map();
    for (const d of data?.days || []) m.set(d.date, d);
    return m;
  }, [data]);

  const cells = useMemo(() => monthCells(year, month), [year, month]);
  const today = businessToday();

  useEffect(() => {
    const inView = today.startsWith(`${year}-${pad(month)}-`);
    setPicked(inView ? today : null);
  }, [year, month, today]);

  const shift = (delta) => {
    const d = new Date(year, month - 1 + delta, 1);
    setYear(d.getFullYear());
    setMonth(d.getMonth() + 1);
  };

  const exportAll = async () => {
    setBusy(true);
    try {
      await api.exportZip("all");
      toast("表格已下载");
    } catch (e) {
      oops(e.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="serif m-0 text-3xl font-semibold">日历</h1>
          <p className="mt-2 mb-0 text-muted">
            上点咖啡、下点酒。一天从凌晨 4 点算起，夜里喝的算前一天。
          </p>
        </div>
        <Btn variant="ghost" onClick={exportAll} disabled={busy}>
          <Download className="h-4 w-4" />
          出表 CSV
        </Btn>
      </header>

      <div className="mt-5 flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <Btn variant="ghost" onClick={() => shift(-1)}>
            上个月
          </Btn>
          <div className="serif text-xl">
            {year} 年 {month} 月
          </div>
          <Btn variant="ghost" onClick={() => shift(1)}>
            下个月
          </Btn>
        </div>
        <div className="flex items-center gap-3 text-xs text-muted">
          <span className="inline-flex items-center gap-1.5">
            <i className="inline-block h-2 w-2 rounded-full bg-amber" />
            咖啡
          </span>
          <span className="inline-flex items-center gap-1.5">
            <i className="inline-block h-2 w-2 rounded-full bg-[#7a64c8]" />
            酒
          </span>
        </div>
      </div>

      <div className="mt-4 flex flex-wrap gap-2">
        <Chip on={!personId} onClick={() => setPersonId(null)}>
          全部
        </Chip>
        {(data?.people || []).map((p) => (
          <Chip
            key={p.id}
            on={personId === p.id}
            onClick={() => setPersonId(p.id)}
            className={p.active === false ? "opacity-50" : ""}
          >
            {p.name}
          </Chip>
        ))}
      </div>

      {!data ? (
        <p className="mt-6 text-muted">读取中…</p>
      ) : (
        <Panel className="mt-5">
          <div className="grid grid-cols-7 gap-2 text-center text-xs text-muted">
            {WEEK.map((w) => (
              <div key={w}>{w}</div>
            ))}
          </div>
          <div className="mt-2 grid grid-cols-7 gap-2">
            {cells.map((c, i) => {
              if (!c) return <div key={`e${i}`} />;
              const mark = byDay.get(c.iso);
              const on = picked === c.iso;
              const isToday = c.iso === today;
              return (
                <button
                  key={c.iso}
                  type="button"
                  onClick={() => setPicked(c.iso)}
                  className={`rounded-xl px-1 py-2 text-center transition ${
                    on
                      ? "border border-amber bg-chip"
                      : "border border-transparent hover:bg-chip"
                  }`}
                >
                  <strong
                    className={`block text-sm font-medium ${
                      isToday ? "text-amber" : "text-cream"
                    }`}
                  >
                    {c.day}
                  </strong>
                  <span className="mt-1.5 flex justify-center gap-1">
                    <i className={`block h-2 w-2 rounded-full ${coffeeDot(mark?.coffee)}`} />
                    <i className={`block h-2 w-2 rounded-full ${drinkDot(mark?.drink)}`} />
                  </span>
                </button>
              );
            })}
          </div>
        </Panel>
      )}

      {picked && (
        <div className="mt-5">
          {!detail ? (
            <p className="text-muted">读取当天…</p>
          ) : detail.events.length === 0 ? (
            <Empty>这一天没有记录。</Empty>
          ) : (
            <Panel>
              <div className="serif text-lg">
                {Number(picked.slice(5, 7))} 月 {Number(picked.slice(8))} 日
              </div>
              <p className="mt-1 mb-3 text-xs text-muted">划掉的是已撤回的，不进月份上的点数。</p>
              <div className="overflow-x-auto">
                <table className="w-full border-collapse text-sm">
                  <thead>
                    <tr className="text-muted">
                      {["时间", "种类", "名称", "谁", "用量", "钱"].map((h) => (
                        <th key={h} className="border-b border-line px-2 py-2 text-left font-normal">
                          {h}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {detail.events.map((e) => (
                      <tr key={e.id} className={e.voided ? "opacity-45 line-through" : ""}>
                        <td className="border-b border-line px-2 py-2 whitespace-nowrap">
                          {clock(e.at)}
                        </td>
                        <td className="border-b border-line px-2 py-2">
                          {e.kind === "drink" ? "酒" : "咖啡"}
                        </td>
                        <td className="border-b border-line px-2 py-2">{e.name}</td>
                        <td className="border-b border-line px-2 py-2">{e.person || "没记"}</td>
                        <td className="border-b border-line px-2 py-2 text-amber">
                          {e.kind === "drink" ? `${e.amount_ml} ml` : `${e.amount_g} g`}
                        </td>
                        <td className="border-b border-line px-2 py-2 text-amber">
                          {e.cost ? money(e.cost) : "—"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Panel>
          )}
        </div>
      )}
    </>
  );
}
