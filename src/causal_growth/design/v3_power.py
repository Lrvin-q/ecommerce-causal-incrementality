"""固定 N 反算 MDE 与 20 个功效格校准（v3 Phase D.1）。

回答方案里的哪个问题
--------------------
v3 的样本量逻辑**不是**"先算需要多少人"，而是**固定 20 万人，反算能检测多小的效应**
（HITL §7.1、``design.mde_direction = fixed_n_inverse_power``）。本模块回答三类问题：

| 问题 | 入口 |
|---|---|
| 固定 n 与分流下，利润/购买率能检测多小的增量？ | :func:`profit_mde` / :func:`purchase_mde` |
| 给定效应量到底有多少功效？ | :func:`profit_power` / :func:`purchase_power` |
| ``design_power_jobs`` 的 20 个格要什么 ``active_mde_multiplier`` 才够？ | :func:`calibrate_power_cell` |

口径（红线）
------------
1. **只读可观测列**：本模块只读 ``treatment`` / ``net_profit`` / ``paid_purchase_7d`` /
   ``split`` 四列（:data:`OBSERVED_COLUMNS`）。方差只能来自 ``ObservedDataset`` 的
   **train split**（:func:`design_sample_profile`）或独立先导模拟；**禁止**读测试集
   真值、潜在结果或 ``audit/`` 下的任何内容来定检测目标。模块导入期不会加载
   ``causal_growth.dgp``——只有独立先导入口 :func:`run_design_pilot` 内部才延迟导入。
2. **n 的符号不混用**：``n_total`` 是全样本，``n_treatment`` / ``n_control`` 是每臂；
   :func:`split_counts` 是唯一把总样本拆成各臂的地方，且保证各臂之和 == ``n_total``。
3. **参数零硬编码**：α、目标功效、分流网格、检验族大小、根容差、队列人数全部从
   ``configs/v3/*.yaml`` 读；配置里没有的（例如单侧 α 的独立取值）作为函数参数，
   在 ``docs/v3_phase_D_mde.md`` 里逐条说明来源与默认值。
4. **失败要响**：``n=0``、``sigma=0``、负效应、概率越界一律抛 ``ValueError``，
   不返回 ``nan``。

公式与近似
----------
* 利润近似 MDE（两独立样本均值差，正态近似，HITL §7.1 明文）::

      MDE_Π = (z_{1-α/2} + z_{1-β}) · sqrt(σ_1²/n_1 + σ_0²/n_0)

  单侧时把 ``z_{1-α/2}`` 换成 ``z_{1-α}``。该式对零膨胀/偏态的利润是**近似**：
  它只给大样本下的检验功效，不给覆盖率保证；正式功效必须用完整 DGP 复跑
  （HITL §7.2，属 Phase D 其它子任务与 Phase G）。
* 购买率用**两比例功效关系数值反解**（:func:`purchase_mde` → ``brentq``）：基线率
  ``p0``、两臂人数、单/双侧、是否多重校正全部落盘。检验标准误在 H0 下用合并比例
  ``p̄``、H1 下用各自比例，因此 ``Δ→0`` 时功效收敛到 ``α/2``（双侧）/ ``α``（单侧），
  反解区间始终有根。
* **多重校正**：Holm 要求 ``p_(k) ≤ α/(m-k+1)``，其充分条件是每项 ``p_i ≤ α/m``。
  设计期用 ``α/m`` 得到的是 Holm **联合检测能力**的保守下界（不对效应排序作假设），
  见 :func:`holm_per_test_alpha`。

不做什么
--------
本模块**不生成任何正式重复**（``R = 0``），不产出 ``achieved_effect`` /
``rejection_rate`` / ``MC_SE``——那三列属 ``design.local_power.report`` 的实证部分，
必须由完整五表 + SQL + 估计流程在 D 的其它子任务与 Phase G 里跑出来。本模块只给
设计期可算的量：设计 MDE、目标效应、所需倍数、解析功效。

合成数据 / 已知 DGP。正式重复次数仍为 0。
"""

from __future__ import annotations

import json
import math
import numbers
import re
import shutil
import time
from dataclasses import dataclass, field, fields
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import pandas as pd
from scipy.optimize import brentq
from scipy.stats import norm

from causal_growth.config import Config
from causal_growth.data.v3_observed import ObservedDataset
from causal_growth.v3_config import V3Protocol, load_v3_protocol
from causal_growth.v3_data_config import load_v3_data_config

__all__ = [
    "MDE_TABLE_COLUMNS",
    "OBSERVED_COLUMNS",
    "ONE_SIDED",
    "TWO_SIDED",
    "Contrast",
    "DesignSampleProfile",
    "PowerCellCalibration",
    "alpha_from_config",
    "allocation_shares_from_config",
    "build_mde_rows",
    "calibrate_power_cell",
    "calibrate_power_cells",
    "contrasts_from_config",
    "design_pilot_rep_ids",
    "design_sample_profile",
    "design_scenario_id",
    "holm_per_test_alpha",
    "multiplier_for_power",
    "multiplier_for_target_effect",
    "power_targets_from_config",
    "profile_from_frame",
    "profile_from_record",
    "profile_to_record",
    "profit_mde",
    "profit_power",
    "purchase_mde",
    "purchase_power",
    "read_mde_csv",
    "read_profiles_json",
    "run_design_pilot",
    "split_counts",
    "target_effect_for_multiplier",
    "write_mde_csv",
    "write_profiles_json",
    "z_alpha",
    "z_power",
]

#: 双侧检验标签（主检验）。
TWO_SIDED = "two_sided"
#: 单侧检验标签（方向性检验口径；本模块只把它当作另一种报告口径）。
ONE_SIDED = "one_sided"
_SIDES = (TWO_SIDED, ONE_SIDED)

#: 本模块**唯一**读取的观测列。多一列都不读，越界即抛错。
OBSERVED_COLUMNS: tuple[str, ...] = ("treatment", "net_profit", "paid_purchase_7d", "split")

#: 汇总表列名（顺序即落盘顺序，报告按名对齐）。
MDE_TABLE_COLUMNS: tuple[str, ...] = (
    "data_source",
    "record_type",
    "scenario_id",
    "level",
    "base_scenario_id",
    "cohort_id",
    "cohort_provenance",
    "contrast",
    "metric",
    "n_total",
    "n_treatment",
    "n_control",
    "treatment_share",
    "alpha",
    "alpha_per_test",
    "sides",
    "power_target",
    "multiplicity",
    "family_size",
    "mde",
    "mde_unit",
    "mde_pp",
    "control_mean",
    "mde_relative_pct",
    "sigma_treatment",
    "sigma_control",
    "p0_baseline",
    "p1_at_mde",
    "target_effect",
    "analytic_power",
    "required_multiplier",
    "configured_multiplier",
    "required_multiplier_90",
    "detectable_at_80",
    "detectable_at_90",
    "primary_row",
    "variance_source",
    "observed_dataset_hash",
    "notes",
)

#: 概率求和容差（纯浮点常数，不是业务参数）。
_PROBABILITY_TOLERANCE = 1e-9
#: 反解根的默认容差（正式表用 ``design.numerical.root_tolerance`` 覆盖）。
_DEFAULT_ROOT_TOLERANCE = 1e-12
#: 反解后回代功效的允许偏差：小于此值才认为根有效。
_POWER_ROUND_TRIP_TOLERANCE = 1e-9


# --------------------------------------------------------------------------- #
# 入参校验（失败要响：AGENTS.md §3.6）
# --------------------------------------------------------------------------- #
def _as_float(name: str, value: Any) -> float:
    """收成有限实数；非数值抛 ``TypeError``，NaN/inf 抛 ``ValueError``。"""
    if isinstance(value, bool) or not isinstance(value, numbers.Real):
        raise TypeError(f"{name} 必须是实数，收到 {type(value).__name__}")
    out = float(value)
    if not math.isfinite(out):
        raise ValueError(f"{name} 必须是有限实数，收到 {value!r}")
    return out


def _positive_float(name: str, value: Any) -> float:
    """严格正实数（σ、MDE、容差一律走这里，0 与负数当场抛错）。"""
    out = _as_float(name, value)
    if out <= 0.0:
        raise ValueError(f"{name} 必须严格为正，收到 {out}")
    return out


def _non_negative_float(name: str, value: Any) -> float:
    """非负实数；负的"目标效应/倍数"是口径错误，直接抛。"""
    out = _as_float(name, value)
    if out < 0.0:
        raise ValueError(f"{name} 不能为负，收到 {out}")
    return out


def _positive_int(name: str, value: Any) -> int:
    """正整数（样本量一律走这里；``n = 0`` 当场抛错，不产生 nan/inf）。"""
    if isinstance(value, bool) or not isinstance(value, numbers.Integral):
        raise TypeError(f"{name} 必须是整数，收到 {type(value).__name__}")
    out = int(value)
    if out < 1:
        raise ValueError(f"{name} 必须 >= 1，收到 {out}")
    return out


def _unit_interval(name: str, value: Any) -> float:
    """严格落在 (0,1) 内的实数（α、功效、概率共用）。"""
    out = _as_float(name, value)
    if not 0.0 < out < 1.0:
        raise ValueError(f"{name} 必须在 (0,1) 内，收到 {out}")
    return out


def _validate_alpha_power(alpha: Any, power: Any) -> tuple[float, float]:
    """α 与功效 ``1-β`` 都必须严格落在 (0,1) 内。"""
    return _unit_interval("alpha", alpha), _unit_interval("power", power)


def _validate_sides(sides: Any) -> str:
    """只接受 :data:`TWO_SIDED` / :data:`ONE_SIDED`；别的一律抛。"""
    if sides not in _SIDES:
        raise ValueError(f"sides 必须是 {_SIDES} 之一，收到 {sides!r}")
    return str(sides)


def _validate_base_rate(p0: Any, delta: float = 0.0) -> float:
    """基线购买率必须落在 (0,1)，且 ``p0 + delta <= 1``（概率尺度不越界）。"""
    base = _unit_interval("p0", p0)
    if base + delta > 1.0:
        raise ValueError(f"p0 + delta = {base} + {delta} = {base + delta} > 1，概率尺度越界")
    return base


# --------------------------------------------------------------------------- #
# z 值与多重校正
# --------------------------------------------------------------------------- #
def z_alpha(alpha: float, sides: str = TWO_SIDED) -> float:
    """返回临界值 ``z_{1-α/2}``（双侧）或 ``z_{1-α}``（单侧）。

    一律用 ``scipy.stats.norm.ppf`` 现算，不手写 1.96/1.645——手写取整会在
    20 万样本上放大成可观测的 MDE 偏差。
    """
    a = _unit_interval("alpha", alpha)
    label = _validate_sides(sides)
    return float(norm.ppf(1.0 - a / 2.0 if label == TWO_SIDED else 1.0 - a))


def z_power(power: float) -> float:
    """返回 ``z_{1-β}``；``power`` 必须落在 (0,1) 内。"""
    return float(norm.ppf(_unit_interval("power", power)))


def holm_per_test_alpha(alpha: float, family_size: int) -> float:
    """Holm 族内"全部拒绝"的**保守**单检验显著性水平 ``α/m``。

    Holm 的逐步临界值是 ``α/m, α/(m-1), …, α/1``，每项都 ``>= α/m``，因此
    "每个 p 都 <= α/m"是"全部拒绝"的充分条件。设计期用 ``α/m`` 反解 MDE 得到的
    是 Holm 联合检测能力的**下界**：不依赖任何效应排序假设，只会偏保守，不会高估。
    """
    a = _unit_interval("alpha", alpha)
    m = _positive_int("family_size", family_size)
    return a / m


# --------------------------------------------------------------------------- #
# 分流
# --------------------------------------------------------------------------- #
def split_counts(n_total: int, probabilities: Sequence[float]) -> tuple[int, ...]:
    """把 ``n_total`` 按 ``probabilities`` 拆成各臂人数（最大余数法，和恒等于 n_total）。

    为什么不用 ``round(n*p)``：``round`` 在 1/3 分流下三臂之和可能不等于 n
    （200000 × 1/3 逐臂取整会差 1–2 人），样本量对不上会让后续 SRM 误报。
    最大余数法保证 ``sum(counts) == n_total``，且各臂与理想配额之差 < 1。
    """
    n = _positive_int("n_total", n_total)
    probs = tuple(_as_float(f"probabilities[{i}]", p) for i, p in enumerate(probabilities))
    if len(probs) < 2:
        raise ValueError(f"至少两个臂才能做两样本比较，收到 {len(probs)} 个概率")
    if any(p <= 0.0 for p in probs):
        raise ValueError("每个臂的概率都必须严格为正（空臂的实验没有对照）")
    total = sum(probs)
    if abs(total - 1.0) > _PROBABILITY_TOLERANCE:
        raise ValueError(f"各臂概率之和必须为 1，收到 {total}（容差 {_PROBABILITY_TOLERANCE}）")
    exact = [p * n for p in probs]
    counts = [int(math.floor(value)) for value in exact]
    remainder = n - sum(counts)
    order = sorted(range(len(exact)), key=lambda i: (-(exact[i] - counts[i]), i))
    for index in order[:remainder]:
        counts[index] += 1
    if sum(counts) != n or min(counts) < 1:
        raise RuntimeError(f"分流失败：counts={counts}, n_total={n}")
    return tuple(counts)


# --------------------------------------------------------------------------- #
# 利润：MDE 与功效（闭式）
# --------------------------------------------------------------------------- #
def profit_mde(
    sigma_treatment: float,
    sigma_control: float,
    n_treatment: int,
    n_control: int,
    *,
    alpha: float,
    power: float,
    sides: str = TWO_SIDED,
) -> float:
    """固定 n 下的利润 MDE（元/合格用户）。

    公式（HITL §7.1 明文，两独立样本均值差的正态近似）::

        MDE = (z_{1-α/2} + z_{1-β}) · sqrt(σ_1²/n_1 + σ_0²/n_0)

    单侧时把 ``z_{1-α/2}`` 换成 ``z_{1-α}``（临界值更小 → MDE 更小）。

    Parameters
    ----------
    sigma_treatment, sigma_control:
        处理/对照臂个体利润标准差（元/人），必须严格为正。**只能**来自训练/设计
        样本或独立先导模拟，不得来自测试集真值。
    n_treatment, n_control:
        各臂人数，必须 >= 1（``n=0`` 直接抛错，不返回 inf/nan）。
    alpha, power:
        显著性水平与目标功效。
    sides:
        ``"two_sided"`` / ``"one_sided"``。

    Returns
    -------
    float
        绝对 MDE（元/人）。相对口径由调用方用 ``mde / control_mean * 100`` 表示。

    Raises
    ------
    ValueError
        σ 非正、n < 1、α/功效越界、``sides`` 非法。
    TypeError
        入参不是实数/整数。
    """
    sd1 = _positive_float("sigma_treatment", sigma_treatment)
    sd0 = _positive_float("sigma_control", sigma_control)
    n1 = _positive_int("n_treatment", n_treatment)
    n0 = _positive_int("n_control", n_control)
    a, pw = _validate_alpha_power(alpha, power)
    label = _validate_sides(sides)
    multiplier = z_alpha(a, label) + z_power(pw)
    return multiplier * math.sqrt(sd1 * sd1 / n1 + sd0 * sd0 / n0)


def profit_power(
    effect: float,
    sigma_treatment: float,
    sigma_control: float,
    n_treatment: int,
    n_control: int,
    *,
    alpha: float,
    sides: str = TWO_SIDED,
) -> float:
    """:func:`profit_mde` 的逆：给定效应量，返回解析功效。

    ``effect = 0`` 时返回 ``α/2``（双侧）或 ``α``（单侧），即零效应下的名义拒绝率
    ——这正是完整 AA 要检验的量（实测走五表/SQL，见 ``design.aa``）。
    """
    delta = _non_negative_float("effect", effect)
    sd1 = _positive_float("sigma_treatment", sigma_treatment)
    sd0 = _positive_float("sigma_control", sigma_control)
    n1 = _positive_int("n_treatment", n_treatment)
    n0 = _positive_int("n_control", n_control)
    a = _unit_interval("alpha", alpha)
    label = _validate_sides(sides)
    standard_error = math.sqrt(sd1 * sd1 / n1 + sd0 * sd0 / n0)
    return float(norm.cdf(delta / standard_error - z_alpha(a, label)))


# --------------------------------------------------------------------------- #
# 购买率：两比例功效关系数值反解
# --------------------------------------------------------------------------- #
def purchase_power(
    p0: float,
    delta: float,
    n_treatment: int,
    n_control: int,
    *,
    alpha: float,
    sides: str = TWO_SIDED,
) -> float:
    """两独立比例的解析功效（H0 用合并标准误，H1 用各自比例）。

    ``Δ = 0`` 时返回 ``α/2``（双侧）/ ``α``（单侧）；``Δ`` 增大时单调上升，
    因此 :func:`purchase_mde` 的反解有唯一根。
    """
    base = _as_float("p0", p0)
    shift = _non_negative_float("delta", delta)
    _validate_base_rate(base, shift)
    n1 = _positive_int("n_treatment", n_treatment)
    n0 = _positive_int("n_control", n_control)
    a = _unit_interval("alpha", alpha)
    label = _validate_sides(sides)
    treated = base + shift
    pooled = (n1 * treated + n0 * base) / (n1 + n0)
    se_null = math.sqrt(pooled * (1.0 - pooled) * (1.0 / n1 + 1.0 / n0))
    se_alt = math.sqrt(treated * (1.0 - treated) / n1 + base * (1.0 - base) / n0)
    if se_alt <= 0.0:  # pragma: no cover - 概率越界已在上面拦截
        raise ValueError("两比例标准误为 0，检查 n 与 p0")
    return float(norm.cdf((shift - z_alpha(a, label) * se_null) / se_alt))


def purchase_mde(
    p0: float,
    n_treatment: int,
    n_control: int,
    *,
    alpha: float,
    power: float,
    sides: str = TWO_SIDED,
    tolerance: float = _DEFAULT_ROOT_TOLERANCE,
) -> float:
    """固定 n 下的购买率 MDE（概率单位；×100 为百分点，见汇总表 ``mde_pp``）。

    用 ``scipy.optimize.brentq`` 对 :func:`purchase_power` 反解::

        find Δ >= 0  s.t.  purchase_power(p0, Δ, n_1, n_0, α, sides) == power

    区间取 ``[0, 1 - p0]``：下端点功效恰为 ``α/2``（双侧）/ ``α``（单侧），上端点
    ``p1 = 1`` 是概率尺度的物理上界。两端点必须跨过目标功效，否则（例如 n 极小
    却要求 99% 功效）**抛错**，而不是返回 clamp 过的假值。

    Parameters
    ----------
    p0:
        对照组基准购买率，必须落在 (0,1)（取设计样本对照臂）。
    n_treatment, n_control:
        各臂人数。
    alpha, power:
        显著性水平与目标功效。
    sides:
        ``"two_sided"`` / ``"one_sided"``。
    tolerance:
        brentq 的 ``xtol``；正式表用 ``design.numerical.root_tolerance``。

    Returns
    -------
    float
        绝对 MDE（概率单位）。反解后回代检查功效误差 <= 1e-9，不满足即抛错。

    Raises
    ------
    ValueError
        ``p0`` 越界、n < 1、α/功效越界、目标功效不高于零效应拒绝率、或
        ``p1 <= 1`` 内达不到目标功效。
    RuntimeError
        反解根回代误差超限。
    """
    base = _validate_base_rate(p0)
    n1 = _positive_int("n_treatment", n_treatment)
    n0 = _positive_int("n_control", n_control)
    a, pw = _validate_alpha_power(alpha, power)
    label = _validate_sides(sides)
    tol = _positive_float("tolerance", tolerance)

    floor = a / 2.0 if label == TWO_SIDED else a
    if pw <= floor:
        raise ValueError(
            f"目标功效 {pw} 不高于零效应下的拒绝率 {floor}（α={a}, {label}）；"
            "此时期望的 MDE 为 0，没有正的检测下限可反解"
        )

    def _gap(delta: float) -> float:
        return purchase_power(base, delta, n1, n0, alpha=a, sides=label) - pw

    upper = 1.0 - base
    if _gap(0.0) >= 0.0 or _gap(upper) <= 0.0:
        raise ValueError(
            f"在 p1 <= 1 的合法区间内达不到目标功效（p0={base}, n1={n1}, n0={n0}, "
            f"power={pw}）；请增大样本或降低目标功效，不允许裁剪概率伪造结果"
        )
    root = float(brentq(_gap, 0.0, upper, xtol=tol, rtol=4.0 * math.ulp(1.0), maxiter=200))
    # 求根容差是**根（概率）轴**上的绝对容差，回代功效误差约为 |功效对 Δ 的斜率| × xtol。
    # 因此判定标准必须跟着斜率走，否则把 xtol 从 1e-12 放宽到配置的 1e-10 就会误报。
    step = max(tol, 1e-12)
    slope = abs(_gap(min(root + step, upper)) - _gap(max(root - step, 0.0))) / (2.0 * step)
    allowed = max(1e-12, 10.0 * slope * tol)
    if abs(_gap(root)) > allowed:
        raise RuntimeError(
            f"购买率 MDE 反解不可信：回代功效误差 {abs(_gap(root)):.3e} 超过允许值 {allowed:.3e}"
        )
    return root


# --------------------------------------------------------------------------- #
# 功效格的倍数校准
# --------------------------------------------------------------------------- #
def multiplier_for_target_effect(target_effect: float, design_mde: float) -> float:
    """给定目标效应，反解该格需要的 ``active_mde_multiplier``。

    ``active_mde_multiplier`` 的定义是"目标效应 / 设计样本 MDE"（见
    ``design.local_power.relative_to_observed_design_mde``）。倍数为 1 表示目标效应
    恰好等于设计 MDE（在该功效下刚好可检出）；倍数 < 1 就是**验不出**。

    Raises
    ------
    ValueError
        目标效应为负，或 ``design_mde <= 0``（没有检测下限时倍数无定义）。
    """
    target = _non_negative_float("target_effect", target_effect)
    mde = _positive_float("design_mde", design_mde)
    return target / mde


def target_effect_for_multiplier(multiplier: float, design_mde: float) -> float:
    """:func:`multiplier_for_target_effect` 的正向：倍数 × 设计 MDE = 目标效应。"""
    factor = _non_negative_float("multiplier", multiplier)
    mde = _positive_float("design_mde", design_mde)
    return factor * mde


def multiplier_for_power(
    power: float,
    *,
    alpha: float,
    sides: str = TWO_SIDED,
    reference_power: float = 0.80,
) -> float:
    """拿到目标功效所需的倍数（相对**参考功效**下的 MDE）。

    由 ``MDE(power) = (z_α + z_power)·se`` 得::

        multiplier = (z_α + z_power) / (z_α + z_reference)

    该比值只依赖 α、功效与单/双侧，**与场景机制无关**——这是本模块能给出的结构性
    结论：``design_power_jobs`` 的通过/不通过只由倍数决定，不由哪一层决定。
    """
    a, pw = _validate_alpha_power(alpha, power)
    _, ref = _validate_alpha_power(alpha, reference_power)
    label = _validate_sides(sides)
    z_a = z_alpha(a, label)
    return (z_a + z_power(pw)) / (z_a + z_power(ref))


# --------------------------------------------------------------------------- #
# 设计样本画像（唯一的方差来源）
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class DesignSampleProfile:
    """设计/训练样本上可观测结果的画像：MDE 的唯一样本侧输入。

    只承载**观测列**的汇总（人数、均值、标准差、购买率），不承载任何真值、
    潜在结果或个体级数据。字段名即落盘字段名。

    Attributes
    ----------
    scenario_id:
        产生该设计样本的已注册场景 ID。
    split:
        必须是 ``"train"``；测试集方差不能用来定检测目标。
    n_total, n_treatment, n_control:
        总人数与各臂人数（禁止把 ``n_total`` 当每臂用）。
    profit_mean_*, profit_sd_*:
        各臂 ``net_profit`` 的均值与样本标准差（``ddof=1``，元/合格用户）。
    purchase_rate_*:
        各臂 ``paid_purchase_7d`` 的均值（0–1）。
    rep_id:
        先导模拟的 rep 编号（落在正式重复网格之外，见 :func:`design_pilot_rep_ids`）。
    observed_dataset_hash / source_path / config_hash:
        ``ObservedDataset`` 的内容指纹与来源，保证方差可追溯。
    """

    scenario_id: str
    split: str
    n_total: int
    n_treatment: int
    n_control: int
    profit_mean_treatment: float
    profit_mean_control: float
    profit_sd_treatment: float
    profit_sd_control: float
    purchase_rate_treatment: float
    purchase_rate_control: float
    rep_id: int
    observed_dataset_hash: str
    source_path: str
    config_hash: str
    notes: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.scenario_id, str) or not self.scenario_id:
            raise ValueError("scenario_id 不能为空")
        if self.split != "train":
            raise ValueError(f"设计样本画像只接受 train split，收到 {self.split!r}")
        if _positive_int("n_total", self.n_total) != self.n_treatment + self.n_control:
            raise ValueError("n_treatment + n_control 必须等于 n_total")
        if self.n_treatment < 2 or self.n_control < 2:
            raise ValueError("每臂至少 2 个用户，否则样本方差无定义")
        _positive_float("profit_sd_treatment", self.profit_sd_treatment)
        _positive_float("profit_sd_control", self.profit_sd_control)
        _validate_base_rate(self.purchase_rate_treatment)
        _validate_base_rate(self.purchase_rate_control)
        _as_float("profit_mean_treatment", self.profit_mean_treatment)
        _as_float("profit_mean_control", self.profit_mean_control)
        if int(self.rep_id) < 0:
            raise ValueError(f"rep_id 不能为负，收到 {self.rep_id}")

    @property
    def purchase_rate(self) -> float:
        """全样本购买率（仅用于描述，不作 MDE 基线）。"""
        return (self.purchase_rate_treatment * self.n_treatment
                + self.purchase_rate_control * self.n_control) / self.n_total


_PROFILE_FIELDS: tuple[str, ...] = tuple(f.name for f in fields(DesignSampleProfile))


def profile_to_record(profile: DesignSampleProfile) -> dict[str, Any]:
    """把画像转成可 JSON 落盘的字典（字段与 ``DesignSampleProfile`` 一一对应）。"""
    return {name: getattr(profile, name) for name in _PROFILE_FIELDS}


def profile_from_record(record: Mapping[str, Any]) -> DesignSampleProfile:
    """从落盘字典还原画像；缺字段一律抛错（不做静默默认）。"""
    missing = set(_PROFILE_FIELDS) - set(record)
    if missing:
        raise ValueError(f"画像记录缺字段：{sorted(missing)}")
    return DesignSampleProfile(**{name: record[name] for name in _PROFILE_FIELDS})


def profile_from_frame(
    frame: pd.DataFrame,
    *,
    scenario_id: str,
    rep_id: int,
    observed_dataset_hash: str,
    source_path: str,
    config_hash: str,
    split: str = "train",
    notes: str = "",
) -> DesignSampleProfile:
    """从**只有观测列**的 DataFrame 汇总出设计样本画像。

    这是 :func:`design_sample_profile` 的下层实现，单独暴露是为了能在单测里用小表
    直接验证口径（否则每个单测都要跑完整五表 + SQL）。

    Raises
    ------
    TypeError
        ``frame`` 不是 DataFrame 或列名重复。
    ValueError
        缺可观测列、``split`` 不唯一、误用非 train 行、出现隔离禁止列
        （``audit``/``truth``/``U``/``p0`` 等）、某臂人数 < 2、购买率越界。
    """
    if not isinstance(frame, pd.DataFrame) or not frame.columns.is_unique:
        raise TypeError("设计样本必须是列名唯一的 DataFrame")
    missing = set(OBSERVED_COLUMNS) - set(frame.columns)
    if missing:
        raise ValueError(f"设计样本缺少可观测列：{sorted(missing)}")
    if split != "train":
        raise ValueError(f"设计样本只能取自 train split，收到 {split!r}")
    if frame.empty:
        raise ValueError("设计样本为空")
    forbidden = load_v3_data_config().require("isolation.forbidden_column_patterns")
    offending = [c for c in frame.columns if any(re.search(pattern, str(c)) for pattern in forbidden)]
    if offending:
        raise ValueError(f"设计样本出现真值/审计类列，拒绝计算 MDE：{offending}")
    labels = set(frame["split"].dropna().unique())
    if labels != {split}:
        raise ValueError(f"设计样本必须只包含 {split} 行，实际 {sorted(map(str, labels))}")

    treatment = frame["treatment"].to_numpy()
    if not set(pd.unique(treatment)) <= {0, 1}:
        raise ValueError("treatment 必须是 0/1")
    purchase = frame["paid_purchase_7d"].to_numpy(dtype=float)
    if not set(pd.unique(purchase)) <= {0.0, 1.0}:
        raise ValueError("paid_purchase_7d 必须是 0/1")
    profit = frame["net_profit"].to_numpy(dtype=float)
    if not all(math.isfinite(value) for value in profit):
        raise ValueError("net_profit 必须是有限实数")

    treated, control = profit[treatment == 1], profit[treatment == 0]
    purchase_treated, purchase_control = purchase[treatment == 1], purchase[treatment == 0]
    if treated.size < 2 or control.size < 2:
        raise ValueError(f"每臂至少 2 个用户，实际 {treated.size}/{control.size}")

    return DesignSampleProfile(
        scenario_id=scenario_id,
        split=split,
        n_total=int(treated.size + control.size),
        n_treatment=int(treated.size),
        n_control=int(control.size),
        profit_mean_treatment=float(treated.mean()),
        profit_mean_control=float(control.mean()),
        profit_sd_treatment=float(treated.std(ddof=1)),
        profit_sd_control=float(control.std(ddof=1)),
        purchase_rate_treatment=float(purchase_treated.mean()),
        purchase_rate_control=float(purchase_control.mean()),
        rep_id=int(rep_id),
        observed_dataset_hash=observed_dataset_hash,
        source_path=source_path,
        config_hash=config_hash,
        notes=notes,
    )


def design_sample_profile(dataset: ObservedDataset, *, scenario_id: str, rep_id: int) -> DesignSampleProfile:
    """从 ``ObservedDataset`` 的 **train split** 汇总设计样本画像。

    这是方差进入 MDE 的唯一正式通道：先 ``select_split("train")`` 才能取
    ``observations``，测试/验证 split 的行在这里物理上不可达。

    Raises
    ------
    TypeError
        传入的不是 :class:`~causal_growth.data.v3_observed.ObservedDataset`
        （模拟器、真值表或裸 DataFrame 一律拒绝）。
    ValueError
        数据集不是历史观测（独立验证队列或诊断快照），或 train split 为空。
    """
    if not isinstance(dataset, ObservedDataset):
        raise TypeError("设计样本必须来自 ObservedDataset，不接受模拟器或裸表")
    dataset.require_history()
    train = dataset.select_split("train")
    return profile_from_frame(
        train.observations,
        scenario_id=scenario_id,
        rep_id=rep_id,
        observed_dataset_hash=train.content_hash,
        source_path=train.source_path,
        config_hash=train.config_hash,
        notes=f"population_kind={dataset.population_kind}; split=train",
    )


def write_profiles_json(profiles: Iterable[DesignSampleProfile], path: str | Path) -> Path:
    """把若干画像写成 UTF-8 JSON（含来源标签与"非正式重复"声明）。"""
    payload = {
        "source_label": "合成数据 / 已知 DGP（非真实企业数据）",
        "record_type": "design_sample_profiles",
        "formal_repetitions_completed": 0,
        "purpose": "独立先导模拟：只提供 MDE 所需方差与基准购买率，不构成任何科学结果",
        "profiles": [profile_to_record(profile) for profile in profiles],
    }
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
                      encoding="utf-8")
    return target


def read_profiles_json(path: str | Path) -> dict[str, DesignSampleProfile]:
    """读回落盘画像，按 ``scenario_id`` 建索引。"""
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if payload.get("record_type") != "design_sample_profiles":
        raise ValueError("不是设计样本画像文件")
    profiles = [profile_from_record(record) for record in payload["profiles"]]
    if len({profile.scenario_id for profile in profiles}) != len(profiles):
        raise ValueError("画像文件中场景重复")
    return {profile.scenario_id: profile for profile in profiles}


# --------------------------------------------------------------------------- #
# 从冻结注册表读取设计参数（零硬编码）
# --------------------------------------------------------------------------- #
def alpha_from_config(protocol: V3Protocol | None = None) -> float:
    """读 ``design.alpha_two_sided``（v3 唯一的显著性水平来源）。"""
    proto = protocol or load_v3_protocol()
    return _unit_interval("design.alpha_two_sided", proto.config.require("design.alpha_two_sided"))


def power_targets_from_config(protocol: V3Protocol | None = None) -> tuple[float, ...]:
    """读 ``design.power_targets``（``[0.80, 0.90]``），升序去重。"""
    proto = protocol or load_v3_protocol()
    raw = proto.config.require("design.power_targets")
    powers = sorted({_unit_interval("design.power_targets", value) for value in raw})
    if not powers:
        raise ValueError("design.power_targets 为空")
    return tuple(powers)


def allocation_shares_from_config(protocol: V3Protocol | None = None) -> tuple[float, ...]:
    """从已注册的 L2 人数×分流交叉格读出分流网格（降序）。

    分流比例不是新造参数：``configs/v3/scenarios.yaml`` 的 L2 交叉格已经把
    0.50 / 0.30 / 0.10 三种处理比例冻结成 12 个格。这里只把注册表里的取值收集起来，
    避免在代码里另写一份 ``[0.5, 0.3, 0.1]`` 而随时间漂移。
    """
    proto = protocol or load_v3_protocol()
    cells = proto.config.to_dict()["scenarios"]
    shares = sorted({
        _unit_interval(f"{cell['id']} treatment_probability", cell["treatment_probability"])
        for cell in cells
        if str(cell["id"]).startswith("L2_n")
    }, reverse=True)
    if not shares:
        raise ValueError("注册表中没有 L2 人数×分流交叉格，无法确定分流网格")
    return tuple(shares)


def design_scenario_id(protocol: V3Protocol | None = None) -> str:
    """主设计场景：``matrix_contract.reference_scenarios.L1``。

    为什么是 L1：``design.mde_cohorts``（20 万总样本 + 10 万训练 + 6 万测试）描述的
    就是 L1 主实验的拆分，L1 也是唯一要求 DR 学习器的异质性主场景。该值从注册表读，
    不在代码里写死 ``"L1_main"``。
    """
    proto = protocol or load_v3_protocol()
    scenario = proto.config.require("matrix_contract.reference_scenarios.L1")
    proto.scenario(str(scenario))  # 未注册即抛
    return str(scenario)


def _families_from_config(protocol: V3Protocol) -> tuple[str, ...]:
    """辅助指标所在的检验族成员（``design.multiplicity.auxiliary_family``）。"""
    members = protocol.config.require("design.multiplicity.auxiliary_family")
    return tuple(str(member) for member in members)


def _policy_comparisons(protocol: V3Protocol) -> tuple[str, ...]:
    """策略对比检验族成员（``design.multiplicity.policy_comparisons``）。"""
    members = protocol.config.require("design.multiplicity.policy_comparisons")
    return tuple(str(member) for member in members)


@dataclass(frozen=True)
class Contrast:
    """一个可检验的对比：哪个队列、哪两臂、各多少人、属于多大的检验族。"""

    cohort_id: str
    contrast: str
    metric_family: str
    n_total: int
    n_treatment: int
    n_control: int
    family_size: int
    provenance: str
    arm_labels: tuple[str, str] = ("treatment", "control")

    def __post_init__(self) -> None:
        if self.n_treatment < 1 or self.n_control < 1:
            raise ValueError(f"{self.cohort_id}/{self.contrast}: 两臂人数都必须 >= 1")
        if self.n_treatment + self.n_control > self.n_total:
            raise ValueError(f"{self.cohort_id}: 两臂人数之和超过队列人数")
        _positive_int("family_size", self.family_size)

    @property
    def treatment_share(self) -> float:
        """处理臂占该对比样本的比例。"""
        return self.n_treatment / (self.n_treatment + self.n_control)


def _resolve_arm(label: str, arms: Sequence[str]) -> str:
    """把 ``targeted_vs_no_coupon`` 这类标签解析到注册表里的真实臂名。

    先试精确匹配，再试"词集合包含"匹配；只允许唯一解，否则抛错——臂名歧义会把
    检测能力挂到错的对比上。
    """
    if label in arms:
        return label
    tokens = set(str(label).split("_"))
    candidates = [
        arm for arm in arms
        if tokens <= set(str(arm).split("_")) or set(str(arm).split("_")) <= tokens
    ]
    if len(candidates) != 1:
        raise ValueError(f"无法从 {label!r} 唯一解析出注册臂名（候选 {candidates}，注册臂 {list(arms)}）")
    return candidates[0]


def contrasts_from_config(protocol: V3Protocol | None = None) -> tuple[Contrast, ...]:
    """把 ``design.mde_cohorts`` 展开成"队列 × 对比"清单。

    * 带 ``treatment_probability`` 的队列 → 一个 ``treatment_vs_control`` 对比；
    * 带 ``arm_probabilities`` 的队列（独立随机验证）→ 按
      ``design.multiplicity.policy_comparisons`` 展开成两个对比（定向 vs 随机、
      定向 vs 不发券），族大小取该列表长度。

    另补一行**派生**队列 ``split_validation``（``design.split.validation × n_total``
    = 40,000 人）：验证集不参与 ``mde_cohorts``，但它是观测选模的样本，列出来才能
    说明"验证集也不是 20 万"。该行的 ``provenance`` 明确标为派生，不与冻结清单混称。
    """
    proto = protocol or load_v3_protocol()
    design = proto.config.section("design")
    n_total_default = _positive_int("design.n_total", design["n_total"])
    split = design["split"]
    comparisons = _policy_comparisons(proto)
    rows: list[Contrast] = []
    for cohort in design["mde_cohorts"]:
        cohort_id = str(cohort["id"])
        size = _positive_int(f"{cohort_id}.n_total", cohort["n_total"])
        if "arm_probabilities" in cohort:
            arms = [str(arm) for arm in proto.config.require("evaluation.independent_validation.arms")]
            probabilities = tuple(_as_float(f"{cohort_id}.arm_probabilities", value)
                                  for value in cohort["arm_probabilities"])
            counts = split_counts(size, probabilities)
            index = {arm: position for position, arm in enumerate(arms)}
            for comparison in comparisons:
                left, _, right = comparison.partition("_vs_")
                if not left or not right:
                    raise ValueError(f"policy_comparisons 命名不规范：{comparison!r}")
                treated_arm = _resolve_arm(left, arms)
                control_arm = _resolve_arm(right, arms)
                rows.append(Contrast(
                    cohort_id=cohort_id,
                    contrast=comparison,
                    metric_family="policy_comparison",
                    n_total=size,
                    n_treatment=counts[index[treated_arm]],
                    n_control=counts[index[control_arm]],
                    family_size=len(comparisons),
                    provenance="design.mde_cohorts",
                    arm_labels=(treated_arm, control_arm),
                ))
        else:
            share = _unit_interval(f"{cohort_id}.treatment_probability", cohort["treatment_probability"])
            counts = split_counts(size, (share, 1.0 - share))
            rows.append(Contrast(
                cohort_id=cohort_id,
                contrast="treatment_vs_control",
                metric_family="confirmatory",
                n_total=size,
                n_treatment=counts[0],
                n_control=counts[1],
                family_size=1,
                provenance="design.mde_cohorts",
            ))
    validation_share = _unit_interval("design.split.validation", split["validation"])
    validation_total = int(round(validation_share * n_total_default))
    if validation_total < 4:
        raise ValueError("验证集人数不足 4（每臂至少 2 人），检查 design.split.validation")
    validation_counts = split_counts(validation_total, (0.5, 0.5))
    rows.append(Contrast(
        cohort_id="split_validation",
        contrast="treatment_vs_control",
        metric_family="confirmatory",
        n_total=validation_total,
        n_treatment=validation_counts[0],
        n_control=validation_counts[1],
        family_size=1,
        provenance="design.split.validation（派生的观测选模样本，非 mde_cohorts 条目）",
    ))
    return tuple(rows)


# --------------------------------------------------------------------------- #
# 20 个功效格的校准
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class PowerCellCalibration:
    """一个 ``design_power_jobs`` 格的设计期校准结果。

    Attributes
    ----------
    cell_id / level / base_scenario_id:
        来自冻结注册表，机制通过 ``base_scenario_id`` 继承。
    n_total, n_treatment, n_control:
        该格自己的设计人数与其 50/50 拆分。
    configured_multiplier:
        注册表里冻结的 ``active_mde_multiplier``。
    design_mde:
        该格设计队列在 ``reference_power`` 下的利润 MDE（元/人），方差来自设计样本。
    target_effect:
        ``configured_multiplier × design_mde``；或调用方显式给定的目标效应。
    required_multiplier:
        ``target_effect / design_mde``。>= 1 才等价于"目标效应不低于设计 MDE"。
    analytic_power:
        目标效应下的解析功效（正态近似），**不是**模拟拒绝率。
    required_multiplier_90:
        要拿到 ``target_power_for_90`` 所需的最小倍数（纯 z 比值，与机制无关）。
    """

    cell_id: str
    level: str
    base_scenario_id: str
    n_total: int
    n_treatment: int
    n_control: int
    configured_multiplier: float
    design_mde: float
    target_effect: float
    required_multiplier: float
    analytic_power: float
    required_multiplier_90: float
    reference_power: float
    profile: DesignSampleProfile = field(repr=False, compare=False)

    @property
    def detectable_at_reference(self) -> bool:
        """目标效应是否不低于参考功效下的 MDE（等价于 ``required_multiplier >= 1``）。"""
        return self.target_effect >= self.design_mde

    @property
    def detectable_at_90(self) -> bool:
        """目标效应是否足以拿到 90% 功效。"""
        return self.required_multiplier >= self.required_multiplier_90


def calibrate_power_cell(
    cell_id: str,
    profile: DesignSampleProfile,
    *,
    level: str,
    n_total: int,
    treatment_probability: float,
    alpha: float,
    reference_power: float,
    configured_multiplier: float,
    target_effect: float | None = None,
    sides: str = TWO_SIDED,
    target_power_for_90: float = 0.90,
) -> PowerCellCalibration:
    """校准单个功效格：给定目标效应反解倍数，并核验"目标效应 ≥ MDE"。

    Parameters
    ----------
    cell_id:
        ``design_power_jobs`` 的稳定 ID。
    profile:
        该格 ``base_scenario_id`` 的设计样本画像（提供 σ）。**机制是继承的，方差也
        必须来自同一机制的设计样本**，不能借用别的层。
    level:
        注册表里的层标签（L0–L3）。
    n_total, treatment_probability:
        该格注册的样本量与处理比例（来自 ``scenarios.yaml``，本函数不给默认值）。
    alpha, reference_power:
        显著性水平与 ``active_mde_multiplier`` 的参考功效（取 ``design.power_targets``
        的最小值，即 0.80）。
    configured_multiplier:
        注册表里冻结的倍数。
    target_effect:
        显式给定的目标效应（元/人）。给 ``None`` 时按注册倍数反推
        ``configured_multiplier × design_mde``；给了值就按它反解所需倍数——这就是
        "给定目标效应，反解 ``active_mde_multiplier``"的入口。

    Raises
    ------
    ValueError
        目标效应为负、``n_total`` 非法、分流越界、倍数为负。
    """
    share = _unit_interval("treatment_probability", treatment_probability)
    counts = split_counts(_positive_int("n_total", n_total), (share, 1.0 - share))
    design_mde = profit_mde(
        profile.profit_sd_treatment, profile.profit_sd_control, counts[0], counts[1],
        alpha=alpha, power=reference_power, sides=sides,
    )
    configured = _non_negative_float("configured_multiplier", configured_multiplier)
    target = (target_effect_for_multiplier(configured, design_mde) if target_effect is None
              else _non_negative_float("target_effect", target_effect))
    return PowerCellCalibration(
        cell_id=str(cell_id),
        level=str(level),
        base_scenario_id=profile.scenario_id,
        n_total=int(n_total),
        n_treatment=counts[0],
        n_control=counts[1],
        configured_multiplier=configured,
        design_mde=design_mde,
        target_effect=target,
        required_multiplier=multiplier_for_target_effect(target, design_mde),
        analytic_power=profit_power(
            target, profile.profit_sd_treatment, profile.profit_sd_control, counts[0], counts[1],
            alpha=alpha, sides=sides,
        ),
        required_multiplier_90=multiplier_for_power(
            target_power_for_90, alpha=alpha, sides=sides, reference_power=reference_power),
        reference_power=reference_power,
        profile=profile,
    )


def calibrate_power_cells(
    protocol: V3Protocol | None = None,
    profiles: Mapping[str, DesignSampleProfile] | None = None,
    *,
    sides: str = TWO_SIDED,
) -> tuple[PowerCellCalibration, ...]:
    """按冻结注册表校准全部 20 个功效格（``design_power_jobs``）。

    ``profiles`` 必须覆盖 ``design.local_power.base_scenarios`` 的每个场景；缺一个
    就抛错（不允许用别的层的方差顶替）。
    """
    proto = protocol or load_v3_protocol()
    provided = dict(profiles or {})
    design = proto.config.section("design")
    required_scenarios = [str(name) for name in design["local_power"]["base_scenarios"]]
    missing = [name for name in required_scenarios if name not in provided]
    if missing:
        raise ValueError(f"缺少这些基础场景的设计样本画像：{missing}")
    alpha = alpha_from_config(proto)
    reference_power = min(power_targets_from_config(proto))
    cells = proto.config.to_dict()["design_power_jobs"]
    results: list[PowerCellCalibration] = []
    for cell in cells:
        base = str(cell["base_scenario_id"])
        if base not in required_scenarios:
            raise ValueError(f"{cell['id']} 的基础场景 {base} 不在 design.local_power.base_scenarios 内")
        multiplier = cell["overrides"].get("design.local_power.active_mde_multiplier")
        if multiplier is None:
            raise ValueError(f"{cell['id']} 没有冻结 active_mde_multiplier")
        results.append(calibrate_power_cell(
            str(cell["id"]),
            provided[base],
            level=str(cell["level"]),
            n_total=int(cell["n"]),
            treatment_probability=float(cell["treatment_probability"]),
            alpha=alpha,
            reference_power=reference_power,
            configured_multiplier=float(multiplier),
            sides=sides,
        ))
    if len(results) != len(cells):
        raise RuntimeError("功效格数量与注册表不一致")
    return tuple(results)


# --------------------------------------------------------------------------- #
# 汇总表
# --------------------------------------------------------------------------- #
def _base_row(protocol: V3Protocol) -> dict[str, Any]:
    """一条汇总行的公共空壳（列顺序即 :data:`MDE_TABLE_COLUMNS`）。"""
    row: dict[str, Any] = {column: None for column in MDE_TABLE_COLUMNS}
    row["data_source"] = str(protocol.config.require("project.data_source_label"))
    return row


def _relative_percent(value: float, base: float) -> float | None:
    """``value / base * 100``；基线非正时返回 ``None``（相对口径无意义，不硬算）。"""
    if not math.isfinite(base) or base <= 0.0:
        return None
    return value / base * 100.0


def build_mde_rows(
    protocol: V3Protocol | None = None,
    profiles: Mapping[str, DesignSampleProfile] | None = None,
    *,
    design_scenario: str | None = None,
    sides_reported: Sequence[str] = (TWO_SIDED, ONE_SIDED),
    root_tolerance: float | None = None,
) -> list[dict[str, Any]]:
    """生成 ``outputs/tables/v3_phase_D_mde.csv`` 的全部行。

    ``record_type = design_mde`` 的行覆盖"队列 × 分流 × 功效 × 单/双侧 × 指标 ×
    是否多重校正"；``record_type = power_cell`` 的行覆盖 20 个功效格。所有参数
    （α、目标功效、分流网格、族大小、根容差、队列人数）都从注册表读。
    """
    proto = protocol or load_v3_protocol()
    provided = dict(profiles or {})
    scenario = design_scenario or design_scenario_id(proto)
    if scenario not in provided:
        raise ValueError(f"缺少主设计场景 {scenario} 的设计样本画像")
    profile = provided[scenario]
    alpha = alpha_from_config(proto)
    powers = power_targets_from_config(proto)
    shares = allocation_shares_from_config(proto)
    design = proto.config.section("design")
    primary_metric = str(design["primary_metric"])
    auxiliary_metric = str(design["auxiliary_metric"])
    auxiliary_family = _families_from_config(proto)
    policy_comparisons = _policy_comparisons(proto)
    tolerance = _positive_float(
        "root_tolerance",
        design["numerical"]["root_tolerance"] if root_tolerance is None else root_tolerance,
    )
    sides_list = [_validate_sides(side) for side in sides_reported]
    if not sides_list:
        raise ValueError("至少要报告一种单/双侧口径")
    level = str(proto.scenario(scenario).require("active_scenario.level"))
    variance_source = f"design_pilot_train_split:{scenario}:rep{profile.rep_id}"

    rows: list[dict[str, Any]] = []
    for contrast in contrasts_from_config(proto):
        if contrast.cohort_id == "independent_validation":
            allocations: tuple[float | None, ...] = (None,)
        else:
            allocations = tuple(shares)  # type: ignore[assignment]
        for share in allocations:
            if share is None:
                n_treatment, n_control = contrast.n_treatment, contrast.n_control
            else:
                counts = split_counts(contrast.n_total, (share, 1.0 - share))
                n_treatment, n_control = counts
            share_label = n_treatment / (n_treatment + n_control)
            for sides in sides_list:
                for power in powers:
                    for metric in (primary_metric, auxiliary_metric):
                        is_proportion = metric == auxiliary_metric
                        if is_proportion:
                            variants = [("none", 1), ("holm", len(auxiliary_family))]
                        elif contrast.metric_family == "policy_comparison":
                            variants = [("none", 1), ("holm", len(policy_comparisons))]
                        else:
                            variants = [("none", 1)]
                        for adjustment, family_size in variants:
                            alpha_per_test = (alpha if adjustment == "none"
                                              else holm_per_test_alpha(alpha, family_size))
                            if is_proportion:
                                mde = purchase_mde(
                                    profile.purchase_rate_control, n_treatment, n_control,
                                    alpha=alpha_per_test, power=power, sides=sides,
                                    tolerance=tolerance,
                                )
                                control_mean = profile.purchase_rate_control
                                p0, p1 = control_mean, control_mean + mde
                            else:
                                mde = profit_mde(
                                    profile.profit_sd_treatment, profile.profit_sd_control,
                                    n_treatment, n_control,
                                    alpha=alpha_per_test, power=power, sides=sides,
                                )
                                control_mean = profile.profit_mean_control
                                p0, p1 = None, None
                            row = _base_row(proto)
                            row.update({
                                "record_type": "design_mde",
                                "scenario_id": scenario,
                                "level": level,
                                "base_scenario_id": scenario,
                                "cohort_id": contrast.cohort_id,
                                "cohort_provenance": contrast.provenance,
                                "contrast": contrast.contrast,
                                "metric": metric,
                                "n_total": contrast.n_total,
                                "n_treatment": n_treatment,
                                "n_control": n_control,
                                "treatment_share": share_label,
                                "alpha": alpha,
                                "alpha_per_test": alpha_per_test,
                                "sides": sides,
                                "power_target": power,
                                "multiplicity": adjustment,
                                "family_size": family_size,
                                "mde": mde,
                                "mde_unit": "probability" if is_proportion else "CNY_per_assigned_user",
                                "mde_pp": mde * 100.0 if is_proportion else None,
                                "control_mean": control_mean,
                                "mde_relative_pct": _relative_percent(mde, control_mean),
                                "sigma_treatment": profile.profit_sd_treatment,
                                "sigma_control": profile.profit_sd_control,
                                "p0_baseline": p0,
                                "p1_at_mde": p1,
                                "analytic_power": power,
                                "variance_source": variance_source,
                                "observed_dataset_hash": profile.observed_dataset_hash,
                                "notes": (f"normal_approximation; root_tolerance={tolerance:g}; "
                                          "cohort_split=user_id_within_run; R=0"),
                            })
                            row["primary_row"] = bool(
                                sides == TWO_SIDED
                                and abs(power - powers[0]) < 1e-12
                                and adjustment == "none"
                                and (
                                    (contrast.cohort_id == "independent_validation"
                                     and contrast.contrast == policy_comparisons[0])
                                    or (contrast.cohort_id != "independent_validation"
                                        and abs(share_label - 0.5) < _PROBABILITY_TOLERANCE)
                                )
                            )
                            rows.append(row)

    for cell in calibrate_power_cells(proto, provided):
        row = _base_row(proto)
        row.update({
            "record_type": "power_cell",
            "scenario_id": cell.base_scenario_id,
            "level": cell.level,
            "base_scenario_id": cell.base_scenario_id,
            "cohort_id": "power_cell",
            "cohort_provenance": "scenarios.design_power_jobs",
            "contrast": "treatment_vs_control",
            "metric": primary_metric,
            "n_total": cell.n_total,
            "n_treatment": cell.n_treatment,
            "n_control": cell.n_control,
            "treatment_share": cell.n_treatment / cell.n_total,
            "alpha": alpha,
            "alpha_per_test": alpha,
            "sides": TWO_SIDED,
            "power_target": cell.reference_power,
            "multiplicity": "none",
            "family_size": 1,
            "mde": cell.design_mde,
            "mde_unit": "CNY_per_assigned_user",
            "control_mean": cell.profile.profit_mean_control,
            "mde_relative_pct": _relative_percent(cell.design_mde, cell.profile.profit_mean_control),
            "sigma_treatment": cell.profile.profit_sd_treatment,
            "sigma_control": cell.profile.profit_sd_control,
            "target_effect": cell.target_effect,
            "analytic_power": cell.analytic_power,
            "required_multiplier": cell.required_multiplier,
            "configured_multiplier": cell.configured_multiplier,
            "required_multiplier_90": cell.required_multiplier_90,
            "detectable_at_80": cell.detectable_at_reference,
            "detectable_at_90": cell.detectable_at_90,
            "primary_row": True,
            "variance_source": f"design_pilot_train_split:{cell.base_scenario_id}:rep{cell.profile.rep_id}",
            "observed_dataset_hash": cell.profile.observed_dataset_hash,
            "notes": ("power_job_design_only; achieved_effect/rejection_rate/MC_SE pending D & G; "
                      "constant_profit_shift_forbidden"),
        })
        rows.append(row)
    return rows


def write_mde_csv(rows: Sequence[Mapping[str, Any]], path: str | Path) -> Path:
    """把汇总行写成 CSV（列顺序固定为 :data:`MDE_TABLE_COLUMNS`，编码取配置）。

    Raises
    ------
    ValueError
        行里出现未知列（防止某次改动静默加列后报告对不上）。
    """
    unknown = {key for row in rows for key in row} - set(MDE_TABLE_COLUMNS)
    if unknown:
        raise ValueError(f"汇总表出现未登记列：{sorted(unknown)}")
    frame = pd.DataFrame([{column: row.get(column) for column in MDE_TABLE_COLUMNS} for row in rows],
                         columns=list(MDE_TABLE_COLUMNS))
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(target, index=False, encoding=load_v3_data_config().require("io.csv_encoding"))
    return target


def read_mde_csv(path: str | Path) -> pd.DataFrame:
    """读回汇总表并核对列顺序（报告引用的每个数字都要能在这里找到）。"""
    frame = pd.read_csv(Path(path), encoding=load_v3_data_config().require("io.csv_encoding"))
    if tuple(frame.columns) != MDE_TABLE_COLUMNS:
        raise ValueError("汇总表列顺序与 MDE_TABLE_COLUMNS 不一致")
    return frame


# --------------------------------------------------------------------------- #
# 独立先导模拟（方差来源；不构成任何正式重复）
# --------------------------------------------------------------------------- #
def design_pilot_rep_ids(protocol: V3Protocol | None = None, count: int = 1) -> tuple[int, ...]:
    """返回先导模拟专用的 rep 编号：**从正式重复网格的右端之外开始**。

    正式 rep 索引范围是 ``[0, R_max-1]``；先导模拟用 ``R_max, R_max+1, …``，因此与
    任何正式 rep 的数据都不重叠（同一个 ``(seed, stream, index)`` 才产出同一串随机
    数）。这样"看先导数据定检测目标"不会偷看任何正式 rep。
    """
    proto = protocol or load_v3_protocol()
    n = _positive_int("count", count)
    data = proto.config.to_dict()
    max_r = max(int(cell["R"]) for cell in data["scenarios"] + data["design_power_jobs"])
    return tuple(range(max_r, max_r + n))


def _generate_design_sample(
    protocol: V3Protocol, scenario_id: str, rep_id: int, work_root: Path
) -> tuple[ObservedDataset, dict[str, Any]]:
    """生成一次先导观测并返回 ``(ObservedDataset, 计时字典)``。

    警告：本函数是全模块**唯一**接触 DGP 的地方，且只取
    ``population.observation_bundle()``（三张观测表），不触碰 ``worlds`` / 真值 /
    审计区。放在函数内延迟导入，是为了让校准路径在导入期就物理上拿不到
    ``causal_growth.dgp``。
    """
    from causal_growth.data.v3_pipeline import build_observed_pipeline
    from causal_growth.dgp.v3_engine import generate_v3_population

    cfg: Config = protocol.scenario(scenario_id)
    n = int(cfg.require("design.n_total"))
    started = time.perf_counter()
    cpu_started = time.process_time()
    population = generate_v3_population(cfg, rep_id=rep_id, n=n)
    users, assignments, orders = population.observation_bundle()
    generate_seconds = time.perf_counter() - started
    directory = work_root / f"{scenario_id}_rep{rep_id}"
    shutil.rmtree(directory, ignore_errors=True)
    try:
        result = build_observed_pipeline(
            users, assignments, orders, cfg,
            directory=directory,
            run_id=f"design_power_pilot:{scenario_id}:{rep_id}",
            rep_id=rep_id,
            stream_prefix=str(population.metadata["stream_prefix"]),
            persist_database=False,
            retention_scope="engineering_full",
        )
        timings = {
            "scenario_id": scenario_id,
            "rep_id": rep_id,
            "n_registered": n,
            "generate_wall_s": generate_seconds,
            "total_wall_s": time.perf_counter() - started,
            "total_cpu_s": time.process_time() - cpu_started,
            "stream_prefix": str(population.metadata["stream_prefix"]),
            "manifest_path": str(result.manifest_path),
        }
        return result.dataset, timings
    finally:
        shutil.rmtree(directory, ignore_errors=True)


def run_design_pilot(
    scenario_ids: Sequence[str] | None = None,
    *,
    work_root: str | Path,
    protocol: V3Protocol | None = None,
    rep_ids: Sequence[int] | None = None,
) -> tuple[DesignSampleProfile, ...]:
    """跑独立先导模拟，只为拿到 MDE 所需的 σ 与基准购买率。

    * 场景默认取 ``design.local_power.base_scenarios``（4 个基础机制）；
    * rep 编号默认由 :func:`design_pilot_rep_ids` 给出（正式网格之外）；
    * 每个场景跑完立即删掉流水线目录，只保留画像与计时，不写 ``data/v3`` 或
      ``audit/v3``，``formal_repetitions_completed`` 恒为 0。

    这不是正式重复，也不产生任何"检出率/达成效应"结论。
    """
    proto = protocol or load_v3_protocol()
    if scenario_ids is None:
        scenario_ids = [str(name) for name in proto.config.require("design.local_power.base_scenarios")]
    names = [str(name) for name in scenario_ids]
    if not names:
        raise ValueError("至少要跑一个先导场景")
    if len(set(names)) != len(names):
        raise ValueError("先导场景重复")
    if rep_ids is None:
        rep_ids = design_pilot_rep_ids(proto, len(names))
    reps = [_positive_int("rep_id", value) for value in rep_ids]
    if len(reps) != len(names):
        raise ValueError("rep_ids 数量必须与场景数量一致")
    root = Path(work_root)
    root.mkdir(parents=True, exist_ok=True)
    profiles: list[DesignSampleProfile] = []
    timings: list[dict[str, Any]] = []
    for name, rep in zip(names, reps, strict=True):
        dataset, timing = _generate_design_sample(proto, name, rep, root)
        profile = design_sample_profile(dataset, scenario_id=name, rep_id=rep)
        profiles.append(profile)
        timings.append(timing)
        print(f"[design-pilot] {name} rep={rep} n={profile.n_total} "
              f"sd=({profile.profit_sd_treatment:.4f}, {profile.profit_sd_control:.4f}) "
              f"p0={profile.purchase_rate_control:.6f} wall={timing['total_wall_s']:.1f}s", flush=True)
    (root / "design_pilot_timings.json").write_text(json.dumps({
        "source_label": "合成数据 / 已知 DGP（非真实企业数据）",
        "record_type": "design_pilot_timings",
        "formal_repetitions_completed": 0,
        "config_hash": proto.config_hash,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "timings": timings,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_profiles_json(profiles, root / "design_pilot_profiles.json")
    return tuple(profiles)


def _main(argv: Sequence[str] | None = None) -> int:
    """薄命令行入口：``--pilot`` 跑先导、``--table`` 出表、默认两者都做。"""
    import argparse

    parser = argparse.ArgumentParser(description="v3 Phase D.1：固定 N 反算 MDE 与功效格校准")
    parser.add_argument("--pilot", action="store_true", help="只跑独立先导模拟（方差来源）")
    parser.add_argument("--table", action="store_true", help="只用已落盘先导画像生成汇总表")
    parser.add_argument("--scenarios", nargs="*", default=None,
                        help="先导场景（默认取 design.local_power.base_scenarios）")
    parser.add_argument("--out-dir", default="out/v3_phase_d_mde", help="先导证据与工作目录")
    parser.add_argument("--table-path", default="outputs/tables/v3_phase_D_mde.csv",
                        help="汇总表落盘路径")
    args = parser.parse_args(argv)

    root = Path(args.out_dir)
    payload = root / "design_pilot_profiles.json"
    do_pilot = args.pilot or not args.table
    do_table = args.table or not args.pilot
    if do_pilot:
        run_design_pilot(args.scenarios, work_root=root)
    if do_table:
        if not payload.exists():
            raise SystemExit(f"缺少先导画像 {payload}；先跑 --pilot")
        protocol = load_v3_protocol()
        rows = build_mde_rows(protocol, read_profiles_json(payload))
        target = write_mde_csv(rows, args.table_path)
        design_rows = sum(1 for row in rows if row["record_type"] == "design_mde")
        print(f"[design-mde] 已写 {target}：design_mde={design_rows}, "
              f"power_cell={len(rows) - design_rows}")
    return 0


if __name__ == "__main__":  # pragma: no cover - 命令行入口
    raise SystemExit(_main())
