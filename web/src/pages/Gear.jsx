// 自己台面上的咖啡器具。登记之后冲煮指导会按滤杯形状给建议。
import { useEffect, useMemo, useState } from "react";

import { api } from "../api.js";
import { Plus, Trash } from "../icons.jsx";
import { Btn, Chip, Cover, Empty, Field, Input, Modal, Panel, Select, coverSrc, money } from "../ui.jsx";

const KIND_LABEL = {
  dripper: "滤杯",
  kettle: "手冲壶",
  grinder: "磨豆机",
  scale: "称",
  server: "分享壶",
  filter: "滤纸",
  other: "其他",
};

export default function Gear({ toast, oops, focusId }) {
  const [meta, setMeta] = useState(null);
  const [mine, setMine] = useState(null);
  const [catalog, setCatalog] = useState([]);
  const [kind, setKind] = useState("all");
  const [adding, setAdding] = useState(false);
  const [picked, setPicked] = useState(null);

  const load = () =>
    api
      .gear()
      .then((d) => {
        setMine(d.gear);
        setCatalog(d.catalog || []);
      })
      .catch((e) => oops(e.message));

  useEffect(() => {
    api.gearMeta().then(setMeta).catch((e) => oops(e.message));
    load();
  }, []);

  useEffect(() => {
    if (!focusId || !mine) return;
    const hit = mine.find((g) => g.id === focusId);
    if (hit) setPicked(hit);
  }, [focusId, mine]);

  const shown = useMemo(() => {
    const list = mine || [];
    return kind === "all" ? list : list.filter((g) => g.kind === kind);
  }, [mine, kind]);

  const ownedCatalog = new Set((mine || []).map((g) => g.catalog_id).filter(Boolean));
  const toClaim = (catalog || []).filter((c) => !ownedCatalog.has(c.id));

  return (
    <>
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="serif m-0 text-2xl font-semibold md:text-3xl">器具</h1>
          <p className="mt-2 mb-0 text-muted">
            登记你台面上的滤杯、壶、磨、称和滤纸。滤纸新开一包再开始计张，冲一杯会加上纸钱。公开后别人能在广场领走一份拷贝。
          </p>
        </div>
        <Btn onClick={() => setAdding(true)}>
          <Plus className="h-4 w-4" />
          登记器具
        </Btn>
      </header>

      <div className="mt-5 flex flex-wrap gap-2">
        <Chip on={kind === "all"} onClick={() => setKind("all")}>
          全部
        </Chip>
        {(meta?.kinds || Object.entries(KIND_LABEL).map(([key, label]) => ({ key, label }))).map(
          (k) => (
            <Chip key={k.key} on={kind === k.key} onClick={() => setKind(k.key)}>
              {k.label}
            </Chip>
          ),
        )}
      </div>

      {toClaim.length > 0 && (
        <Panel className="mt-5">
          <div className="serif text-lg">目录里有、你还没领</div>
          <p className="mt-1 mb-0 text-[13px] text-muted">
            管理员收录过的型号。点一下加到台面，不用重新拍照。
          </p>
          <div className="mt-3 flex flex-wrap gap-2">
            {toClaim.map((c) => (
              <button
                key={c.id}
                type="button"
                className="rounded-full border border-line px-3.5 py-1.5 text-sm text-cream hover:border-amber"
                onClick={async () => {
                  try {
                    const item = await api.gearFromCatalog(c.id);
                    toast(`已领到台面：${item.name}`);
                    load();
                  } catch (e) {
                    oops(e.message);
                  }
                }}
              >
                {c.name}
                {c.kind_label ? ` · ${c.kind_label}` : ""}
              </button>
            ))}
          </div>
        </Panel>
      )}

      {!mine ? (
        <div className="mt-6 grid gap-4 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4">
          {[0, 1, 2, 3].map((i) => (
            <div
              key={i}
              className="rise overflow-hidden rounded-2xl border border-line bg-panel"
              style={{ animationDelay: `${i * 45}ms` }}
            >
              <Cover className="h-40 w-full" />
              <div className="p-5">
                <div className="h-5 w-2/3 rounded bg-line" />
                <div className="mt-3 h-3 w-1/2 rounded bg-line" />
              </div>
            </div>
          ))}
        </div>
      ) : shown.length === 0 ? (
        <div className="mt-6">
          <Empty>
            {kind === "all"
              ? "台面还是空的。右上角登记一件，滤杯记得选锥形还是平底。"
              : "这一类还没有。"}
          </Empty>
        </div>
      ) : (
        <div className="mt-6 grid gap-4 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4">
          {shown.map((g, i) => (
            <article
              key={g.id}
              onClick={() => setPicked(g)}
              className="rise cursor-pointer overflow-hidden rounded-2xl border border-line
                bg-panel transition hover:border-amber"
              style={{ animationDelay: `${Math.min(i, 12) * 45}ms` }}
            >
              <Cover src={coverSrc(g.cover)} className="h-40 w-full" />
              <div className="p-5">
                <div className="flex items-baseline justify-between gap-2">
                  <div className="serif truncate text-lg">{g.name}</div>
                  <span className="shrink-0 text-xs text-muted">
                    {[g.visibility === "public" ? "公开" : null, g.collected ? "已收录" : null]
                      .filter(Boolean)
                      .join(" · ")}
                  </span>
                </div>
                <div className="mt-1 truncate text-[13px] text-muted">
                  {[g.kind_label, g.family_label, g.brand, g.model].filter(Boolean).join(" · ")}
                  {g.kind === "filter"
                    ? g.counting
                      ? ` · 还剩 ${g.sheets_left} 张`
                      : " · 还没开始计张"
                    : ""}
                </div>
              </div>
            </article>
          ))}
        </div>
      )}

      <GearForm
        open={adding}
        meta={meta}
        onClose={() => setAdding(false)}
        onDone={(item) => {
          setAdding(false);
          toast(`已登记：${item.name}`);
          load();
          setPicked(item);
        }}
        oops={oops}
      />

      {picked && (
        <GearDetail
          item={picked}
          meta={meta}
          onClose={() => setPicked(null)}
          onChange={(item) => {
            setPicked(item);
            load();
          }}
          onGone={() => {
            setPicked(null);
            load();
          }}
          toast={toast}
          oops={oops}
        />
      )}
    </>
  );
}

function blank(kind = "dripper") {
  return {
    name: "",
    kind,
    family: "",
    brand: "",
    model: "",
    brew_method: "",
    note: "",
    visibility: "private",
  };
}

function GearForm({ open, meta, initial, onClose, onDone, oops }) {
  const [f, setF] = useState(blank);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (open) {
      setF(
        initial
          ? {
              name: initial.name || "",
              kind: initial.kind || "dripper",
              family: initial.family || "",
              brand: initial.brand || "",
              model: initial.model || "",
              brew_method: initial.brew_method || "",
              note: initial.note || "",
              visibility: initial.visibility || "private",
            }
          : blank(),
      );
    }
  }, [open, initial]);

  const families = meta?.families?.[f.kind] || [];
  const methods = meta?.methods || [];

  const save = async () => {
    if (!f.name.trim()) {
      oops("先写器具名字");
      return;
    }
    setBusy(true);
    try {
      const payload = {
        name: f.name.trim(),
        kind: f.kind,
        family: f.family || null,
        brand: f.brand,
        model: f.model,
        brew_method: f.brew_method || null,
        note: f.note,
        visibility: f.visibility || "private",
      };
      const item = initial
        ? await api.updateGear(initial.id, payload)
        : await api.createGear(payload);
      onDone(item);
    } catch (e) {
      oops(e.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal
      open={open}
      onClose={() => !busy && onClose()}
      title={initial ? "改这件器具" : "登记器具"}
      sub={
        f.kind === "filter"
          ? "滤纸新开一包再开始计张。现在手里这包剩多少不要估。"
          : "滤杯请选锥形或平底，冲煮建议才知道该推 V60 还是 Kalita。"
      }
      footer={
        <>
          <Btn variant="ghost" onClick={onClose} disabled={busy}>
            取消
          </Btn>
          <Btn onClick={save} disabled={busy || !f.name.trim()}>
            {initial ? "保存" : "登记"}
          </Btn>
        </>
      }
    >
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="名字">
          <Input
            value={f.name}
            onChange={(e) => setF({ ...f, name: e.target.value })}
            placeholder="Hario V60 02"
            autoFocus
          />
        </Field>
        <Field label="类型">
          <Select
            className="w-full"
            value={f.kind}
            onChange={(e) => setF({ ...f, kind: e.target.value, family: "" })}
          >
            {(meta?.kinds || []).map((k) => (
              <option key={k.key} value={k.key}>
                {k.label}
              </option>
            ))}
          </Select>
        </Field>
        {families.length > 0 && (
          <Field label={f.kind === "kettle" ? "壶嘴" : "形状"}>
            <Select
              className="w-full"
              value={f.family}
              onChange={(e) => setF({ ...f, family: e.target.value })}
            >
              <option value="">还没定</option>
              {families.map((x) => (
                <option key={x.key} value={x.key}>
                  {x.label}
                </option>
              ))}
            </Select>
          </Field>
        )}
        <Field label="对应冲煮" hint="可空。选了会优先推这种方式">
          <Select
            className="w-full"
            value={f.brew_method}
            onChange={(e) => setF({ ...f, brew_method: e.target.value })}
          >
            <option value="">不指定</option>
            {methods.map((m) => (
              <option key={m.key} value={m.key}>
                {m.label}
              </option>
            ))}
          </Select>
        </Field>
        <Field label="品牌">
          <Input value={f.brand} onChange={(e) => setF({ ...f, brand: e.target.value })} />
        </Field>
        <Field label="型号">
          <Input value={f.model} onChange={(e) => setF({ ...f, model: e.target.value })} />
        </Field>
      </div>
      <div className="mt-3">
        <Field label="备注">
          <Input value={f.note} onChange={(e) => setF({ ...f, note: e.target.value })} />
        </Field>
      </div>
      <label className="mt-3 flex items-center gap-2 text-sm text-cream">
        <input
          type="checkbox"
          checked={f.visibility === "public"}
          onChange={(e) => setF({ ...f, visibility: e.target.checked ? "public" : "private" })}
        />
        公开到广场，别人可以领一份到自己台面
      </label>
    </Modal>
  );
}

function GearDetail({ item, meta, onClose, onChange, onGone, toast, oops }) {
  const [editing, setEditing] = useState(false);
  const [packing, setPacking] = useState(false);
  const [busy, setBusy] = useState(false);

  const upload = async (file) => {
    if (!file) return;
    setBusy(true);
    try {
      await api.addGearPhoto(item.id, file);
      onChange(await api.gearItem(item.id));
      toast("照片已挂上");
    } catch (e) {
      oops(e.message);
    } finally {
      setBusy(false);
    }
  };

  const delPhoto = async (id) => {
    try {
      await api.delGearPhoto(id);
      onChange(await api.gearItem(item.id));
    } catch (e) {
      oops(e.message);
    }
  };

  const drop = async () => {
    if (!window.confirm(`从台面拿掉「${item.name}」？目录里已收录的还在。`)) return;
    try {
      await api.deleteGear(item.id);
      toast("已拿掉");
      onGone();
    } catch (e) {
      oops(e.message);
    }
  };

  return (
    <Modal
      open
      wide
      onClose={onClose}
      title={item.name}
      sub={[item.kind_label, item.family_label, item.brand, item.model].filter(Boolean).join(" · ")}
      footer={
        <>
          <Btn variant="ghost" onClick={onClose}>
            关闭
          </Btn>
          <Btn
            variant="ghost"
            onClick={async () => {
              const next = item.visibility === "public" ? "private" : "public";
              try {
                const out = await api.updateGear(item.id, { visibility: next });
                toast(next === "public" ? "已公开。别人能在广场领走一份" : "已改回只自己看");
                onChange(out);
              } catch (e) {
                oops(e.message);
              }
            }}
          >
            {item.visibility === "public" ? "改回只自己看" : "公开这件"}
          </Btn>
          {(item.kind === "filter" || item.kind === "other") && (
            <Btn variant="ghost" onClick={() => setPacking(true)}>
              开一包
            </Btn>
          )}
          <Btn variant="ghost" onClick={() => setEditing(true)}>
            改字段
          </Btn>
          <Btn variant="danger" onClick={drop}>
            <Trash className="h-4 w-4" />
            拿掉
          </Btn>
        </>
      }
    >
      {item.visibility === "public" ? (
        <p className="mt-0 mb-3 text-sm text-amber">已公开。别人能在广场领走一份拷贝。</p>
      ) : null}
      {item.source_gear_id ? (
        <p className="mt-0 mb-3 text-[13px] text-muted">从广场领来的拷贝，改自己的不影响原件。</p>
      ) : null}
      {item.collected && item.catalog?.note ? (
        <p className="mt-0 mb-4 text-sm text-amber">目录备注：{item.catalog.note}</p>
      ) : null}
      {item.note ? <p className="mt-0 mb-4 text-sm text-muted">{item.note}</p> : null}
      {item.kind === "filter" || item.counting ? (
        <p className="mt-0 mb-4 text-sm text-amber">
          {item.counting
            ? `已开始计张，还剩 ${item.sheets_left} 张。冲一杯扣一张${
                item.open_pack?.unit_cost != null ? `，大约 ${money(item.open_pack.unit_cost)} / 张` : ""
              }。`
            : "还没开始计张。现在这包剩多少不要估，等新开一包再记枚数和价钱。"}
        </p>
      ) : item.kind === "other" ? (
        <p className="mt-0 mb-4 text-[13px] text-muted">
          如果这是滤纸，点「开一包」会改成滤纸耗材，才开始计张。旧包剩多少不要估。
        </p>
      ) : null}
      <div className="flex flex-wrap gap-2">
        <label className="inline-flex cursor-pointer items-center gap-1.5 rounded-full border border-line px-3.5 py-1.5 text-sm hover:border-amber">
          <Plus className="h-3.5 w-3.5" />
          {busy ? "上传中…" : "传照片"}
          <input
            type="file"
            accept="image/*,.heic,.heif"
            className="hidden"
            onChange={(e) => {
              const file = e.target.files?.[0];
              e.target.value = "";
              upload(file);
            }}
          />
        </label>
      </div>
      {item.photos?.length ? (
        <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-3">
          {item.photos.map((p) => (
            <figure key={p.id} className="group relative m-0">
              <img src={p.thumb || p.url} alt="" className="h-36 w-full rounded-xl object-cover" />
              <button
                type="button"
                className="absolute top-2 right-2 hidden rounded-full bg-black/60 px-2 py-0.5 text-xs text-cream group-hover:block"
                onClick={() => delPhoto(p.id)}
              >
                删
              </button>
            </figure>
          ))}
        </div>
      ) : (
        <p className="mt-3 mb-0 text-[13px] text-muted">还没有照片。手机拍完直接传。</p>
      )}
      <PackForm
        open={packing}
        item={item}
        onClose={() => setPacking(false)}
        onDone={(next) => {
          setPacking(false);
          toast("已开一包，开始计张");
          onChange(next);
        }}
        oops={oops}
      />
      <GearForm
        open={editing}
        meta={meta}
        initial={item}
        onClose={() => setEditing(false)}
        onDone={(next) => {
          setEditing(false);
          toast("已改好");
          onChange(next);
        }}
        oops={oops}
      />
    </Modal>
  );
}

function PackForm({ open, item, onClose, onDone, oops }) {
  const [sheets, setSheets] = useState("100");
  const [price, setPrice] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (open) {
      setSheets("100");
      setPrice("");
    }
  }, [open]);

  const save = async () => {
    const n = Number(sheets);
    if (!(n > 0)) {
      oops("先写这一包多少张");
      return;
    }
    setBusy(true);
    try {
      const out = await api.openFilterPack(item.id, {
        sheets: n,
        price: price === "" ? null : Number(price),
      });
      onDone(out);
    } catch (e) {
      oops(e.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal
      open={open}
      onClose={() => !busy && onClose()}
      title="开一包滤纸"
      sub="从这一包开始计张。不要把旧包剩多少估进去。"
      footer={
        <>
          <Btn variant="ghost" onClick={onClose} disabled={busy}>
            取消
          </Btn>
          <Btn onClick={save} disabled={busy || !(Number(sheets) > 0)}>
            开始计张
          </Btn>
        </>
      }
    >
      <Field label="这一包多少张">
        <Input type="number" value={sheets} onChange={(e) => setSheets(e.target.value)} autoFocus />
      </Field>
      <Field label="这一包多少钱" hint="可空。填了冲一杯才会加上纸钱">
        <Input type="number" step="0.01" value={price} onChange={(e) => setPrice(e.target.value)} />
      </Field>
    </Modal>
  );
}
