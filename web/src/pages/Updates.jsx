// 版本更新：用白话记下每次改了什么，给吧台的人看，不写术语。
import { CHANGELOG } from "../changelog.js";
import { Panel } from "../ui.jsx";

export default function Updates() {
  return (
    <>
      <header>
        <h1 className="serif m-0 text-3xl font-semibold">更新</h1>
        <p className="mt-2 mb-0 text-muted">每次上了什么，用白话记在最上面。</p>
      </header>
      <ol className="mt-6 mb-0 grid list-none gap-4 p-0 xl:grid-cols-2">
        {CHANGELOG.map((entry) => (
          <li key={`${entry.date}-${entry.title}`} className="min-w-0">
            <Panel className="h-full">
              <div className="text-[13px] text-amber">{entry.date}</div>
              <h2 className="serif mt-1 mb-0 text-xl">{entry.title}</h2>
              <ul className="mt-3 mb-0 list-disc space-y-1.5 pl-5 text-[15px] leading-relaxed text-cream">
                {entry.notes.map((note) => (
                  <li key={note}>{note}</li>
                ))}
              </ul>
            </Panel>
          </li>
        ))}
      </ol>
    </>
  );
}
