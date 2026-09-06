"""本机 MCP：Cursor 经 stdio 调用，打同一套 FastAPI / 写锁。"""

from __future__ import annotations

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
    brew_method: str | None = None,
    brew_dose_g: float | None = None,
    brew_ratio: float | None = None,
    brew_note: str | None = None,
) -> Any:
    """建一张豆卡。带 nominal_g 会同时入第一袋。返回 id。"""
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
                "brew_method": brew_method,
                "brew_dose_g": brew_dose_g,
                "brew_ratio": brew_ratio,
                "brew_note": brew_note,
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
) -> Any:
    """改豆卡产地、烘焙、风味、标签。网页占锁时会被拒。"""
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
) -> Any:
    """给这支豆打一杯杯测分。"""
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
    note: str | None = None,
) -> Any:
    """同豆再入一袋，不新建卡。"""
    return _call(
        client().create_bean_lot,
        bean_id,
        _drop_none(
            {
                "nominal_g": nominal_g,
                "price": price,
                "measured_g": measured_g,
                "bought_on": bought_on,
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
    """列出冲煮方式。"""
    return _call(client().list_brew_methods)


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
    note: str | None = None,
    as_cup: bool = True,
) -> Any:
    """记一次冲煮。多袋未关必须给 lot_id，我会回报扣的是哪一袋。"""
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


def run() -> None:
    mcp.run()


if __name__ == "__main__":
    run()
