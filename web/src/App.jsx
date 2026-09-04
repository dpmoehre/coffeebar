// 全端同一套功能，只换布局：宽屏侧栏 + 内容，窄屏收成顶部横排。
import { useCallback, useEffect, useState } from "react";

import { api } from "./api.js";
import { Bean, Cart, Chart, CupMark, People } from "./icons.jsx";
import { useToast } from "./ui.jsx";

import BeanCard from "./pages/BeanCard.jsx";
import Beans from "./pages/Beans.jsx";
import PeoplePage from "./pages/People.jsx";
import Restock from "./pages/Restock.jsx";
import Stats from "./pages/Stats.jsx";

const NAV = [
  { key: "beans", label: "豆子", Icon: Bean },
  { key: "restock", label: "补货", Icon: Cart },
  { key: "stats", label: "统计", Icon: Chart },
  { key: "people", label: "画像", Icon: People },
];

export default function App() {
  const [page, setPage] = useState("beans");
  const [beanId, setBeanId] = useState(null);
  const { toast, oops, node } = useToast();
  const [health, setHealth] = useState(null);

  useEffect(() => {
    api
      .beans()
      .then(() => setHealth("ok"))
      .catch(() => setHealth("down"));
  }, []);

  const openBean = useCallback((id) => {
    setBeanId(id);
    setPage("bean");
  }, []);

  const go = (key) => {
    setBeanId(null);
    setPage(key);
  };

  if (health === "down") {
    return (
      <div className="grid min-h-screen place-items-center p-8 text-center">
        <div>
          <CupMark className="mx-auto h-12 w-12 text-amber" />
          <h1 className="serif mt-4 text-2xl">coffeebar 没在运行</h1>
          <p className="mt-2 text-muted">
            先在小主机上双击 <code className="text-amber">start.bat</code>，再刷新这一页。
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen md:grid md:grid-cols-[252px_1fr]">
      <nav
        className="border-b border-line bg-[#100e0c] px-5 py-4 md:sticky md:top-0 md:h-screen
          md:border-b-0 md:border-r md:py-7"
      >
        <div className="mb-0 flex items-center gap-3 md:mb-8 md:flex-col md:gap-0">
          <CupMark className="h-9 w-9 text-amber md:h-12 md:w-12" />
          <div className="md:mt-2.5 md:text-center">
            <strong className="serif block text-base font-semibold tracking-[0.18em]">
              COFFEEBAR
            </strong>
            <em className="serif mt-1 hidden text-xs not-italic tracking-wider text-muted md:block">
              咖啡 · 记录 · 发现
            </em>
          </div>
          <div className="ml-auto flex gap-1 md:hidden">
            {NAV.map(({ key, Icon }) => (
              <button
                key={key}
                onClick={() => go(key)}
                className={`rounded-xl p-2 ${
                  page === key || (key === "beans" && page === "bean")
                    ? "bg-amber text-[#1a120a]"
                    : "text-muted"
                }`}
              >
                <Icon className="h-5 w-5" />
              </button>
            ))}
          </div>
        </div>

        <div className="hidden md:block">
          {NAV.map(({ key, label, Icon }) => {
            const on = page === key || (key === "beans" && page === "bean");
            return (
              <button
                key={key}
                onClick={() => go(key)}
                className={`mb-1 flex w-full cursor-pointer items-center gap-3 rounded-xl px-3.5
                  py-3 text-left transition ${
                    on
                      ? "bg-gradient-to-r from-amber to-[#a86e2e] font-semibold text-[#1a120a]"
                      : "text-muted hover:bg-chip hover:text-cream"
                  }`}
              >
                <Icon className="h-5 w-5 shrink-0" />
                {label}
              </button>
            );
          })}
        </div>
      </nav>

      <main className="min-w-0 max-w-[1480px] px-5 py-7 md:px-12 md:py-9">
        {page === "beans" && <Beans onOpen={openBean} toast={toast} oops={oops} />}
        {page === "bean" && (
          <BeanCard id={beanId} onBack={() => go("beans")} toast={toast} oops={oops} />
        )}
        {page === "restock" && <Restock onOpen={openBean} />}
        {page === "stats" && <Stats onOpenPerson={() => go("people")} />}
        {page === "people" && <PeoplePage toast={toast} oops={oops} />}
      </main>

      {node}
    </div>
  );
}
