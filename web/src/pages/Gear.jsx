// 自己台面上的咖啡器具。登记之后冲煮指导会按滤杯形状给建议。
import { useEffect, useMemo, useState } from "react";

import { api } from "../api.js";
import { Plus, Trash } from "../icons.jsx";
import { Btn, Chip, Empty, Field, Input, Modal, Panel, Select } from "../ui.jsx";

const KIND_LABEL = {
  dripper: "滤杯",
  kettle: "手冲壶",
  grinder: "磨豆机",
  scale: "称",
  server: "分享壶",
  other: "其他",
};

export default function Gear({ toast, oops }) {
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
          <h1 className="serif m-0 text-3xl font-semibold">器具</h1>
          <p className="mt-2 mb-0 text-muted">
            登记你台面上的滤杯、壶、磨和称。冲煮指导会按你有的滤杯给建议。
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
        <p className="mt-6 text-muted">读取中…</p>
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
          {shown.map((g) => (
            <article
              key={g.id}
              onClick={() => setPicked(g)}
              className="rise cursor-pointer overflow-hidden rounded-2xl border border-line
                bg-panel transition hover:border-amber"
            >
              {g.cover ? (
                <img src={g.cover.thumb} alt="" className="h-40 w-full object-cover" />
              ) : (
                <div
                  className="h-40"
                  style={{
                    background:
                      "radial-gradient(circle at 40% 35%, #5a3d28, transparent 46%), linear-gradient(135deg, #3a2618, #1a120e)",
                  }}
                />
              )}
              <div className="p-5">
                <div className="flex items-baseline justify-between gap-2">
                  <div className="serif truncate text-lg">{g.name}</div>
                  {g.collected ? <span className="shrink-0 text-xs text-amber">已收录</span> : null}
                </div>
                <div className="mt-1 truncate text-[13px] text-muted">
                  {[g.kind_label, g.family_label, g.brand, g.model].filter(Boolean).join(" · ")}
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
  return { name: "", kind, family: "", brand: "", model: "", brew_method: "", note: "" };
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
      sub="滤杯请选锥形或平底，冲煮建议才知道该推 V60 还是 Kalita。"
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
    </Modal>
  );
}

function GearDetail({ item, meta, onClose, onChange, onGone, toast, oops }) {
  const [editing, setEditing] = useState(false);
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
      {item.collected && item.catalog?.note ? (
        <p className="mt-0 mb-4 text-sm text-amber">目录备注：{item.catalog.note}</p>
      ) : null}
      {item.note ? <p className="mt-0 mb-4 text-sm text-muted">{item.note}</p> : null}
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
