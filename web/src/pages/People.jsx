// 画像 + 人管理：可增、可改名、可停用（停用不删记录），每人一页追踪。
import { useEffect, useState } from "react";

import { api } from "../api.js";
import { Plus } from "../icons.jsx";
import { Bar, Btn, Chip, Empty, Field, Input, Modal, Panel, g, money } from "../ui.jsx";

export default function People({ toast, oops }) {
  const [people, setPeople] = useState([]);
  const [pickedId, setPicked] = useState(null);
  const [profile, setProfile] = useState(null);
  const [manage, setManage] = useState(false);

  const loadPeople = () =>
    api.people(true).then((d) => {
      setPeople(d.people);
      // 选中的人可能刚被删掉，落回第一个
      setPicked((cur) => (d.people.some((p) => p.id === cur) ? cur : (d.people[0]?.id ?? null)));
    });

  useEffect(() => {
    loadPeople();
  }, []);

  useEffect(() => {
    if (pickedId == null) return setProfile(null);
    setProfile(null);
    api.profile(pickedId).then(setProfile).catch((e) => oops(e.message));
  }, [pickedId, oops]);

  return (
    <>
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="serif m-0 text-3xl font-semibold">画像</h1>
          <p className="mt-2 mb-0 text-muted">按「谁喝的」自动汇总，不用另填问卷。</p>
        </div>
        <Btn variant="ghost" onClick={() => setManage(true)}>
          <Plus className="h-4 w-4" />
          管理「谁喝的」
        </Btn>
      </header>

      {people.length === 0 ? (
        <Empty>还没记过谁喝的。冲一次的时候打个名字，这里就有画像了。</Empty>
      ) : (
        <>
          <div className="mt-5 flex flex-wrap gap-2">
            {people
              .filter((p) => p.active)
              .map((p) => (
                <Chip key={p.id} on={p.id === pickedId} onClick={() => setPicked(p.id)}>
                  {p.name}
                </Chip>
              ))}
            {people.some((p) => !p.active) && (
              <>
                <span className="mx-1 h-5 w-px bg-line" />
                {people
                  .filter((p) => !p.active)
                  .map((p) => (
                    <Chip
                      key={p.id}
                      on={p.id === pickedId}
                      onClick={() => setPicked(p.id)}
                      className="opacity-50"
                    >
                      {p.name}
                    </Chip>
                  ))}
              </>
            )}
          </div>

          {profile && <Profile p={profile} />}
        </>
      )}

      <Manage
        open={manage}
        onClose={() => setManage(false)}
        people={people}
        reload={loadPeople}
        toast={toast}
        oops={oops}
      />
    </>
  );
}

function Profile({ p }) {
  const t = p.taste || {};
  return (
    <>
      <p className="serif mt-5 mb-6 max-w-[52ch] text-2xl leading-snug">
        {!p.enough_sample
          ? `${p.name} 才喝了 ${p.cups} 杯，还不够判断口味。`
          : summarize(p)}
      </p>

      <div className="grid gap-3.5 sm:grid-cols-2 lg:grid-cols-4">
        <Kpi label="喝掉的豆" value={Math.round(p.beans_g)} unit="g" hint={`${p.cups} 杯`} />
        <Kpi label="平均每杯" value={p.avg_dose_g ?? "—"} unit="g" hint="他自己的实际用量" />
        <Kpi label="喝掉的钱" value={money(p.spent).replace("¥", "")} unit="¥" hint="按单价快照摊" />
        <Kpi
          label="样本"
          value={p.cups}
          unit="杯"
          hint={p.enough_sample ? "够判断了" : "不足 3 杯"}
        />
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        <Panel>
          <div className="serif text-lg">口味倾向</div>
          <p className="mt-1 text-xs text-muted">
            从他喝过的豆子的杯测分加权来的，不是他自己打的分。
          </p>
          <div className="mt-4 space-y-3">
            {[
              ["酸质", t.acidity],
              ["甜感", t.sweetness],
              ["干香", t.dry],
            ].map(([label, v]) => (
              <div key={label}>
                <div className="flex justify-between text-[13px] text-muted">
                  <span>{label}</span>
                  <span>{v ?? "—"}</span>
                </div>
                <div className="mt-1">
                  <Bar pct={((v || 0) / 10) * 100} />
                </div>
              </div>
            ))}
          </div>
        </Panel>

        <Panel>
          <div className="serif text-lg">常喝</div>
          {p.top_beans.length === 0 ? (
            <p className="mt-3 text-muted">还没有。</p>
          ) : (
            <div className="mt-2">
              {p.top_beans.map((b) => (
                <div key={b.id} className="border-b border-line py-2.5 last:border-0">
                  <div className="flex justify-between gap-2 text-sm">
                    <span className="truncate">{b.name}</span>
                    <span className="whitespace-nowrap text-amber">
                      {b.cups} 杯 · {Math.round(b.beans_g)} g
                    </span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </Panel>
      </div>

      <Panel className="mt-4">
        <div className="serif text-lg">追踪记录</div>
        <p className="mt-1 mb-3 text-xs text-muted">划掉的是已撤回的，不进上面任何数字。</p>
        <div className="overflow-x-auto">
          <table className="w-full border-collapse text-sm">
            <thead>
              <tr className="text-muted">
                {["时间", "豆", "粉量", "钱"].map((h) => (
                  <th key={h} className="border-b border-line px-2 py-2 text-left font-normal">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {p.log.map((r) => (
                <tr key={r.id} className={r.voided_at ? "opacity-45 line-through" : ""}>
                  <td className="border-b border-line px-2 py-2 whitespace-nowrap">
                    {r.at.slice(5, 16)}
                  </td>
                  <td className="border-b border-line px-2 py-2">{r.bean_name}</td>
                  <td className="border-b border-line px-2 py-2 text-amber">{r.amount_g} g</td>
                  <td className="border-b border-line px-2 py-2 text-amber">
                    {r.unit_cost ? money(r.cost) : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>
    </>
  );
}

function summarize(p) {
  const top = p.top_beans[0];
  const t = p.taste || {};
  const bits = [];
  if ((t.acidity ?? 0) >= 7) bits.push("偏爱高酸");
  else if ((t.sweetness ?? 0) >= 7) bits.push("偏爱甜感足的");
  if (top) bits.push(`最常喝${top.name}`);
  bits.push(`一杯习惯用 ${p.avg_dose_g} g 粉`);
  return `${p.name}${bits.join("，")}。`;
}

function Kpi({ label, value, unit, hint }) {
  return (
    <div className="rise rounded-2xl border border-line bg-panel p-5">
      <div className="text-[13px] text-muted">{label}</div>
      <div className="serif mt-2 text-3xl leading-tight">
        {value}
        <small className="ml-1 text-base font-medium text-amber">{unit}</small>
      </div>
      <div className="mt-1.5 text-xs text-muted">{hint}</div>
    </div>
  );
}

function Manage({ open, onClose, people, reload, toast, oops }) {
  const [adding, setAdding] = useState("");
  const [edits, setEdits] = useState({});
  const [confirm, setConfirm] = useState(null);

  useEffect(() => {
    if (open) {
      setAdding("");
      setEdits({});
      setConfirm(null);
    }
  }, [open]);

  const save = async (p) => {
    const name = (edits[p.id] ?? p.name).trim();
    if (!name || name === p.name) return;
    try {
      await api.patchPerson(p.id, { name });
      toast(`改名不动历史：${p.name} → ${name}`);
      reload();
    } catch (e) {
      oops(e.message);
    }
  };

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="管理「谁喝的」"
      sub="改名只改一处，历史记录跟着变。停用只是从选人列表里收起来；删除会把这个人彻底移走。"
      footer={
        <Btn variant="ghost" onClick={onClose}>
          关闭
        </Btn>
      }
    >
      <div>
        {people.map((p) => (
          <div key={p.id} className="border-b border-line py-2 last:border-0">
            <div className="flex items-center gap-2">
              <Input
                value={edits[p.id] ?? p.name}
                onChange={(e) => setEdits({ ...edits, [p.id]: e.target.value })}
                onBlur={() => save(p)}
                className={p.active ? "" : "opacity-50"}
              />
              <button
                className="shrink-0 text-xs text-muted underline hover:text-amber"
                onClick={async () => {
                  await api.patchPerson(p.id, { active: !p.active });
                  toast(p.active ? `${p.name} 已收起，记录保留` : `${p.name} 已恢复`);
                  reload();
                }}
              >
                {p.active ? "停用" : "恢复"}
              </button>
              <button
                className="shrink-0 text-xs text-muted underline hover:text-warn"
                onClick={() => setConfirm(p)}
              >
                删除
              </button>
            </div>
            <div className="mt-1 text-xs text-muted">
              {p.cups ? `${p.cups} 条记录` : "还没有记录"}
              {!p.active && " · 已停用"}
            </div>
          </div>
        ))}
      </div>

      <Modal
        open={!!confirm}
        onClose={() => setConfirm(null)}
        title={`删除「${confirm?.name}」？`}
        footer={
          <>
            <Btn variant="ghost" onClick={() => setConfirm(null)}>
              不删了
            </Btn>
            <Btn
              variant="danger"
              onClick={async () => {
                const p = confirm;
                setConfirm(null);
                try {
                  const out = await api.deletePerson(p.id);
                  toast(
                    out.orphaned
                      ? `${out.name} 已删除，${out.orphaned} 条记录变成「没记」`
                      : `${out.name} 已删除`
                  );
                  reload();
                } catch (e) {
                  oops(e.message);
                }
              }}
            >
              删除
            </Btn>
          </>
        }
      >
        <p className="text-muted">
          {confirm?.cups
            ? `他名下有 ${confirm.cups} 条记录。这些豆是真扣过的、钱也真花了，所以记录会留下来，只是变成「没记」——库存和统计总数不变，只有按人拆分里少了他。`
            : "他还没有任何记录，删掉不影响任何数字。"}
        </p>
        {confirm?.cups > 0 && (
          <p className="text-muted">
            想把这些记录留给别人，先在流水里逐条「改归属」挪走，再回来删。只是暂时不想看见他的话，用「停用」就行。
          </p>
        )}
      </Modal>

      <Field label="新增" hint="打个名字就有这个人">
        <div className="flex gap-2">
          <Input value={adding} onChange={(e) => setAdding(e.target.value)} placeholder="戚浩辰" />
          <Btn
            onClick={async () => {
              if (!adding.trim()) return;
              try {
                await api.addPerson(adding.trim());
                toast(`已添加 ${adding.trim()}`);
                setAdding("");
                reload();
              } catch (e) {
                oops(e.message);
              }
            }}
            disabled={!adding.trim()}
          >
            添加
          </Btn>
        </div>
      </Field>
    </Modal>
  );
}
