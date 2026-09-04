// 开封动画：拉开封口条 → 袋口张开 → 香气飘出 → 露出豆子。
// anime.js 描线（见 https://animejs.com/documentation/svg），跟冲煮那套同一手法。
import { useEffect, useRef, useState } from "react";
import { createTimeline, stagger, utils } from "animejs";

import { api } from "../api.js";
import { Btn, Field, Input, Modal } from "../ui.jsx";

export default function OpenBag({ open, lot, onClose, onDone, oops }) {
  const [phase, setPhase] = useState("ready"); // ready → playing → done
  const [measured, setMeasured] = useState("");
  const zip = useRef(null);
  const lipL = useRef(null);
  const lipR = useRef(null);
  const aroma = useRef([]);
  const beans = useRef([]);

  useEffect(() => {
    if (open) {
      setPhase("ready");
      setMeasured("");
    }
  }, [open]);

  const play = async () => {
    setPhase("playing");
    try {
      await api.openLot(lot.id);
    } catch (e) {
      setPhase("ready");
      return oops(e.message);
    }

    const tl = createTimeline({
      defaults: { ease: "outQuad" },
      onComplete: () => setPhase("done"),
    });

    utils.set(zip.current, { strokeDashoffset: 120 });
    utils.set(aroma.current, { strokeDashoffset: 60, opacity: 0 });
    utils.set(beans.current, { opacity: 0, scale: 0 });

    tl
      // 拉链滑开
      .add(zip.current, { strokeDashoffset: 0, duration: 620, ease: "inOutQuad" })
      // 袋口向两侧翻开
      .add(lipL.current, { rotate: -17, duration: 520, ease: "outBack" }, "-=120")
      .add(lipR.current, { rotate: 17, duration: 520, ease: "outBack" }, "<")
      // 豆子露出来
      .add(
        beans.current,
        { opacity: 1, scale: 1, duration: 420, delay: stagger(70) },
        "-=300"
      )
      // 香气飘上去
      .add(
        aroma.current,
        {
          strokeDashoffset: 0,
          opacity: [0, 0.85, 0],
          translateY: -18,
          duration: 1150,
          delay: stagger(140),
        },
        "-=280"
      );
  };

  const finish = async () => {
    const val = Number(measured);
    if (measured.trim() && Number.isFinite(val) && val > 0) {
      try {
        await api.measure(lot.id, val);
      } catch (e) {
        return oops(e.message);
      }
    }
    onDone(measured.trim() ? `开封了，记下实称 ${measured.trim()} g` : "开封了");
  };

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={phase === "done" ? "开封了" : "要开这袋吗？"}
      sub={
        phase === "done"
          ? "开封日记的是今天。称一下是可选的，不称就按袋上印的克重接着扣。"
          : `袋上印的是 ${lot?.nominal_g} g。开封只记日子，不动克数。`
      }
      footer={
        phase === "done" ? (
          <Btn onClick={finish}>{measured.trim() ? "记下实称" : "好"}</Btn>
        ) : (
          <>
            <Btn variant="ghost" onClick={onClose} disabled={phase === "playing"}>
              先不开
            </Btn>
            <Btn onClick={play} disabled={phase === "playing"}>
              {phase === "playing" ? "开封中…" : "开封"}
            </Btn>
          </>
        )
      }
    >
      <svg viewBox="0 0 240 210" className="mx-auto w-full" style={{ maxHeight: 250 }}>
        {/* 香气：三条向上飘的曲线 */}
        {[
          "M104 52c-7-11 7-19 0-30",
          "M120 46c-8-13 8-22 0-34",
          "M136 52c-7-11 7-19 0-30",
        ].map((d, i) => (
          <path
            key={i}
            ref={(el) => (aroma.current[i] = el)}
            d={d}
            fill="none"
            stroke="#c88d44"
            strokeWidth="2"
            strokeLinecap="round"
            strokeDasharray="60"
            strokeDashoffset="60"
            opacity="0"
          />
        ))}

        {/* 袋身 */}
        <path
          d="M62 66h116v116a10 10 0 0 1-10 10H72a10 10 0 0 1-10-10z"
          fill="#241c16"
          stroke="#3a3228"
          strokeWidth="2"
        />
        {/* 侧边压痕，撑出立体感 */}
        <path d="M80 66v126M160 66v126" stroke="#3a3228" strokeWidth="1.4" opacity="0.7" />
        {/* 标签：呼应真实包装那块琥珀色 */}
        <rect x="76" y="108" width="88" height="46" rx="3" fill="#d9b871" />
        <path
          d="M84 120h44M84 130h56M84 140h30"
          stroke="#6b5330"
          strokeWidth="2.4"
          strokeLinecap="round"
          opacity="0.55"
        />

        {/* 豆子：开封后从袋口露出来 */}
        {[
          [104, 60],
          [120, 56],
          [136, 60],
        ].map(([cx, cy], i) => (
          <g
            key={i}
            ref={(el) => (beans.current[i] = el)}
            style={{ transformOrigin: `${cx}px ${cy}px` }}
          >
            <ellipse cx={cx} cy={cy} rx="7" ry="5.4" fill="#7a5333" />
            <path
              d={`M${cx - 5} ${cy}q5 -3.4 10 0`}
              stroke="#2a1c14"
              strokeWidth="1.4"
              fill="none"
            />
          </g>
        ))}

        {/* 袋口两片，开封后向外翻 */}
        <path
          ref={lipL}
          d="M62 66h58v-18H62z"
          fill="#2e251d"
          stroke="#3a3228"
          strokeWidth="2"
          style={{ transformOrigin: "62px 66px" }}
        />
        <path
          ref={lipR}
          d="M120 66h58v-18h-58z"
          fill="#2e251d"
          stroke="#3a3228"
          strokeWidth="2"
          style={{ transformOrigin: "178px 66px" }}
        />

        {/* 封口拉链 */}
        <path
          ref={zip}
          d="M64 56h112"
          stroke="#c88d44"
          strokeWidth="3"
          strokeLinecap="round"
          strokeDasharray="120"
          strokeDashoffset="120"
        />
      </svg>

      {phase === "done" && (
        <Field label="称一下？（可以不称）" hint="留空就按袋上印的克重继续扣">
          <Input
            type="number"
            step="0.001"
            value={measured}
            onChange={(e) => setMeasured(e.target.value)}
            placeholder={String(lot?.nominal_g ?? "")}
            autoFocus
          />
        </Field>
      )}
    </Modal>
  );
}
