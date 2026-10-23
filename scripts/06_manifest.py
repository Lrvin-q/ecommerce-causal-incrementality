"""生成产物哈希清单（S11：把"逐字节一致"换成可核对的 SHA256 清单）。

用法
----
    $env:PYTHONUTF8='1'
    .\\.venv\\Scripts\\python.exe scripts\\06_manifest.py

为什么不是"逐字节一致"
----------------------
浮点结果在不同 BLAS / pandas / numpy 版本上可能差最后几位，
声称"逐字节一致"既不可验证也不诚实。可核对的说法是：
**同一台机器、同一份 requirements 下，重跑后 SHA256 清单不变**，
清单本身就是证据——审稿人拿到清单可以自行重算比对。
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def sha256_of(path: Path, *, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while True:
            block = fh.read(chunk)
            if not block:
                break
            h.update(block)
    return h.hexdigest()


def main() -> int:
    targets: list[Path] = []
    for sub, pattern in (
        ("outputs/tables", "*.csv"),
        ("outputs/figures/paper", "*.png"),
        ("configs", "*.yaml"),
        ("data", "*.csv"),
    ):
        base = ROOT / sub
        if base.exists():
            targets.extend(sorted(p for p in base.glob(pattern) if p.is_file()))

    out = ROOT / "outputs" / "SHA256SUMS.txt"
    lines = []
    for p in targets:
        rel = p.relative_to(ROOT).as_posix()
        lines.append(f"{sha256_of(p)}  {rel}")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[manifest] {len(lines)} 个文件 -> {out.relative_to(ROOT)}")
    print(f"[manifest] 其中 outputs/tables {sum(1 for x in targets if 'outputs/tables' in x.as_posix())} 个、"
          f"图 {sum(1 for x in targets if 'figures' in x.as_posix())} 个")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
