// 推荐酒单：上架纯饮或鸡尾酒，从这里倒一杯（可改实际毫升）。
import { useCallback, useEffect, useRef, useState } from "react";

import { api } from "../api.js";
import { Plus } from "../icons.jsx";
import { Btn, Chip, Empty, Field, Input, Modal, Select, money } from "../ui.jsx";

function linePreview(item) {
  return (item.lines || [])
    .map((ln) => `${ln.spirit_name} ${Number(ln.amount_ml)} ml`)
    .join(" · ");
}

export default function Menu({ onOpenSpirit, toast, oops }) {
  const [items, setItems] = useState(null);
  const [spirits, setSpirits] = useState([]);
  const [recipes, setRecipes] = useState([]);
  const [people, setPeople] = useState([]);
  const [edit, setEdit] = useState(false);
  const [pour, setPour] = useState(null);
  const [addingNeat, setAddingNeat] = useState(false);
  const [recipeOpen, setRecipeOpen] = useState(false);
  const [editing, setEditing] = useState(null);
  const [lockInfo, setLockInfo] = useState(null);
  const [q, setQ] = useState("");
  const holding = useRef(false);
  const heldRecipe = useRef(null);

  function releaseHeld() {
    const rid = heldRecipe.current;
    if (!rid || !holding.current) return;
    holding.current = false;
    heldRecipe.current = null;
    api.unlock(`recipe:${rid}`).catch(() => {});
  }

  useEffect(() => {
    const t = setInterval(async () => {
      const rid = heldRecipe.current;
      if (!holding.current || !rid) return;
      try {
        await api.heartbeat(`recipe:${rid}`);
      } catch (e) {
        holding.current = false;
        heldRecipe.current = null;
        if (e.status === 409) oops(e.message);
      }
    }, 60000);
    return () => {
      clearInterval(t);
      releaseHeld();
    };
  }, [oops]);

  async function lockRecipe(rid) {
    if (heldRecipe.current && heldRecipe.current !== rid) releaseHeld();
    await api.lock(`recipe:${rid}`);
    holding.current = true;
    heldRecipe.current = rid;
  }

  async function openEdit(item) {
    try {
      await lockRecipe(item.recipe_id);
      setEditing(item);
    } catch (e) {
      if (e.isLocked && e.body.can_take_over) {
        setLockInfo({ ...e.body, item });
      } else {
        oops(e.message);
      }
    }
  }

  function closeRecipe() {
    releaseHeld();
    setEditing(null);
    setRecipeOpen(false);
  }

  const load = useCallback(() => {
    api.menu(false).then((d) => setItems(d.items)).catch((e) => oops(e.message));
    api.recipes().then((d) => setRecipes(d.recipes || [])).catch((e) => oops(e.message));
  }, [oops]);

  useEffect(() => {
    load();
    api.spirits("all").then((d) => setSpirits(d.spirits || [])).catch((e) => oops(e.message));
    api.people().then((d) => setPeople(d.people || [])).catch((e) => oops(e.message));
  }, [load, oops]);

  const shown = (items || []).filter((it) => {
    if (!edit && !it.listed) return false;
    const needle = q.trim().toLowerCase();
    if (!needle) return true;
    const blob = [it.name, it.kind === "neat" ? "纯饮" : "鸡尾酒", it.steps, linePreview(it)]
      .filter(Boolean)
      .join(" ")
      .toLowerCase();
    return blob.includes(needle);
  });
  const usedSpirit = new Set((items || []).filter((it) => it.kind === "neat").map((it) => it.spirit_id));
  const unused = spirits.filter((s) => !usedSpirit.has(s.id));

  async function move(id, dir) {
    const ids = items.map((it) => it.id);
    const i = ids.indexOf(id);
    const j = i + dir;
    if (j < 0 || j >= ids.length) return;
    [ids[i], ids[j]] = [ids[j], ids[i]];
    try {
      const out = await api.reorderMenu(ids);
      setItems(out.items);
    } catch (e) {
      oops(e.message);
    }
  }

  return (
    <>
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="serif m-0 text-2xl font-semibold md:text-3xl">酒单</h1>
          <p className="mt-2 mb-0 text-muted">
            今晚出品。纯饮点了直接倒；鸡尾酒按配方扣各瓶，毫升都能改。同类有好几支时当场选要用哪一支。
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Chip on={!edit} onClick={() => setEdit(false)}>
            出品
          </Chip>
          <Chip on={edit} onClick={() => setEdit(true)}>
            编辑
          </Chip>
        </div>
      </header>

      <div className="mt-5">
        <Input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="搜酒单、材料…"
          className="max-w-xs py-1.5 text-sm"
        />
      </div>

      {edit && (
        <div className="mt-5 flex flex-wrap gap-2">
          <Btn onClick={() => setAddingNeat(true)} disabled={unused.length === 0}>
            <Plus className="h-4 w-4" />
            上架纯饮
          </Btn>
          <Btn variant="ghost" onClick={() => setRecipeOpen(true)}>
            <Plus className="h-4 w-4" />
            上架鸡尾酒
          </Btn>
        </div>
      )}

      <div className="mt-6 space-y-3">
        {shown.map((it) => (
          <article
            key={it.id}
            className="rounded-2xl border border-line bg-panel p-4"
          >
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <strong className="serif text-lg font-medium">{it.name}</strong>
                  <span className="text-xs text-muted">{it.kind === "neat" ? "纯饮" : "鸡尾酒"}</span>
                  {!it.listed && <span className="text-xs text-warn">已下架</span>}
                </div>
                <p className="mt-1 mb-0 text-[13px] text-muted">{linePreview(it) || "还没写材料"}</p>
                {it.steps && <p className="mt-1 mb-0 text-[13px] text-muted">{it.steps}</p>}
                {!it.enough && (
                  <p className="mt-1 mb-0 text-[13px] text-warn">有基酒不够默认用量，倒的时候改毫升或换瓶。</p>
                )}
              </div>
              <div className="flex flex-wrap gap-2">
                {!edit && (
                  <Btn onClick={() => setPour(it)} disabled={!it.lines?.length}>
                    倒一杯
                  </Btn>
                )}
                {edit && (
                  <>
                    {it.kind === "cocktail" && it.recipe_id && (
                      <button className="text-sm text-muted underline" onClick={() => openEdit(it)}>
                        改配方
                      </button>
                    )}
                    <button className="text-sm text-muted underline" onClick={() => move(it.id, -1)}>
                      上移
                    </button>
                    <button className="text-sm text-muted underline" onClick={() => move(it.id, 1)}>
                      下移
                    </button>
                    <button
                      className="text-sm text-amber underline"
                      onClick={async () => {
                        try {
                          const row = await api.patchMenuItem(it.id, { listed: !it.listed });
                          setItems((cur) => cur.map((x) => (x.id === it.id ? row : x)));
                          toast(row.listed ? `「${it.name}」上架了` : `「${it.name}」下架了`);
                        } catch (e) {
                          oops(e.message);
                        }
                      }}
                    >
                      {it.listed ? "下架" : "上架"}
                    </button>
                    <button
                      className="text-sm text-warn underline"
                      onClick={async () => {
                        if (!window.confirm(`从酒单拿掉「${it.name}」？配方还在，只是不摆了。`)) return;
                        try {
                          await api.deleteMenuItem(it.id);
                          setItems((cur) => cur.filter((x) => x.id !== it.id));
                          toast(`已拿掉「${it.name}」`);
                        } catch (e) {
                          oops(e.message);
                        }
                      }}
                    >
                      拿掉
                    </button>
                  </>
                )}
              </div>
            </div>
          </article>
        ))}
      </div>

      {items && shown.length === 0 && (
        <Empty>
          {q.trim()
            ? "没有对得上的酒单。"
            : edit
              ? "还没有条目。上架一支纯饮，或写一款鸡尾酒。"
              : "酒单是空的。点「编辑」把今晚要出的酒摆上来。"}
        </Empty>
      )}

      <PourModal
        item={pour}
        people={people}
        onClose={() => setPour(null)}
        onOpenSpirit={onOpenSpirit}
        toast={toast}
        oops={oops}
        onDone={() => {
          setPour(null);
          load();
        }}
      />

      <AddNeat
        open={addingNeat}
        unused={unused}
        onClose={() => setAddingNeat(false)}
        onDone={(row) => {
          setItems((cur) => [...(cur || []), row]);
          setAddingNeat(false);
          toast(`「${row.name}」摆上酒单了`);
        }}
        oops={oops}
      />

      <RecipeModal
        open={recipeOpen || !!editing}
        item={editing}
        spirits={spirits}
        recipes={recipes}
        listedRecipeIds={new Set((items || []).filter((it) => it.kind === "cocktail").map((it) => it.recipe_id))}
        onLockRecipe={async (rid) => {
          if (!rid) {
            releaseHeld();
            return;
          }
          await lockRecipe(rid);
        }}
        onClose={closeRecipe}
        onDone={(row) => {
          if (editing) {
            toast(`「${row.name}」配方改好了`);
            closeRecipe();
            load();
          } else {
            setRecipeOpen(false);
            toast(`「${row.name}」摆上酒单了`);
            load();
          }
        }}
        oops={oops}
      />

      <Modal
        open={!!lockInfo}
        onClose={() => setLockInfo(null)}
        title="另一处正在改这款配方"
        footer={
          <>
            <Btn variant="ghost" onClick={() => setLockInfo(null)}>
              先不动
            </Btn>
            <Btn
              onClick={async () => {
                const item = lockInfo.item;
                setLockInfo(null);
                try {
                  await api.lock(`recipe:${item.recipe_id}`, true);
                  holding.current = true;
                  heldRecipe.current = item.recipe_id;
                  setEditing(item);
                } catch (e) {
                  oops(e.message);
                }
              }}
            >
              接管
            </Btn>
          </>
        }
      >
        <p className="text-muted">{lockInfo?.message}</p>
      </Modal>
    </>
  );
}

function AddNeat({ open, unused, onClose, onDone, oops }) {
  const [sid, setSid] = useState("");
  useEffect(() => {
    if (open) setSid(unused[0]?.id ? String(unused[0].id) : "");
  }, [open, unused]);
  return (
    <Modal
      open={open}
      onClose={onClose}
      title="上架纯饮"
      sub="从酒库挑一支，倒的时候默认 30 ml，能改。"
      footer={
        <>
          <Btn variant="ghost" onClick={onClose}>
            取消
          </Btn>
          <Btn
            disabled={!sid}
            onClick={async () => {
              try {
                onDone(await api.addMenuItem({ kind: "neat", spirit_id: Number(sid) }));
              } catch (e) {
                oops(e.message);
              }
            }}
          >
            摆上酒单
          </Btn>
        </>
      }
    >
      <Field label="基酒">
        <Select value={sid} onChange={(e) => setSid(e.target.value)}>
          {unused.map((s) => (
            <option key={s.id} value={s.id}>
              {s.name}
              {s.balance_ml != null ? ` · 剩 ${Math.round(s.balance_ml)} ml` : ""}
            </option>
          ))}
        </Select>
      </Field>
    </Modal>
  );
}

function fillLines(src) {
  const rows = src || [];
  if (!rows.length) return [{ spirit_id: "", spirit_name: "", amount_ml: "30" }];
  return rows.map((ln) => ({
    spirit_id: ln.spirit_id ? String(ln.spirit_id) : "",
    spirit_name: ln.spirit_name || "",
    amount_ml: String(ln.amount_ml ?? 30),
  }));
}

function spiritChoices(spirits, lines) {
  const seen = new Set();
  const out = [];
  for (const s of spirits || []) {
    if (seen.has(s.id)) continue;
    seen.add(s.id);
    out.push(s);
  }
  for (const ln of lines || []) {
    const id = Number(ln.spirit_id);
    if (!id || seen.has(id)) continue;
    seen.add(id);
    out.push({ id, name: ln.spirit_name || `酒 #${id}` });
  }
  return out;
}

function RecipeModal({
  open,
  item,
  spirits,
  recipes = [],
  listedRecipeIds = new Set(),
  onLockRecipe,
  onClose,
  onDone,
  oops,
}) {
  const [name, setName] = useState("");
  const [steps, setSteps] = useState("");
  const [lines, setLines] = useState([{ spirit_id: "", spirit_name: "", amount_ml: "30" }]);
  const [pickedId, setPickedId] = useState("");
  const editing = !!item;
  const unusedRecipes = (recipes || []).filter((r) => !listedRecipeIds.has(r.id));
  const choices = spiritChoices(spirits, [
    ...lines,
    ...(item?.lines || []),
    ...unusedRecipes.flatMap((r) => r.lines || []),
  ]);

  useEffect(() => {
    if (!open) return;
    setPickedId("");
    if (item) {
      setName(item.name || "");
      setSteps(item.steps || "");
      setLines(fillLines(item.lines));
      return;
    }
    setName("");
    setSteps("");
    setLines([{ spirit_id: "", spirit_name: "", amount_ml: "30" }]);
  }, [open, item]);

  async function pickRecipe(id) {
    if (!id) {
      setPickedId("");
      setName("");
      setSteps("");
      setLines([{ spirit_id: "", spirit_name: "", amount_ml: "30" }]);
      try {
        await onLockRecipe?.(null);
      } catch (e) {
        oops(e.message);
      }
      return;
    }
    const rec = recipes.find((r) => String(r.id) === id);
    if (!rec) return;
    try {
      await onLockRecipe?.(rec.id);
      setPickedId(id);
      setName(rec.name || "");
      setSteps(rec.steps || "");
      setLines(fillLines(rec.lines));
    } catch (e) {
      oops(e.message);
    }
  }

  return (
    <Modal
      open={open}
      onClose={onClose}
      wide
      title={editing ? "改配方" : "上架鸡尾酒"}
      sub={
        editing
          ? "名字、步骤、基酒和默认毫升都能改，一次保存。已经倒过的巡不会跟着改。"
          : "可以先选已有配方，再换里面的基酒，一起保存摆上酒单。冰块汤力写在步骤里，不扣库存。"
      }
      footer={
        <>
          <Btn variant="ghost" onClick={onClose}>
            取消
          </Btn>
          <Btn
            disabled={!name.trim() || lines.some((ln) => !ln.spirit_id || !(Number(ln.amount_ml) > 0))}
            onClick={async () => {
              try {
                const payload = {
                  name: name.trim(),
                  steps: steps.trim() || undefined,
                  lines: lines.map((ln, i) => ({
                    spirit_id: Number(ln.spirit_id),
                    amount_ml: Number(ln.amount_ml),
                    sort: i,
                  })),
                };
                if (editing) {
                  onDone(await api.updateRecipe(item.recipe_id, payload));
                  return;
                }
                if (pickedId) {
                  await api.updateRecipe(Number(pickedId), payload);
                  onDone(await api.addMenuItem({ kind: "cocktail", recipe_id: Number(pickedId) }));
                  return;
                }
                const rec = await api.createRecipe(payload);
                onDone(await api.addMenuItem({ kind: "cocktail", recipe_id: rec.id }));
              } catch (e) {
                oops(e.message);
              }
            }}
          >
            {editing ? "保存" : "摆上酒单"}
          </Btn>
        </>
      }
    >
      <div className="space-y-3">
        {!editing && unusedRecipes.length > 0 && (
          <Field label="用已有配方" hint="选了之后下面的基酒都能换，保存时一起改掉。">
            <Select className="w-full" value={pickedId} onChange={(e) => pickRecipe(e.target.value)}>
              <option value="">写新的</option>
              {unusedRecipes.map((r) => (
                <option key={r.id} value={r.id}>
                  {r.name}
                  {r.lines?.length ? ` · ${linePreview(r)}` : ""}
                </option>
              ))}
            </Select>
          </Field>
        )}
        <Field label="名字">
          <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="威士忌酸" />
        </Field>
        <Field label="步骤 / 辅料（可选）">
          <Input value={steps} onChange={(e) => setSteps(e.target.value)} placeholder="摇壶，加柠檬，不加苏打" />
        </Field>
        {lines.map((ln, i) => (
          <div key={i} className="grid grid-cols-[1fr_90px_auto] items-end gap-2">
            <Field label={`基酒 ${lines.length > 1 ? i + 1 : ""}`.trim()}>
              <Select
                className="w-full"
                value={ln.spirit_id}
                onChange={(e) =>
                  setLines((cur) => cur.map((x, j) => (j === i ? { ...x, spirit_id: e.target.value } : x)))
                }
              >
                <option value="">选一支</option>
                {choices.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.name}
                    {s.balance_ml != null ? ` · 剩 ${Math.round(s.balance_ml)} ml` : ""}
                  </option>
                ))}
              </Select>
            </Field>
            <Field label="毫升">
              <Input
                type="number"
                min="1"
                step="1"
                value={ln.amount_ml}
                onChange={(e) =>
                  setLines((cur) => cur.map((x, j) => (j === i ? { ...x, amount_ml: e.target.value } : x)))
                }
              />
            </Field>
            {lines.length > 1 ? (
              <button
                className="mb-1 text-xs text-warn underline"
                onClick={() => setLines((cur) => cur.filter((_, j) => j !== i))}
              >
                去掉
              </button>
            ) : (
              <span />
            )}
          </div>
        ))}
        <button
          className="text-sm text-amber underline"
          onClick={() => setLines((cur) => [...cur, { spirit_id: "", spirit_name: "", amount_ml: "20" }])}
        >
          再加一支基酒
        </button>
      </div>
    </Modal>
  );
}

function lastPeople() {
  try {
    const raw = JSON.parse(localStorage.getItem("coffeebar-last-people") || "[]");
    if (Array.isArray(raw)) return raw.filter((x) => typeof x === "string" && x);
  } catch {
    /* ignore */
  }
  const one = localStorage.getItem("coffeebar-last-person");
  return one ? [one] : [];
}

function PourModal({ item, people, onClose, onOpenSpirit, toast, oops, onDone }) {
  const [picked, setPicked] = useState([]);
  const [draft, setDraft] = useState("");
  const [rows, setRows] = useState([]);
  const [needs, setNeeds] = useState(null);

  useEffect(() => {
    if (!item) return;
    setPicked(lastPeople());
    setDraft("");
    setNeeds(null);
    setRows(
      (item.lines || []).map((ln) => ({
        spirit_id: ln.spirit_id,
        spirit_name: ln.spirit_name,
        kind: ln.kind,
        amount_ml: String(ln.amount_ml),
        lot_id: ln.open_lots?.length === 1 ? ln.open_lots[0].lot_id : "",
        lots: ln.open_lots || [],
        balance_ml: ln.balance_ml,
        alts: ln.alts || [],
      }))
    );
  }, [item]);

  if (!item) return null;

  const names = [...new Set([...people.map((p) => p.name), ...picked])];
  const cups = Math.max(picked.length, 1);

  function toggle(name) {
    setPicked((cur) => (cur.includes(name) ? cur.filter((x) => x !== name) : [...cur, name]));
  }

  function addDraft() {
    const n = draft.trim();
    if (!n) return;
    setPicked((cur) => (cur.includes(n) ? cur : [...cur, n]));
    setDraft("");
  }

  return (
    <Modal
      open={!!item}
      onClose={onClose}
      title={`${cups > 1 ? `倒 ${cups} 杯` : "倒一杯"} · ${item.name}`}
      sub={
        item.kind === "neat"
          ? "纯饮，毫升按这次实际倒的填。多选人名就是一人一杯。"
          : "按配方预填。同类有好几支就选要用哪一支，毫升也能改。多选人名就是一人一杯。"
      }
      footer={
        <>
          <Btn variant="ghost" onClick={onClose}>
            取消
          </Btn>
          <Btn
            disabled={rows.some(
              (r) => !(Number(r.amount_ml) > 0) || (r.lots.length > 1 && !r.lot_id)
            )}
            onClick={async () => {
              try {
                const out = await api.pourMenu({
                  menu_item_id: item.id,
                  people: picked,
                  lines: rows.map((r) => ({
                    spirit_id: r.spirit_id,
                    amount_ml: Number(r.amount_ml),
                    lot_id: r.lot_id ? Number(r.lot_id) : undefined,
                  })),
                });
                if (out.error) {
                  setNeeds(out.needs || []);
                  const by = Object.fromEntries((out.needs || []).map((n) => [n.spirit_id, n.lots]));
                  setRows((cur) =>
                    cur.map((r) => (by[r.spirit_id] ? { ...r, lots: by[r.spirit_id], lot_id: "" } : r))
                  );
                  oops(out.error);
                  return;
                }
                localStorage.setItem("coffeebar-last-people", JSON.stringify(picked));
                if (picked[0]) localStorage.setItem("coffeebar-last-person", picked[0]);
                const who = picked.length ? picked.join("、") : "没记谁";
                const n = out.cups || out.serves?.length || 1;
                toast(
                  `${who} · ${item.name} · ${n} 杯 · ${out.amount_ml} ml${
                    out.cost ? ` · ${money(out.cost)}` : ""
                  }`
                );
                onDone();
              } catch (e) {
                oops(e.message);
              }
            }}
          >
            {cups > 1 ? `记下 ${cups} 杯并扣库存` : "记下并扣库存"}
          </Btn>
        </>
      }
    >
      <div className="space-y-3">
        <Field label="谁喝的" hint="点名字就能选，可以多选；多选是一人一杯。也可以空着。">
          <div className="flex gap-2">
            <Input
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  e.preventDefault();
                  addDraft();
                }
              }}
              placeholder="新名字回车加上"
            />
            <Btn variant="ghost" disabled={!draft.trim()} onClick={addDraft}>
              加上
            </Btn>
          </div>
        </Field>
        {names.length > 0 && (
          <div className="flex flex-wrap gap-2">
            {names.map((name) => (
              <Chip key={name} on={picked.includes(name)} onClick={() => toggle(name)}>
                {name}
              </Chip>
            ))}
          </div>
        )}
        {picked.length > 1 && (
          <p className="m-0 text-[13px] text-muted">
            已选 {picked.length} 人，按一人一杯记 {picked.length} 巡，库存也按 {picked.length} 倍扣。
          </p>
        )}
        {rows.map((r, i) => (
          <div key={`${r.kind || r.spirit_id}-${i}`} className="rounded-xl border border-line p-3">
            {r.alts.length > 1 ? (
              <Field label={`用哪支${r.kind || "酒"}`}>
                <Select
                  value={String(r.spirit_id)}
                  onChange={(e) => {
                    const sid = e.target.value;
                    setRows((cur) =>
                      cur.map((x, j) => {
                        if (j !== i) return x;
                        const alt = (x.alts || []).find((a) => String(a.spirit_id) === sid);
                        if (!alt) return { ...x, spirit_id: Number(sid) };
                        const lots = alt.open_lots || [];
                        return {
                          ...x,
                          spirit_id: alt.spirit_id,
                          spirit_name: alt.spirit_name,
                          balance_ml: alt.balance_ml,
                          lots,
                          lot_id: lots.length === 1 ? lots[0].lot_id : "",
                        };
                      })
                    );
                  }}
                >
                  {r.alts.map((a) => (
                    <option key={a.spirit_id} value={a.spirit_id}>
                      {a.spirit_name}
                      {a.balance_ml != null ? ` · 剩 ${Math.round(a.balance_ml)} ml` : ""}
                    </option>
                  ))}
                </Select>
              </Field>
            ) : (
              <button
                type="button"
                className="text-sm text-amber underline"
                onClick={() => onOpenSpirit?.(r.spirit_id)}
              >
                {r.spirit_name}
              </button>
            )}
            {r.alts.length > 1 && onOpenSpirit && (
              <button
                type="button"
                className="mt-1 text-xs text-muted underline"
                onClick={() => onOpenSpirit(r.spirit_id)}
              >
                看这支酒卡
              </button>
            )}
            <div className="mt-2 grid grid-cols-2 gap-2">
              <Field label="这次毫升">
                <Input
                  type="number"
                  min="1"
                  step="1"
                  value={r.amount_ml}
                  onChange={(e) =>
                    setRows((cur) =>
                      cur.map((x, j) => (j === i ? { ...x, amount_ml: e.target.value } : x))
                    )
                  }
                />
              </Field>
              <div className="text-[13px] text-muted self-end pb-2">
                剩 {Math.round(r.balance_ml || 0)} ml
              </div>
            </div>
            {r.lots.length > 1 && (
              <Field label="这支有几瓶未关，用哪一瓶">
                <Select
                  value={r.lot_id}
                  onChange={(e) =>
                    setRows((cur) => cur.map((x, j) => (j === i ? { ...x, lot_id: e.target.value } : x)))
                  }
                >
                  <option value="">先选一瓶，我不自己挑</option>
                  {r.lots.map((l) => (
                    <option key={l.lot_id} value={l.lot_id}>
                      第 {l.seq || "?"} 瓶 · 剩 {Math.round(l.balance_ml)} ml
                    </option>
                  ))}
                </Select>
              </Field>
            )}
          </div>
        ))}
        {needs && <p className="text-[13px] text-warn">有多瓶未关的，选好再记。</p>}
      </div>
    </Modal>
  );
}
