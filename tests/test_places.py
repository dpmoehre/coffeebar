"""产地词典匹配：seed 里的真豆、拼配多钉、手定点不被改产地冲掉。"""

from app import places, store


CHENXI = (
    "拼配 · 埃塞俄比亚 耶加雪菲 & 巴西 米纳斯吉拉斯 & "
    "卢旺达 恩戈罗雷罗 & 洪都拉斯 弗朗西斯科-莫拉桑"
)


def test_match_seed_origins():
    assert [p["key"] for p in places.guess("埃塞俄比亚 迪马 Dimma")] == ["dimma"]
    assert [p["key"] for p in places.guess("巴西 南米纳斯 Sul De Minas")] == ["sul_de_minas"]
    assert [p["key"] for p in places.guess("卢旺达 恩戈罗雷罗 Ngororero District")] == ["ngororero"]
    assert [p["key"] for p in places.guess("埃塞俄比亚 西达玛 Sidama")] == ["sidama"]
    assert [p["key"] for p in places.guess("哥伦比亚 蕙兰 Huila")] == ["huila"]


def test_blend_splits_into_four():
    keys = [p["key"] for p in places.guess(CHENXI)]
    assert keys == ["yirgacheffe", "minas", "ngororero", "francisco_morazan"]


def test_producer_adds_estate_pin():
    keys = [p["key"] for p in places.guess("卢旺达 恩戈罗雷罗", "Matyazo CWS 处理厂")]
    assert keys == ["ngororero", "matyazo"]


def test_unknown_origin_empty():
    assert places.guess("【测试】虚构日晒") == []
    assert places.guess(None, None) == []


def test_origin_guides_cover_countries_and_regions():
    keys = {p["key"] for p in places._PLACES if p["level"] <= 1}
    guides = {o["key"]: o for o in places.origin_guides()}
    assert keys == set(guides)
    eth = guides["ethiopia"]
    assert eth["kind"] == "country"
    assert eth["iso"] == "231"
    assert "1500" in eth["altitude"]
    assert "Heirloom" in eth["beans"]
    assert "茉莉" in eth["flavors"]
    assert "耶加雪菲" in eth["famous"]
    yir = guides["yirgacheffe"]
    assert yir["kind"] == "region"
    assert yir.get("iso") in (None, "")
    assert "科契尔" in yir["famous"]
    assert guides["brazil"]["iso"] == "076"
    assert guides["hawaii"].get("iso") in (None, "")
    assert all(o["key"] != "matyazo" for o in places.origin_guides())


def test_click_survives_origin_change(conn):
    bean_id = store.create_bean(conn, {"name": "手点豆", "origin": "肯尼亚"})
    assert [p["source"] for p in places.list_places(conn, bean_id)] == ["gazetteer"]
    places.set_click_places(conn, bean_id, [{"lat": 35.0, "lng": 139.0, "label": "东京"}])
    store.update_bean(conn, bean_id, {"origin": "哥伦比亚 蕙兰 Huila"})
    pins = places.list_places(conn, bean_id)
    assert len(pins) == 1
    assert pins[0]["source"] == "click"
    assert pins[0]["lat"] == 35.0


def test_guess_again_replaces_click(conn):
    bean_id = store.create_bean(conn, {"name": "重猜", "origin": "肯尼亚"})
    places.set_click_places(conn, bean_id, [{"lat": 1.0, "lng": 2.0}])
    store.update_bean(conn, bean_id, {"origin": "哥伦比亚 蕙兰 Huila"})
    pins = places.guess_again(conn, bean_id, "哥伦比亚 蕙兰 Huila", None)
    assert len(pins) == 1
    assert pins[0]["source"] == "gazetteer"
    assert "蕙兰" in pins[0]["label"]
