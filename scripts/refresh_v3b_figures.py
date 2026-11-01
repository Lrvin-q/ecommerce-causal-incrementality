"""重绘论文配图（合成数据 / 已知 DGP）。

2026-11-01：图 1 参考 HITL/技术路线图_可编辑.pptx 的六阶段布局；
图 2、3 原生绘制，其余图复用原脚本的数据读取与统计结果，只调整视觉表现。
运行：项目虚拟环境 python scripts/refresh_v3b_figures.py。
源表只读；不训练、不重算实验；PNG 与矢量 PDF/SVG 同步导出。
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.colors import to_rgba, to_hex
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch
from matplotlib.text import Text

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from causal_growth import viz

OUT = ROOT / "outputs/figures/v3b"
PAPER = ROOT / "paper/v3b/figures"
AUDIT = ROOT / "outputs/tables/v3b_figure_refresh.json"
BLUE, GREEN, ORANGE, RED, PURPLE = "#1E88E5", "#2E7D32", "#FB8C00", "#E53935", "#6A1B9A"
INK, GREY = "#263238", "#757575"
RECORDS: list[dict] = []
CHECKS: list[tuple[plt.Axes, Text, tuple[float, float, float, float]]] = []


def configure() -> None:
    """沿用 v2 的微软雅黑、固定配色、细网格与最终尺寸字号。"""
    viz.apply_style()
    plt.rcParams.update({"font.size": 8, "axes.titlesize": 9,
                        "axes.labelsize": 8, "xtick.labelsize": 7,
                        "ytick.labelsize": 7, "legend.fontsize": 7,
                        "axes.linewidth": .7, "grid.alpha": .25,
                        "lines.linewidth": 1.3, "pdf.fonttype": 42,
                        "ps.fonttype": 42, "svg.fonttype": "none",
                        "mathtext.fontset": "stix", "mathtext.default": "it"})


def card(ax: plt.Axes, x: float, y: float, w: float, h: float,
         title: str, body: str = "", color: str = BLUE,
         *, title_size: float = 8.5, body_size: float = 7.3,
         dashed: bool = False) -> None:
    """绘制按最终版心设计的模块，并登记文字必须留在框内的断言。"""
    patch = FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.004,rounding_size=.009",
                          edgecolor=color, facecolor=to_rgba(color, .065),
                          linewidth=.85, linestyle="--" if dashed else "-", zorder=2)
    ax.add_patch(patch)
    ty = y + h * (.73 if body else .5)
    t = ax.text(x+w/2, ty, title, ha="center", va="center", fontsize=title_size,
                color=color, fontweight="bold", zorder=3)
    CHECKS.append((ax, t, (x, y, w, h)))
    if body:
        t = ax.text(x+w/2, y+h*.32, body, ha="center", va="center", fontsize=body_size,
                    color=INK, linespacing=1.55, zorder=3)
        CHECKS.append((ax, t, (x, y, w, h)))


def arrow(ax: plt.Axes, start: tuple, end: tuple, *, dashed: bool = False,
          color: str = GREY) -> None:
    ax.add_patch(FancyArrowPatch(start, end, arrowstyle="-|>", mutation_scale=8,
                                color=color, linewidth=.85, linestyle="--" if dashed else "-",
                                shrinkA=2, shrinkB=2, zorder=1))


def canvas(height: float) -> tuple:
    fig = plt.figure(figsize=(7.2, height))
    ax = fig.add_axes([.015, .015, .97, .97])
    ax.set(xlim=(0, 1), ylim=(0, 1)); ax.axis("off")
    return fig, ax


def roadmap() -> None:
    """按参考 PPTX 的业务、模拟、数据、因果、策略、验证六行重建路线。"""
    fig, ax = canvas(7.1)
    stages = [("01", "业务定义", .918, GREY), ("02", "模拟机制", .787, BLUE),
              ("03", "数据构建", .624, PURPLE), ("04", "因果分析", .437, GREEN),
              ("05", "策略决策", .254, ORANGE), ("06", "验证与交付", .093, RED)]
    for num, label, y, color in stages:
        ax.text(.045, y+.02, num, ha="center", va="center", fontsize=10,
                fontweight="bold", color=color,
                bbox=dict(boxstyle="circle,pad=.28", fc=to_rgba(color,.10), ec="none"))
        ax.text(.045, y-.03, label, ha="center", va="center", fontsize=7.1, color=INK)
    x, w = .125, .855
    card(ax,x,.877,w,.094,"预算约束下最大化净增量贡献利润",
         "全部分配用户 · 7 天购买 / 30 天利润 · 保留退款 · 券成本只扣一次",GREY)
    # 潜在响应和分配机制是并列机制，不能画成结果决定分配的因果箭头。
    for xx, title in zip([.125,.345,.565,.785],
                         [r"用户特征 $X$", r"潜在响应 $p_0(X),p_1(X)$", r"处理分配 $T$", "订单与金额链路"]):
        card(ax,xx,.786,.195,.054,title,color=BLUE,title_size=7.8)
    ax.text(.552,.755,"L0 基线校准   ·   L1 金额与异质性   ·   L2 时间漂移   ·   L3 选择与混淆",
            ha="center",fontsize=7.1,color=INK)
    arrow(ax,(.552,.877),(.552,.845))
    card(ax,.125,.578,.61,.126,"可观测数据：五张关系表",
         "用户 · 曝光 · 订单 · 退款明细 · 成本\n污染与清洗 → SQL 双窗口核算 → 训练 / 验证 / 测试",PURPLE)
    card(ax,.765,.578,.215,.126,"真值库（封存）",
         "解析 ATE / CATE\n只用于最终审计",PURPLE,dashed=True,title_size=7.8)
    arrow(ax,(.43,.745),(.43,.708));arrow(ax,(.87,.745),(.87,.708),dashed=True,color=PURPLE)
    specs = [(.125,.264,"随机实验评估","样本量 · AA / SRM\n均值差与置信区间\n退款护栏 · 多重比较",GREEN),
             (.418,.317,"异质性效应学习","常数 / T / S / DR / 因果森林\n仅用观测数据选模\n输出预期增量利润",GREEN),
             (.765,.215,"观察性因果","Naive / PSM / IPW / DR\n选择偏差与混淆扫描\n重叠与平衡诊断",ORANGE)]
    for xx,ww,title,body,col in specs:
        card(ax,xx,.389,ww,.133,title,body,col,title_size=8.0,body_size=7.0)
    # 三条分析支路均来自可观测数据；真值库不向学习模块出箭头。
    ax.plot([.43,.43],[.578,.55],color=GREY,lw=.85,zorder=1)
    ax.plot([.257,.872],[.55,.55],color=GREY,lw=.85,zorder=1)
    for cx in [.257,.576,.872]:
        arrow(ax,(cx,.55),(cx,.526))
    card(ax,.125,.216,.61,.116,"预算约束下的定向发券",
         "预期增量利润 + 预测核销成本 → 名单与预算\n同预算比较规则 / 随机 / 贪心；小规模精确解与上界核验",ORANGE)
    card(ax,.765,.216,.215,.116,"识别边界",
         "选择 / 混淆 / 漂移\n结论失效条件",ORANGE,title_size=8.0)
    arrow(ax,(.43,.389),(.43,.337));arrow(ax,(.872,.389),(.872,.337))
    card(ax,x,.05,w,.111,"独立测试、随机验证与真值审计",
         "效应精度 / 排序质量 · 策略价值 / regret · 预算与退款护栏\n固定策略与重训重采样 → 收益、风险与适用条件",RED)
    arrow(ax,(.43,.216),(.43,.166));arrow(ax,(.872,.216),(.872,.166))
    # 参考 PPTX 中的虚线真值审计通道：绕行所有学习与选模模块。
    ax.plot([.993,.993],[.11,.64],ls="--",lw=.85,color=PURPLE,zorder=1)
    ax.plot([.981,.993],[.64,.64],ls="--",lw=.85,color=PURPLE,zorder=1)
    arrow(ax,(.993,.11),(.982,.11),dashed=True,color=PURPLE)
    ax.text(.552,.012,"实线：观测分析流程    虚线：封存真值的审计通道（不进入训练与选模）",
            ha="center",fontsize=7,color=INK)
    save(fig,"fig1_roadmap",diagram=True)


def layers() -> None:
    """用平行机制卡片区分随机分配三层和 L3 选择机制。"""
    fig, ax = canvas(3.45)
    cards=[("L0","基线校准","随机分配\n同质效应与成本","估计量是否准确",BLUE),
           ("L1","金额与异质性","首单 / 核销 / 复购\n效应随特征变化","平均与个体能否一致",GREEN),
           ("L2","时间与人群","分周投放与漂移\n人群构成变化","结论是否依赖窗口",ORANGE),
           ("L3","选择与混淆","基于特征的选择\n另作未观测混淆扫描","偏差来自哪里",PURPLE)]
    for i,(tag,title,body,question,color) in enumerate(cards):
        xx=.018+i*.25
        card(ax,xx,.33,.213,.57,tag+"\n"+title,body,color,title_size=9,body_size=8)
        ax.text(xx+.1065,.24,question,ha="center",fontsize=7.4,color=color,fontweight="bold")
    ax.plot([.03,.72],[.13,.13],color=BLUE,lw=1)
    ax.text(.375,.035,"L0–L2：随机分配场景",ha="center",fontsize=7.5,color=BLUE)
    ax.plot([.78,.97],[.13,.13],color=PURPLE,lw=1)
    ax.text(.875,.035,"L3：观察性场景",ha="center",fontsize=7.5,color=PURPLE)
    save(fig,"fig2_layer_mechanisms",diagram=True)


def money() -> None:
    """重建条件分支链路，避免把核销、退款、复购画成必经顺序。"""
    fig, ax = canvas(4.75)
    ax.text(.02,.965,"(a) 首单、核销与复购",fontsize=9,fontweight="bold",color=INK)
    card(ax,.025,.73,.235,.16,r"购物车金额 $V$", "首单金额不超过购物车",BLUE)
    card(ax,.36,.73,.26,.16,r"已支付首单 $G_1$", "$G_1=\\lfloor QV\\rfloor$\n以分计，下取整",BLUE)
    card(ax,.72,.73,.255,.16,r"复购订单 $G_2$", "首单支付后可能发生\n复购不带券",GREEN)
    arrow(ax,(.26,.81),(.36,.81));arrow(ax,(.62,.81),(.72,.81))
    card(ax,.36,.48,.26,.15,"首单核销", "发券且支付才可能核销\n抵扣不超过首单金额",ORANGE)
    arrow(ax,(.49,.73),(.49,.63),color=ORANGE)
    card(ax,.72,.48,.255,.15,"退款处理", "首单与复购均可能退款\n保留订单与用户",RED)
    arrow(ax,(.845,.73),(.845,.63),color=RED)
    ax.plot([.65,.65,.845],[.81,.675,.675],color=RED,lw=.85)
    arrow(ax,(.845,.675),(.845,.63),color=RED)
    ax.text(.02,.39,"(b) 30 天净贡献利润的组成",fontsize=9,fontweight="bold",color=INK)
    accounting=[("支付收入", "扣除退款",BLUE), ("商品成本", "减去回收",GREEN),
                ("履约成本", "已发生不回收",GREY), ("券成本", "首单一次扣除",ORANGE),
                ("退款手续费", "另计成本",RED)]
    for i,(title,body,color) in enumerate(accounting):
        xx=.025+i*.197
        card(ax,xx,.18,.164,.15,title,body,color,title_size=8,body_size=7)
        if i<4:ax.text(xx+.18,.25,"−",ha="center",va="center",fontsize=12,color=INK)
    ax.text(.5,.07,"按全部分配用户汇总；预算限制资源使用，策略价值不再次扣除券成本",
            ha="center",fontsize=7.4,color=INK)
    save(fig,"fig3_money_chain",diagram=True)


TITLES = {
"fig4_aa_calibration":["(a) 利润假阳性率与精确区间","(b) 三指标的假阳性率","(c) 标准误校准比","(d) 负对照的拒绝率"],
"fig5_mde_power":["(a) 固定样本的检测能力","(b) 局部功效验证","(c) 样本规模与利润 MDE"],
"fig6_four_layer_ate":["(a) 核心格均值与 MC 区间","(b) 核心格读数 / L0 读数","(c) 标准差与 MC 标准误"],
"fig7_mechanism_knobs":["(a) 处理侧混淆扫描","(b) 联合放大两侧混淆","(c) 重叠与缺失压力测试","(d) 异质性与成本设定"],
"fig8_model_comparison":["(a) 模型被选中的次数","(b) 模型名次与入选比例","(c) 因果森林：定向 − 规则"],
"fig9_budget_regimes":["(a) 策略价值与支出效率","(b) 预算口径与入选人数","(c) 预算口径与策略价值"],
"fig10_solvers":["(a) 候选规模与求解时间","(b) 成本桶宽与预测价值"],
"fig11_refund_guardrail":["(a) 全员发券的退款率差","(b) 定向发券的单侧上界","(c) 预算与退款率差"],
"fig12_ope_cost":["(a) 离策略估计的审计误差","(b) 成本预测的十分位校准","(c) 实际支出 / 预测支出"],
"fig13_bootstrap":["(a) 固定策略：重抽用户","(b) 重新训练：重抽总体"],
"fig15_effect_sweep":["(a) 净增量利润：均值锚点近似","(b) 券成本：逐用户解析扫描"]}
LABELS={"causal_forest":"因果森林", "constant":"常数", "dr_learner":"DR", "s_learner":"S", "t_learner":"T",
        "greedy":"贪心", "greedy_local_swap":"贪心＋交换", "dp_restricted":"局部背包", "scipy_milp":"整数规划",
        "ratio_bucket_milp":"比值分桶", "cost_bucket_dp":"成本分桶", "lp_relaxation":"LP 松弛",
        "greedy_proxy_netipw":"IPW", "greedy_proxy_draipw":"DR", "greedy_proxy_naive":"均值差",
        "greedy_proxy_truncated_ipw":"截断 IPW", "greedy_proxy_unadjusted":"均值差",
        "targeted":"定向", "random_same_budget":"同预算随机",
        "no_coupon":"不发券", "greedy_increment":"增量贪心",
        "greedy_incremental_profit_per_cost":"增量贪心",
        "time_limited_milp":"限时整数规划", "bucket_dp":"分桶背包", "cent_exact_dp":"分币精确背包",
        "利润（左轴，元/人）":"利润（左轴）", "购买率（右轴，百分点）":"购买率（右轴）"}


def translate(text: str) -> str:
    return LABELS.get(text,text)


def signature(fig: plt.Figure) -> str:
    """记录数据图元，保证改排版前后没有改变线、散点与柱子的数值。"""
    data=[]
    for ax in fig.axes:
        data.append({"lines":[np.asarray(l.get_xydata()).tolist() for l in ax.lines],
                     "collections":[np.asarray(c.get_offsets()).tolist() for c in ax.collections],
                     "bars":[[p.get_x(),p.get_y(),p.get_width(),p.get_height()]
                             for p in ax.patches if hasattr(p,'get_height')]})
    return hashlib.sha256(json.dumps(data,sort_keys=True,allow_nan=True,
                                     default=lambda x:x.item()).encode()).hexdigest()


def style_result(fig: plt.Figure, name: str) -> None:
    """按最终印刷尺寸统一组图；外置图例避免遮挡数据。"""
    main=[ax for ax in fig.axes if ax.get_title()]
    rows=2 if len(main)==4 else 1
    fig.set_size_inches(7.2,4.8 if rows==2 else 2.65,forward=True)
    if fig._suptitle:fig._suptitle.set_visible(False)
    for text in fig.texts:text.set_visible(False)
    for ax in fig.axes:
        for side in ("top","right"):ax.spines[side].set_visible(False)
        ax.tick_params(labelsize=7,length=3,width=.6)
        ax.xaxis.label.set_size(8);ax.yaxis.label.set_size(8)
        ax.grid(True,alpha=.23,ls="--",lw=.6)
        for t in ax.texts:
            t.set_fontsize(6.8);t.set_text(translate(t.get_text()))
        for line in ax.lines:
            line.set_linewidth(min(line.get_linewidth(),1.5))
            line.set_markersize(min(line.get_markersize(),4))
        if ax not in main:ax.grid(False)
        # 与 v2 METHOD_COLORS / STRATEGY_COLORS 同源的色彩映射。
        palette={'#2c3e50':'#0D47A1','#c0392b':RED,'#2980b9':BLUE,
                 '#27ae60':GREEN,'#8e44ad':PURPLE,'#95a5a6':GREY}
        for artist in [*ax.lines,*ax.patches,*ax.collections,*ax.texts]:
            for get,setter in [('get_color','set_color'),('get_facecolor','set_facecolor'),('get_edgecolor','set_edgecolor')]:
                if not hasattr(artist,get) or not hasattr(artist,setter):continue
                value=getattr(artist,get)()
                try:
                    hex_color=to_hex(value)
                except (ValueError,TypeError):
                    continue
                if hex_color in palette:getattr(artist,setter)(palette[hex_color])
    for i,ax in enumerate(main):
        ax.set_title(TITLES[name][i],fontsize=8.7,pad=8,loc="center")
        # 模型名使用短标签，避免英文长词伸出相邻面板。
        for tick in ax.get_yticklabels():tick.set_text(translate(tick.get_text()))
        if name=="fig8_model_comparison" and i==0:
            ax.set_yticks(ax.get_yticks(),[translate(t.get_text()) for t in ax.get_yticklabels()])
        leg=ax.get_legend()
        if leg:
            handles=list(leg.legend_handles);labels=[translate(t.get_text()) for t in leg.get_texts()]
            for handle in handles:
                for get,setter in [('get_color','set_color'),('get_facecolor','set_facecolor')]:
                    if not hasattr(handle,get) or not hasattr(handle,setter):continue
                    try:old=to_hex(getattr(handle,get)())
                    except (ValueError,TypeError):continue
                    if old in palette:getattr(handle,setter)(palette[old])
            leg.remove()
            ncol=2 if len(labels)>1 else 1
            ax.legend(handles,labels,loc="upper center",bbox_to_anchor=(.5,-.29),
                      ncol=ncol,fontsize=6.6,frameon=False,handlelength=1.35,
                      columnspacing=.8,handletextpad=.4,labelspacing=.45,borderaxespad=0)
        ax.margins(y=.14)
    # 原始长注释/刻度的定向修复：保留数字、单位与统计口径。
    if name=="fig4_aa_calibration":
        main[3].set_xticks(range(3),["购买率\n零效应", "退款率\n非零效应", "利润\n非零效应"],fontsize=7)
    if name=="fig5_mde_power":
        main[0].set_ylabel("利润 MDE（元/人）",fontsize=7.3)
        fig.axes[3].yaxis.label.set_fontsize(7.3)
    if name=="fig8_model_comparison":
        ax=main[1]
        offsets={"causal_forest":(-3,-13),"constant":(-8,8),"dr_learner":(-17,-13),
                 "s_learner":(-12,8),"t_learner":(-7,-13)}
        for t in ax.texts:
            key=next((k for k,v in LABELS.items() if v==t.get_text()),"")
            if key in offsets:t.set_position(offsets[key]);t.set_ha("center")
        ax.set_xlim(.7,4.9);ax.set_ylim(-.045,.62)
        main[0].set_xlim(0,150)
        main[2].margins(x=.14,y=.25)
        for t,offset in zip(main[2].texts,[(-3,10),(-8,-14),(-9,10),(-9,-13),(12,-18),(2,10),(-9,11),(4,-14)]):
            t.set_position(offset)
    if name=="fig13_bootstrap":
        for ax in main:
            ax.set_yticks(ax.get_yticks(),["L0","L1","L2","L3"],fontsize=7)
        main[0].set_xlim(-.14,.38)
    if name=="fig10_solvers":main[1].set_xlabel("成本桶宽（元）")
    fig.set_layout_engine("constrained",h_pad=.08,w_pad=.04,hspace=.16,wspace=.14)


def save(fig: plt.Figure, name: str, *, diagram: bool = False, note: str = "") -> None:
    """导出三种格式并做框内文字与画布边界检查。"""
    before=signature(fig)
    if not diagram:style_result(fig,name)
    fig.canvas.draw()
    renderer=fig.canvas.get_renderer()
    errors=[]
    for ax,t,(x,y,w,h) in CHECKS:
        if ax.figure is not fig:continue
        bb=t.get_window_extent(renderer);p0=ax.transData.transform((x,y));p1=ax.transData.transform((x+w,y+h))
        if bb.x0<p0[0]-1 or bb.y0<p0[1]-1 or bb.x1>p1[0]+1 or bb.y1>p1[1]+1:
            errors.append('框内文字溢出：'+t.get_text())
    if before!=signature(fig):raise AssertionError('排版改变了数据图元：'+name)
    if errors:raise ValueError(name+': '+str(errors))
    issues=[] if diagram else load('08_check_figures.py').check_figure(fig,name)
    if any(item['level']=='error' for item in issues):raise ValueError(str(issues))
    files={}
    for ext in ("png","pdf","svg"):
        if ext=='png':
            p=viz.save_fig(fig,name,subdir='v3b',dpi=600,close=False)
        else:
            p=OUT/f'{name}.{ext}'
            fig.savefig(p,bbox_inches='tight',facecolor='white')
        shutil.copy2(p,PAPER/p.name)
        files[ext]={"sha256":hashlib.sha256(p.read_bytes()).hexdigest(),"bytes":p.stat().st_size}
    RECORDS.append({"figure":name,"files":files,"data_artist_sha256":before,
                    "source_note":note,"diagram_text_containment_errors":errors,"layout_issues":issues,
                    "width_in":fig.get_figwidth(),"height_in":fig.get_figheight()})
    plt.close(fig);print('saved',name,flush=True)


def load(filename: str):
    spec=importlib.util.spec_from_file_location(filename.replace('.','_'),ROOT/'scripts'/filename)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def results() -> None:
    """调用原始数据绘图函数，统一由本入口完成排版与三格式输出。"""
    for filename,functions in [
        ('50_v3b_figures.py',['fig4_aa','fig6_four_layers','fig7_knobs']),
        ('53_v3b_figures_batch2.py',['fig5_mde_power','fig8_model_comparison','fig11_guardrail','fig13_bootstrap']),
        ('54_v3b_figures_batch3.py',['fig9_budget','fig10_solvers','fig12_ope'])]:
        module=load(filename)
        module._finish=lambda fig,name,note,caption:save(fig,name,note=note)
        for fn in functions:getattr(module,fn)()
    # 盈亏平衡图只读取已保存扫描表，绝不重新运行 56 号脚本的 DGP 重算。
    d=pd.read_csv(ROOT/'outputs/tables/v3b_effect_anchor_plot.csv')
    be=float(np.interp(0,d.mean_anchor_ate,d.dp_pp))
    fig,axes=plt.subplots(1,2)
    ax=axes[0];ax.plot(d.dp_pp,d.mean_anchor_ate,color=BLUE,label="净增量利润")
    ax.axhline(0,color=GREY,ls='--',lw=.8)
    ax.axvline(be,color=RED,ls=':',label=f'盈亏平衡 {be:.2f} pp')
    ax.axvline(5,color=GREEN,ls='--',label='设计效应 5 pp')
    ax.set(xlabel='购买率增量（百分点）',ylabel='净增量利润（元/人）',title='a');ax.legend()
    ax=axes[1];ax.plot(d.dp_pp,d.coupon_cost,color=ORANGE)
    ax.set(xlabel='购买率增量（百分点）',ylabel='券成本（元/人）',title='b')
    save(fig,'fig15_effect_sweep',note='(a) 按正文两锚点近似，源于 L1 解析真值与券成本；(b) 原有 4 万人逐用户解析扫描。二者不混为同一设定；不新增抽样')


def main() -> None:
    """全量重绘并确保结果表逐字节不变。"""
    for d in (OUT,PAPER):d.mkdir(parents=True,exist_ok=True)
    sweep=pd.read_csv(ROOT/'outputs/tables/v3_paper_effect_sweep.csv')
    truth=pd.read_csv(ROOT/'outputs/tables/v3_paper_truth_core.csv')
    anchor=float(truth.loc[(truth.level=='L1')&(truth.metric=='ate'),'truth'].item())
    cost=float(sweep.loc[sweep.dp_pp==0,'coupon_cost'].item())
    design=float(sweep.dp_design_pp.iloc[0])
    sweep['mean_anchor_ate']=-cost+(anchor+cost)*sweep.dp_pp/design
    sweep['mean_anchor_cost']=cost;sweep['mean_anchor_design_ate']=anchor
    sweep.to_csv(ROOT/'outputs/tables/v3b_effect_anchor_plot.csv',index=False,encoding='utf-8-sig')
    source={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()
            for p in (ROOT/'outputs/tables').glob('*.csv')}
    configure();roadmap();layers();money();results()
    # 图号取正文实际出现顺序，避免文件编号（如 fig15）冒充论文图号。
    caption_map={}
    for part in sorted((ROOT/'paper/v3b/body').glob('*.md')):
        for caption,filename in re.findall(r'!\[([^\]]+)\]\(figures/([^\)]+)\)',part.read_text(encoding='utf-8')):
            caption_map[Path(filename).with_suffix('.png').name]=f'图 {len(caption_map)+1}　{caption}'
    (PAPER/'_captions.json').write_text(json.dumps(caption_map,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    (PAPER/'_captions.md').write_text('\n\n'.join(f'**{k}**\n\n{v}' for k,v in caption_map.items())+'\n',encoding='utf-8')
    for name,digest in source.items():
        if hashlib.sha256((ROOT/name).read_bytes()).hexdigest()!=digest:raise AssertionError('源表被改写：'+name)
    AUDIT.write_text(json.dumps({"source_label":"合成数据 / 已知 DGP",
        "maintained_at":datetime.now(ZoneInfo('Asia/Shanghai')).strftime('%Y-%m-%d %H:%M'),
        "timezone":"Asia/Shanghai","reference":"HITL/技术路线图_可编辑.pptx",
        "reference_sha256":hashlib.sha256((ROOT/'HITL/技术路线图_可编辑.pptx').read_bytes()).hexdigest(),
        "source_csv_sha256":source,"figures":RECORDS},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


if __name__=='__main__':main()
