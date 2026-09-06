"""MCP 打现有 HTTP：未运行要报、网页占锁硬拒、多袋不自挑。"""

import io
import json
import zipfile
from pathlib import Path

import anyio
import httpx
import pytest
from PIL import Image

from app.mcp_client import ApiError, Client, Locked, Offline
from app.mcp_server import mcp


def _mcp(client) -> Client:
    return Client.from_test(client)


def _jpg(tmp_path: Path) -> Path:
    p = tmp_path / "pack.jpg"
    Image.new("RGB", (16, 16), (80, 40, 20)).save(p, "JPEG")
    return p


def test_offline_when_service_down():
    c = Client(httpx.Client(base_url="http://127.0.0.1:1", timeout=0.2), email="a@b.c", password="testpass1")
    with pytest.raises(Offline, match="未在运行"):
        c.list_beans()


def test_missing_credentials():
    c = Client(httpx.Client(base_url="http://127.0.0.1:1", timeout=0.2))
    with pytest.raises(ApiError, match="COFFEEBAR_EMAIL"):
        c._login()


def test_wrong_password_is_not_retried(client):
    c = Client(client, email="test@coffeebar.local", password="wrongwrong")
    with pytest.raises(ApiError, match="邮箱或密码不对"):
        c._login()
    assert c._auth_error is not None
    with pytest.raises(ApiError, match="邮箱或密码不对"):
        c._login()


def test_tool_catalog_covers_bar():
    tools = anyio.run(mcp.list_tools)
    names = {t.name for t in tools}
    for n in (
        "list_beans",
        "get_bean",
        "create_bean",
        "update_bean",
        "delete_bean",
        "add_bean_photo",
        "delete_photo",
        "add_score",
        "create_bean_lot",
        "open_lot",
        "measure_lot",
        "adjust_lot",
        "close_lot",
        "writeoff_lot",
        "brew_plan",
        "list_brew_methods",
        "set_brew_default",
        "record_brew",
        "list_consumption",
        "void_consumption",
        "unvoid_consumption",
        "delete_voided_consumption",
        "reassign_consumption",
        "add_brew_photo",
        "delete_brew_photo",
        "list_people",
        "add_person",
        "rename_person",
        "set_person_active",
        "delete_person",
        "get_profile",
        "list_spirits",
        "get_spirit",
        "create_spirit",
        "update_spirit",
        "delete_spirit",
        "add_spirit_photo",
        "create_bottle_lot",
        "open_bottle",
        "adjust_bottle",
        "close_bottle",
        "record_drink",
        "list_menu",
        "add_menu_item",
        "set_menu_listed",
        "reorder_menu",
        "create_recipe",
        "update_recipe",
        "list_recipes",
        "get_recipe",
        "delete_recipe",
        "delete_menu_item",
        "pour_menu",
        "list_restock",
        "add_restock_photo",
        "get_stats",
        "calendar_month",
        "calendar_day",
        "export_csv",
        "get_map",
        "set_bean_places",
        "guess_bean_places",
        "list_review_queue",
        "get_review_bean",
        "certify_bean",
        "uncertify_bean",
        "review_set_places",
        "review_guess_places",
        "list_plaza",
        "get_plaza_bean",
        "take_plaza_bean",
        "list_plaza_gear",
        "get_plaza_gear",
        "take_plaza_gear",
        "list_gear",
        "get_gear",
        "create_gear",
        "open_filter_pack",
        "update_gear",
        "delete_gear",
        "add_gear_photo",
        "delete_gear_photo",
        "add_gear_from_catalog",
        "list_gear_catalog",
        "list_gear_queue",
        "collect_gear",
        "update_gear_catalog",
        "list_kingdom",
        "get_kingdom",
        "score_kingdom",
        "unscore_kingdom",
        "add_kingdom_score_photo",
        "delete_kingdom_score_photo",
        "favorite_kingdom",
        "list_kingdom_queue",
        "collect_kingdom",
    ):
        assert n in names, n
    assert "delete_account" not in names
    assert "lock" not in names


def test_create_list_and_brew_reports_lot(client):
    c = _mcp(client)
    bean = c.create_bean({"name": "MCP西达摩", "nominal_g": 200, "price": 80, "origin": "埃塞俄比亚"})
    assert bean["name"] == "MCP西达摩"
    listed = c.list_beans("stock")
    assert any(b["id"] == bean["id"] for b in listed["beans"])
    brew = c.record_brew({"lot_id": bean["lots"][0]["id"], "amount_g": 16, "person": "戚浩辰", "bean_id": bean["id"]})
    assert brew["lot_id"] == bean["lots"][0]["id"]
    assert brew["used_lot"]
    assert brew["bean_name"] == "MCP西达摩"


def test_multi_lot_refuses_to_pick(client):
    c = _mcp(client)
    bean = c.create_bean({"name": "MCP双袋", "nominal_g": 200, "price": 80})
    c.create_bean_lot(bean["id"], {"nominal_g": 200, "price": 80})
    out = c.record_brew({"bean_id": bean["id"], "amount_g": 15})
    assert out["error"]
    assert len(out["lots"]) == 2


def test_web_lock_hard_rejects_mcp(client):
    c = _mcp(client)
    bean = c.create_bean({"name": "MCP锁", "nominal_g": 200, "price": 80})
    res = f"bean:{bean['id']}"
    assert client.post(f"/api/locks/{res}", json={"holder": "小主机"}, headers={"X-Session": "web1"}).status_code == 200
    with pytest.raises(Locked):
        c.record_brew({"lot_id": bean["lots"][0]["id"], "amount_g": 15})


def test_void_and_export(client, tmp_path):
    c = _mcp(client)
    bean = c.create_bean({"name": "MCP出表", "nominal_g": 200, "price": 80})
    brew = c.record_brew({"lot_id": bean["lots"][0]["id"], "amount_g": 16, "person": "戚浩辰"})
    c.void_consumption(brew["id"], "记错了")
    dest = tmp_path / "账.zip"
    out = c.export_csv(str(dest), "all")
    assert dest.is_file()
    assert out["bytes"] > 0
    zf = zipfile.ZipFile(io.BytesIO(dest.read_bytes()))
    assert "消耗明细.csv" in zf.namelist()


def test_photo_calendar_stats_spirit(client, tmp_path):
    c = _mcp(client)
    bean = c.create_bean({"name": "MCP图", "nominal_g": 200, "price": 80, "origin": "埃塞俄比亚 西达玛"})
    pic = c.add_bean_photo(bean["id"], str(_jpg(tmp_path)), "pack")
    assert pic["id"]
    month = c.calendar_month(2026, 9)
    assert "days" in month
    stats = c.get_stats("all")
    assert "beans_g" in stats
    spirit = c.create_spirit({"name": "MCP酒", "abv": 40, "kind": "威士忌", "nominal_ml": 700, "price": 200})
    drink = c.record_drink({"lot_id": spirit["lots"][0]["id"], "amount_ml": 30, "person": "丁瀚舟"})
    assert drink["lot_id"] == spirit["lots"][0]["id"]
    rec = c.create_recipe("【测试】MCP纯饮方", json.dumps([{"spirit_id": spirit["id"], "amount_ml": 25}]))
    item = c.add_menu_item({"kind": "cocktail", "recipe_id": rec["id"]})
    poured = c.pour_menu(item["id"], "丁瀚舟", json.dumps([
        {"spirit_id": spirit["id"], "lot_id": spirit["lots"][0]["id"], "amount_ml": 20}
    ]))
    assert poured["amount_ml"] == 20
    assert poured["kind"] == "cocktail"
    mapped = c.get_map()
    assert "beans" in mapped or "pins" in mapped or "places" in mapped or "origins" in mapped


def test_mcp_recipe_can_swap_spirits(client):
    """先选配方，再换里面的基酒，一次改掉。"""
    c = _mcp(client)
    gin = c.create_spirit({"name": "【测试】MCP金", "kind": "金酒", "abv": 40, "nominal_ml": 700, "price": 80})
    rum = c.create_spirit({"name": "【测试】MCP朗姆", "kind": "朗姆", "abv": 40, "nominal_ml": 700, "price": 90})
    rec = c.create_recipe("【测试】MCP可换基酒", json.dumps([{"spirit_id": gin["id"], "amount_ml": 30}]))
    listed = c.add_menu_item({"kind": "cocktail", "recipe_id": rec["id"]})
    assert listed["lines"][0]["spirit_id"] == gin["id"]

    got = c.get_recipe(rec["id"])
    assert got["name"] == "【测试】MCP可换基酒"
    names = [r["name"] for r in c.list_recipes()["recipes"]]
    assert "【测试】MCP可换基酒" in names

    updated = c.update_recipe(
        rec["id"],
        lines_json=json.dumps(
            [{"spirit_id": rum["id"], "amount_ml": 40}, {"spirit_id": gin["id"], "amount_ml": 15}]
        ),
    )
    assert [ln["spirit_name"] for ln in updated["lines"]] == ["【测试】MCP朗姆", "【测试】MCP金"]
    menu_row = next(it for it in c.list_menu(False)["items"] if it["id"] == listed["id"])
    assert [ln["spirit_name"] for ln in menu_row["lines"]] == ["【测试】MCP朗姆", "【测试】MCP金"]

    c.delete_menu_item(listed["id"])
    assert all(it["id"] != listed["id"] for it in c.list_menu(False)["items"])
    c.delete_recipe(rec["id"])
    assert all(r["id"] != rec["id"] for r in c.list_recipes()["recipes"])


def test_mcp_gear_and_brew_methods(client):
    c = _mcp(client)
    item = c.create_gear(
        {
            "name": "【测试】MCP滤杯",
            "kind": "dripper",
            "family": "flat",
        }
    )
    assert item["name"] == "【测试】MCP滤杯"
    listed = c.list_gear()["gear"]
    assert any(g["id"] == item["id"] for g in listed)
    methods = {m["key"]: m for m in c.list_brew_methods()["methods"]}
    assert methods["kalita"]["owned"] is True
    assert methods["v60"]["owned"] is False
    c.delete_gear(item["id"])
    assert all(g["id"] != item["id"] for g in c.list_gear()["gear"])


def test_mcp_plaza_is_sanitized(client):
    public = client.post(
        "/api/beans",
        json={
            "name": "MCP广场浅烘",
            "origin": "埃塞俄比亚",
            "roast": "浅烘",
            "process": "水洗",
            "tags": ["柑橘"],
            "visibility": "public",
            "nominal_g": 200,
            "price": 88,
        },
    ).json()
    private = client.post("/api/beans", json={"name": "MCP广场私库", "visibility": "private"}).json()
    c = _mcp(client)
    listed = c.list_plaza(q="MCP广场浅烘")["beans"]
    assert any(b["id"] == public["id"] for b in listed)
    assert all(b["id"] != private["id"] for b in listed)
    hit = next(b for b in listed if b["id"] == public["id"])
    assert hit["offer"]["price"] == 88
    assert hit["offer"]["nominal_g"] == 200
    assert hit["offer"]["per_g"] == pytest.approx(88 / 200)
    for key in ("unit_cost", "balance_g", "lots", "log", "owner_id", "price", "remaining_value"):
        assert key not in hit
    card = c.get_plaza_bean(public["id"])
    assert card["name"] == "MCP广场浅烘"
    assert card["offer"]["price"] == 88
    assert card["offer"]["nominal_g"] == 200
    assert card["offer"]["per_g"] == pytest.approx(88 / 200)
    assert "unit_cost" not in card
    assert "balance_g" not in card
    roast = c.list_plaza(roast="浅烘", q="MCP广场")["beans"]
    assert any(b["id"] == public["id"] for b in roast)
    mid = c.list_plaza(roast="中烘", q="MCP广场浅烘")["beans"]
    assert all(b["id"] != public["id"] for b in mid)
    try:
        c.get_plaza_bean(private["id"])
        raise AssertionError("私卡不应出现在广场")
    except ApiError as exc:
        assert exc.status == 404


def test_mcp_take_plaza_bean_and_gear(client):
    bean = client.post(
        "/api/beans",
        json={"name": "MCP领回豆", "origin": "肯尼亚", "visibility": "public"},
    ).json()
    gear = client.post(
        "/api/gear",
        json={"name": "MCP领回壶", "kind": "kettle", "family": "gooseneck", "visibility": "public"},
    ).json()
    client.post("/api/auth/logout")
    client.post(
        "/api/auth/register",
        json={"email": "mcp-taker@coffeebar.local", "password": "testpass1"},
    )
    c = _mcp(client)
    listed = c.list_plaza_gear()["gear"]
    assert any(g["id"] == gear["id"] for g in listed)
    got = c.get_plaza_gear(gear["id"])
    assert got["name"] == "MCP领回壶"
    copied_gear = c.take_plaza_gear(gear["id"])
    assert copied_gear["source_gear_id"] == gear["id"]
    assert c.take_plaza_gear(gear["id"])["id"] == copied_gear["id"]
    copied_bean = c.take_plaza_bean(bean["id"])
    assert copied_bean["source_bean_id"] == bean["id"]
    assert copied_bean["lots"] == []
    assert c.take_plaza_bean(bean["id"])["id"] == copied_bean["id"]


def test_mcp_kingdom_cupping(client, monkeypatch):
    monkeypatch.setenv("COFFEEBAR_ADMIN_EMAILS", "boss@coffeebar.local")
    bean = client.post("/api/beans", json={"name": "【测试】MCP王国", "origin": "埃塞俄比亚"}).json()
    client.patch(f"/api/beans/{bean['id']}", json={"visibility": "public"})
    client.post("/api/auth/logout")
    client.post(
        "/api/auth/register",
        json={"email": "boss@coffeebar.local", "password": "testpass1"},
    )
    kid = client.post(f"/api/admin/kingdom/collect/{bean['id']}", json={}).json()["id"]
    client.post("/api/auth/logout")
    client.post(
        "/api/auth/login",
        json={"email": "test@coffeebar.local", "password": "testpass1"},
    )

    c = _mcp(client)
    listed = c.list_kingdom()["beans"]
    assert any(b["id"] == kid for b in listed)
    scored = c.score_kingdom(kid, {"overall": 8, "comment": "MCP杯测"})
    assert scored["mine"]["overall"] == 8
    fav = c.favorite_kingdom(kid)
    assert fav["favorited"] is True
    saved = c.list_kingdom(True)["beans"]
    assert [b["id"] for b in saved] == [kid]
    gone = c.unscore_kingdom(kid)
    assert gone["mine"] is None
