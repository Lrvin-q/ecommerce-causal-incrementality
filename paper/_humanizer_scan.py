"""humanizer 体检：按固定正则统计稿子里的 11 类 AI 写作痕迹。

用法
----
    $env:PYTHONUTF8='1'
    .\\.venv\\Scripts\\python.exe paper\\_humanizer_scan.py <文本文件>

说明
----
- 只统计正文（``## 1 引言`` 起），跳过 Markdown 表格行（``|`` 开头）与 LaTeX 原始块。
- 每条规则给出"命中次数"，不是"段落数"；比较的是同一把尺子下的前后差值。
- 规则编号沿用 blader/humanizer 的条目号（§1 §2 §3 §6 §8 §12 §13 §15 §19 §25 §26）。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

RULES: dict[str, list[str]] = {
    # §1 不是 X 而是 Y（含"而非"与跨句否定）
    "§1": [
        r"不是[^。；\n]{0,25}?而是",
        r"并非[^。；\n]{0,25}?而是",
        r"不在于[^。；\n]{0,20}?而在于",
        r"而非",
        r"不是[^，。；\n]{0,20}，是",
    ],
    # §3 听起来很深的说法
    "§3": [r"真正的", r"本质上", r"归根结底", r"说到底", r"关键在于", r"核心在于", r"说白了"],
    # §6 三段式排比（一句里两个分号 = 三件并列）
    "§6": [r"；[^。\n]{2,40}；"],
    # §8 破折号（中文破折号与 em dash）
    "§8": [r"—"],
    # §12 AI 高频词
    "§12": [
        r"值得注意的是",
        r"至关重要",
        r"深刻",
        r"赋能",
        r"抓手",
        r"闭环",
        r"层面",
        r"助力",
        r"彰显",
        r"凸显",
        r"进一步",
        r"从而",
        r"综上",
        r"由此可见",
        r"毋庸置疑",
        r"不容忽视",
    ],
    # §13 拔高意义
    "§13": [
        r"具有重要意义",
        r"意义重大",
        r"奠定了[^。\n]{0,8}基础",
        r"标志着",
        r"为[^。\n]{0,12}提供[^。\n]{0,8}参考",
        r"填补了[^。\n]{0,6}空白",
    ],
    # §15 句末附加的 -ing 式评语
    "§15": [r"体现了", r"反映了", r"说明了", r"表明了", r"凸显了", r"印证了", r"揭示了", r"彰显了"],
    # §25 写文档本身（不是写研究对象）
    "§25": [
        r"本文引用",
        r"本文采用",
        r"本文只",
        r"本文不",
        r"本节",
        r"下文",
        r"如上",
        r"如下",
        r"正文中",
        r"附录中",
    ],
    # §26 复述读者已知的信息
    "§26": [r"换句话说", r"也就是说", r"简言之", r"即：", r"所谓"],
    # §19 装饰性加粗（表题只加粗编号不算）
    "§19": [r"\*\*[^*\n]+\*\*"],
}


def body(path: Path) -> str:
    text = path.read_text(encoding="utf-8-sig")
    i = text.index("## 1 引言")
    text = text[i:]
    keep = []
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("|") or s.startswith("```") or s.startswith("**表 "):
            continue
        keep.append(line)
    return "\n".join(keep)


def count_sentences_last_short(text: str) -> int:
    """§2 单句评语：段落末句 <= 12 个汉字且不承担新事实。"""
    n = 0
    for para in re.split(r"\n\s*\n", text):
        p = para.strip()
        if not p or p.startswith("#") or p.startswith("$$") or p.startswith("- "):
            continue
        sents = [s for s in re.split(r"(?<=[。！？])", p) if s.strip()]
        if len(sents) < 2:
            continue
        last = re.sub(r"[^\u4e00-\u9fff]", "", sents[-1])
        # 含数字/拉丁字母的短句多是有事实负载的陈述（"另有 404 项测试"），不算评语
        if re.search(r"[0-9A-Za-z$]", sents[-1]):
            continue
        if 0 < len(last) <= 12:
            n += 1
    return n


def main(argv: list[str]) -> int:
    path = Path(argv[1])
    text = body(path)
    counts = {}
    for key, pats in RULES.items():
        counts[key] = sum(len(re.findall(p, text)) for p in pats)
    counts["§2"] = count_sentences_last_short(text)
    order = ["§1", "§2", "§3", "§6", "§8", "§12", "§13", "§15", "§19", "§25", "§26"]
    print(f"{path.name}: " + "  ".join(f"{k}={counts[k]}" for k in order))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
