// 与 FastAPI 说话。写请求带上会话 id，服务端据此判断写锁归属。
const SESSION = (() => {
  let s = localStorage.getItem("coffeebar-session");
  if (!s) {
    s = Math.random().toString(36).slice(2) + Date.now().toString(36);
    localStorage.setItem("coffeebar-session", s);
  }
  return s;
})();

export const holderName = () =>
  localStorage.getItem("coffeebar-holder") ||
  (window.innerWidth < 900 ? "手机" : "这台电脑");

export class ApiError extends Error {
  constructor(status, body) {
    super(body?.message || body?.error || `请求失败（${status}）`);
    this.status = status;
    this.body = body || {};
  }
  get isLocked() {
    return this.status === 423;
  }
}

async function req(method, path, body) {
  const res = await fetch(path, {
    method,
    headers: {
      "Content-Type": "application/json",
      "X-Session": SESSION,
      "X-Source": "web",
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const text = await res.text();
  const data = text ? JSON.parse(text) : null;
  if (!res.ok) throw new ApiError(res.status, data);
  return data;
}

// 传文件不能带 Content-Type，让浏览器自己写 multipart 边界
async function upload(path, formData) {
  const res = await fetch(path, {
    method: "POST",
    headers: { "X-Session": SESSION, "X-Source": "web" },
    body: formData,
  });
  const text = await res.text();
  const data = text ? JSON.parse(text) : null;
  if (!res.ok) throw new ApiError(res.status, data);
  return data;
}

export const api = {
  beans: (scope = "stock") => req("GET", `/api/beans?scope=${scope}`),
  bean: (id) => req("GET", `/api/beans/${id}`),
  createBean: (data) => req("POST", "/api/beans", data),
  updateBean: (id, data) => req("PATCH", `/api/beans/${id}`, data),
  addScore: (id, data) => req("POST", `/api/beans/${id}/scores`, data),

  addPhoto: (beanId, file, kind = "pack") => {
    const fd = new FormData();
    fd.append("file", file);
    fd.append("kind", kind);
    return upload(`/api/beans/${beanId}/photos`, fd);
  },
  delPhoto: (id) => req("DELETE", `/api/photos/${id}`),
  addRestockPhoto: (beanId, file, note = "") => {
    const fd = new FormData();
    fd.append("file", file);
    fd.append("note", note);
    return upload(`/api/beans/${beanId}/restock-photos`, fd);
  },

  addLot: (beanId, data) => req("POST", `/api/beans/${beanId}/lots`, data),
  openLot: (lotId) => req("POST", `/api/lots/${lotId}/open`, {}),
  measure: (lotId, g) => req("POST", `/api/lots/${lotId}/measure`, { measured_g: g }),
  adjust: (lotId, g, note) => req("POST", `/api/lots/${lotId}/adjust`, { actual_g: g, note }),
  closeLot: (lotId, note) => req("POST", `/api/lots/${lotId}/close`, { note }),

  brewPlan: (method, dose, ratio) =>
    req("GET", `/api/brew/plan?method=${method}&dose_g=${dose}&ratio=${ratio}`),
  brewMethods: () => req("GET", "/api/brew/methods"),
  setBrewDefault: (beanId, data) => req("POST", `/api/beans/${beanId}/brew-default`, data),

  recordBrew: (data) => req("POST", "/api/brews", data),
  consumption: (params = "") => req("GET", `/api/consumption${params}`),
  voidBrew: (id, reason) => req("POST", `/api/consumption/${id}/void`, { reason }),
  unvoidBrew: (id) => req("POST", `/api/consumption/${id}/unvoid`),
  reassign: (id, person) => req("POST", `/api/consumption/${id}/person`, { person }),

  people: (all = false) => req("GET", `/api/people?include_inactive=${all}`),
  addPerson: (name) => req("POST", "/api/people", { name }),
  patchPerson: (id, data) => req("PATCH", `/api/people/${id}`, data),
  deletePerson: (id) => req("DELETE", `/api/people/${id}`),
  profile: (id) => req("GET", `/api/people/${id}/profile`),

  spirits: (scope = "stock") => req("GET", `/api/spirits?scope=${scope}`),
  spirit: (id) => req("GET", `/api/spirits/${id}`),
  createSpirit: (data) => req("POST", "/api/spirits", data),
  updateSpirit: (id, data) => req("PATCH", `/api/spirits/${id}`, data),
  addBottleLot: (id, data) => req("POST", `/api/spirits/${id}/lots`, data),
  addBottlePhoto: (id, file, kind = "pack") => {
    const fd = new FormData();
    fd.append("file", file);
    fd.append("kind", kind);
    return upload(`/api/spirits/${id}/photos`, fd);
  },
  openBottle: (lotId) => req("POST", `/api/bottle-lots/${lotId}/open`, {}),
  adjustBottle: (lotId, ml, note) =>
    req("POST", `/api/bottle-lots/${lotId}/adjust`, { actual_ml: ml, note }),
  closeBottle: (lotId, note) => req("POST", `/api/bottle-lots/${lotId}/close`, { note }),
  recordDrink: (data) => req("POST", "/api/drinks", data),

  stats: (period = "month") => req("GET", `/api/stats?period=${period}`),
  restock: () => req("GET", "/api/restock"),

  lock: (resource, takeOver = false) =>
    req("POST", `/api/locks/${resource}`, { holder: holderName(), take_over: takeOver }),
  heartbeat: (resource) => req("PUT", `/api/locks/${resource}`),
  unlock: (resource) => req("DELETE", `/api/locks/${resource}`),
};
