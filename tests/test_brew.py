"""冲煮方案：各段加总必须严格等于总水，末段吃余数。"""

import pytest

from app import brew


ALL = ["v60", "hoffmann", "kasuya", "kalita", "volcano"]


@pytest.mark.parametrize("method", ALL)
@pytest.mark.parametrize("dose,ratio", [(15, 16), (16, 15.5), (12, 17), (20, 16), (13.7, 16.3)])
def test_stages_sum_to_total(method, dose, ratio):
    p = brew.plan(method, dose, ratio)
    assert p["total_water_g"] == round(dose * ratio)
    assert sum(s["add_g"] for s in p["stages"]) == p["total_water_g"]


@pytest.mark.parametrize("method", ALL)
def test_targets_are_cumulative(method):
    p = brew.plan(method, 15, 16)
    running = 0
    for s in p["stages"]:
        running += s["add_g"]
        assert s["target_g"] == running
    assert p["stages"][-1]["target_g"] == p["total_water_g"]


@pytest.mark.parametrize("method", ALL)
def test_time_is_cumulative_and_present(method):
    p = brew.plan(method, 15, 16)
    elapsed = 0
    for s in p["stages"]:
        assert s["seconds"] > 0, "每段都要有建议秒数，时间不是装饰"
        elapsed += s["seconds"]
        assert s["elapsed_s"] == elapsed
    assert p["total_seconds"] == elapsed


def test_last_stage_is_drawdown_with_no_water():
    for method in ALL:
        last = brew.plan(method, 15, 16)["stages"][-1]
        assert last["add_g"] == 0
        assert last["scene"] == "drawdown"


def test_changing_dose_recomputes():
    a = brew.plan("v60", 15, 16)
    b = brew.plan("v60", 20, 16)
    assert b["total_water_g"] > a["total_water_g"]
    assert b["stages"][0]["add_g"] > a["stages"][0]["add_g"]


def test_unknown_method_falls_back_to_v60():
    assert brew.plan("espresso", 15, 16)["method"] == "v60"


def test_volcano_matches_the_shop_card():
    """店家豆卡写的是 1:14、2'15"、多段式火山冲，方案要对得上。"""
    p = brew.plan("volcano", 15, 14)
    assert p["method_label"] == "多段式火山冲"
    assert p["total_water_g"] == 210
    assert p["total_seconds"] == 135, "2'15\""
    assert [s["name"] for s in p["stages"]] == [
        "闷蒸", "火山 1", "火山 2", "火山 3", "火山 4", "滴滤",
    ]
    assert [s["add_g"] for s in p["stages"]] == [30, 45, 45, 45, 45, 0]
    assert all("中心" in s["how"] for s in p["stages"][:5]), "火山冲全程咬住中心"


def test_volcano_scales_with_dose():
    p = brew.plan("volcano", 20, 14)
    assert p["total_water_g"] == 280
    assert sum(s["add_g"] for s in p["stages"]) == 280
    assert p["total_seconds"] == 135, "段数固定，改粉量只改水量"
