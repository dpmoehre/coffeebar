// 豆卡照片：pack 包装 / tray 豆盘 / card 店家豆卡，都可以缺。
// 没开封往往只有包装，开封后再补豆盘；豆卡是店家印的参数说明，拍下来留档。
import { useRef, useState } from "react";

import { api } from "../api.js";
import { Plus } from "../icons.jsx";
import { Panel } from "../ui.jsx";

const KINDS = [
  ["pack", "包装袋"],
  ["tray", "豆盘"],
  ["card", "豆卡"],
];

export default function Photos({
  beanId,
  photos,
  onDone,
  toast,
  oops,
  kinds = KINDS,
  upload,
}) {
  const LABEL = Object.fromEntries(kinds);
  const add = upload || ((file, kind) => api.addPhoto(beanId, file, kind));
  const [busy, setBusy] = useState(null);
  const [zoom, setZoom] = useState(null);
  const inputs = useRef({});

  const pick = async (kind, files) => {
    if (!files?.length) return;
    setBusy(kind);
    try {
      for (const f of files) await add(f, kind);
      toast(files.length > 1 ? `加了 ${files.length} 张` : "照片挂上了");
      onDone();
    } catch (e) {
      oops(e.message);
    } finally {
      setBusy(null);
      if (inputs.current[kind]) inputs.current[kind].value = "";
    }
  };

  return (
    <Panel className="mt-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="serif text-lg">照片</div>
        <div className="flex gap-2">
          {kinds.map(([kind, label]) => (
            <label
              key={kind}
              className="inline-flex cursor-pointer items-center gap-1.5 rounded-full border
                border-line px-3.5 py-1.5 text-sm hover:border-amber"
            >
              <Plus className="h-3.5 w-3.5" />
              {busy === kind ? "上传中…" : label}
              <input
                ref={(el) => (inputs.current[kind] = el)}
                type="file"
                accept="image/*,.heic,.heif"
                multiple
                className="hidden"
                onChange={(e) => pick(kind, [...e.target.files])}
              />
            </label>
          ))}
        </div>
      </div>

      {photos.length === 0 ? (
        <p className="mt-3 text-[13px] text-muted">
          还没有照片。手机拍完直接传，HEIC 会自动转成 JPEG。
        </p>
      ) : (
        <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-3">
          {photos.map((p) => (
            <figure key={p.id} className="group relative m-0">
              <img
                src={p.thumb}
                alt={LABEL[p.kind] || p.kind}
                onClick={() => setZoom(p)}
                className="aspect-square w-full cursor-zoom-in rounded-xl border border-line
                  object-cover transition hover:border-amber"
              />
              <figcaption
                className="absolute bottom-2 left-2 rounded-full bg-black/65 px-2.5 py-1
                  text-xs text-cream"
              >
                {LABEL[p.kind] || p.kind}
              </figcaption>
              <button
                title="删掉这张"
                className="absolute right-2 top-2 hidden h-7 w-7 rounded-full bg-black/70
                  text-cream hover:bg-warn group-hover:block"
                onClick={async () => {
                  try {
                    await api.delPhoto(p.id);
                    toast("删掉了");
                    onDone();
                  } catch (e) {
                    oops(e.message);
                  }
                }}
              >
                ×
              </button>
            </figure>
          ))}
        </div>
      )}

      {zoom && (
        <div
          onClick={() => setZoom(null)}
          className="fixed inset-0 z-50 grid cursor-zoom-out place-items-center bg-black/80 p-6"
        >
          <img src={zoom.url} alt="" className="max-h-full max-w-full rounded-xl" />
        </div>
      )}
    </Panel>
  );
}
