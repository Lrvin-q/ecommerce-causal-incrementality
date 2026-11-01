"""可复现的随机数流派生。

为什么需要这一层
----------------
本项目有**上千次重复实验**（AA 校验 1000 次、每层 R = 200~500 次、λ 扫描、预算扫描）。
如果用全局 ``np.random.seed()``，任何一处新增的随机调用都会扰动后面所有结果，
"两次运行结果一致"就无法保证，论文级的可复现性直接失守。

设计目标
--------
1. **确定性**：同一 ``(master_seed, stream, index)`` 永远产出同一串随机数。
2. **正交性**：新增一个 stream 不会扰动任何已有 stream 的随机数。
3. **可追溯**：stream 用带语义的字符串命名（如 ``"dgp.l1"``、``"aa.rep"``），
   出问题时能一眼定位是哪个环节的随机性。

实现依据
--------
用 ``numpy.random.SeedSequence`` 的 entropy 序列承载
``[master_seed, sha256(stream), index]``。sha256 保证字符串 → 整数稳定
（不受 ``PYTHONHASHSEED`` 影响），SeedSequence 保证不同 entropy 产出的
随机流统计上独立。

用法
----
>>> rng = child_rng(20240101, "dgp.l1", index=0)   # Generator，无状态污染
>>> seed = child_seed(20240101, "sklearn.cate", 0)  # 给 sklearn 的 random_state
>>> rngs = child_rngs(20240101, "aa.rep", range(1000))  # 批量取 1000 条独立流
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable

import numpy as np

__all__ = [
    "child_rng",
    "child_rngs",
    "child_seed",
    "child_seeds",
    "derive_key",
]

_HASH_BYTES = 8


def derive_key(stream: str) -> int:
    """把带语义的 stream 名稳定地映射为非负整数。

    使用 sha256 而非内置 ``hash()``，因为后者受 ``PYTHONHASHSEED`` 影响，
    跨进程不稳定，会破坏可复现性。
    """
    if not isinstance(stream, str):
        raise TypeError(f"stream 必须是 str，收到 {type(stream).__name__}")
    if not stream.strip():
        raise ValueError("stream 不能为空字符串或纯空白")
    digest = hashlib.sha256(stream.encode("utf-8")).digest()
    return int.from_bytes(digest[:_HASH_BYTES], "big", signed=False)


def _validate_index(index: int) -> int:
    if isinstance(index, bool) or not isinstance(index, (int, np.integer)):
        raise TypeError(f"index 必须是整数，收到 {type(index).__name__}")
    if index < 0:
        raise ValueError(f"index 必须 >= 0，收到 {index}")
    return int(index)


def _seed_sequence(master_seed: int, stream: str, index: int) -> np.random.SeedSequence:
    if isinstance(master_seed, bool) or not isinstance(master_seed, (int, np.integer)):
        raise TypeError(f"master_seed 必须是整数，收到 {type(master_seed).__name__}")
    return np.random.SeedSequence([int(master_seed), derive_key(stream), _validate_index(index)])


def child_rng(master_seed: int, stream: str, index: int = 0) -> np.random.Generator:
    """返回一条独立的 ``numpy.random.Generator`` 随机流。"""
    return np.random.default_rng(_seed_sequence(master_seed, stream, index))


def child_rngs(
    master_seed: int, stream: str, indices: Iterable[int]
) -> list[np.random.Generator]:
    """批量返回多条独立随机流（如 AA 的 1000 次重复各一条）。"""
    return [child_rng(master_seed, stream, i) for i in indices]


def child_seed(master_seed: int, stream: str, index: int = 0) -> int:
    """返回一个 32 位无符号整数种子，供 ``random_state`` 参数使用。

    注意：``child_seed`` 与 ``child_rng`` 用同一 SeedSequence 起点但产出不同，
    不要拿 ``child_seed`` 的结果去喂 ``child_rng`` 期望的同一串随机数。
    """
    seq = _seed_sequence(master_seed, stream, index)
    return int(seq.generate_state(1, dtype=np.uint32)[0])


def child_seeds(master_seed: int, stream: str, indices: Iterable[int]) -> list[int]:
    """批量返回整数种子。"""
    return [child_seed(master_seed, stream, i) for i in indices]
