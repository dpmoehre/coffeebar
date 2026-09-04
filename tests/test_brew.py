"""冲煮方案：各段加总必须严格等于总水，末段吃余数。"""

import pytest

from app import brew


@pytest.mark.parametrize("method", ["v60", "hoffmann", "kasuya", "kalita"])
@pytest.mark.parametrize("dose,ratio", [(15, 16), (16, 15.5), (12, 17), (20, 16), (13.7, 16.3)])
def test_stages_sum_to_total(method, dose, ratio):
    p = brew.plan(method, dose, ratio)
    assert p["total_water_g"] == round(dose * ratio)
    assert sum(s["add_g"] for s in p["stages"]) == p["total_water_g"]


@pytest.mark.parametrize("method", ["v60", "hoffmann", "kasuya", "kalita"])
def test_targets_are_cumulative(method):
    p = brew.plan(method, 15, 16)
    running = 0
    for s in p["stages"]:
        running += s["add_g"]
        assert s["target_g"] == running
    assert p["stages"][-1]["target_g"] == p["total_water_g"]


@pytest.mark.parametrize("method", ["v60", "hoffmann", "kasuya", "kalita"])
def test_time_is_cumulative_and_present(method):
    p = brew.plan(method, 15, 16)
    elapsed = 0
    for s in p["stages"]:
        assert s["seconds"] > 0, "每段都要有建议秒数，时间不是装饰"
        elapsed += s["seconds"]
        assert s["elapsed_s"] == elapsed
    assert p["total_seconds"] == elapsed


def test_last_stage_is_drawdown_with_no_water():
    for method in ["v60", "hoffmann", "kasuya", "kalita"]:
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
