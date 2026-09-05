// 细线描边图标，跟静图 _Doc/2026-09-04-ui-样张/画像.png 一套。
const base = {
  viewBox: "0 0 24 24",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 1.7,
  strokeLinecap: "round",
  strokeLinejoin: "round",
};

export const CupMark = ({ className = "" }) => (
  <svg {...base} className={className} strokeWidth={1.5}>
    <path d="M6 10h10v4.2A4.2 4.2 0 0 1 11.8 18.4h-.6A4.2 4.2 0 0 1 7 14.2V10z" />
    <path d="M16 11.2h2.2a2 2 0 0 1 0 4H16" />
    <path d="M9 5.2c.3.8.3 1.6 0 2.4M12 5.2c.3.8.3 1.6 0 2.4" />
    <path d="M5 20.4h13" />
  </svg>
);

export const Bean = ({ className = "" }) => (
  <svg {...base} className={className}>
    <ellipse cx="12" cy="12" rx="7.2" ry="8.4" transform="rotate(28 12 12)" />
    <path d="M8.6 16.4c2.6-1.2 4-4.6 3.2-8.2" />
  </svg>
);

export const Chart = ({ className = "" }) => (
  <svg {...base} className={className}>
    <path d="M4 20V6M4 20h16" />
    <path d="M8 17v-5M12.5 17V8.5M17 17v-3" />
  </svg>
);

export const Cart = ({ className = "" }) => (
  <svg {...base} className={className}>
    <path d="M3.5 4.5h2l2.2 9.4h9.6l2-6.6H7" />
    <circle cx="9.5" cy="18.5" r="1.4" />
    <circle cx="16.5" cy="18.5" r="1.4" />
  </svg>
);

export const Glass = ({ className = "" }) => (
  <svg {...base} className={className}>
    <path d="M8 4h8l-1.2 7.2A3.8 3.8 0 0 1 11 15h0a3.8 3.8 0 0 1-3.8-3.8L8 4z" />
    <path d="M12 15v4M9 20h6" />
  </svg>
);

export const People = ({ className = "" }) => (
  <svg {...base} className={className}>
    <circle cx="9.5" cy="8.5" r="3.2" />
    <path d="M3.8 19.4c.4-3 2.8-4.9 5.7-4.9s5.3 1.9 5.7 4.9" />
    <path d="M16 6.2a3 3 0 0 1 0 5.6M17.6 14.9c2 .6 3.4 2.3 3.6 4.5" />
  </svg>
);

export const Plus = ({ className = "" }) => (
  <svg {...base} className={className}>
    <path d="M12 5v14M5 12h14" />
  </svg>
);

export const Play = ({ className = "" }) => (
  <svg {...base} className={className}>
    <path d="M8 5.5l11 6.5L8 18.5z" />
  </svg>
);

export const Undo = ({ className = "" }) => (
  <svg {...base} className={className}>
    <path d="M4 9h10.5a4.5 4.5 0 0 1 0 9H8" />
    <path d="M7.5 5.5L4 9l3.5 3.5" />
  </svg>
);

export const Trash = ({ className = "" }) => (
  <svg {...base} className={className}>
    <path d="M4.5 7h15" />
    <path d="M9 7V5.2A1.2 1.2 0 0 1 10.2 4h3.6A1.2 1.2 0 0 1 15 5.2V7" />
    <path d="M6.5 7l.8 12.2A1.5 1.5 0 0 0 8.8 20.5h6.4a1.5 1.5 0 0 0 1.5-1.3L17.5 7" />
    <path d="M10 10.5v6M14 10.5v6" />
  </svg>
);
