// 版本更新：用白话记下每次改了什么，给吧台的人看，不写术语。
import { CHANGELOG, groupByDate } from "../changelog.js";
import { Panel } from "../ui.jsx";

export default function Updates() {
  return (
    <>
      <header>
        <h1 className="serif m-0 text-2xl font-semibold md:text-3xl">更新</h1>
        <p className="mt-2 mb-0 text-muted">每次上了什么，用白话记在最上面。同一天写在一张卡片里。</p>
      </header>
      <ol className="mt-6 mb-0 flex list-none flex-col gap-4 p-0">
        {groupByDate(CHANGELOG).map((day) => (
          <li key={day.date}>
            <Panel>
              <div className="text-[13px] text-amber">{day.date}</div>
              <div className="mt-3 space-y-5">
                {day.items.map((entry) => (
                  <section key={entry.title}>
                    <h2 className="serif mt-0 mb-0 text-lg md:text-xl">{entry.title}</h2>
                    <ul className="mt-2 mb-0 list-disc space-y-1.5 pl-5 leading-relaxed text-cream">
                      {entry.notes.map((note) => (
                        <li key={note}>{note}</li>
                      ))}
                    </ul>
                  </section>
                ))}
              </div>
            </Panel>
          </li>
        ))}
      </ol>
    </>
  );
}
