// 全端同一套功能，只换布局：宽屏侧栏 + 内容，窄屏收成顶部横排。
import { useCallback, useEffect, useState } from "react";

import { api } from "./api.js";
import { Bean, Cart, Chart, CupMark, Glass, People } from "./icons.jsx";
import { Btn, Field, Input, useToast } from "./ui.jsx";

import BeanCard from "./pages/BeanCard.jsx";
import Beans from "./pages/Beans.jsx";
import PeoplePage from "./pages/People.jsx";
import Restock from "./pages/Restock.jsx";
import SpiritCard from "./pages/SpiritCard.jsx";
import Spirits from "./pages/Spirits.jsx";
import Stats from "./pages/Stats.jsx";

const NAV = [
  { key: "beans", label: "豆子", Icon: Bean },
  { key: "spirits", label: "酒水", Icon: Glass },
  { key: "restock", label: "补货", Icon: Cart },
  { key: "stats", label: "统计", Icon: Chart },
  { key: "people", label: "画像", Icon: People },
];

export default function App() {
  const [page, setPage] = useState("beans");
  const [beanId, setBeanId] = useState(null);
  const [spiritId, setSpiritId] = useState(null);
  const { toast, oops, node } = useToast();
  const [health, setHealth] = useState(null);
  const [me, setMe] = useState(undefined);

  useEffect(() => {
    api
      .health()
      .then(() => setHealth("ok"))
      .catch(() => setHealth("down"));
  }, []);

  useEffect(() => {
    if (health !== "ok") return;
    api
      .me()
      .then(setMe)
      .catch((e) => {
        if (e.status === 401) setMe(null);
        else setHealth("down");
      });
  }, [health]);

  const openBean = useCallback((id) => {
    setBeanId(id);
    setSpiritId(null);
    setPage("bean");
  }, []);

  const openSpirit = useCallback((id) => {
    setSpiritId(id);
    setBeanId(null);
    setPage("spirit");
  }, []);

  const go = (key) => {
    setBeanId(null);
    setSpiritId(null);
    setPage(key);
  };

  const navOn = (key) =>
    page === key || (key === "beans" && page === "bean") || (key === "spirits" && page === "spirit");

  if (health === null || (health === "ok" && me === undefined)) {
    return <p className="grid min-h-screen place-items-center text-muted">读取中…</p>;
  }

  if (health === "ok" && me === null) {
    return (
      <>
        <Gate
          onIn={(user) => setMe(user)}
          oops={oops}
        />
        {node}
      </>
    );
  }

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
            {me?.email && (
              <div className="mt-2 hidden text-[11px] text-muted md:block">{me.email}</div>
            )}
          </div>
          <div className="ml-auto flex gap-1 md:hidden">
            {NAV.map(({ key, Icon }) => (
              <button
                key={key}
                onClick={() => go(key)}
                className={`rounded-xl p-2 ${
                  navOn(key)
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
            const on = navOn(key);
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
          {me && (
            <button
              className="mt-4 text-left text-sm text-muted underline hover:text-amber"
              onClick={async () => {
                try {
                  await api.logout();
                  setMe(null);
                } catch (e) {
                  oops(e.message);
                }
              }}
            >
              退出
            </button>
          )}
        </div>
      </nav>

      <main className="min-w-0 max-w-[1480px] px-5 py-7 md:px-12 md:py-9">
        {page === "beans" && <Beans onOpen={openBean} toast={toast} oops={oops} />}
        {page === "bean" && (
          <BeanCard id={beanId} onBack={() => go("beans")} toast={toast} oops={oops} />
        )}
        {page === "spirits" && <Spirits onOpen={openSpirit} toast={toast} oops={oops} />}
        {page === "spirit" && (
          <SpiritCard id={spiritId} onBack={() => go("spirits")} toast={toast} oops={oops} />
        )}
        {page === "restock" && <Restock onOpen={openBean} />}
        {page === "stats" && <Stats onOpenPerson={() => go("people")} />}
        {page === "people" && <PeoplePage toast={toast} oops={oops} />}
      </main>

      {node}
    </div>
  );
}

function Gate({ onIn, oops }) {
  const [mode, setMode] = useState("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    setBusy(true);
    try {
      const user =
        mode === "register"
          ? await api.register(email, password)
          : await api.login(email, password);
      onIn(user);
    } catch (e) {
      oops(e.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="grid min-h-screen place-items-center p-8">
      <div className="w-full max-w-sm">
        <CupMark className="mx-auto h-12 w-12 text-amber" />
        <h1 className="serif mt-4 text-center text-2xl">
          {mode === "register" ? "建一个账号" : "登录 coffeebar"}
        </h1>
        <p className="mt-2 mb-6 text-center text-sm text-muted">
          {mode === "register"
            ? "第一个注册的人会接手这台机器上已有的豆和酒。"
            : "每人一份私库。豆、酒、进价只给自己看。"}
        </p>
        <Field label="邮箱">
          <Input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="you@example.com"
            autoFocus
          />
        </Field>
        <div className="mt-3">
          <Field label="密码" hint="至少 8 个字符">
            <Input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && submit()}
            />
          </Field>
        </div>
        <Btn className="mt-5 w-full justify-center" onClick={submit} disabled={busy || !email || password.length < 8}>
          {mode === "register" ? "注册并进入" : "登录"}
        </Btn>
        <button
          className="mt-4 w-full text-center text-sm text-amber underline"
          onClick={() => setMode(mode === "register" ? "login" : "register")}
        >
          {mode === "register" ? "已有账号，去登录" : "还没有账号，注册一个"}
        </button>
      </div>
    </div>
  );
}
