"""按用户的三分切分（训练 / 验证 / 测试）。

为什么必须按**用户**切、且绝不重叠
----------------------------------
同一个用户如果既进训练集又进测试集，模型等于见过答案。本项目里
CATE 模型的训练目标是"观测到的利润"，而评估目标是"真值 τ(x)"；
一旦切分泄漏，CATE RMSE 会被系统性低估，策略价值会被系统性高估
（方案 §2.4 常见坑 5：用同一批数据学策略又评策略）。

切分随机流独立于 DGP，这样"换一批切分"不会改变底层数据。
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from causal_growth.rng import child_rng

__all__ = ["Split", "train_val_test_split"]


@dataclass(frozen=True)
class Split:
    """三分索引。三者两两不相交、并集为全体。"""

    train: np.ndarray
    val: np.ndarray
    test: np.ndarray
    n_total: int

    def __post_init__(self) -> None:
        sizes = self.train.size + self.val.size + self.test.size
        if sizes != self.n_total:
            raise ValueError(f"切分覆盖 {sizes} 个用户，但总数为 {self.n_total}")
        overlap = (
            np.intersect1d(self.train, self.test).size
            + np.intersect1d(self.train, self.val).size
            + np.intersect1d(self.val, self.test).size
        )
        if overlap:
            raise ValueError(f"切分存在重叠用户 {overlap} 个——这就是数据泄漏")

    def summary(self) -> dict[str, float]:
        return {
            "n_total": float(self.n_total),
            "n_train": float(self.train.size),
            "n_val": float(self.val.size),
            "n_test": float(self.test.size),
            "share_train": float(self.train.size / self.n_total),
            "share_val": float(self.val.size / self.n_total),
            "share_test": float(self.test.size / self.n_total),
        }


def train_val_test_split(
    n_total: int,
    *,
    test_size: float,
    val_size: float,
    master_seed: int,
    index: int = 0,
    stream: str = "split.users",
) -> Split:
    """把 ``n_total`` 个用户随机切成 train / val / test。

    参数
    ----
    test_size, val_size : 测试集与验证集占比，二者之和必须 < 1。
    index : 重复实验编号；不同 index 得到不同切分，用于重复评估。

    返回
    ----
    ``Split``，三个索引数组均已排序，便于落盘与复现。
    """
    if n_total <= 0:
        raise ValueError(f"n_total 必须为正，收到 {n_total}")
    if not 0.0 < test_size < 1.0:
        raise ValueError(f"test_size 必须在 (0,1) 内，收到 {test_size}")
    if not 0.0 <= val_size < 1.0:
        raise ValueError(f"val_size 必须在 [0,1) 内，收到 {val_size}")
    if test_size + val_size >= 1.0:
        raise ValueError(
            f"test_size({test_size}) + val_size({val_size}) 必须 < 1，否则训练集为空"
        )

    rng = child_rng(master_seed, stream, index)
    perm = rng.permutation(n_total)

    n_test = int(round(n_total * test_size))
    n_val = int(round(n_total * val_size))
    # 保证三个集合都非空
    n_test = max(1, min(n_test, n_total - 2))
    n_val = max(1, min(n_val, n_total - n_test - 1))

    test = np.sort(perm[:n_test])
    val = np.sort(perm[n_test : n_test + n_val])
    train = np.sort(perm[n_test + n_val :])
    return Split(train=train, val=val, test=test, n_total=n_total)
