"""MCP 打现有 HTTP：未运行要报、网页占锁硬拒、多袋不自挑。"""

import io
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
        "add_spirit_photo",
        "create_bottle_lot",
        "open_bottle",
        "adjust_bottle",
        "close_bottle",
        "record_drink",
        "list_restock",
        "add_restock_photo",
        "get_stats",
        "calendar_month",
        "calendar_day",
        "export_csv",
        "get_map",
        "set_bean_places",
        "guess_bean_places",
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
    mapped = c.get_map()
    assert "beans" in mapped or "pins" in mapped or "places" in mapped or "origins" in mapped
