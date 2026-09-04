// 冲煮指导：单独占一整行，不和库存挤宫格。
// 方案按当场输入的粉量与比例即时算（后端算，保证与统计同一套口径）。
import { useEffect, useRef, useState } from "react";
import { createTimeline, utils } from "animejs";

import { api } from "../api.js";
import { Play } from "../icons.jsx";
import { Btn, Field, Input, Panel, Select } from "../ui.jsx";

export default function BrewPlan({ bean, onRecord, toast, oops }) {
  const [methods, setMethods] = useState([]);
  const [form, setForm] = useState({
    method: bean.brew?.method || "v60",
    dose: bean.brew?.dose_g ?? 15,
    ratio: bean.brew?.ratio ?? 16,
  });
  const [plan, setPlan] = useState(null);
  const [active, setActive] = useState(-1);
  const [left, setLeft] = useState(0);
  const [playing, setPlaying] = useState(false);
  const actualRef = useRef([]);
  const tickRef = useRef(null);

  useEffect(() => {
    api.brewMethods().then((d) => setMethods(d.methods));
  }, []);

  // 改粉量或比例，各段立刻重算
  useEffect(() => {
    const t = setTimeout(() => {
      api
        .brewPlan(form.method, Number(form.dose) || 15, Number(form.ratio) || 16)
        .then(setPlan)
        .catch((e) => oops(e.message));
    }, 120);
    return () => clearTimeout(t);
  }, [form, oops]);

  const stop = () => {
    clearInterval(tickRef.current);
    tickRef.current = null;
    setPlaying(false);
    setActive(-1);
    setLeft(0);
  };

  useEffect(() => () => clearInterval(tickRef.current), []);

  const play = () => {
    if (!plan) return;
    actualRef.current = [];
    let i = 0;
    let remain = plan.stages[0].seconds;
    setActive(0);
    setLeft(remain);
    setPlaying(true);
    const startedAt = Date.now();
    let stageStart = startedAt;

    clearInterval(tickRef.current);
    tickRef.current = setInterval(() => {
      remain -= 1;
      if (remain > 0) {
        setLeft(remain);
        return;
      }
      // 记下这一段实际用了多少秒
      actualRef.current.push(Math.round((Date.now() - stageStart) / 1000));
      stageStart = Date.now();
      i += 1;
      if (i >= plan.stages.length) {
        clearInterval(tickRef.current);
        tickRef.current = null;
        setPlaying(false);
        setActive(-1);
        setLeft(0);
        toast("冲完了，记一次吧");
        onRecord?.({
          method: form.method,
          ratio: Number(form.ratio),
          dose: Number(form.dose),
          total_s: Math.round((Date.now() - startedAt) / 1000),
          stages: actualRef.current,
        });
        return;
      }
      remain = plan.stages[i].seconds;
      setActive(i);
      setLeft(remain);
    }, 1000);
  };

  const cur = active >= 0 && plan ? plan.stages[active] : null;

  return (
    <Panel className="mt-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="serif text-lg">冲煮指导</div>
          {bean.brew?.note && (
            <p className="mt-1 mb-0 text-[13px] text-muted">店家推荐：{bean.brew.note}</p>
          )}
        </div>
        <div className="flex items-center gap-2">
          {playing ? (
            <Btn variant="ghost" onClick={stop}>
              停
            </Btn>
          ) : (
            <Btn variant="ghost" onClick={play} disabled={!plan}>
              <Play className="h-4 w-4" />
              播放
            </Btn>
          )}
          <Btn
            variant="ghost"
            onClick={async () => {
              await api.setBrewDefault(bean.id, {
                method: form.method,
                dose_g: Number(form.dose),
                ratio: Number(form.ratio),
              });
              toast("存成这支豆的默认");
            }}
          >
            存为默认
          </Btn>
        </div>
      </div>

      <div className="mt-4 flex flex-wrap items-end gap-3">
        <Field label="方式">
          <Select
            value={form.method}
            onChange={(e) => setForm({ ...form, method: e.target.value })}
          >
            {methods.map((m) => (
              <option key={m.key} value={m.key}>
                {m.label}
              </option>
            ))}
          </Select>
        </Field>
        <Field label="粉量 g">
          <Input
            type="number"
            step="0.5"
            className="w-24"
            value={form.dose}
            onChange={(e) => setForm({ ...form, dose: e.target.value })}
          />
        </Field>
        <Field label="比例 1 :">
          <Input
            type="number"
            step="0.5"
            className="w-24"
            value={form.ratio}
            onChange={(e) => setForm({ ...form, ratio: e.target.value })}
          />
        </Field>
        {plan && (
          <div className="pb-2 text-[13px] text-muted">
            总水 <b className="text-amber">{plan.total_water_g} g</b> · 建议总时间{" "}
            {fmt(plan.total_seconds)}
          </div>
        )}
      </div>

      <div className="mt-4 grid gap-5 lg:grid-cols-[1.35fr_1fr]">
        <div className="min-w-0 overflow-x-auto">
          <table className="w-full border-collapse text-[13px]">
            <thead>
              <tr className="text-muted">
                {["段", "本段", "秤到", "本段", "累计", "手法", "目标", "功能"].map((h, i) => (
                  <th key={i} className="border-b border-line px-2 py-2 text-left font-normal">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {plan?.stages.map((s, i) => (
                <tr key={i} className={i === active ? "bg-amber/12 text-cream" : ""}>
                  <td className="border-b border-line px-2 py-2">{s.name}</td>
                  <td className="whitespace-nowrap border-b border-line px-2 py-2 text-amber">
                    {s.add_g ? `+${s.add_g} g` : "—"}
                  </td>
                  <td className="whitespace-nowrap border-b border-line px-2 py-2 text-amber">
                    {s.target_g} g
                  </td>
                  <td className="whitespace-nowrap border-b border-line px-2 py-2">{s.seconds}s</td>
                  <td className="whitespace-nowrap border-b border-line px-2 py-2 text-muted">
                    {fmt(s.elapsed_s)}
                  </td>
                  <td className="border-b border-line px-2 py-2">{s.how}</td>
                  <td className="border-b border-line px-2 py-2 text-muted">{s.goal}</td>
                  <td className="border-b border-line px-2 py-2 text-muted">{s.function}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div>
          <div className="serif text-xl">
            {cur
              ? cur.add_g
                ? `${cur.name} · 本段 +${cur.add_g} g · 秤到 ${cur.target_g} g`
                : `${cur.name} · 停手`
              : "未播放"}
          </div>
          <p className="mt-1.5 text-[13px] text-muted">
            {cur ? `${cur.how} · ${cur.goal} · ${cur.function}` : "改粉量或比例，各段立刻重算。"}
          </p>
          {playing && (
            <div className="serif mt-1 text-3xl text-amber">
              {left}
              <span className="ml-1 text-base">s</span>
            </div>
          )}
          <PourAnimation stage={cur} target={plan?.total_water_g || 1} />
        </div>
      </div>
    </Panel>
  );
}

const fmt = (s) => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;

// anime.js SVG：按场景键切动画（bloom 打湿 / 螺旋 / 中心注 / 滴滤）
function PourAnimation({ stage, target }) {
  const spiral = useRef(null);
  const center = useRef(null);
  const mound = useRef(null);
  const water = useRef(null);
  const drip = useRef(null);

  useEffect(() => {
    if (!stage || !spiral.current) return;
    const tl = createTimeline({ defaults: { ease: "inOutSine" } });
    const level = Math.min(1, stage.target_g / target);
    // 中心注水不该画螺旋：水柱咬住一点，粉层中间被顶起来（火山冲全程如此）
    const isCenter = stage.scene === "center_pour";
    const trace = isCenter ? center.current : spiral.current;

    utils.set([spiral.current, center.current], { opacity: 0 });
    utils.set(mound.current, { opacity: 0, scaleY: 0.2 });

    if (stage.scene === "drawdown") {
      tl.add(water.current, { opacity: 0.05, scaleY: 0.2, duration: 900 }).add(
        drip.current,
        { opacity: 0.9, duration: 600 },
        0
      );
    } else {
      utils.set(trace, { opacity: 1, strokeDashoffset: 140 });
      tl.add(trace, {
        strokeDashoffset: 0,
        duration: stage.scene === "bloom" ? 1400 : 1000,
      })
        .add(water.current, { opacity: 0.15 + level * 0.35, scaleY: 0.4 + level, duration: 900 }, 0)
        .add(drip.current, { opacity: stage.scene === "bloom" ? 0.25 : 0.6, duration: 700 }, 0);
      if (isCenter) {
        tl.add(mound.current, { opacity: 0.5, scaleY: 1, duration: 800 }, 0);
      }
    }
    return () => tl.pause();
  }, [stage, target]);

  return (
    <svg viewBox="0 0 240 190" className="mt-3 w-full" style={{ maxHeight: 200 }}>
      {/* 滤杯 */}
      <path d="M70 46h100l-14 34H84z" fill="none" stroke="#c88d44" strokeWidth="2" />
      {/* 注水螺旋 */}
      <path
        ref={spiral}
        d="M120 56c20 8 30 20 19 33s-34 11-38 0 9-19 21-17"
        fill="none"
        stroke="#f3e6d0"
        strokeWidth="2"
        strokeDasharray="140"
        strokeDashoffset="140"
      />
      {/* 中心细水柱：一路咬住中心，不画圈 */}
      <path
        ref={center}
        d="M120 50v26"
        fill="none"
        stroke="#f3e6d0"
        strokeWidth="2.4"
        strokeDasharray="140"
        strokeDashoffset="140"
        opacity="0"
      />
      {/* 火山口：中心被顶起来的粉丘 */}
      <path
        ref={mound}
        d="M100 76q20-14 40 0"
        fill="none"
        stroke="#c88d44"
        strokeWidth="2"
        opacity="0"
        style={{ transformOrigin: "120px 76px" }}
      />
      {/* 水位 */}
      <ellipse
        ref={water}
        cx="120"
        cy="72"
        rx="40"
        ry="6"
        fill="#c88d44"
        opacity="0.15"
        style={{ transformOrigin: "120px 72px" }}
      />
      {/* 滴滤 */}
      <path
        ref={drip}
        d="M120 84v34"
        stroke="#c88d44"
        strokeWidth="2"
        strokeDasharray="5 7"
        opacity="0.2"
      />
      {/* 分享壶 */}
      <path d="M88 122h64v34a8 8 0 0 1-8 8H96a8 8 0 0 1-8-8z" fill="none" stroke="#9c8b74" strokeWidth="1.6" />
      <path d="M152 130h9a7 7 0 0 1 0 14h-9" fill="none" stroke="#9c8b74" strokeWidth="1.6" />
    </svg>
  );
}
