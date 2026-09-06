"""咖啡产地词典：把自由文本产地对上经纬度，不调外网。

匹配规则：按 `&` / `、` 切开（拼配一张卡多个钉），每段取**最具体**的命中
（庄园 > 产区 > 国家）。已有人手点的钉，改产地字符串也不会冲掉。
"""

from __future__ import annotations

import math
import re
import sqlite3

from . import db

# 词典钉是产区中心，和手点庄园差几十公里都正常；超过这个再警告
PLACE_WARN_KM = 80

# level: 0 国家 / 1 产区 / 2 处理站或庄园
# 坐标取产区中心附近，不是某座农场的测绘点。
_PLACES: list[dict] = [
    # ── 埃塞 ──
    {"key": "ethiopia", "label": "埃塞俄比亚", "lat": 9.15, "lng": 40.49, "level": 0,
     "aliases": ("埃塞俄比亚", "ethiopia", "ethiopian")},
    {"key": "sidama", "label": "埃塞俄比亚 西达玛", "lat": 6.72, "lng": 38.31, "level": 1,
     "aliases": ("西达玛", "sidama", "sidamo")},
    {"key": "yirgacheffe", "label": "埃塞俄比亚 耶加雪菲", "lat": 6.16, "lng": 38.20, "level": 1,
     "aliases": ("耶加雪菲", "yirgacheffe", "yirgachefe", "yega chef")},
    {"key": "guji", "label": "埃塞俄比亚 古吉", "lat": 5.93, "lng": 38.98, "level": 1,
     "aliases": ("古吉", "guji")},
    {"key": "limu", "label": "埃塞俄比亚 利姆", "lat": 8.15, "lng": 36.95, "level": 1,
     "aliases": ("利姆", "limu")},
    {"key": "illubabor", "label": "埃塞俄比亚 伊鲁巴博", "lat": 8.25, "lng": 35.58, "level": 1,
     "aliases": ("伊鲁巴博", "illubabor")},
    {"key": "dimma", "label": "埃塞俄比亚 迪马", "lat": 8.21, "lng": 34.62, "level": 1,
     "aliases": ("迪马", "dimma")},
    {"key": "yaye_testi", "label": "Yaye-Testi 处理站", "lat": 6.68, "lng": 38.42, "level": 2,
     "aliases": ("yaye-testi", "yaye testi", "yaya-testi", "yaya testi")},
    # ── 巴西 ──
    {"key": "brazil", "label": "巴西", "lat": -14.24, "lng": -51.93, "level": 0,
     "aliases": ("巴西", "brazil", "brasil")},
    {"key": "minas", "label": "巴西 米纳斯吉拉斯", "lat": -18.51, "lng": -44.56, "level": 1,
     "aliases": ("米纳斯吉拉斯", "minas gerais")},
    {"key": "sul_de_minas", "label": "巴西 南米纳斯", "lat": -21.25, "lng": -45.00, "level": 1,
     "aliases": ("南米纳斯", "sul de minas", "sul de minas")},
    {"key": "cerrado", "label": "巴西 塞拉多", "lat": -18.92, "lng": -46.99, "level": 1,
     "aliases": ("塞拉多", "cerrado")},
    # ── 哥伦比亚 ──
    {"key": "colombia", "label": "哥伦比亚", "lat": 4.57, "lng": -74.30, "level": 0,
     "aliases": ("哥伦比亚", "colombia")},
    {"key": "huila", "label": "哥伦比亚 蕙兰", "lat": 2.54, "lng": -75.53, "level": 1,
     "aliases": ("蕙兰", "乌伊拉", "huila")},
    {"key": "narino", "label": "哥伦比亚 纳里尼奥", "lat": 1.29, "lng": -77.36, "level": 1,
     "aliases": ("纳里尼奥", "nariño", "narino")},
    {"key": "antioquia", "label": "哥伦比亚 安蒂奥基亚", "lat": 6.25, "lng": -75.57, "level": 1,
     "aliases": ("安蒂奥基亚", "antioquia")},
    # ── 卢旺达 ──
    {"key": "rwanda", "label": "卢旺达", "lat": -1.94, "lng": 29.87, "level": 0,
     "aliases": ("卢旺达", "rwanda")},
    {"key": "ngororero", "label": "卢旺达 恩戈罗雷罗", "lat": -1.86, "lng": 29.63, "level": 1,
     "aliases": ("恩戈罗雷罗", "ngororero")},
    {"key": "matyazo", "label": "Matyazo CWS", "lat": -1.89, "lng": 29.52, "level": 2,
     "aliases": ("matyazo", "matyazo cws")},
    # ── 中美 ──
    {"key": "honduras", "label": "洪都拉斯", "lat": 14.72, "lng": -86.24, "level": 0,
     "aliases": ("洪都拉斯", "honduras")},
    {"key": "francisco_morazan", "label": "洪都拉斯 弗朗西斯科-莫拉桑", "lat": 14.08, "lng": -87.21, "level": 1,
     "aliases": ("弗朗西斯科-莫拉桑", "弗朗西斯科莫拉桑", "francisco morazan", "francisco morazán")},
    {"key": "guatemala", "label": "危地马拉", "lat": 15.50, "lng": -90.25, "level": 0,
     "aliases": ("危地马拉", "guatemala")},
    {"key": "antigua", "label": "危地马拉 安提瓜", "lat": 14.56, "lng": -90.73, "level": 1,
     "aliases": ("安提瓜", "antigua")},
    {"key": "costa_rica", "label": "哥斯达黎加", "lat": 9.75, "lng": -83.75, "level": 0,
     "aliases": ("哥斯达黎加", "costa rica")},
    {"key": "tarrazu", "label": "哥斯达黎加 塔拉珠", "lat": 9.66, "lng": -84.03, "level": 1,
     "aliases": ("塔拉珠", "tarrazu", "tarrazú")},
    {"key": "panama", "label": "巴拿马", "lat": 8.54, "lng": -80.78, "level": 0,
     "aliases": ("巴拿马", "panama")},
    {"key": "boquete", "label": "巴拿马 波克特", "lat": 8.78, "lng": -82.43, "level": 1,
     "aliases": ("波克特", "boquete")},
    {"key": "el_salvador", "label": "萨尔瓦多", "lat": 13.79, "lng": -88.90, "level": 0,
     "aliases": ("萨尔瓦多", "el salvador")},
    {"key": "nicaragua", "label": "尼加拉瓜", "lat": 12.87, "lng": -85.21, "level": 0,
     "aliases": ("尼加拉瓜", "nicaragua")},
    {"key": "mexico", "label": "墨西哥", "lat": 17.50, "lng": -92.50, "level": 0,
     "aliases": ("墨西哥", "mexico", "méxico")},
    # ── 东非 / 也门 ──
    {"key": "kenya", "label": "肯尼亚", "lat": -0.02, "lng": 37.91, "level": 0,
     "aliases": ("肯尼亚", "kenya")},
    {"key": "nyeri", "label": "肯尼亚 涅里", "lat": -0.42, "lng": 36.95, "level": 1,
     "aliases": ("涅里", "nyeri")},
    {"key": "tanzania", "label": "坦桑尼亚", "lat": -6.37, "lng": 34.89, "level": 0,
     "aliases": ("坦桑尼亚", "tanzania")},
    {"key": "uganda", "label": "乌干达", "lat": 1.37, "lng": 32.29, "level": 0,
     "aliases": ("乌干达", "uganda")},
    {"key": "burundi", "label": "布隆迪", "lat": -3.37, "lng": 29.92, "level": 0,
     "aliases": ("布隆迪", "burundi")},
    {"key": "yemen", "label": "也门", "lat": 15.55, "lng": 48.52, "level": 0,
     "aliases": ("也门", "yemen")},
    # ── 亚洲 ──
    {"key": "indonesia", "label": "印度尼西亚", "lat": -0.79, "lng": 113.92, "level": 0,
     "aliases": ("印度尼西亚", "印尼", "indonesia")},
    {"key": "sumatra", "label": "印尼 苏门答腊", "lat": 0.59, "lng": 98.68, "level": 1,
     "aliases": ("苏门答腊", "sumatra")},
    {"key": "java", "label": "印尼 爪哇", "lat": -7.32, "lng": 110.38, "level": 1,
     "aliases": ("爪哇",)},
    {"key": "vietnam", "label": "越南", "lat": 14.06, "lng": 108.28, "level": 0,
     "aliases": ("越南", "vietnam")},
    {"key": "india", "label": "印度", "lat": 15.32, "lng": 75.71, "level": 0,
     "aliases": ("印度", "india")},
    {"key": "yunnan", "label": "中国 云南", "lat": 24.47, "lng": 101.34, "level": 1,
     "aliases": ("云南", "yunnan")},
    {"key": "china", "label": "中国", "lat": 35.86, "lng": 104.20, "level": 0,
     "aliases": ("中国", "china")},
    # ── 其他 ──
    {"key": "peru", "label": "秘鲁", "lat": -9.19, "lng": -75.02, "level": 0,
     "aliases": ("秘鲁", "peru")},
    {"key": "bolivia", "label": "玻利维亚", "lat": -16.29, "lng": -63.59, "level": 0,
     "aliases": ("玻利维亚", "bolivia")},
    {"key": "hawaii", "label": "美国 夏威夷", "lat": 19.90, "lng": -155.58, "level": 1,
     "aliases": ("夏威夷", "kona", "hawaii")},
    {"key": "jamaica", "label": "牙买加", "lat": 18.11, "lng": -77.30, "level": 0,
     "aliases": ("牙买加", "jamaica", "蓝山", "blue mountain")},
]

# 国家 / 大产区百科。iso 是 world-atlas 的 ISO 数字国码（三位），只给国家；
# 夏威夷不标美国，避免整片北美亮起来。文案是常识级，不调外网。
_PROFILES: dict[str, dict] = {
    "ethiopia": {
        "iso": "231",
        "altitude": "1500–2200 m",
        "beans": "原生种 Heirloom、74110、74112、74158",
        "flavors": "茉莉、柑橘、浆果、红茶",
        "famous": "耶加雪菲、西达玛、古吉",
    },
    "sidama": {
        "altitude": "1500–2200 m",
        "beans": "74110、74112、74158、原生种",
        "flavors": "浆果、柑橘、花香、红茶",
        "famous": "马森秋、西达摩水洗",
    },
    "yirgacheffe": {
        "altitude": "1700–2200 m",
        "beans": "原生种 Heirloom、74110、74112",
        "flavors": "茉莉、柠檬、佛手柑、红茶",
        "famous": "科契尔、沃卡、科里图",
    },
    "guji": {
        "altitude": "1800–2300 m",
        "beans": "原生种、74110、74112",
        "flavors": "浆果、热带水果、花香",
        "famous": "罕贝拉、沙琪索",
    },
    "limu": {
        "altitude": "1400–2100 m",
        "beans": "原生种",
        "flavors": "柑橘、香料、可可、花香",
        "famous": "利姆水洗",
    },
    "illubabor": {
        "altitude": "1500–2000 m",
        "beans": "原生种",
        "flavors": "核果、可可、香料",
        "famous": "伊鲁巴博林区豆",
    },
    "dimma": {
        "altitude": "1500–1900 m",
        "beans": "原生种",
        "flavors": "核果、可可、草本",
        "famous": "迪马日晒 / 水洗",
    },
    "brazil": {
        "iso": "076",
        "altitude": "800–1300 m",
        "beans": "黄波旁、卡杜艾、新世界、蒙多诺沃",
        "flavors": "坚果、巧克力、焦糖、低酸",
        "famous": "南米纳斯、塞拉多、圣保罗",
    },
    "minas": {
        "altitude": "800–1300 m",
        "beans": "黄波旁、卡杜艾、新世界",
        "flavors": "坚果、巧克力、焦糖",
        "famous": "南米纳斯、塞拉多矿区",
    },
    "sul_de_minas": {
        "altitude": "900–1300 m",
        "beans": "黄波旁、卡杜艾、蒙多诺沃",
        "flavors": "坚果、牛奶巧克力、焦糖",
        "famous": "南米纳斯合作社豆",
    },
    "cerrado": {
        "altitude": "900–1250 m",
        "beans": "卡杜艾、黄波旁、托皮西奥",
        "flavors": "巧克力、坚果、甜感干净",
        "famous": "塞拉多机械采收庄园",
    },
    "colombia": {
        "iso": "170",
        "altitude": "1200–2000 m",
        "beans": "卡杜拉、卡斯蒂优、哥伦比亚、铁皮卡",
        "flavors": "红糖、柑橘、焦糖、均衡",
        "famous": "蕙兰、纳里尼奥、安蒂奥基亚",
    },
    "huila": {
        "altitude": "1500–2100 m",
        "beans": "卡杜拉、卡斯蒂优、铁皮卡",
        "flavors": "红糖、柑橘、核果、可可",
        "famous": "蕙兰水洗、SOE 深烘",
    },
    "narino": {
        "altitude": "1800–2300 m",
        "beans": "卡杜拉、卡斯蒂优、哥伦比亚",
        "flavors": "柑橘、花香、高甜、明亮",
        "famous": "纳里尼奥高海拔水洗",
    },
    "antioquia": {
        "altitude": "1300–2000 m",
        "beans": "卡斯蒂优、哥伦比亚、卡杜拉",
        "flavors": "红糖、坚果、可可",
        "famous": "麦德林周边庄园",
    },
    "rwanda": {
        "iso": "646",
        "altitude": "1500–2200 m",
        "beans": "波旁、红波旁",
        "flavors": "红茶、柑橘、红糖、花香",
        "famous": "西部处理站、Cup of Excellence",
    },
    "ngororero": {
        "altitude": "1600–2000 m",
        "beans": "红波旁",
        "flavors": "红茶、柑橘、红糖",
        "famous": "恩戈罗雷罗处理站",
    },
    "honduras": {
        "iso": "340",
        "altitude": "1200–1800 m",
        "beans": "帕卡斯、卡杜艾、帕卡玛拉、波旁",
        "flavors": "焦糖、核果、可可、柑橘",
        "famous": "科班、科马亚瓜、弗朗西斯科-莫拉桑",
    },
    "francisco_morazan": {
        "altitude": "1300–1700 m",
        "beans": "帕卡斯、卡杜艾、波旁",
        "flavors": "焦糖、核果、可可",
        "famous": "弗朗西斯科-莫拉桑日晒 / 水洗",
    },
    "guatemala": {
        "iso": "320",
        "altitude": "1300–2000 m",
        "beans": "波旁、卡杜拉、卡杜艾、帕卡玛拉",
        "flavors": "巧克力、香料、柑橘、烟熏",
        "famous": "安提瓜、韦韦特南戈、阿蒂特兰",
    },
    "antigua": {
        "altitude": "1500–1700 m",
        "beans": "波旁、卡杜拉",
        "flavors": "巧克力、香料、柑橘",
        "famous": "安提瓜火山灰土壤",
    },
    "costa_rica": {
        "iso": "188",
        "altitude": "1200–1900 m",
        "beans": "卡杜拉、卡杜艾、维拉萨奇",
        "flavors": "柑橘、蜂蜜、干净、花香",
        "famous": "塔拉珠、西部谷、蜜处理",
    },
    "tarrazu": {
        "altitude": "1200–1900 m",
        "beans": "卡杜拉、卡杜艾",
        "flavors": "柑橘、蜂蜜、明亮酸质",
        "famous": "塔拉珠 SHB",
    },
    "panama": {
        "iso": "591",
        "altitude": "1400–2000 m",
        "beans": "瑰夏、卡杜艾、帕卡玛拉",
        "flavors": "茉莉、柑橘、热带水果、红茶",
        "famous": "波克特瑰夏、沃肯、翡翠庄园",
    },
    "boquete": {
        "altitude": "1400–2000 m",
        "beans": "瑰夏、卡杜艾",
        "flavors": "茉莉、柑橘、佛手柑",
        "famous": "波克特瑰夏、翡翠庄园",
    },
    "el_salvador": {
        "iso": "222",
        "altitude": "1200–1800 m",
        "beans": "帕卡斯、帕卡玛拉、波旁",
        "flavors": "巧克力、坚果、花香、柑橘",
        "famous": "阿帕内卡、帕卡玛拉",
    },
    "nicaragua": {
        "iso": "558",
        "altitude": "1100–1700 m",
        "beans": "卡杜拉、卡杜艾、马拉卡图拉",
        "flavors": "巧克力、柑橘、核果",
        "famous": "新塞哥维亚、希诺特加",
    },
    "mexico": {
        "iso": "484",
        "altitude": "1000–1700 m",
        "beans": "波旁、铁皮卡、蒙多诺沃、卡杜拉",
        "flavors": "坚果、巧克力、柑橘、花香",
        "famous": "恰帕斯、瓦哈卡、韦拉克鲁斯",
    },
    "kenya": {
        "iso": "404",
        "altitude": "1500–2100 m",
        "beans": "SL28、SL34、Ruiru 11、Batian",
        "flavors": "黑加仑、番茄、柑橘、红茶",
        "famous": "涅里、基里尼亚加、AA / AB",
    },
    "nyeri": {
        "altitude": "1700–2100 m",
        "beans": "SL28、SL34",
        "flavors": "黑加仑、柑橘、番茄、花香",
        "famous": "涅里合作社 AA",
    },
    "tanzania": {
        "iso": "834",
        "altitude": "1200–2000 m",
        "beans": "波旁、肯特、N39",
        "flavors": "黑加仑、柑橘、红茶、可可",
        "famous": "乞力马扎罗、姆宾加",
    },
    "uganda": {
        "iso": "800",
        "altitude": "1200–2200 m",
        "beans": "SL14、SL28、罗布斯塔",
        "flavors": "红茶、柑橘、花香；罗布斯塔偏可可",
        "famous": "埃尔贡山、西尼罗罗布斯塔",
    },
    "burundi": {
        "iso": "108",
        "altitude": "1500–2000 m",
        "beans": "波旁、杰克逊",
        "flavors": "红茶、柑橘、红糖、花香",
        "famous": "卡扬扎、恩戈齐处理站",
    },
    "yemen": {
        "iso": "887",
        "altitude": "1500–2400 m",
        "beans": "乌德尼、达瓦里、图法希",
        "flavors": "葡萄干、香料、可可、酒香",
        "famous": "摩卡、马塔里、伊斯梅利",
    },
    "indonesia": {
        "iso": "360",
        "altitude": "1000–1800 m",
        "beans": "铁皮卡、卡特莫、阿滕戈洛、罗布斯塔",
        "flavors": "草本、雪松、可可、烟草",
        "famous": "曼特宁、爪哇、苏拉威西",
    },
    "sumatra": {
        "altitude": "1000–1600 m",
        "beans": "铁皮卡、卡特莫",
        "flavors": "草本、雪松、可可、泥土甜",
        "famous": "林东曼特宁、湿刨 G1",
    },
    "java": {
        "altitude": "900–1600 m",
        "beans": "铁皮卡、S795",
        "flavors": "草本、可可、香料、干净",
        "famous": "爪哇水洗庄园",
    },
    "vietnam": {
        "iso": "704",
        "altitude": "500–1500 m",
        "beans": "罗布斯塔为主，少量卡蒂莫 / 阿拉比卡",
        "flavors": "橡胶、可可、坚果、低酸",
        "famous": "西原罗布斯塔、达拉特阿拉比卡",
    },
    "india": {
        "iso": "356",
        "altitude": "800–1600 m",
        "beans": "S795、肯特、罗布斯塔",
        "flavors": "香料、雪松、可可、季风豆",
        "famous": "季风马拉巴尔、卡纳塔克",
    },
    "china": {
        "iso": "156",
        "altitude": "1000–1800 m",
        "beans": "卡蒂姆、铁皮卡、波旁",
        "flavors": "坚果、红糖、花香、茶感",
        "famous": "云南保山、普洱、德宏",
    },
    "yunnan": {
        "altitude": "1000–1800 m",
        "beans": "卡蒂姆、铁皮卡、波旁",
        "flavors": "坚果、红糖、花香、茶感",
        "famous": "保山、普洱、德宏小粒种",
    },
    "peru": {
        "iso": "604",
        "altitude": "1200–2000 m",
        "beans": "铁皮卡、波旁、卡杜拉、卡杜艾",
        "flavors": "坚果、红糖、柑橘、花香",
        "famous": "卡哈马卡、库斯科、普诺",
    },
    "bolivia": {
        "iso": "068",
        "altitude": "1500–2300 m",
        "beans": "铁皮卡、卡杜拉",
        "flavors": "柑橘、花香、红糖、干净",
        "famous": "永加斯、卡拉纳维",
    },
    "hawaii": {
        "altitude": "300–900 m",
        "beans": "铁皮卡、卡杜艾、摩卡",
        "flavors": "坚果、蜂蜜、柑橘、干净",
        "famous": "科纳 Extra Fancy",
    },
    "jamaica": {
        "iso": "388",
        "altitude": "600–1700 m",
        "beans": "铁皮卡",
        "flavors": "坚果、花香、可可、柔酸",
        "famous": "蓝山 No.1",
    },
}

_SPLIT = re.compile(r"\s*[&＋+]\s*|\s*、\s*|\s+and\s+", re.I)
_BLEND_PREFIX = re.compile(r"^拼配\s*[·.•．.\-—–]?\s*", re.I)
_SPACE = re.compile(r"[\s·.•．，,。/／\\|\-—–_（）()【】\[\]]+")


class Conflict(Exception):
    pass


def _norm(text: str) -> str:
    return _SPACE.sub(" ", (text or "")).strip().lower()


def _has_alias(hay: str, alias: str) -> bool:
    a = _norm(alias)
    if not a:
        return False
    if re.fullmatch(r"[a-z0-9][a-z0-9 '\-]*", a) and len(a) <= 4:
        return re.search(rf"(?<![a-z0-9]){re.escape(a)}(?![a-z0-9])", hay) is not None
    return a in hay


def split_origins(origin: str | None) -> list[str]:
    raw = _BLEND_PREFIX.sub("", (origin or "").strip())
    parts = [p.strip() for p in _SPLIT.split(raw) if p.strip()]
    return parts or ([raw] if raw else [])


def match_segment(segment: str) -> dict | None:
    hay = _norm(segment)
    if not hay:
        return None
    best = None
    best_key = (-1, -1)  # level, alias length
    for place in _PLACES:
        for alias in place["aliases"]:
            if not _has_alias(hay, alias):
                continue
            key = (place["level"], len(_norm(alias)))
            if key > best_key:
                best = place
                best_key = key
    return best


def origin_guides() -> list[dict]:
    """国家 / 大产区百科，给地图悬停。庄园不单独出面。"""
    out: list[dict] = []
    for place in _PLACES:
        if place["level"] > 1:
            continue
        prof = _PROFILES.get(place["key"])
        if not prof:
            continue
        out.append(
            {
                "key": place["key"],
                "label": place["label"],
                "kind": "country" if place["level"] == 0 else "region",
                "lat": place["lat"],
                "lng": place["lng"],
                "iso": prof.get("iso"),
                "altitude": prof.get("altitude"),
                "beans": prof.get("beans"),
                "flavors": prof.get("flavors"),
                "famous": prof.get("famous"),
            }
        )
    return out


def guess(origin: str | None, producer: str | None = None) -> list[dict]:
    """从产地 + 处理厂文本推出一组钉。同一 key 只留一次。"""
    segments = split_origins(origin)
    if producer and producer.strip():
        segments.append(producer.strip())
    seen: set[str] = set()
    out: list[dict] = []
    for seg in segments:
        hit = match_segment(seg)
        if hit and hit["key"] not in seen:
            seen.add(hit["key"])
            out.append(
                {
                    "key": hit["key"],
                    "label": hit["label"],
                    "lat": hit["lat"],
                    "lng": hit["lng"],
                }
            )
    if not out and (origin or producer):
        hit = match_segment(" ".join(x for x in (origin, producer) if x))
        if hit:
            out.append(
                {
                    "key": hit["key"],
                    "label": hit["label"],
                    "lat": hit["lat"],
                    "lng": hit["lng"],
                }
            )
    return out


def copy_to(conn: sqlite3.Connection, src_id: int, dest_id: int) -> None:
    """把原卡的钉拷到新卡。广场领回用，不带认证。"""
    pins = list_places(conn, src_id)
    conn.execute("DELETE FROM bean_place WHERE bean_id = ?", (dest_id,))
    ts = db.now()
    for p in pins:
        conn.execute(
            """INSERT INTO bean_place (bean_id, lat, lng, label, source, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (dest_id, p["lat"], p["lng"], p.get("label"), p.get("source") or "copy", ts),
        )


def list_places(conn: sqlite3.Connection, bean_id: int) -> list[dict]:
    return [
        dict(r)
        for r in conn.execute(
            """SELECT id, lat, lng, label, source FROM bean_place
               WHERE bean_id = ? ORDER BY id""",
            (bean_id,),
        )
    ]


def has_click(conn: sqlite3.Connection, bean_id: int) -> bool:
    return (
        conn.execute(
            "SELECT 1 FROM bean_place WHERE bean_id = ? AND source = 'click' LIMIT 1",
            (bean_id,),
        ).fetchone()
        is not None
    )


def _insert(conn: sqlite3.Connection, bean_id: int, pins: list[dict], source: str) -> None:
    ts = db.now()
    for p in pins:
        conn.execute(
            """INSERT INTO bean_place (bean_id, lat, lng, label, source, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (bean_id, p["lat"], p["lng"], p.get("label"), source, ts),
        )


def sync_gazetteer(
    conn: sqlite3.Connection, bean_id: int, origin: str | None, producer: str | None
) -> list[dict]:
    """没有手定点时，按文本重写词典钉。有手定点则原样返回。"""
    if has_click(conn, bean_id):
        return list_places(conn, bean_id)
    conn.execute("DELETE FROM bean_place WHERE bean_id = ? AND source = 'gazetteer'", (bean_id,))
    _insert(conn, bean_id, guess(origin, producer), "gazetteer")
    return list_places(conn, bean_id)


def set_click_places(conn: sqlite3.Connection, bean_id: int, pins: list[dict]) -> list[dict]:
    """人手点的一组钉，整表替换（推测钉一起拿掉）。"""
    if not pins:
        raise Conflict("至少点一个位置")
    cleaned = []
    for p in pins:
        try:
            lat = float(p.get("lat"))
            lng = float(p.get("lng"))
        except (TypeError, ValueError) as exc:
            raise Conflict("经纬度要是数字") from exc
        if not (-90 <= lat <= 90 and -180 <= lng <= 180):
            raise Conflict("经纬度超出范围")
        cleaned.append(
            {"lat": lat, "lng": lng, "label": (p.get("label") or "手点").strip() or "手点"}
        )
    conn.execute("DELETE FROM bean_place WHERE bean_id = ?", (bean_id,))
    _insert(conn, bean_id, cleaned, "click")
    conn.execute("UPDATE bean SET updated_at = ? WHERE id = ?", (db.now(), bean_id))
    from . import store

    store.clear_certification(conn, bean_id)
    return list_places(conn, bean_id)


def guess_again(
    conn: sqlite3.Connection, bean_id: int, origin: str | None, producer: str | None
) -> list[dict]:
    """清掉手定，按词典重猜。"""
    conn.execute("DELETE FROM bean_place WHERE bean_id = ?", (bean_id,))
    pins = sync_gazetteer(conn, bean_id, origin, producer)
    from . import store

    store.clear_certification(conn, bean_id)
    return pins


def _km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(h)))


def review_places(
    conn: sqlite3.Connection, bean_id: int, origin: str | None, producer: str | None
) -> dict:
    """对照当前钉和词典推测，给审核用。"""
    current = list_places(conn, bean_id)
    gazetteer = guess(origin, producer)
    warnings: list[str] = []
    if not current:
        warnings.append("还没有地图落点")
    elif not gazetteer:
        if origin or producer:
            warnings.append("词典对不上产地文字，请手校")
    else:
        for pin in current:
            nearest = min(
                gazetteer,
                key=lambda g: _km(pin["lat"], pin["lng"], g["lat"], g["lng"]),
            )
            dist = _km(pin["lat"], pin["lng"], nearest["lat"], nearest["lng"])
            if dist > PLACE_WARN_KM:
                label = pin.get("label") or "钉"
                warnings.append(
                    f"「{label}」离词典「{nearest['label']}」约 {int(dist)} km，请确认"
                )
    return {
        "current": current,
        "gazetteer": gazetteer,
        "warnings": warnings,
        "ok": not warnings,
    }


def backfill(conn: sqlite3.Connection) -> int:
    """老库里还没有落点的豆，启动时补一回词典钉。"""
    rows = conn.execute(
        "SELECT id, origin, producer FROM bean WHERE deleted_at IS NULL"
    ).fetchall()
    n = 0
    for r in rows:
        has = conn.execute(
            "SELECT 1 FROM bean_place WHERE bean_id = ? LIMIT 1", (r["id"],)
        ).fetchone()
        if has:
            continue
        if sync_gazetteer(conn, r["id"], r["origin"], r["producer"]):
            n += 1
    return n


def map_data(conn: sqlite3.Connection, owner_id: int, cover_of) -> dict:
    """给地图页：钉 + 还没定点的豆。cover_of(bean_id) -> 封面或 None。"""
    from . import store  # 函数内导入，避免和 store → places 顶层循环

    beans = conn.execute(
        f"""SELECT b.id, b.name, b.origin, b.roast, b.process, b.producer,
                  (SELECT COUNT(*) FROM bean_lot l
                    WHERE l.bean_id = b.id AND l.closed_at IS NULL) AS open_lots,
                  (SELECT COUNT(*) FROM bean_lot l WHERE l.bean_id = b.id) AS all_lots,
                  COALESCE((SELECT SUM({store.BALANCE}) FROM bean_lot l
                             WHERE l.bean_id = b.id AND l.closed_at IS NULL), 0) AS balance_g
           FROM bean b
           WHERE b.owner_id = ? AND b.deleted_at IS NULL
           ORDER BY b.updated_at DESC""",
        (owner_id,),
    ).fetchall()
    pins: list[dict] = []
    unplaced: list[dict] = []
    for b in beans:
        in_stock = b["open_lots"] > 0
        pending = b["all_lots"] == 0
        info = {
            "id": b["id"],
            "name": b["name"],
            "origin": b["origin"],
            "roast": b["roast"],
            "process": b["process"],
            "producer": b["producer"],
            "tags": store.bean_tags(conn, b["id"]),
            "balance_g": round(float(b["balance_g"] or 0), 1),
            "in_stock": in_stock,
            "pending": pending,
            "cover": cover_of(b["id"]),
        }
        pts = list_places(conn, b["id"])
        if not pts:
            unplaced.append(info)
            continue
        for p in pts:
            pins.append(
                {
                    **info,
                    "bean_id": b["id"],
                    "place_id": p["id"],
                    "lat": p["lat"],
                    "lng": p["lng"],
                    "label": p["label"],
                    "source": p["source"],
                }
            )
    return {"pins": pins, "unplaced": unplaced, "origins": origin_guides()}
