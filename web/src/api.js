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
    super(body?.message || body?.error || body?.detail || `请求失败（${status}）`);
    this.status = status;
    this.body = body || {};
  }
  get isLocked() {
    return this.status === 423;
  }
}

function readBody(text, status) {
  if (!text) return null;
  const trimmed = text.trim();
  if (trimmed.startsWith("<!") || trimmed.startsWith("<html")) {
    throw new ApiError(status, {
      message: "服务还是旧版本，没接到这个接口。关掉再开一次 start.sh / start.bat。",
    });
  }
  try {
    return JSON.parse(text);
  } catch {
    throw new ApiError(status, { message: text.slice(0, 80) || `请求失败（${status}）` });
  }
}

async function req(method, path, body) {
  const res = await fetch(path, {
    method,
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      "X-Session": SESSION,
      "X-Source": "web",
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const data = readBody(await res.text(), res.status);
  if (!res.ok) throw new ApiError(res.status, data);
  return data;
}

// 传文件不能带 Content-Type，让浏览器自己写 multipart 边界
async function upload(path, formData) {
  const res = await fetch(path, {
    method: "POST",
    credentials: "include",
    headers: { "X-Session": SESSION, "X-Source": "web" },
    body: formData,
  });
  const data = readBody(await res.text(), res.status);
  if (!res.ok) throw new ApiError(res.status, data);
  return data;
}

async function download(path, filename) {
  const res = await fetch(path, {
    credentials: "include",
    headers: { "X-Session": SESSION, "X-Source": "web" },
  });
  if (!res.ok) {
    const data = readBody(await res.text(), res.status);
    throw new ApiError(res.status, data);
  }
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

export const api = {
  me: () => req("GET", "/api/me"),
  health: () => req("GET", "/api/health"),
  authConfig: () => req("GET", "/api/auth/config"),
  register: (email, password, invite) =>
    req("POST", "/api/auth/register", { email, password, invite }),
  login: (email, password) => req("POST", "/api/auth/login", { email, password }),
  logout: () => req("POST", "/api/auth/logout", {}),
  changePassword: (oldPassword, newPassword) =>
    req("POST", "/api/auth/password", { old: oldPassword, new: newPassword }),
  deleteAccount: (email, password) => req("POST", "/api/auth/delete", { email, password }),
  forgot: (email) => req("POST", "/api/auth/forgot", { email }),
  reset: (token, password) => req("POST", "/api/auth/reset", { token, password }),
  verify: (token) => req("POST", "/api/auth/verify", { token }),
  resendVerify: () => req("POST", "/api/auth/resend-verify", {}),

  beans: (scope = "stock") => req("GET", `/api/beans?scope=${scope}`),
  bean: (id) => req("GET", `/api/beans/${id}`),
  createBean: (data) => req("POST", "/api/beans", data),
  updateBean: (id, data) => req("PATCH", `/api/beans/${id}`, data),
  deleteBean: (id, mode) =>
    req("DELETE", `/api/beans/${id}${mode ? `?mode=${encodeURIComponent(mode)}` : ""}`),
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
  deleteBrew: (id) => req("DELETE", `/api/consumption/${id}`),
  reassign: (id, person) => req("POST", `/api/consumption/${id}/person`, { person }),
  addBrewPhoto: (consId, file, kind = "bed") => {
    const fd = new FormData();
    fd.append("file", file);
    fd.append("kind", kind);
    return upload(`/api/consumption/${consId}/photos`, fd);
  },
  delBrewPhoto: (id) => req("DELETE", `/api/consumption-photos/${id}`),

  people: (all = false) => req("GET", `/api/people?include_inactive=${all}`),
  addPerson: (name) => req("POST", "/api/people", { name }),
  patchPerson: (id, data) => req("PATCH", `/api/people/${id}`, data),
  deletePerson: (id) => req("DELETE", `/api/people/${id}`),
  profile: (id) => req("GET", `/api/people/${id}/profile`),

  spirits: (scope = "stock") => req("GET", `/api/spirits?scope=${scope}`),
  spirit: (id) => req("GET", `/api/spirits/${id}`),
  createSpirit: (data) => req("POST", "/api/spirits", data),
  updateSpirit: (id, data) => req("PATCH", `/api/spirits/${id}`, data),
  deleteSpirit: (id, mode) =>
    req("DELETE", `/api/spirits/${id}${mode ? `?mode=${encodeURIComponent(mode)}` : ""}`),
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

  menu: (listedOnly = false) => req("GET", `/api/menu?listed_only=${listedOnly}`),
  addMenuItem: (data) => req("POST", "/api/menu", data),
  patchMenuItem: (id, data) => req("PATCH", `/api/menu/${id}`, data),
  reorderMenu: (ids) => req("PUT", "/api/menu/order", { ids }),
  deleteMenuItem: (id) => req("DELETE", `/api/menu/${id}`),
  pourMenu: (data) => req("POST", "/api/menu/pour", data),
  recipes: () => req("GET", "/api/recipes"),
  createRecipe: (data) => req("POST", "/api/recipes", data),
  updateRecipe: (id, data) => req("PATCH", `/api/recipes/${id}`, data),
  deleteRecipe: (id) => req("DELETE", `/api/recipes/${id}`),

  stats: (period = "month") => req("GET", `/api/stats?period=${period}`),
  calendar: (year, month, personId) => {
    const q = new URLSearchParams({ year, month });
    if (personId) q.set("person_id", personId);
    return req("GET", `/api/calendar?${q}`);
  },
  calendarDay: (date, personId) => {
    const q = new URLSearchParams({ date });
    if (personId) q.set("person_id", personId);
    return req("GET", `/api/calendar/day?${q}`);
  },
  exportZip: (period = "month") =>
    download(`/api/export?period=${period}`, `coffeebar-${period}.zip`),
  restock: () => req("GET", "/api/restock"),
  map: () => req("GET", "/api/map"),
  setPlaces: (id, places) => req("PUT", `/api/beans/${id}/places`, { places }),
  guessPlaces: (id) => req("POST", `/api/beans/${id}/places/guess`, {}),

  lock: (resource, takeOver = false) =>
    req("POST", `/api/locks/${resource}`, { holder: holderName(), take_over: takeOver }),
  heartbeat: (resource) => req("PUT", `/api/locks/${resource}`),
  unlock: (resource) => req("DELETE", `/api/locks/${resource}`),
};
