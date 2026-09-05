// 共用的小组件：按钮、面板、进度条、芯片、对话框、提示。
// 全站只有这一套样式来源。
import { useCallback, useEffect, useRef, useState } from "react";

export function Btn({ variant = "solid", className = "", ...rest }) {
  const base =
    "inline-flex items-center gap-2 rounded-full px-4 py-2 text-sm font-semibold transition " +
    "disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer";
  const styles = {
    solid: "bg-amber text-[#1a120a] hover:bg-amber2",
    ghost: "border border-line text-cream hover:border-amber",
    danger: "border border-warn text-warn hover:bg-warn/10",
  };
  return <button className={`${base} ${styles[variant]} ${className}`} {...rest} />;
}

export function Panel({ className = "", children }) {
  return (
    <div className={`rounded-2xl border border-line bg-panel p-6 ${className}`}>{children}</div>
  );
}

export function Chip({ on, className = "", ...rest }) {
  return (
    <button
      className={`rounded-full border px-3.5 py-1.5 text-sm cursor-pointer transition ${
        on ? "border-amber bg-amber text-[#1a120a]" : "border-[#6b5438] text-cream hover:bg-chip"
      } ${className}`}
      {...rest}
    />
  );
}

export function Bar({ pct, warn }) {
  return (
    <div className="h-[7px] overflow-hidden rounded-full bg-line">
      <div
        className={`h-full rounded-full transition-[width] duration-500 ${
          warn ? "bg-warn" : "bg-gradient-to-r from-amber to-amber2"
        }`}
        style={{ width: `${Math.max(0, Math.min(100, pct))}%` }}
      />
    </div>
  );
}

export function Field({ label, hint, children }) {
  return (
    <label className="block">
      <span className="mb-1.5 block text-[13px] text-muted">{label}</span>
      {children}
      {hint && <span className="mt-1.5 block text-xs text-muted">{hint}</span>}
    </label>
  );
}

export function Input({ className = "", ...rest }) {
  return (
    <input
      className={`w-full rounded-lg border border-line bg-bg px-3 py-2 text-cream
        outline-none focus:border-amber ${className}`}
      {...rest}
    />
  );
}

export function Select({ className = "", ...rest }) {
  return (
    <select
      className={`rounded-lg border border-line bg-bg px-3 py-2 text-cream
        outline-none focus:border-amber ${className}`}
      {...rest}
    />
  );
}

export function Modal({ open, onClose, title, sub, children, footer, wide }) {
  const ref = useRef(null);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    if (open && !el.open) el.showModal();
    if (!open && el.open) el.close();
  }, [open]);

  return (
    <dialog
      ref={ref}
      onCancel={(e) => {
        e.preventDefault();
        onClose();
      }}
      className={`rounded-2xl border border-line bg-panel p-6 text-cream backdrop:bg-black/60
        ${wide ? "w-[min(720px,94vw)]" : "w-[min(460px,94vw)]"} max-h-[88vh] overflow-auto`}
    >
      <h2 className="serif m-0 text-xl">{title}</h2>
      {sub && <p className="mt-1.5 mb-0 text-[13px] text-muted">{sub}</p>}
      <div className="mt-4 space-y-3">{children}</div>
      {footer && <div className="mt-6 flex justify-end gap-2">{footer}</div>}
    </dialog>
  );
}

export function useToast() {
  const [msg, setMsg] = useState(null);
  const toast = useCallback((text) => setMsg({ text }), []);
  const oops = useCallback((text) => setMsg({ text, bad: true }), []);
  useEffect(() => {
    if (!msg) return;
    const t = setTimeout(() => setMsg(null), 2600);
    return () => clearTimeout(t);
  }, [msg]);
  const node = msg ? (
    <div
      className={`rise fixed bottom-7 right-7 z-50 rounded-xl px-4 py-2.5 font-semibold shadow-lg ${
        msg.bad ? "bg-warn text-white" : "bg-amber text-[#1a120a]"
      }`}
    >
      {msg.text}
    </div>
  ) : null;
  return { toast, oops, node };
}

export function Empty({ children }) {
  return (
    <div className="rounded-2xl border border-dashed border-line py-14 text-center text-muted">
      {children}
    </div>
  );
}

export const g = (n) => (n == null ? "—" : `${Math.round(n)} g`);
export const money = (n) => (n == null ? "—" : `¥${Number(n).toFixed(n < 10 ? 1 : 0)}`);
// 克价：0.26 / 0.45 / 0.76 这种，money() 对小于 10 只留一位会把 0.45 收成 0.5
export const perG = (n) => (n == null ? null : `${Number(n).toFixed(2)} 元/g`);
