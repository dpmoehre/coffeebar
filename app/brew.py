"""冲煮方案：按当场输入的粉量与比例算各段。

纯函数，不碰数据库。规则见 docs/002「冲煮指导：按方式算出每一段」：
总水 = round(粉量 × 粉水比)，各段按该方式的比例切分，**最后一段吃掉余数**，
保证各段加总严格等于总水。
"""

from __future__ import annotations

from dataclasses import dataclass, asdict

DEFAULT_DOSE = 15.0
DEFAULT_RATIO = 16.0

METHODS = {
    "v60": "V60 四段",
    "hoffmann": "Hoffmann 一杯",
    "kasuya": "4:6 粕谷",
    "kalita": "Kalita",
    "volcano": "多段式火山冲",
}


def water_ratio(water_g: float, dose_g: float) -> float:
    """本段/累计用水 ÷ 粉量，两位小数，和方程式称上的 1:x 对齐。"""
    return round(float(water_g) / float(dose_g), 2)


@dataclass
class Stage:
    name: str
    add_g: int          # 本段用水（滴滤为 0）
    target_g: int       # 累计目标：秤上要看到的克数
    add_ratio: float    # 本段用水 ÷ 粉量（滴滤为 0）
    target_ratio: float # 累计用水 ÷ 粉量
    seconds: int        # 本段建议秒数
    elapsed_s: int      # 累计时间
    how: str            # 手法
    goal: str           # 这一段要做成什么状态
    function: str       # 对萃取起什么作用
    scene: str          # 动画场景键


def _split(total: int, weights: list[float]) -> list[int]:
    """按权重切分整数总量，最后一份吃掉四舍五入的余数。"""
    if not weights:
        return []
    out = [round(total * w) for w in weights[:-1]]
    out.append(total - sum(out))
    return out


def plan(method: str, dose_g: float, ratio: float) -> dict:
    """算出一套完整方案。dose_g 与 ratio 都取当场输入的值。"""
    method = method if method in METHODS else "v60"
    dose = max(1.0, float(dose_g))
    ratio = max(1.0, float(ratio))
    total = round(dose * ratio)
    bloom = min(round(dose * 2), total)  # 闷蒸约两倍粉量

    if method == "v60":
        rest = _split(total - bloom, [0.6, 0.4])
        raw = [
            (bloom, 8, "中心向外小圈打湿全部粉层", "粉床均匀吸水、开始排气",
             "排气；排不干净后面会通道", "bloom"),
            (rest[0], 30, "由中心螺旋向外，不冲滤纸", "注到总水约六成",
             "这一段决定酸质与甜感", "spiral"),
            (rest[1], 30, "螺旋后收回中心，压住液面", "注满总水",
             "补浓度与厚度", "center_pour"),
            (0, 60, "停手等滤完", "滤干", "总时间偏长就调粗研磨", "drawdown"),
        ]
    elif method == "hoffmann":
        pours = _split(total - bloom, [0.25, 0.25, 0.25, 0.25])
        raw = [(bloom, 45, "中心小圈打湿，轻搅一下", "充分闷蒸",
                "排气充分，风味更干净", "bloom")]
        for i, add in enumerate(pours, start=1):
            raw.append((add, 15, "由中心向外均匀绕圈", f"完成第 {i} 注",
                        "四注均分，复现性好、通道少",
                        "spiral" if i % 2 else "center_pour"))
        raw.append((0, 45, "停手等滤完", "滤干", "看总时间判断研磨", "drawdown"))
    elif method == "kasuya":
        front = _split(round(total * 0.4), [0.5, 0.5])
        back = _split(total - sum(front), [1 / 3, 1 / 3, 1 / 3])
        raw = [
            (front[0], 45, "中心小圈", "先打湿并定调", "前 40% 管酸甜平衡", "bloom"),
            (front[1], 45, "略放大螺旋", "完成前段 40%",
             "这一注偏多更甜、偏少更亮酸", "spiral"),
            (back[0], 30, "稳定螺旋", "开始加浓度", "后 60% 管浓度", "spiral"),
            (back[1], 30, "稳定螺旋，少搅动", "继续加浓度", "保持液位", "center_pour"),
            (back[2], 30, "收回中心后停手", "注完总水", "收尾、定杯量", "center_pour"),
            (0, 45, "等滴完", "滤干", "看时间判研磨", "drawdown"),
        ]
    elif method == "volcano":
        # 多段式火山冲：细水流一直咬住中心，把粉层顶成火山口，靠翻涌带出萃取。
        # 段数与秒数照店家豆卡那套（总时长 2'15"），比例按当场输入算。
        pours = _split(total - bloom, [0.25, 0.25, 0.25, 0.25])
        raw = [
            (bloom, 30, "细水流点中心，让粉层整体吃透", "中心微微鼓起",
             "先把气排干净，后面才顶得起来", "bloom"),
        ]
        for i, add in enumerate(pours, start=1):
            raw.append((
                add, 20,
                "细水流咬住中心一点，别绕大圈",
                f"第 {i} 次顶起火山口" if i < 4 else "最后一次顶起，收水",
                "中心持续翻涌把细粉带上来，边缘少扰动" if i < 3 else "补甜与厚度，别冲塌粉墙",
                "center_pour",
            ))
        raw.append((0, 25, "停手，等粉墙塌下去", "滤干", "总时间偏长就调粗研磨", "drawdown"))
    else:  # kalita
        pours = _split(total - bloom, [1 / 3, 1 / 3, 1 / 3])
        raw = [
            (bloom, 40, "中心小圈，别冲杯壁", "湿润平底粉床",
             "平底怕冲出细粉沟", "bloom"),
            (pours[0], 25, "中心为主，轻画小圈", "维持液位", "均匀过水", "center_pour"),
            (pours[1], 25, "中心小圈", "继续均匀萃取", "补甜和厚度", "center_pour"),
            (pours[2], 25, "中心收尾", "注满总水", "定浓度", "spiral"),
            (0, 45, "停手", "滤干", "看总时间", "drawdown"),
        ]

    stages: list[Stage] = []
    target = 0
    elapsed = 0
    for add, secs, how, goal, function, scene in raw:
        target += add
        elapsed += secs
        stages.append(
            Stage(
                name=_stage_name(method, len(stages), add),
                add_g=add,
                target_g=target,
                add_ratio=water_ratio(add, dose) if add else 0,
                target_ratio=water_ratio(target, dose),
                seconds=secs,
                elapsed_s=elapsed,
                how=how,
                goal=goal,
                function=function,
                scene=scene,
            )
        )

    return {
        "method": method,
        "method_label": METHODS[method],
        "dose_g": dose,
        "ratio": ratio,
        "total_water_g": total,
        "total_ratio": water_ratio(total, dose),
        "total_seconds": stages[-1].elapsed_s if stages else 0,
        "stages": [asdict(s) for s in stages],
    }


def _stage_name(method: str, index: int, add: int) -> str:
    if add == 0:
        return "滴滤"
    if index == 0:
        return "闷蒸"
    if method == "kasuya":
        return f"前段 {index}" if index <= 2 else f"后段 {index - 2}"
    if method == "volcano":
        return f"火山 {index}"
    return f"第 {index} 注"
