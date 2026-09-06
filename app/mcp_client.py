"""MCP 打现有 HTTP。不另开库。X-Source=mcp，不接管写锁。"""

from __future__ import annotations

import json
import mimetypes
import os
from pathlib import Path

import httpx

SESSION = "coffeebar-mcp"
ROOT = Path(__file__).resolve().parent.parent


class Offline(Exception):
    def __init__(self) -> None:
        super().__init__("coffeebar 未在运行。先在小主机开 start.bat，或本机跑 start.sh。")


class Locked(Exception):
    def __init__(self, body: dict) -> None:
        super().__init__(body.get("message") or "网页正在编辑这一条，先去保存或取消，再让我写入。")


class ApiError(Exception):
    def __init__(self, status: int, message: str) -> None:
        self.status = status
        super().__init__(message)


def load_dotenv(path: Path | None = None) -> None:
    env = path or (ROOT / ".env")
    if not env.is_file():
        return
    for line in env.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        os.environ.setdefault(key.strip(), val.strip().strip("'").strip('"'))


def _msg(res: httpx.Response) -> str:
    try:
        data = res.json()
    except Exception:
        text = (res.text or "").strip()
        return text[:200] or f"请求失败（{res.status_code}）"
    if isinstance(data, dict):
        detail = data.get("detail")
        if isinstance(detail, str) and detail:
            return detail
        return str(data.get("message") or data.get("error") or data)
    return str(data)


class Client:
    def __init__(
        self,
        http: httpx.Client,
        *,
        email: str | None = None,
        password: str | None = None,
        authed: bool = False,
    ) -> None:
        self.http = http
        self.email = email
        self.password = password
        self._authed = authed
        self._auth_error: ApiError | None = None

    @classmethod
    def from_env(cls) -> Client:
        load_dotenv()
        url = (os.environ.get("COFFEEBAR_URL") or "http://127.0.0.1:8000").rstrip("/")
        return cls(
            httpx.Client(base_url=url, timeout=30.0),
            email=os.environ.get("COFFEEBAR_EMAIL"),
            password=os.environ.get("COFFEEBAR_PASSWORD"),
        )

    @classmethod
    def from_test(cls, test_client: httpx.Client) -> Client:
        return cls(test_client, authed=True)

    def _connect(self, method: str, path: str, **kw) -> httpx.Response:
        try:
            return self.http.request(method, path, **kw)
        except httpx.ConnectError as exc:
            raise Offline() from exc
        except httpx.TimeoutException as exc:
            raise Offline() from exc

    def _login(self) -> None:
        if self._authed:
            return
        if self._auth_error:
            raise self._auth_error
        if not self.email or not self.password:
            raise ApiError(401, "请在 MCP 配置或仓库 .env 里写 COFFEEBAR_EMAIL 和 COFFEEBAR_PASSWORD")
        try:
            self._connect("GET", "/api/health")
        except Offline:
            raise
        res = self._connect(
            "POST",
            "/api/auth/login",
            json={"email": self.email, "password": self.password},
            headers={"X-Source": "mcp"},
        )
        if res.status_code >= 400:
            err = ApiError(res.status_code, _msg(res))
            if res.status_code in (401, 429):
                self._auth_error = err
            raise err
        self._authed = True

    def request(self, method: str, path: str, **kw):
        self._login()
        headers = {**(kw.pop("headers", None) or {}), "X-Source": "mcp", "X-Session": SESSION}
        res = self._connect(method, path, headers=headers, **kw)
        if res.status_code == 423:
            try:
                body = res.json()
            except Exception:
                body = {}
            raise Locked(body if isinstance(body, dict) else {})
        if res.status_code >= 400:
            raise ApiError(res.status_code, _msg(res))
        if not res.content:
            return {}
        ctype = res.headers.get("content-type", "")
        if "json" in ctype:
            return res.json()
        return res.content

    def upload(self, path: str, file_path: str, fields: dict | None = None):
        p = Path(file_path).expanduser()
        if not p.is_file():
            raise ApiError(400, f"没有这个文件：{p}")
        mime = mimetypes.guess_type(p.name)[0] or "application/octet-stream"
        return self.request(
            "POST",
            path,
            files={"file": (p.name, p.read_bytes(), mime)},
            data=fields or {},
        )

    # ── 豆子 ──────────────────────────────────────────────

    def list_beans(self, scope: str = "stock"):
        return self.request("GET", f"/api/beans?scope={scope}")

    def get_bean(self, bean_id: int):
        return self.request("GET", f"/api/beans/{bean_id}")

    def create_bean(self, data: dict):
        return self.request("POST", "/api/beans", json=data)

    def update_bean(self, bean_id: int, data: dict):
        return self.request("PATCH", f"/api/beans/{bean_id}", json=data)

    def delete_bean(self, bean_id: int, mode: str | None = None):
        q = f"?mode={mode}" if mode else ""
        return self.request("DELETE", f"/api/beans/{bean_id}{q}")

    def add_bean_photo(self, bean_id: int, file_path: str, kind: str = "pack"):
        return self.upload(f"/api/beans/{bean_id}/photos", file_path, {"kind": kind})

    def delete_photo(self, photo_id: int):
        return self.request("DELETE", f"/api/photos/{photo_id}")

    def add_score(self, bean_id: int, data: dict):
        return self.request("POST", f"/api/beans/{bean_id}/scores", json=data)

    def create_bean_lot(self, bean_id: int, data: dict):
        return self.request("POST", f"/api/beans/{bean_id}/lots", json=data)

    def open_lot(self, lot_id: int, on: str | None = None):
        return self.request("POST", f"/api/lots/{lot_id}/open", json={"on": on} if on else {})

    def measure_lot(self, lot_id: int, measured_g: float):
        return self.request("POST", f"/api/lots/{lot_id}/measure", json={"measured_g": measured_g})

    def adjust_lot(self, lot_id: int, actual_g: float, note: str | None = None):
        return self.request("POST", f"/api/lots/{lot_id}/adjust", json={"actual_g": actual_g, "note": note})

    def close_lot(self, lot_id: int, note: str | None = None):
        return self.request("POST", f"/api/lots/{lot_id}/close", json={"note": note} if note else {})

    def writeoff_lot(self, lot_id: int, note: str | None = None):
        return self.request("POST", f"/api/lots/{lot_id}/writeoff", json={"note": note} if note else {})

    # ── 冲煮 / 流水 ────────────────────────────────────────

    def brew_plan(self, method: str = "v60", dose_g: float = 15, ratio: float = 16):
        return self.request("GET", f"/api/brew/plan?method={method}&dose_g={dose_g}&ratio={ratio}")

    def list_brew_methods(self):
        return self.request("GET", "/api/brew/methods")

    def set_brew_default(self, bean_id: int, data: dict):
        return self.request("POST", f"/api/beans/{bean_id}/brew-default", json=data)

    def _lot_label(self, bean: dict, lot_id: int) -> dict:
        for lot in bean.get("lots") or []:
            if lot.get("id") == lot_id:
                return {
                    "lot_id": lot_id,
                    "lot_seq": lot.get("seq"),
                    "bean_id": bean.get("id"),
                    "bean_name": bean.get("name"),
                    "used_lot": f"第 {lot.get('seq')} 袋" if lot.get("seq") else f"袋子 {lot_id}",
                    "balance_g": lot.get("balance_g"),
                }
        return {"lot_id": lot_id, "bean_name": bean.get("name")}

    def record_brew(self, data: dict):
        lot_id = data.get("lot_id")
        bean_id = data.get("bean_id")
        if lot_id is None:
            if bean_id is None:
                raise ApiError(400, "要指定 lot_id。多袋未关时先 get_bean 看袋子，不要让我自己挑。")
            bean = self.get_bean(int(bean_id))
            open_lots = [l for l in bean.get("lots") or [] if not l.get("closed_at")]
            if not open_lots:
                raise ApiError(400, "这支豆没有未关的袋子")
            if len(open_lots) > 1:
                return {
                    "error": "有多袋未关，请指定 lot_id，我不自己挑",
                    "lots": [
                        {
                            "lot_id": l["id"],
                            "seq": l.get("seq"),
                            "balance_g": l.get("balance_g"),
                            "opened_on": l.get("opened_on"),
                            "price": l.get("price"),
                        }
                        for l in open_lots
                    ],
                }
            lot_id = open_lots[0]["id"]
            bean_id = bean["id"]
        payload = {k: v for k, v in data.items() if k != "bean_id" and v is not None}
        payload["lot_id"] = int(lot_id)
        out = self.request("POST", "/api/brews", json=payload)
        if not bean_id:
            beans = self.list_beans("all").get("beans") or []
            for b in beans:
                full = self.get_bean(b["id"])
                if any(l.get("id") == payload["lot_id"] for l in full.get("lots") or []):
                    bean = full
                    break
            else:
                bean = {}
        else:
            bean = self.get_bean(int(bean_id))
        out.update(self._lot_label(bean, payload["lot_id"]))
        return out

    def list_consumption(self, bean_id: int | None = None, person_id: int | None = None, limit: int = 50):
        q = [f"limit={limit}"]
        if bean_id:
            q.append(f"bean_id={bean_id}")
        if person_id:
            q.append(f"person_id={person_id}")
        return self.request("GET", "/api/consumption?" + "&".join(q))

    def void_consumption(self, cons_id: int, reason: str | None = None):
        return self.request("POST", f"/api/consumption/{cons_id}/void", json={"reason": reason} if reason else {})

    def unvoid_consumption(self, cons_id: int):
        return self.request("POST", f"/api/consumption/{cons_id}/unvoid")

    def delete_voided_consumption(self, cons_id: int):
        return self.request("DELETE", f"/api/consumption/{cons_id}")

    def reassign_consumption(self, cons_id: int, person: str):
        return self.request("POST", f"/api/consumption/{cons_id}/person", json={"person": person})

    def add_brew_photo(self, cons_id: int, file_path: str, kind: str = "bed"):
        return self.upload(f"/api/consumption/{cons_id}/photos", file_path, {"kind": kind})

    def delete_brew_photo(self, photo_id: int):
        return self.request("DELETE", f"/api/consumption-photos/{photo_id}")

    # ── 人 ────────────────────────────────────────────────

    def list_people(self, include_inactive: bool = False):
        return self.request("GET", f"/api/people?include_inactive={str(include_inactive).lower()}")

    def add_person(self, name: str):
        return self.request("POST", "/api/people", json={"name": name})

    def rename_person(self, person_id: int, name: str):
        return self.request("PATCH", f"/api/people/{person_id}", json={"name": name})

    def set_person_active(self, person_id: int, active: bool):
        return self.request("PATCH", f"/api/people/{person_id}", json={"active": active})

    def delete_person(self, person_id: int):
        return self.request("DELETE", f"/api/people/{person_id}")

    def get_profile(self, person_id: int):
        return self.request("GET", f"/api/people/{person_id}/profile")

    # ── 酒 ────────────────────────────────────────────────

    def list_spirits(self, scope: str = "stock"):
        return self.request("GET", f"/api/spirits?scope={scope}")

    def get_spirit(self, bottle_id: int):
        return self.request("GET", f"/api/spirits/{bottle_id}")

    def create_spirit(self, data: dict):
        return self.request("POST", "/api/spirits", json=data)

    def update_spirit(self, bottle_id: int, data: dict):
        return self.request("PATCH", f"/api/spirits/{bottle_id}", json=data)

    def delete_spirit(self, bottle_id: int, mode: str | None = None):
        q = f"?mode={mode}" if mode else ""
        return self.request("DELETE", f"/api/spirits/{bottle_id}{q}")

    def add_spirit_photo(self, bottle_id: int, file_path: str, kind: str = "pack"):
        return self.upload(f"/api/spirits/{bottle_id}/photos", file_path, {"kind": kind})

    def create_bottle_lot(self, bottle_id: int, data: dict):
        return self.request("POST", f"/api/spirits/{bottle_id}/lots", json=data)

    def open_bottle(self, lot_id: int):
        return self.request("POST", f"/api/bottle-lots/{lot_id}/open", json={})

    def adjust_bottle(self, lot_id: int, actual_ml: float, note: str | None = None):
        return self.request(
            "POST", f"/api/bottle-lots/{lot_id}/adjust", json={"actual_ml": actual_ml, "note": note}
        )

    def close_bottle(self, lot_id: int, note: str | None = None):
        return self.request("POST", f"/api/bottle-lots/{lot_id}/close", json={"note": note} if note else {})

    def record_drink(self, data: dict):
        lot_id = data.get("lot_id")
        bottle_id = data.get("bottle_id")
        if lot_id is None:
            if bottle_id is None:
                raise ApiError(400, "要指定 lot_id。多瓶未关时先 get_spirit 看瓶子，不要让我自己挑。")
            bottle = self.get_spirit(int(bottle_id))
            open_lots = [l for l in bottle.get("lots") or [] if not l.get("closed_at")]
            if not open_lots:
                raise ApiError(400, "这支酒没有未关的瓶子")
            if len(open_lots) > 1:
                return {
                    "error": "有多瓶未关，请指定 lot_id，我不自己挑",
                    "lots": [{"lot_id": l["id"], "balance_ml": l.get("balance_ml")} for l in open_lots],
                }
            lot_id = open_lots[0]["id"]
        payload = {k: v for k, v in data.items() if k != "bottle_id" and v is not None}
        payload["lot_id"] = int(lot_id)
        out = self.request("POST", "/api/drinks", json=payload)
        out["lot_id"] = payload["lot_id"]
        return out

    def list_menu(self, listed_only: bool = True):
        return self.request("GET", f"/api/menu?listed_only={'true' if listed_only else 'false'}")

    def add_menu_item(self, data: dict):
        return self.request("POST", "/api/menu", json=data)

    def set_menu_listed(self, item_id: int, listed: bool):
        return self.request("PATCH", f"/api/menu/{item_id}", json={"listed": listed})

    def reorder_menu(self, ids: list[int]):
        return self.request("PUT", "/api/menu/order", json={"ids": ids})

    def list_recipes(self):
        return self.request("GET", "/api/recipes")

    def get_recipe(self, recipe_id: int):
        return self.request("GET", f"/api/recipes/{recipe_id}")

    def delete_recipe(self, recipe_id: int):
        return self.request("DELETE", f"/api/recipes/{recipe_id}")

    def delete_menu_item(self, item_id: int):
        return self.request("DELETE", f"/api/menu/{item_id}")

    def create_recipe(self, name: str, lines_json: str, steps: str | None = None, note: str | None = None):
        data = {"name": name, "lines": json.loads(lines_json)}
        if steps is not None:
            data["steps"] = steps
        if note is not None:
            data["note"] = note
        return self.request("POST", "/api/recipes", json=data)

    def update_recipe(
        self,
        recipe_id: int,
        name: str | None = None,
        lines_json: str | None = None,
        steps: str | None = None,
        note: str | None = None,
    ):
        data: dict = {}
        if name is not None:
            data["name"] = name
        if lines_json is not None:
            data["lines"] = json.loads(lines_json)
        if steps is not None:
            data["steps"] = steps
        if note is not None:
            data["note"] = note
        return self.request("PATCH", f"/api/recipes/{recipe_id}", json=data)

    def pour_menu(
        self,
        menu_item_id: int,
        person: str | None = None,
        lines_json: str | None = None,
        note: str | None = None,
        people_json: str | None = None,
    ):
        payload: dict = {"menu_item_id": menu_item_id}
        if people_json:
            payload["people"] = json.loads(people_json)
        elif person:
            payload["person"] = person
        if note:
            payload["note"] = note
        if lines_json:
            payload["lines"] = json.loads(lines_json)
        return self.request("POST", "/api/menu/pour", json=payload)

    # ── 统计 / 日历 / 地图 / 出表 ──────────────────────────

    def list_restock(self):
        return self.request("GET", "/api/restock")

    def add_restock_photo(self, bean_id: int, file_path: str, note: str = ""):
        return self.upload(f"/api/beans/{bean_id}/restock-photos", file_path, {"note": note})

    def get_stats(self, period: str = "month"):
        return self.request("GET", f"/api/stats?period={period}")

    def calendar_month(self, year: int, month: int, person_id: int | None = None):
        q = f"/api/calendar?year={year}&month={month}"
        if person_id:
            q += f"&person_id={person_id}"
        return self.request("GET", q)

    def calendar_day(self, date: str, person_id: int | None = None):
        q = f"/api/calendar/day?date={date}"
        if person_id:
            q += f"&person_id={person_id}"
        return self.request("GET", q)

    def export_csv(self, dest: str, period: str = "all"):
        raw = self.request("GET", f"/api/export?period={period}")
        if isinstance(raw, dict):
            raise ApiError(500, "出表没拿到文件")
        path = Path(dest).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
        return {"path": str(path.resolve()), "bytes": len(raw), "period": period}

    def get_map(self):
        return self.request("GET", "/api/map")

    def set_bean_places(self, bean_id: int, places: list):
        if isinstance(places, str):
            places = json.loads(places)
        return self.request("PUT", f"/api/beans/{bean_id}/places", json={"places": places})

    def guess_bean_places(self, bean_id: int):
        return self.request("POST", f"/api/beans/{bean_id}/places/guess", json={})

    def list_review_queue(self, status: str = "pending"):
        return self.request("GET", f"/api/admin/review/beans?status={status}")

    def get_review_bean(self, bean_id: int):
        return self.request("GET", f"/api/admin/review/beans/{bean_id}")

    def certify_bean(
        self,
        bean_id: int,
        note: str = "",
        verify_places: bool = True,
        force_places: bool = False,
    ):
        return self.request(
            "POST",
            f"/api/admin/review/beans/{bean_id}/certify",
            json={
                "note": note,
                "verify_places": verify_places,
                "force_places": force_places,
            },
        )

    def uncertify_bean(self, bean_id: int, note: str = ""):
        return self.request(
            "POST",
            f"/api/admin/review/beans/{bean_id}/uncertify",
            json={"note": note},
        )

    def review_set_places(self, bean_id: int, places):
        if isinstance(places, str):
            places = json.loads(places)
        return self.request(
            "PUT",
            f"/api/admin/review/beans/{bean_id}/places",
            json={"places": places},
        )

    def review_guess_places(self, bean_id: int):
        return self.request("POST", f"/api/admin/review/beans/{bean_id}/places/guess", json={})
