r"""交叉引用后处理：给表、图、公式、文献、章节补锚点，并把正文引用改成可跳转链接。

为什么需要这一步
----------------
论文正文里的"表 3""图 5""式(2)""[7]""§3.2"都是**手写编号**（表号由粗体题注给出、
图号由 LaTeX 自动编号、文献号手工维护、章节号写在标题文本里），它们没有 ``\label``，
因此 hyperref 无从建立链接，读者点不动，也不会显示为蓝色。要满足"可跳转引用全部蓝色"，
只能在 pandoc 之后、xelatex 之前补一遍锚点。

六件事
------
1. 表格：在每个 ``\textbf{表 N`` 前插入 ``\phantomsection\label{tab:N}``
2. 图：在每个 ``\begin{figure}`` 前插入 ``\phantomsection\label{fig:N}``（按出现顺序编号）；
   图 1 额外给 ``[htbp]``，允许它落到 §1.3 附近，而不是死守页顶（审稿意见 S1）
3. 公式：把 ``\tag{N}`` 补成 ``\tag{N}\label{eq:N}``
4. 文献：在参考文献列表每条 ``{[}N{]}}`` 前插入 ``\phantomsection\label{ref:N}``
5. 章节：在 ``\section{1 引言}`` / ``\subsection{3.2 实验设计}`` 后插 ``\label{sec:N.N}``。
   标题是 pandoc 转出来的，编号写在标题文本里（``secnumdepth=0``），故按文本前缀取号。
   标题可能被 pandoc 折成两行（``\subsection{1.3`` + 下一行），必须跨行匹配。
6. 正文：把 ``表 N`` / ``图 N`` / ``式(N)`` / ``{[}N{]}`` / ``§N.N`` 包成 ``\hyperref[...]{...}``

两遍处理
--------
必须先确定"合法编号集合"再包裹。否则「用户表 20 万行」「事件表 120.1 万行」里的数字
会被当成表号，生成 ``tab:20`` 这类未定义引用，在 PDF 里渲染成问号。
另加负向先行断言：编号后紧跟量词（万/行/元…）的一律不算引用。

题注行与文献条目行只加锚点、不包链接，避免"表 3 指向自己"的自环。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

#: 表格题注：行首可能已有 \needspace 前缀；附录里的表是「表 A1 / B1 / C1」
RE_TABLE_CAPTION = re.compile(r"\\textbf\{表\s*([A-Z]?\d+)")
#: 图环境
RE_FIGURE_BEGIN = re.compile(r"\\begin\{figure\}")
#: 公式编号
RE_TAG = re.compile(r"\\tag\{(\d+)\}")
#: 章节标题：编号写在标题文本里（"3.2 实验设计"），标题可能被 pandoc 折行
RE_SECTION = re.compile(r"\\(section|subsection|subsubsection)\{(\d+(?:\.\d+)*)([^}]*)\}", re.S)
#: 正文里的章节引用
RE_SECREF = re.compile(r"§\s*(\d+(?:\.\d+)*)")
#: 编号后跟这些字符时不是引用（"用户表 20 万行"）
QUANTIFIER = "0123456789万亿人行元个次张列条%位年月日"
RE_REF_TABLE = re.compile(r"(表)\s*([A-Z]?\d+)(?![" + QUANTIFIER + r"])")
RE_REF_FIG = re.compile(r"(图)\s*(\d+)(?![" + QUANTIFIER + r"])")
RE_REF_EQ = re.compile(r"(式)\s*\((\d+)\)")
#: 文献条目行首：pandoc 把 [1] 转义成 {[}1{]}（注意 [ 后面还有一个 }）
RE_REF_ENTRY = re.compile(r"^\{\[\}(\d+)\{\]\}")
#: 正文中的文献引用
RE_CITE = re.compile(r"\{\[\}(\d+)\{\]\}")


def process(text: str) -> tuple[str, dict[str, int]]:
    """返回 (改写后的文本, 统计)。"""
    stats = {"table": 0, "figure": 0, "equation": 0, "reference": 0,
             "section": 0, "ref": 0, "secref": 0}

    # ---- 第 0 遍：章节标题补 \label{sec:N.N}（跨行匹配，必须在拆行前做） ----
    def _seclabel(m: re.Match[str]) -> str:
        stats["section"] += 1
        return ("\\" + m.group(1) + "{" + m.group(2) + m.group(3) + "}"
                + "\\label{sec:" + m.group(2) + "}")

    text = RE_SECTION.sub(_seclabel, text)

    # ---- 第一遍：确定合法编号集合 ----
    valid_tab = set(re.findall(r"\\textbf\{表\s*([A-Z]?\d+)", text))
    valid_fig = set(range(1, len(re.findall(r"\\begin\{figure\}", text)) + 1))
    valid_eq = {int(n) for n in re.findall(r"\\tag\{(\d+)\}", text)}
    valid_ref = {int(n) for n in re.findall(r"(?m)^\{\[\}(\d+)\{\]\}", text)}
    valid_sec = set(re.findall(r"\\label\{sec:([\d.]+)\}", text))

    out: list[str] = []
    fig_no = 0

    # ---- 第二遍：逐行改写 ----
    for line in text.splitlines():
        # ① 公式：补 label
        def _tag(m: re.Match[str]) -> str:
            g = m.group(1)
            stats["equation"] += 1
            return "\\tag{" + g + "}\\label{eq:" + g + "}"

        line = RE_TAG.sub(_tag, line)

        # ② 图：在 \begin{figure} 前加锚点
        if RE_FIGURE_BEGIN.search(line):
            fig_no += 1
            stats["figure"] += 1
            # 图 1（技术路线图）允许就地或页底：只见 [t] 时它会一直占着页顶，
            # 把 §1.3 之后的内容顶到下一页，页底留下近 20% 空白（审稿意见 S1）。
            if fig_no == 1:
                line = line.replace("\\begin{figure}", "\\begin{figure}[htbp]", 1)
            line = "\\phantomsection\\label{fig:" + str(fig_no) + "}\n" + line

        is_caption = bool(RE_TABLE_CAPTION.search(line))
        m_entry = RE_REF_ENTRY.match(line)
        is_ref_entry = bool(m_entry) and int(m_entry.group(1)) in valid_ref

        # ③ 表格题注：加锚点
        if is_caption:
            def _cap(m: re.Match[str]) -> str:
                n = m.group(1)
                stats["table"] += 1
                return ("\\phantomsection\\label{tab:" + n + "}"
                        "\\textbf{表 " + n)

            line = RE_TABLE_CAPTION.sub(_cap, line, count=1)
        # ④ 文献条目：加锚点
        elif is_ref_entry:
            n = m_entry.group(1)
            stats["reference"] += 1
            line = "\\phantomsection\\label{ref:" + n + "}" + line

        # ⑤ 正文引用 → 链接
        if not is_caption and not is_ref_entry:
            def _ref(m: re.Match[str]) -> str:
                k = m.group(2)
                if k not in valid_tab:
                    return m.group(0)
                stats["ref"] += 1
                return "\\hyperref[tab:" + k + "]{表 " + k + "}"

            def _reffig(m: re.Match[str]) -> str:
                k = int(m.group(2))
                if k not in valid_fig:
                    return m.group(0)
                stats["ref"] += 1
                return "\\hyperref[fig:" + str(k) + "]{图 " + str(k) + "}"

            def _refeq(m: re.Match[str]) -> str:
                k = int(m.group(2))
                if k not in valid_eq:
                    return m.group(0)
                stats["ref"] += 1
                return "\\hyperref[eq:" + str(k) + "]{式(" + str(k) + ")}"

            def _cite(m: re.Match[str]) -> str:
                k = int(m.group(1))
                if k not in valid_ref:
                    return m.group(0)
                stats["ref"] += 1
                # pandoc 把 [10] 写成 {[}10{]}，其中 '{' 会提前闭合 \hyperref 的参数，
                # 于是只有 "[" 进入链接、变蓝的也只有一个字符。必须再包一层大括号。
                return ("\\hyperref[ref:" + str(k) + "]{{[}" + str(k) + "{]}}")

            def _refsec(m: re.Match[str]) -> str:
                k = m.group(1)
                if k not in valid_sec:
                    return m.group(0)
                stats["secref"] += 1
                return "\\hyperref[sec:" + k + "]{§" + k + "}"

            line = RE_REF_TABLE.sub(_ref, line)
            line = RE_REF_FIG.sub(_reffig, line)
            line = RE_REF_EQ.sub(_refeq, line)
            line = RE_CITE.sub(_cite, line)
            line = RE_SECREF.sub(_refsec, line)

        out.append(line)

    return "\n".join(out) + "\n", stats


def main(argv: list[str]) -> int:
    path = Path(argv[1] if len(argv) > 1 else "paper/body.tex")
    if not path.exists():
        print("[xref] 找不到 " + str(path), file=sys.stderr)
        return 1
    raw = path.read_text(encoding="utf-8")
    new, stats = process(raw)
    path.write_text(new, encoding="utf-8")
    print("[xref] 锚点：表 " + str(stats["table"])
          + " / 图 " + str(stats["figure"])
          + " / 公式 " + str(stats["equation"])
          + " / 文献 " + str(stats["reference"])
          + " / 章节 " + str(stats["section"])
          + "；正文引用链接 " + str(stats["ref"])
          + " 处（其中章节 § " + str(stats["secref"]) + " 处）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
