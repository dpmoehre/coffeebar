"""本机 MCP：Cursor 经 stdio 调用，打同一套 FastAPI / 写锁。"""

from __future__ import annotations

import json
from typing import Any

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from .mcp_client import ApiError, Client, Locked, Offline

mcp = MCPServer(
    "coffeebar",
    version="0.1.0",
    instructions=(
        "公司吧台手冲/调酒账本。写入与网页共用接口和写锁。"
        "网页正在改这一条时硬拒绝，不要接管、不要重试。"
        "关袋、撤回、删卡、删人必须人明确说。"
        "多袋/多瓶未关时不要自己挑，先列出再等 lot_id。"
        "酒单可上架纯饮或鸡尾酒；倒一杯可改实际毫升，同类可换支。自制基酒还没有。"
        "豆卡默认只自己看；主人可改成公开。公开未认证也能上广场。"
        "逛广场用 list_plaza / get_plaza_bean，和网页同一套卡：有买袋价和袋上克重，没有还剩多少和流水。"
        "公开器具用 list_plaza_gear / get_plaza_gear。take_plaza_bean / take_plaza_gear 领到自己库，是拷贝不是抢。"
        "roast、process 逗号分隔是或选，tags 逗号分隔是且选。in_kingdom 只看已进王国的。"
        "认证必须管理员账号：list_review_queue / get_review_bean。"
        "先看 checklist（照片/杯测/描述/进价/产地/落点）和档案是不是正常豆子，再对照 places.gazetteer。"
        "空卡或乱钉不要过。不对就 review_set_places 或 review_guess_places，再 certify_bean。"
        "对不上又坚持认证时带 force_places。普通人调审核工具会 403。"
        "改名字/产地/豆种/处理厂/处理法/烘焙/海拔或改钉会掉认证，要重审。"
        "咖啡器具挂在账号台面上：list_gear / create_gear。滤纸 kind=filter，"
        "open_filter_pack 新开一包才计张，不估旧包。冲一杯自动扣一张并加纸钱。"
        "滤杯要写 family=cone 或 flat，才能按器具给冲煮建议。"
        "管理员用 list_gear_queue / collect_gear 收到公共目录，"
        "再 update_gear_catalog 挂 brew_method 和冲煮备注。"
        "咖啡王国是公共豆种和公共器具：list_kingdom / get_kingdom，score_kingdom 一人一豆一条可改，"
        "add_kingdom_score_photo 给自己的杯测挂图，favorite_kingdom 开关收藏。"
        "器具复用目录：list_kingdom_gear / get_kingdom_gear，score_kingdom_gear 只打总体分和一句话，"
        "favorite_kingdom_gear 收藏。管理员 collect_gear 收到目录就是进王国，不要另收一套。"
        "管理员 collect_kingdom 把公开豆卡收进王国，两张同名卡可挂同一支。"
        "服务没开就说 coffeebar 未在运行。"
    ),
)

_client: Client | None = None


def client() -> Client:
    global _client
    if _client is None:
        _client = Client.from_env()
    return _client


def _call(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except (Offline, Locked, ApiError) as exc:
        raise ToolError(str(exc)) from exc


def _drop_none(data: dict) -> dict:
    return {k: v for k, v in data.items() if v is not None}


# ── 豆子 ──────────────────────────────────────────────────


@mcp.tool()
def list_beans(scope: str = "stock") -> Any:
    """查豆库。scope: stock 在库 / history 历史 / all 全部。"""
    return _call(client().list_beans, scope)


@mcp.tool()
def get_bean(bean_id: int) -> Any:
    """看一张豆卡：袋子、照片、冲煮记录、写锁。"""
    return _call(client().get_bean, bean_id)


@mcp.tool()
def create_bean(
    name: str,
    origin: str | None = None,
    varietal: str | None = None,
    producer: str | None = None,
    altitude: str | None = None,
    process: str | None = None,
    roast: str | None = None,
    water_temp: str | None = None,
    note: str | None = None,
    tags: list[str] | None = None,
    nominal_g: float | None = None,
    price: float | None = None,
    bought_on: str | None = None,
    roasted_on: str | None = None,
    brew_method: str | None = None,
    brew_dose_g: float | None = None,
    brew_ratio: float | None = None,
    brew_note: str | None = None,
    visibility: str | None = None,
) -> Any:
    """建一张豆卡。带 nominal_g 会同时入第一袋。roasted_on 是袋上烘焙日，可空。visibility=public 建完就公开，默认只自己看。返回 id。"""
    return _call(
        client().create_bean,
        _drop_none(
            {
                "name": name,
                "origin": origin,
                "varietal": varietal,
                "producer": producer,
                "altitude": altitude,
                "process": process,
                "roast": roast,
                "water_temp": water_temp,
                "note": note,
                "tags": tags,
                "nominal_g": nominal_g,
                "price": price,
                "bought_on": bought_on,
                "roasted_on": roasted_on,
                "brew_method": brew_method,
                "brew_dose_g": brew_dose_g,
                "brew_ratio": brew_ratio,
                "brew_note": brew_note,
                "visibility": visibility,
            }
        ),
    )


@mcp.tool()
def update_bean(
    bean_id: int,
    name: str | None = None,
    origin: str | None = None,
    varietal: str | None = None,
    producer: str | None = None,
    altitude: str | None = None,
    process: str | None = None,
    roast: str | None = None,
    water_temp: str | None = None,
    note: str | None = None,
    tags: list[str] | None = None,
    visibility: str | None = None,
) -> Any:
    """改豆卡产地、烘焙、风味、标签、公开状态。改认证相关字段会掉认证。网页占锁时会被拒。"""
    return _call(
        client().update_bean,
        bean_id,
        _drop_none(
            {
                "name": name,
                "origin": origin,
                "varietal": varietal,
                "producer": producer,
                "altitude": altitude,
                "process": process,
                "roast": roast,
                "water_temp": water_temp,
                "note": note,
                "tags": tags,
                "visibility": visibility,
            }
        ),
    )


@mcp.tool()
def delete_bean(bean_id: int, mode: str | None = None) -> Any:
    """删整张豆卡。有未撤回冲煮必须人指定 mode=keep（留下钱）或 wipe（连记录抹）。"""
    return _call(client().delete_bean, bean_id, mode)


@mcp.tool()
def add_bean_photo(bean_id: int, path: str, kind: str = "pack") -> Any:
    """挂本地图片。kind: pack 包装 / tray 豆盘 / card 店家豆卡。"""
    return _call(client().add_bean_photo, bean_id, path, kind)


@mcp.tool()
def delete_photo(photo_id: int) -> Any:
    """删一张豆或酒的照片。"""
    return _call(client().delete_photo, photo_id)


@mcp.tool()
def add_score(
    bean_id: int,
    dry: float | None = None,
    flavor: float | None = None,
    aftertaste: float | None = None,
    acidity: float | None = None,
    sweetness: float | None = None,
    body: float | None = None,
    balance: float | None = None,
    overall: float | None = None,
    comment: str | None = None,
    lot_id: int | None = None,
    roasted_on: str | None = None,
) -> Any:
    """给这支豆打一杯杯测分。lot_id / roasted_on 可空；烘后天数和阶段由服务端算，不要手填。"""
    return _call(
        client().add_score,
        bean_id,
        _drop_none(
            {
                "dry": dry,
                "flavor": flavor,
                "aftertaste": aftertaste,
                "acidity": acidity,
                "sweetness": sweetness,
                "body": body,
                "balance": balance,
                "overall": overall,
                "comment": comment,
                "lot_id": lot_id,
                "roasted_on": roasted_on,
            }
        ),
    )


@mcp.tool()
def create_bean_lot(
    bean_id: int,
    nominal_g: float,
    price: float | None = None,
    measured_g: float | None = None,
    bought_on: str | None = None,
    roasted_on: str | None = None,
    note: str | None = None,
) -> Any:
    """同豆再入一袋，不新建卡。roasted_on 是袋上烘焙日，可空。"""
    return _call(
        client().create_bean_lot,
        bean_id,
        _drop_none(
            {
                "nominal_g": nominal_g,
                "price": price,
                "measured_g": measured_g,
                "bought_on": bought_on,
                "roasted_on": roasted_on,
                "note": note,
            }
        ),
    )


@mcp.tool()
def open_lot(lot_id: int, on: str | None = None) -> Any:
    """显式开封：只记日子，不动克数。"""
    return _call(client().open_lot, lot_id, on)


@mcp.tool()
def measure_lot(lot_id: int, measured_g: float) -> Any:
    """开袋实称（可选）。改的是这袋原本有多少。"""
    return _call(client().measure_lot, lot_id, measured_g)


@mcp.tool()
def adjust_lot(lot_id: int, actual_g: float, note: str | None = None) -> Any:
    """盘点：输入现在实际还剩多少克。"""
    return _call(client().adjust_lot, lot_id, actual_g, note)


@mcp.tool()
def close_lot(lot_id: int, note: str | None = None) -> Any:
    """这袋用完并结清偏差。必须人明确说要用完。"""
    return _call(client().close_lot, lot_id, note)


@mcp.tool()
def writeoff_lot(lot_id: int, note: str | None = None) -> Any:
    """整袋补录：克重和钱进统计，不算杯、不算到人。"""
    return _call(client().writeoff_lot, lot_id, note)


# ── 冲煮 / 流水 ────────────────────────────────────────────


@mcp.tool()
def brew_plan(method: str = "v60", dose_g: float = 15, ratio: float = 16) -> Any:
    """按当场粉量和比例算各段用水。不落库。"""
    return _call(client().brew_plan, method, dose_g, ratio)


@mcp.tool()
def list_brew_methods() -> Any:
    """列出冲煮方式。已登录时按台面上的滤杯标 owned / suggested。"""
    return _call(client().list_brew_methods)


@mcp.tool()
def list_gear() -> Any:
    """看自己台面上的器具，以及管理员已收录的公共目录。"""
    return _call(client().list_gear)


@mcp.tool()
def get_gear(gear_id: int) -> Any:
    """看一件自己的器具。"""
    return _call(client().get_gear, gear_id)


@mcp.tool()
def create_gear(
    name: str,
    kind: str = "dripper",
    family: str | None = None,
    brand: str | None = None,
    model: str | None = None,
    brew_method: str | None = None,
    note: str | None = None,
    visibility: str | None = None,
) -> Any:
    """登记一件器具。kind: dripper / kettle / grinder / scale / server / filter / other。
    滤杯 family: cone 锥形 / flat 平底 / immersion 浸泡；壶 family: gooseneck 细嘴。
    brew_method 可挂 v60 / hoffmann / kasuya / kalita / volcano。
    visibility=public 公开到广场，默认只自己看。滤纸用 kind=filter，开包走 open_filter_pack。"""
    return _call(
        client().create_gear,
        _drop_none(
            {
                "name": name,
                "kind": kind,
                "family": family,
                "brand": brand,
                "model": model,
                "brew_method": brew_method,
                "note": note,
                "visibility": visibility,
            }
        ),
    )


@mcp.tool()
def open_filter_pack(gear_id: int, sheets: int, price: float | None = None) -> Any:
    """新开一包滤纸才开始计张。sheets 是这包多少张，price 是这包多少钱。不估旧包还剩多少。"""
    return _call(client().open_filter_pack, gear_id, _drop_none({"sheets": sheets, "price": price}))


@mcp.tool()
def update_gear(
    gear_id: int,
    name: str | None = None,
    kind: str | None = None,
    family: str | None = None,
    brand: str | None = None,
    model: str | None = None,
    brew_method: str | None = None,
    note: str | None = None,
    visibility: str | None = None,
) -> Any:
    """改一件自己的器具。visibility=public 公开到广场，private 改回只自己看。"""
    return _call(
        client().update_gear,
        gear_id,
        _drop_none(
            {
                "name": name,
                "kind": kind,
                "family": family,
                "brand": brand,
                "model": model,
                "brew_method": brew_method,
                "note": note,
                "visibility": visibility,
            }
        ),
    )


@mcp.tool()
def delete_gear(gear_id: int) -> Any:
    """从台面拿掉一件器具。人明确说才删。目录里已收录的那条还在。"""
    return _call(client().delete_gear, gear_id)


@mcp.tool()
def add_gear_photo(gear_id: int, path: str) -> Any:
    """给自己的器具挂一张照片。"""
    return _call(client().add_gear_photo, gear_id, path)


@mcp.tool()
def delete_gear_photo(photo_id: int) -> Any:
    """删一张器具照片。"""
    return _call(client().delete_gear_photo, photo_id)


@mcp.tool()
def add_gear_from_catalog(catalog_id: int) -> Any:
    """从管理员收录的目录领一件到自己台面。已经有了会 409。"""
    return _call(client().add_gear_from_catalog, catalog_id)


@mcp.tool()
def list_gear_catalog() -> Any:
    """看公共器具目录。"""
    return _call(client().list_gear_catalog)


@mcp.tool()
def list_gear_queue() -> Any:
    """管理员：还没收录的私人器具。普通人 403。"""
    return _call(client().list_gear_queue)


@mcp.tool()
def collect_gear(
    gear_id: int,
    catalog_id: int | None = None,
    name: str | None = None,
    kind: str | None = None,
    family: str | None = None,
    brand: str | None = None,
    model: str | None = None,
    brew_method: str | None = None,
    note: str | None = None,
) -> Any:
    """管理员：把一件私人器具收到目录。给 catalog_id 就是挂到已有条目，否则新建。
    可改名字、形状、冲煮方式和备注。普通人 403。"""
    return _call(
        client().collect_gear,
        gear_id,
        _drop_none(
            {
                "catalog_id": catalog_id,
                "name": name,
                "kind": kind,
                "family": family,
                "brand": brand,
                "model": model,
                "brew_method": brew_method,
                "note": note,
            }
        ),
    )


@mcp.tool()
def update_gear_catalog(
    catalog_id: int,
    name: str | None = None,
    kind: str | None = None,
    family: str | None = None,
    brand: str | None = None,
    model: str | None = None,
    brew_method: str | None = None,
    note: str | None = None,
) -> Any:
    """管理员：改目录里一件器具，把冲煮方式和备注挂到配方上。普通人 403。"""
    return _call(
        client().update_gear_catalog,
        catalog_id,
        _drop_none(
            {
                "name": name,
                "kind": kind,
                "family": family,
                "brand": brand,
                "model": model,
                "brew_method": brew_method,
                "note": note,
            }
        ),
    )


@mcp.tool()
def set_brew_default(
    bean_id: int,
    method: str = "v60",
    dose_g: float = 15,
    ratio: float = 16,
    note: str | None = None,
) -> Any:
    """把店家推荐存成这支豆的默认冲煮参数。"""
    return _call(
        client().set_brew_default,
        bean_id,
        _drop_none({"method": method, "dose_g": dose_g, "ratio": ratio, "note": note}),
    )


@mcp.tool()
def record_brew(
    amount_g: float,
    lot_id: int | None = None,
    bean_id: int | None = None,
    person: str | None = None,
    brew_method: str | None = None,
    brew_ratio: float | None = None,
    brew_total_s: float | None = None,
    brew_stages_json: str | None = None,
    note: str | None = None,
    as_cup: bool = True,
    filter_pack_id: int | None = None,
) -> Any:
    """记一次冲煮。多袋未关必须给 lot_id，我会回报扣的是哪一袋。带 brew_total_s 会对照方案给研磨建议。
    开着好几包滤纸时给 filter_pack_id，不自挑；没开包就不扣纸。"""
    extra = {}
    if brew_stages_json:
        extra["brew_stages"] = json.loads(brew_stages_json)
    return _call(
        client().record_brew,
        _drop_none(
            {
                "amount_g": amount_g,
                "lot_id": lot_id,
                "bean_id": bean_id,
                "person": person,
                "brew_method": brew_method,
                "brew_ratio": brew_ratio,
                "brew_total_s": brew_total_s,
                "note": note,
                "as_cup": as_cup,
                "filter_pack_id": filter_pack_id,
                **extra,
            }
        ),
    )


@mcp.tool()
def list_consumption(
    bean_id: int | None = None,
    person_id: int | None = None,
    limit: int = 50,
) -> Any:
    """看消耗流水。"""
    return _call(client().list_consumption, bean_id, person_id, limit)


@mcp.tool()
def void_consumption(cons_id: int, reason: str | None = None) -> Any:
    """撤回一笔消耗。只划掉不删。必须人明确说要撤回。"""
    return _call(client().void_consumption, cons_id, reason)


@mcp.tool()
def unvoid_consumption(cons_id: int) -> Any:
    """把已撤回的一笔恢复。"""
    return _call(client().unvoid_consumption, cons_id)


@mcp.tool()
def delete_voided_consumption(cons_id: int) -> Any:
    """彻底删掉已经撤回的一笔。没撤回的拒删。"""
    return _call(client().delete_voided_consumption, cons_id)


@mcp.tool()
def reassign_consumption(cons_id: int, person: str) -> Any:
    """改这笔是谁喝的。库存和钱不动。"""
    return _call(client().reassign_consumption, cons_id, person)


@mcp.tool()
def add_brew_photo(cons_id: int, path: str, kind: str = "bed") -> Any:
    """给一笔冲煮挂过程照。kind: beans 称豆 / bed 粉床 / finish 冲完 / gear 器具。"""
    return _call(client().add_brew_photo, cons_id, path, kind)


@mcp.tool()
def delete_brew_photo(photo_id: int) -> Any:
    """删一张冲煮过程照。"""
    return _call(client().delete_brew_photo, photo_id)


# ── 人 ────────────────────────────────────────────────────


@mcp.tool()
def list_people(include_inactive: bool = False) -> Any:
    """查「谁喝的」。"""
    return _call(client().list_people, include_inactive)


@mcp.tool()
def add_person(name: str) -> Any:
    """加人。"""
    return _call(client().add_person, name)


@mcp.tool()
def rename_person(person_id: int, name: str) -> Any:
    """改名，历史流水跟着变。"""
    return _call(client().rename_person, person_id, name)


@mcp.tool()
def set_person_active(person_id: int, active: bool) -> Any:
    """停用或恢复一个人。停用不删记录。"""
    return _call(client().set_person_active, person_id, active)


@mcp.tool()
def delete_person(person_id: int) -> Any:
    """删人。他名下流水变成「没记」，库存和统计总数不变。必须人明确说要删。"""
    return _call(client().delete_person, person_id)


@mcp.tool()
def get_profile(person_id: int) -> Any:
    """看这个人的画像：口味、常喝、花了多少钱。"""
    return _call(client().get_profile, person_id)


# ── 酒 ────────────────────────────────────────────────────


@mcp.tool()
def list_spirits(scope: str = "stock") -> Any:
    """查酒库。scope: stock / history / all。"""
    return _call(client().list_spirits, scope)


@mcp.tool()
def get_spirit(bottle_id: int) -> Any:
    """看一张酒卡和各瓶。"""
    return _call(client().get_spirit, bottle_id)


@mcp.tool()
def create_spirit(
    name: str,
    abv: float | None = None,
    kind: str | None = None,
    flavor: str | None = None,
    category: str | None = None,
    origin: str | None = None,
    note: str | None = None,
    nominal_ml: float | None = None,
    price: float | None = None,
) -> Any:
    """建一张基酒卡。带 nominal_ml 会同时入第一瓶。"""
    return _call(
        client().create_spirit,
        _drop_none(
            {
                "name": name,
                "abv": abv,
                "kind": kind,
                "flavor": flavor,
                "category": category,
                "origin": origin,
                "note": note,
                "nominal_ml": nominal_ml,
                "price": price,
            }
        ),
    )


@mcp.tool()
def update_spirit(
    bottle_id: int,
    name: str | None = None,
    abv: float | None = None,
    kind: str | None = None,
    flavor: str | None = None,
    category: str | None = None,
    origin: str | None = None,
    note: str | None = None,
) -> Any:
    """改酒卡。"""
    return _call(
        client().update_spirit,
        bottle_id,
        _drop_none(
            {
                "name": name,
                "abv": abv,
                "kind": kind,
                "flavor": flavor,
                "category": category,
                "origin": origin,
                "note": note,
            }
        ),
    )


@mcp.tool()
def delete_spirit(bottle_id: int, mode: str | None = None) -> Any:
    """删整张酒卡。有未撤回倒酒必须人指定 mode=keep（留下钱）或 wipe（连记录抹）。"""
    return _call(client().delete_spirit, bottle_id, mode)


@mcp.tool()
def add_spirit_photo(bottle_id: int, path: str, kind: str = "pack") -> Any:
    """给酒瓶挂本地图片。"""
    return _call(client().add_spirit_photo, bottle_id, path, kind)


@mcp.tool()
def create_bottle_lot(
    bottle_id: int,
    nominal_ml: float,
    price: float | None = None,
    bought_on: str | None = None,
    note: str | None = None,
) -> Any:
    """同样的酒再入一瓶。"""
    return _call(
        client().create_bottle_lot,
        bottle_id,
        _drop_none({"nominal_ml": nominal_ml, "price": price, "bought_on": bought_on, "note": note}),
    )


@mcp.tool()
def open_bottle(lot_id: int) -> Any:
    """开瓶：只记日子，不动毫升。"""
    return _call(client().open_bottle, lot_id)


@mcp.tool()
def adjust_bottle(lot_id: int, actual_ml: float, note: str | None = None) -> Any:
    """酒瓶盘点：输入现在实际还剩多少毫升。"""
    return _call(client().adjust_bottle, lot_id, actual_ml, note)


@mcp.tool()
def close_bottle(lot_id: int, note: str | None = None) -> Any:
    """这瓶用完。必须人明确说要用完。"""
    return _call(client().close_bottle, lot_id, note)


@mcp.tool()
def record_drink(
    amount_ml: float,
    lot_id: int | None = None,
    bottle_id: int | None = None,
    person: str | None = None,
    note: str | None = None,
) -> Any:
    """倒一杯。多瓶未关必须给 lot_id。"""
    return _call(
        client().record_drink,
        _drop_none(
            {"amount_ml": amount_ml, "lot_id": lot_id, "bottle_id": bottle_id, "person": person, "note": note}
        ),
    )


# ── 酒单 / 鸡尾酒 ──────────────────────────────────────────


@mcp.tool()
def list_menu(listed_only: bool = True) -> Any:
    """查推荐酒单。listed_only 只看已上架。"""
    return _call(client().list_menu, listed_only)


@mcp.tool()
def add_menu_item(
    kind: str,
    spirit_id: int | None = None,
    recipe_id: int | None = None,
    listed: bool = True,
) -> Any:
    """上架一条。kind=neat 要 spirit_id；kind=cocktail 要 recipe_id。"""
    return _call(
        client().add_menu_item,
        _drop_none({"kind": kind, "spirit_id": spirit_id, "recipe_id": recipe_id, "listed": listed}),
    )


@mcp.tool()
def set_menu_listed(item_id: int, listed: bool) -> Any:
    """上架或下架一条酒单。"""
    return _call(client().set_menu_listed, item_id, listed)


@mcp.tool()
def reorder_menu(ids: list[int]) -> Any:
    """按这个顺序重排酒单，必须包含全部条目。"""
    return _call(client().reorder_menu, ids)


@mcp.tool()
def delete_menu_item(item_id: int) -> Any:
    """从酒单拿掉一条。配方还在，只是不摆了。"""
    return _call(client().delete_menu_item, item_id)


@mcp.tool()
def list_recipes() -> Any:
    """查所有鸡尾酒配方（含没摆上酒单的）。"""
    return _call(client().list_recipes)


@mcp.tool()
def get_recipe(recipe_id: int) -> Any:
    """看一款配方和里面的基酒。"""
    return _call(client().get_recipe, recipe_id)


@mcp.tool()
def create_recipe(name: str, lines_json: str, steps: str | None = None, note: str | None = None) -> Any:
    """建鸡尾酒配方。lines_json 是 JSON 数组，每项 {spirit_id, amount_ml}。"""
    return _call(client().create_recipe, name, lines_json, steps, note)


@mcp.tool()
def update_recipe(
    recipe_id: int,
    name: str | None = None,
    lines_json: str | None = None,
    steps: str | None = None,
    note: str | None = None,
) -> Any:
    """改鸡尾酒配方：名字、步骤、基酒和默认毫升。lines_json 是整份材料 JSON 数组 [{spirit_id, amount_ml}]，一次换掉。已经倒过的巡不跟着改。网页占锁时会被拒。"""
    return _call(client().update_recipe, recipe_id, name, lines_json, steps, note)


@mcp.tool()
def delete_recipe(recipe_id: int) -> Any:
    """删掉一款配方。还有没撤回的出品用过它时会拒。必须人明确说要删。"""
    return _call(client().delete_recipe, recipe_id)


@mcp.tool()
def pour_menu(
    menu_item_id: int,
    person: str | None = None,
    lines_json: str | None = None,
    note: str | None = None,
    people_json: str | None = None,
) -> Any:
    """从酒单倒酒。people_json 是人名数组，多选一人一杯。lines_json 可改毫升、换同一类的 spirit_id、指定 lot_id。同一支多瓶未关不自挑。撤回整巡用 void_consumption。"""
    return _call(client().pour_menu, menu_item_id, person, lines_json, note, people_json)


# ── 统计 / 日历 / 地图 / 出表 ──────────────────────────────


@mcp.tool()
def list_restock() -> Any:
    """补货清单。"""
    return _call(client().list_restock)


@mcp.tool()
def add_restock_photo(bean_id: int, path: str, note: str = "") -> Any:
    """给补货条目挂对照图。"""
    return _call(client().add_restock_photo, bean_id, path, note)


@mcp.tool()
def get_stats(period: str = "month") -> Any:
    """统计数字。period: week / month / year / all。按人看 get_profile。"""
    return _call(client().get_stats, period)


@mcp.tool()
def calendar_month(year: int, month: int, person_id: int | None = None) -> Any:
    """月历点数。一天从凌晨 4 点算起。可按人滤。"""
    return _call(client().calendar_month, year, month, person_id)


@mcp.tool()
def calendar_day(date: str, person_id: int | None = None) -> Any:
    """某一天的流水。date 用 YYYY-MM-DD。"""
    return _call(client().calendar_day, date, person_id)


@mcp.tool()
def export_csv(path: str, period: str = "all") -> Any:
    """把账出成 zip（里面是 UTF-8 BOM CSV）写到本机路径。"""
    return _call(client().export_csv, path, period)


@mcp.tool()
def get_map() -> Any:
    """豆子产地地图数据：钉、国家、产区。不调外网。"""
    return _call(client().get_map)


@mcp.tool()
def set_bean_places(bean_id: int, places_json: str) -> Any:
    """手定落点。places_json 是 JSON 数组，每项 {lat, lng, label}。"""
    return _call(client().set_bean_places, bean_id, places_json)


@mcp.tool()
def guess_bean_places(bean_id: int) -> Any:
    """清掉手定点，用词典重猜。"""
    return _call(client().guess_bean_places, bean_id)


@mcp.tool()
def list_review_queue(status: str = "pending") -> Any:
    """管理员：待审公开豆卡。status: pending 未认证 / certified 已认证 / public 全部公开。普通人 403。"""
    return _call(client().list_review_queue, status)


@mcp.tool()
def get_review_bean(bean_id: int) -> Any:
    """管理员：取一张待审/已公开豆卡。含产地处理烘焙、描述、杯测、照片、进价摘要、checklist，以及当前钉和词典对照。先看是不是正常档案再认证。普通人 403。"""
    return _call(client().get_review_bean, bean_id)


@mcp.tool()
def certify_bean(
    bean_id: int,
    note: str = "",
    verify_places: bool = True,
    force_places: bool = False,
) -> Any:
    """管理员：认证一张已公开豆卡。默认先校对地图钉，对不上会拒绝；force_places 才强行过。普通人 403。"""
    return _call(client().certify_bean, bean_id, note, verify_places, force_places)


@mcp.tool()
def uncertify_bean(bean_id: int, note: str = "") -> Any:
    """管理员：取消认证。卡仍可公开。普通人 403。"""
    return _call(client().uncertify_bean, bean_id, note)


@mcp.tool()
def review_set_places(bean_id: int, places_json: str) -> Any:
    """管理员：审核时改正地图钉。places_json 是 JSON 数组，每项 {lat, lng, label}。会掉认证。普通人 403。"""
    return _call(client().review_set_places, bean_id, places_json)


@mcp.tool()
def review_guess_places(bean_id: int) -> Any:
    """管理员：审核时按词典重猜落点。会掉认证。普通人 403。"""
    return _call(client().review_guess_places, bean_id)


@mcp.tool()
def list_plaza(
    certified_only: bool = False,
    q: str | None = None,
    roast: str | None = None,
    process: str | None = None,
    tags: str | None = None,
    in_kingdom: bool | None = None,
    sort: str = "recent",
) -> Any:
    """逛广场：别人公开的豆卡。offer 有买袋价、袋上克重、每克价，没有还剩多少。roast/process 逗号分隔（多选=或）；tags 逗号分隔（多选=且）。sort: recent / cost / cost_desc / price / price_desc / roast / origin / score。"""
    return _call(
        client().list_plaza,
        certified_only,
        q,
        roast,
        process,
        tags,
        in_kingdom,
        sort,
    )


@mcp.tool()
def get_plaza_bean(bean_id: int) -> Any:
    """看一张广场公开卡：产地、照片、杯测、落点、买袋价、袋上克重和每克价。没有还剩多少和流水。私卡会 404。"""
    return _call(client().get_plaza_bean, bean_id)


@mcp.tool()
def take_plaza_bean(bean_id: int) -> Any:
    """把别人公开的豆卡领到自己豆库。只拷档案和照片，不带袋子和剩余。自己的卡会 400。已经领过就还已有的那张。"""
    return _call(client().take_plaza_bean, bean_id)


@mcp.tool()
def list_plaza_gear() -> Any:
    """逛广场上别人公开的器具。"""
    return _call(client().list_plaza_gear)


@mcp.tool()
def get_plaza_gear(gear_id: int) -> Any:
    """看一件广场上的公开器具。没公开会 404。"""
    return _call(client().get_plaza_gear, gear_id)


@mcp.tool()
def take_plaza_gear(gear_id: int) -> Any:
    """把别人公开的器具领到自己台面。图是拷贝。自己的不用领。已经领过就还已有的那件。"""
    return _call(client().take_plaza_gear, gear_id)


@mcp.tool()
def list_kingdom(saved: bool = False) -> Any:
    """咖啡王国公共豆种。saved=true 只看自己收藏的。"""
    return _call(client().list_kingdom, saved)


@mcp.tool()
def get_kingdom(kingdom_id: int) -> Any:
    """看一支王国豆：平均分、大家的杯测和评价。"""
    return _call(client().get_kingdom, kingdom_id)


@mcp.tool()
def score_kingdom(
    kingdom_id: int,
    overall: float | None = None,
    dry: float | None = None,
    flavor: float | None = None,
    aftertaste: float | None = None,
    acidity: float | None = None,
    sweetness: float | None = None,
    body: float | None = None,
    balance: float | None = None,
    comment: str | None = None,
) -> Any:
    """给王国里这支豆打杯测。一人一豆一条，再打会改掉自己上次的。分 1–10。"""
    return _call(
        client().score_kingdom,
        kingdom_id,
        _drop_none(
            {
                "overall": overall,
                "dry": dry,
                "flavor": flavor,
                "aftertaste": aftertaste,
                "acidity": acidity,
                "sweetness": sweetness,
                "body": body,
                "balance": balance,
                "comment": comment,
            }
        ),
    )


@mcp.tool()
def unscore_kingdom(kingdom_id: int) -> Any:
    """撤回自己在王国里这支豆的杯测（图一起走）。人明确说才删。"""
    return _call(client().unscore_kingdom, kingdom_id)


@mcp.tool()
def add_kingdom_score_photo(kingdom_id: int, path: str) -> Any:
    """给自己在王国里这支豆的杯测挂一张图。要先 score_kingdom。一杯最多 8 张。"""
    return _call(client().add_kingdom_score_photo, kingdom_id, path)


@mcp.tool()
def delete_kingdom_score_photo(photo_id: int) -> Any:
    """删掉自己杯测上的一张图。人明确说才删。"""
    return _call(client().delete_kingdom_score_photo, photo_id)


@mcp.tool()
def favorite_kingdom(kingdom_id: int) -> Any:
    """收藏或取消收藏王国里的一支豆。再调一次就反过来。"""
    return _call(client().favorite_kingdom, kingdom_id)


@mcp.tool()
def list_kingdom_gear(saved: bool = False) -> Any:
    """王国里的公共器具（管理员收录的目录）。saved=true 只看自己收藏的。"""
    return _call(client().list_kingdom_gear, saved)


@mcp.tool()
def get_kingdom_gear(catalog_id: int) -> Any:
    """看一件王国器具：总体均分、大家的评价。看不见谁的台面库存。"""
    return _call(client().get_kingdom_gear, catalog_id)


@mcp.tool()
def score_kingdom_gear(
    catalog_id: int,
    overall: float | None = None,
    comment: str | None = None,
) -> Any:
    """给王国里这件器具打分。一人一件一条，再打会改掉自己上次的。只打总体 1–10 和一句话，不要套八维。"""
    return _call(
        client().score_kingdom_gear,
        catalog_id,
        _drop_none({"overall": overall, "comment": comment}),
    )


@mcp.tool()
def unscore_kingdom_gear(catalog_id: int) -> Any:
    """撤回自己在王国里这件器具的评价（图一起走）。人明确说才删。"""
    return _call(client().unscore_kingdom_gear, catalog_id)


@mcp.tool()
def add_kingdom_gear_score_photo(catalog_id: int, path: str) -> Any:
    """给自己在王国里这件器具的评价挂一张图。要先 score_kingdom_gear。一条最多 8 张。"""
    return _call(client().add_kingdom_gear_score_photo, catalog_id, path)


@mcp.tool()
def delete_kingdom_gear_score_photo(photo_id: int) -> Any:
    """删掉自己器具评价上的一张图。人明确说才删。"""
    return _call(client().delete_kingdom_gear_score_photo, photo_id)


@mcp.tool()
def favorite_kingdom_gear(catalog_id: int) -> Any:
    """收藏或取消收藏王国里的一件器具。再调一次就反过来。"""
    return _call(client().favorite_kingdom_gear, catalog_id)


@mcp.tool()
def list_kingdom_queue() -> Any:
    """管理员：公开了还没进王国的豆卡。普通人 403。"""
    return _call(client().list_kingdom_queue)


@mcp.tool()
def collect_kingdom(
    bean_id: int,
    kingdom_id: int | None = None,
    name: str | None = None,
) -> Any:
    """管理员：把一张公开豆卡收进王国。给 kingdom_id 就挂到已有那支（大家评同一支），否则新建。普通人 403。"""
    return _call(
        client().collect_kingdom,
        bean_id,
        _drop_none({"kingdom_id": kingdom_id, "name": name}),
    )


def run() -> None:
    mcp.run()


if __name__ == "__main__":
    run()
