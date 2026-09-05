// 全端同一套功能，只换布局：宽屏侧栏 + 内容，窄屏收成顶部横排。
import { useCallback, useEffect, useState } from "react";

import { api } from "./api.js";
import { Bean, Cart, Chart, CupMark, Glass, People } from "./icons.jsx";
import { Btn, Field, Input, Modal, useToast } from "./ui.jsx";

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
  const [bye, setBye] = useState(false);
  const [byeEmail, setByeEmail] = useState("");
  const [byePass, setByePass] = useState("");
  const [byeBusy, setByeBusy] = useState(false);

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

  const signOut = async () => {
    try {
      await api.logout();
      setMe(null);
    } catch (e) {
      oops(e.message);
    }
  };

  const wipeAccount = async () => {
    setByeBusy(true);
    try {
      await api.deleteAccount(byeEmail, byePass);
      setBye(false);
      setByeEmail("");
      setByePass("");
      setMe(null);
    } catch (e) {
      oops(e.message);
    } finally {
      setByeBusy(false);
    }
  };

  const navOn = (key) =>
    page === key || (key === "beans" && page === "bean") || (key === "spirits" && page === "spirit");

  const gateLink =
    typeof window !== "undefined" &&
    (new URLSearchParams(window.location.search).get("verify") ||
      new URLSearchParams(window.location.search).get("reset"));

  if (health === null || (health === "ok" && me === undefined && !gateLink)) {
    return <p className="grid min-h-screen place-items-center text-muted">读取中…</p>;
  }

  if (health === "ok" && (me === null || gateLink)) {
    return (
      <>
        <Gate onIn={setMe} oops={oops} toast={toast} />
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
              <div className="mt-2 hidden text-[11px] text-muted md:block">
                {me.email}
                {me.email_verified === false && (
                  <button
                    className="mt-1 block text-amber underline"
                    onClick={async () => {
                      try {
                        const out = await api.resendVerify();
                        if (out.verify_url) window.location.href = out.verify_url;
                        else toast("验证信已发出");
                      } catch (e) {
                        oops(e.message);
                      }
                    }}
                  >
                    邮箱还没验证，再发一封
                  </button>
                )}
              </div>
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
        {me && (
          <div className="mt-3 flex gap-4 text-xs text-muted md:hidden">
            <button className="underline hover:text-amber" onClick={signOut}>
              退出
            </button>
            <button className="underline hover:text-warn" onClick={() => setBye(true)}>
              注销账号
            </button>
          </div>
        )}

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
            <div className="mt-4 flex flex-col items-start gap-2">
              <button
                className="text-left text-sm text-muted underline hover:text-amber"
                onClick={signOut}
              >
                退出
              </button>
              <button
                className="text-left text-sm text-muted underline hover:text-warn"
                onClick={() => setBye(true)}
              >
                注销账号
              </button>
            </div>
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
      <Modal
        open={bye}
        onClose={() => !byeBusy && setBye(false)}
        title="注销账号"
        sub="会删掉你的豆、酒、照片和流水，不可恢复。别人的库不动。小主机上若这是接手真库存的那个号，注销等于清掉吧台账本。"
        footer={
          <>
            <Btn variant="ghost" onClick={() => setBye(false)} disabled={byeBusy}>
              取消
            </Btn>
            <Btn
              variant="danger"
              onClick={wipeAccount}
              disabled={byeBusy || !byeEmail || byePass.length < 8}
            >
              确认注销
            </Btn>
          </>
        }
      >
        <Field label="再输入一遍邮箱">
          <Input
            type="email"
            value={byeEmail}
            onChange={(e) => setByeEmail(e.target.value)}
            placeholder={me?.email || ""}
          />
        </Field>
        <Field label="密码">
          <Input
            type="password"
            value={byePass}
            onChange={(e) => setByePass(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && wipeAccount()}
          />
        </Field>
      </Modal>
    </div>
  );
}

function gateQuery() {
  const q = new URLSearchParams(window.location.search);
  return { verify: q.get("verify"), reset: q.get("reset") };
}

function clearGateQuery() {
  window.history.replaceState({}, "", window.location.pathname || "/");
}

function Gate({ onIn, oops, toast }) {
  const q = gateQuery();
  const [mode, setMode] = useState(q.reset ? "reset" : q.verify ? "verify" : "login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [password2, setPassword2] = useState("");
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState("");
  const [devLink, setDevLink] = useState("");

  useEffect(() => {
    if (mode !== "verify" || !q.verify) return;
    setBusy(true);
    api
      .verify(q.verify)
      .then((user) => {
        clearGateQuery();
        toast?.("邮箱已验证");
        onIn(user);
      })
      .catch((e) => {
        oops(e.message);
        clearGateQuery();
        setMode("login");
      })
      .finally(() => setBusy(false));
  }, []);

  const submit = async () => {
    setBusy(true);
    setNote("");
    setDevLink("");
    try {
      if (mode === "forgot") {
        const out = await api.forgot(email);
        setNote("如果这个邮箱有账号，就发了一封重设信。本机没配邮箱时，下面会直接出链接。");
        if (out.reset_url) setDevLink(out.reset_url);
        return;
      }
      if (mode === "reset") {
        if (password !== password2) {
          oops("两次密码不一样");
          return;
        }
        await api.reset(q.reset, password);
        clearGateQuery();
        toast?.("密码已改，用新密码登录");
        setPassword("");
        setPassword2("");
        setMode("login");
        onIn(null);
        return;
      }
      const user =
        mode === "register"
          ? await api.register(email, password)
          : await api.login(email, password);
      if (user.verify_url) {
        toast?.("本机没配邮箱，打开验证链接即可");
        setDevLink(user.verify_url);
      }
      onIn(user);
    } catch (e) {
      oops(e.message);
    } finally {
      setBusy(false);
    }
  };

  const title = {
    login: "登录 coffeebar",
    register: "建一个账号",
    forgot: "忘记密码",
    reset: "设新密码",
    verify: "正在验证邮箱…",
  }[mode];
  const sub = {
    login: "每人一份私库。豆、酒、进价只给自己看。",
    register: "第一个注册的人会接手这台机器上已有的豆和酒。",
    forgot: "填注册时的邮箱。有这个账号就发重设链接。",
    reset: "新密码至少 8 个字符。改完要重新登录。",
    verify: "请稍等。",
  }[mode];

  const canSubmit =
    mode === "forgot"
      ? Boolean(email)
      : mode === "reset"
        ? password.length >= 8 && password === password2
        : Boolean(email) && password.length >= 8;

  return (
    <div className="grid min-h-screen place-items-center p-8">
      <div className="w-full max-w-sm">
        <CupMark className="mx-auto h-12 w-12 text-amber" />
        <h1 className="serif mt-4 text-center text-2xl">{title}</h1>
        <p className="mt-2 mb-6 text-center text-sm text-muted">{sub}</p>
        {mode !== "reset" && mode !== "verify" && (
          <Field label="邮箱">
            <Input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@example.com"
              autoFocus
            />
          </Field>
        )}
        {(mode === "login" || mode === "register" || mode === "reset") && (
          <div className={mode === "reset" ? "" : "mt-3"}>
            <Field label={mode === "reset" ? "新密码" : "密码"} hint="至少 8 个字符">
              <Input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && mode !== "reset" && submit()}
              />
            </Field>
          </div>
        )}
        {mode === "reset" && (
          <div className="mt-3">
            <Field label="再输一次">
              <Input
                type="password"
                value={password2}
                onChange={(e) => setPassword2(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && submit()}
              />
            </Field>
          </div>
        )}
        {mode !== "verify" && (
          <Btn
            className="mt-5 w-full justify-center"
            onClick={submit}
            disabled={busy || !canSubmit}
          >
            {mode === "register" ? "注册并进入" : mode === "forgot" ? "发送重设链接" : mode === "reset" ? "保存新密码" : "登录"}
          </Btn>
        )}
        {note && <p className="mt-4 text-center text-sm text-muted">{note}</p>}
        {devLink && (
          <a className="mt-3 block text-center text-sm text-amber underline" href={devLink}>
            本机没配邮箱，点这里继续
          </a>
        )}
        {mode === "login" && (
          <button
            className="mt-4 w-full text-center text-sm text-muted underline hover:text-amber"
            onClick={() => setMode("forgot")}
          >
            忘记密码
          </button>
        )}
        {(mode === "login" || mode === "register" || mode === "forgot") && (
          <button
            className="mt-3 w-full text-center text-sm text-amber underline"
            onClick={() => setMode(mode === "register" ? "login" : "register")}
          >
            {mode === "register" ? "已有账号，去登录" : "还没有账号，注册一个"}
          </button>
        )}
        {(mode === "forgot" || mode === "reset") && (
          <button
            className="mt-3 w-full text-center text-sm text-amber underline"
            onClick={() => {
              clearGateQuery();
              setMode("login");
            }}
          >
            回到登录
          </button>
        )}
      </div>
    </div>
  );
}
