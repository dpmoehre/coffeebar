// 统计：一进来先看数字，再看曲线和按人。撤回的流水不进任何汇总。
import { useEffect, useState } from "react";

import { api } from "../api.js";
import { Chip, Empty, Panel, money } from "../ui.jsx";

const PERIODS = [
  ["week", "本周"],
  ["month", "本月"],
  ["year", "今年"],
  ["all", "全部"],
];

export default function Stats() {
  const [period, setPeriod] = useState("month");
  const [s, setS] = useState(null);

  useEffect(() => {
    setS(null);
    api.stats(period).then(setS);
  }, [period]);

  const dose = s?.avg_dose;

  return (
    <>
      <header>
        <h1 className="serif m-0 text-3xl font-semibold">统计</h1>
        <p className="mt-2 mb-0 text-muted">
          先看数字：消耗了多少豆、多少酒、花了多少钱。
        </p>
      </header>

      <div className="mt-5 flex flex-wrap gap-2">
        {PERIODS.map(([k, label]) => (
          <Chip key={k} on={period === k} onClick={() => setPeriod(k)}>
            {label}
          </Chip>
        ))}
      </div>

      {!s ? (
        <p className="mt-6 text-muted">读取中…</p>
      ) : s.cups === 0 && s.drink_cups === 0 && s.bought === 0 ? (
        <Empty>这段时间还没冲过、也没买过。记一次消耗或入库，这里就有数字了。</Empty>
      ) : (
        <>
          <div className="mt-5 grid gap-3.5 sm:grid-cols-2 lg:grid-cols-4">
            <Kpi
              label="咖啡豆"
              value={s.beans_g >= 1000 ? (s.beans_g / 1000).toFixed(2) : Math.round(s.beans_g)}
              unit={s.beans_g >= 1000 ? "kg" : "g"}
              hint={`${Math.round(s.beans_g)} g · ${s.cups} 杯`}
            />
            <Kpi
              label="平均每杯粉量"
              value={dose.avg_g}
              unit="g"
              hint={
                dose.lo_g != null && dose.lo_g !== dose.hi_g
                  ? `${s.cups} 杯实际用量 · ${dose.lo_g}–${dose.hi_g} g`
                  : `${s.cups} 杯实际用量`
              }
            />
            <Kpi
              label="喝掉的钱"
              value={money(s.spent).replace("¥", "")}
              unit="¥"
              hint="按每笔冻结的单价摊"
            />
            <Kpi
              label="买进来的钱"
              value={money(s.bought).replace("¥", "")}
              unit="¥"
              hint="期间新入袋、新入瓶的买入价"
            />
          </div>
          <div className="mt-3.5 grid gap-3.5 sm:grid-cols-2 lg:grid-cols-4">
            <Kpi
              label="酒"
              value={s.drinks_ml >= 1000 ? (s.drinks_ml / 1000).toFixed(2) : Math.round(s.drinks_ml)}
              unit={s.drinks_ml >= 1000 ? "L" : "ml"}
              hint={`${s.drink_cups} 杯`}
            />
            <Kpi
              label="酒精约"
              value={s.alcohol_g}
              unit="g"
              hint="毫升 × 酒精度 × 0.789"
            />
            <Kpi
              label="在库还值"
              value={money(s.on_hand).replace("¥", "")}
              unit="¥"
              hint="未关袋/未关瓶的账面 × 单价"
            />
          </div>

          <div className="mt-4 grid gap-4 lg:grid-cols-2">
            <Panel>
              <div className="serif text-lg">消耗速度（克 / 天）</div>
              <Spark data={s.daily} />
            </Panel>

            <Panel>
              <div className="serif text-lg">按人</div>
              {s.by_person.length === 0 ? (
                <p className="mt-3 text-muted">还没记过谁喝的。</p>
              ) : (
                <table className="mt-3 w-full border-collapse text-sm">
                  <thead>
                    <tr className="text-muted">
                      <th className="border-b border-line px-1.5 py-2 text-left font-normal">谁</th>
                      <th className="border-b border-line px-1.5 py-2 text-right font-normal">豆</th>
                      <th className="border-b border-line px-1.5 py-2 text-right font-normal">杯</th>
                      <th className="border-b border-line px-1.5 py-2 text-right font-normal">
                        平均
                      </th>
                      <th className="border-b border-line px-1.5 py-2 text-right font-normal">钱</th>
                    </tr>
                  </thead>
                  <tbody>
                    {s.by_person.map((p) => (
                      <tr key={p.name}>
                        <td className="border-b border-line px-1.5 py-2">{p.name}</td>
                        <td className="border-b border-line px-1.5 py-2 text-right text-amber">
                          {Math.round(p.beans_g)} g
                        </td>
                        <td className="border-b border-line px-1.5 py-2 text-right text-amber">
                          {p.cups}
                        </td>
                        <td className="border-b border-line px-1.5 py-2 text-right text-muted">
                          {p.avg_dose_g} g
                        </td>
                        <td className="border-b border-line px-1.5 py-2 text-right text-amber">
                          {money(p.spent)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </Panel>
          </div>

          <Panel className="mt-4">
            <div className="serif text-lg">喝得最多的豆</div>
            <div className="mt-2">
              {s.by_bean.map((b) => (
                <div
                  key={b.id}
                  className="flex items-center gap-3 border-b border-line py-2.5 last:border-0"
                >
                  <div
                    className="h-9 w-9 shrink-0 rounded-full"
                    style={{
                      background: "radial-gradient(circle at 35% 35%, #7a5333, #2a1c14)",
                    }}
                  />
                  <div className="min-w-0 flex-1">
                    <div className="truncate">{b.name}</div>
                    <div className="text-xs text-muted">{b.cups} 杯</div>
                  </div>
                  <div className="whitespace-nowrap text-sm text-amber">
                    {Math.round(b.beans_g)} g · {money(b.spent)}
                  </div>
                </div>
              ))}
            </div>
          </Panel>
        </>
      )}
    </>
  );
}

function Kpi({ label, value, unit, hint }) {
  return (
    <div className="rise rounded-2xl border border-line bg-panel p-5">
      <div className="text-[13px] text-muted">{label}</div>
      <div className="serif mt-2 text-3xl leading-tight tracking-tight">
        {value}
        <small className="ml-1 text-base font-medium text-amber">{unit}</small>
      </div>
      <div className="mt-1.5 text-xs text-muted">{hint}</div>
    </div>
  );
}

function Spark({ data }) {
  if (!data?.length) return <p className="mt-3 text-muted">还没有足够的点。</p>;
  const w = 360;
  const h = 140;
  const max = Math.max(...data.map((d) => d.beans_g), 1);
  const pts = data.map((d, i) => [
    data.length === 1 ? w / 2 : (i / (data.length - 1)) * (w - 20) + 10,
    h - 12 - (d.beans_g / max) * (h - 30),
  ]);
  const line = pts.map((p, i) => `${i ? "L" : "M"}${p[0].toFixed(1)} ${p[1].toFixed(1)}`).join(" ");

  return (
    <svg viewBox={`0 0 ${w} ${h}`} className="mt-3 w-full" style={{ maxHeight: 170 }}>
      <path d={`M10 ${h - 12}h${w - 20}`} stroke="#3a3228" fill="none" />
      <path d={line} fill="none" stroke="#c88d44" strokeWidth="2.5" strokeLinejoin="round" />
      {pts.map((p, i) => (
        <circle key={i} cx={p[0]} cy={p[1]} r="2.5" fill="#e0a85a" />
      ))}
      <text x="10" y="12" fill="#9c8b74" fontSize="10">
        峰值 {Math.round(max)} g
      </text>
    </svg>
  );
}
