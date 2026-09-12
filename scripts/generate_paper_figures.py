"""Generate the paper-ready Q2--Q4 figures from persisted experiment outputs.

This script is intentionally read-only with respect to model outputs and the
formal Excel workbooks.  Its only write target is ``target/paper_figures``.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import tempfile
import warnings

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / "target" / "paper_figures"
OPTIONAL_DIR = OUTPUT_DIR / "optional"
os.environ.setdefault("MPLCONFIGDIR", str(ROOT / "tmp" / "matplotlib"))

import matplotlib  # noqa: E402

matplotlib.use("Agg")
from matplotlib import font_manager, pyplot as plt  # noqa: E402
from matplotlib.patches import Patch  # noqa: E402


COLORS = {
    "navy": "#263B62",
    "blue": "#27649B",
    "teal": "#168C91",
    "orange": "#DC8526",
    "gold": "#D4A72C",
    "purple": "#76549B",
    "red": "#B34C4C",
    "slate": "#8192AD",
    "gray": "#747B83",
    "light": "#DCE3E8",
}

FIGURE_INFO = {
    "q2_ablation_cost": {
        "sources": "target/question2/ablation_summary.csv",
        "conclusion": "A7 将总费用由 1760.98 万元降至 1468.93 万元，节省 16.58%。",
        "caption": "问题2消融实验的计划购电费与紧急购电费构成。A7（残差加权场景与因果滚动执行）取得最低总费用。",
        "section": "问题2：模型优化与消融实验",
        "placement": "正文",
    },
    "q2_monthly_baseline_vs_a7": {
        "sources": "target/question2/baseline_daily_metrics.csv；target/question2/residual_weighted_causal_daily_metrics.csv",
        "conclusion": "A7 的全年节省同时来自计划购电费和高惩罚紧急购电费的下降。",
        "caption": "基线 A0 与优化策略 A7 的月度费用构成对比，费用均按计划购电与紧急购电分解。",
        "section": "问题2：优化效果的时间分解",
        "placement": "正文",
    },
    "q2_scenario_calibration": {
        "sources": "target/question2/baseline_daily_metrics.csv；target/question2/residual_weighted_causal_daily_metrics.csv",
        "conclusion": "残差加权场景显著修正均值偏差，并使全年 P80 覆盖率接近 0.80。",
        "caption": "基线与 A7 场景校准对比：上图为14日滚动均值偏差，下图为月均 P80 覆盖率。",
        "section": "问题2：不确定性场景校准",
        "placement": "正文",
    },
    "q3_model_ablation": {
        "sources": "target/question3/model_ablation_summary.csv",
        "conclusion": "残差场景与因果储能均有收益，二者联合时总费用最低（1464.17万元）。",
        "caption": "问题3四种场景生成与储能执行组合的总费用和紧急购电量对比。",
        "section": "问题3：模型机制消融",
        "placement": "正文",
    },
    "q3_update_policy": {
        "sources": "target/question3/ablation_summary.csv",
        "conclusion": "0、6、12点更新组合最优；增加18点更新反而使总费用小幅上升约0.12万元。",
        "caption": "不同时刻更新组合下的全年总费用与紧急购电量，青色柱为选定策略0+6+12。",
        "section": "问题3：更新时间选择",
        "placement": "正文",
    },
    "q3_forecast_accuracy": {
        "sources": "target/question3/forecast_accuracy.csv",
        "conclusion": "越接近运行时刻，光伏预报误差总体越低；统一18—24点时域下各版本差异较小。",
        "caption": "0、6、12、18点发布预报的 MAE 与 RMSE；右图控制为共同的18—24点评价时域。",
        "section": "问题3：预报误差分析",
        "placement": "附录（正文可引用）",
    },
    "q3_dispatch_2025-12-21": {
        "sources": "target/question3/daily_results.jsonl",
        "conclusion": "6点和12点滚动更新改变后续合同，储能按因果信息执行且 SOC 始终满足边界。",
        "caption": "2025年12月21日问题3典型日：净负荷、初始/最终合同、合同调整、储能功率及 SOC。",
        "section": "问题3：典型日运行机理",
        "placement": "正文",
    },
    "q4_dynamic_prices": {
        "sources": "target/question4/question4_3/prices.json",
        "conclusion": "动态电价同时呈现稳定的日内峰谷与明显的跨日波动。",
        "caption": "2025年全年动态电价热力图，以及每日均价和日内最低—最高价区间。",
        "section": "问题4：动态电价特征",
        "placement": "正文",
    },
    "q4_fixed_dynamic_comparison": {
        "sources": "target/question4/question4_2/comparison.csv；target/question4/question4_3/comparison.csv",
        "conclusion": "动态电价下 Q4-2 与 Q4-3 总费用分别增加 3.92% 和 3.76%，紧急购电量略有下降。",
        "caption": "问题4两种计划机制在固定与动态电价下的总费用和紧急购电量对比。",
        "section": "问题4：固定—动态电价对比",
        "placement": "正文",
    },
    "q4_dispatch_2025-12-21": {
        "sources": "target/question4/question4_3/daily_results.jsonl；target/question4/question4_3/prices.json",
        "conclusion": "滚动合同与储能响应动态价格和最新负荷信息，SOC 全程满足约束。",
        "caption": "动态电价下2025年12月21日 Q4-3 典型日调度：价格、合同调整、储能与 SOC。",
        "section": "问题4：典型日调度",
        "placement": "正文",
    },
    "q2_surplus_emergency_tradeoff": {
        "sources": "target/question2/ablation_summary.csv",
        "conclusion": "各改进策略在富余电量、紧急购电量和总费用间形成清晰权衡，A7 综合表现最佳。",
        "caption": "问题2代表性策略的富余电量—紧急购电量权衡；点大小表示总费用。",
        "section": "问题2：稳健性与权衡",
        "placement": "附录",
    },
}


def configure_style() -> str:
    """Apply a restrained paper style with a non-fatal Chinese font fallback."""
    candidates = [
        "Microsoft YaHei",
        "SimHei",
        "Noto Sans CJK SC",
        "Source Han Sans SC",
        "SimSun",
    ]
    installed = {font.name for font in font_manager.fontManager.ttflist}
    selected = next((name for name in candidates if name in installed), "DejaVu Sans")
    if selected == "DejaVu Sans":
        warnings.warn("未找到常用中文字体，已回退到 DejaVu Sans；中文字符可能由系统替代字体渲染。")
    plt.rcParams.update(
        {
            "font.family": "sans-serif",
            "font.sans-serif": [selected, "DejaVu Sans"],
            "axes.unicode_minus": False,
            "font.size": 9.5,
            "axes.titlesize": 11,
            "axes.labelsize": 9.5,
            "legend.fontsize": 8.5,
            "xtick.labelsize": 8.5,
            "ytick.labelsize": 8.5,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.axisbelow": True,
            "grid.alpha": 0.22,
            "grid.linewidth": 0.6,
            "legend.frameon": False,
            "figure.facecolor": "white",
            "axes.facecolor": "white",
            "savefig.facecolor": "white",
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
        }
    )
    return selected


def save_pair(fig, name: str, directory: Path = OUTPUT_DIR) -> list[Path]:
    """Atomically save a 320-dpi PNG and a vector PDF, then close the figure."""
    directory.mkdir(parents=True, exist_ok=True)
    final_paths = [directory / f"{name}.png", directory / f"{name}.pdf"]
    staged: list[Path] = []
    try:
        for suffix in (".png", ".pdf"):
            with tempfile.NamedTemporaryFile(
                dir=directory, prefix=f".{name}.", suffix=suffix, delete=False
            ) as handle:
                staged_path = Path(handle.name)
            staged.append(staged_path)
            kwargs = {"bbox_inches": "tight", "facecolor": "white"}
            if suffix == ".png":
                kwargs["dpi"] = 320
            fig.savefig(staged_path, **kwargs)
        for source, target in zip(staged, final_paths):
            os.replace(source, target)
    finally:
        for path in staged:
            path.unlink(missing_ok=True)
        plt.close(fig)
    return final_paths


def _read_csv(relative: str) -> pd.DataFrame:
    path = ROOT / relative
    if not path.is_file():
        raise FileNotFoundError(f"缺少绘图数据：{path}")
    return pd.read_csv(path)


def _jsonl_day(relative: str, target_day: str) -> dict:
    path = ROOT / relative
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            row = json.loads(line)
            schedule = row.get("schedule", {})
            initial = schedule.get("initial_plan", {})
            if initial.get("date") == target_day:
                return row
    raise ValueError(f"{path} 中未找到日期 {target_day}")


def _time_axis(ax, xlabel: bool = False) -> None:
    ticks = np.arange(0, 145, 24)
    ax.set_xlim(0, 144)
    ax.set_xticks(ticks, ["0:00", "4:00", "8:00", "12:00", "16:00", "20:00", "24:00"])
    if xlabel:
        ax.set_xlabel("时刻（每个时段10分钟）")


def _revision_lines(axes, starts=(36, 72)) -> None:
    for ax in axes:
        for start in starts:
            ax.axvline(start, color=COLORS["gray"], linestyle=":", linewidth=0.9, zorder=0)


def _annotate_bars(ax, bars, fmt="{:.1f}", offset=3, fontsize=8.5) -> None:
    for bar in bars:
        height = bar.get_height()
        ax.annotate(
            fmt.format(height),
            (bar.get_x() + bar.get_width() / 2, height),
            xytext=(0, offset if height >= 0 else -offset - 8),
            textcoords="offset points",
            ha="center",
            va="bottom" if height >= 0 else "top",
            fontsize=fontsize,
        )


def validate_q2(df: pd.DataFrame) -> None:
    indexed = df.set_index("ablation")
    expected = {"A0": 17_609_791.6865, "A7": 14_689_283.3613, "A8": 16_136_652.5019}
    for key, value in expected.items():
        actual = float(indexed.loc[key, "total_cost"])
        if not np.isclose(actual, value, atol=0.02):
            raise ValueError(f"Q2 {key} 总费用异常：{actual} != {value}")


def plot_q2_ablation() -> str:
    data = _read_csv("target/question2/ablation_summary.csv")
    data = data[data["ablation"].isin([f"A{i}" for i in range(9)])].copy()
    data["order"] = data["ablation"].str[1:].astype(int)
    data.sort_values("order", inplace=True)
    validate_q2(data)

    descriptions = {
        "A0": "基线",
        "A1": "因果滚动",
        "A2": "工作日校正",
        "A3": "工作日+趋势",
        "A4": "加权组合",
        "A5": "残差等权",
        "A6": "趋势因果",
        "A7": "残差加权+因果",
        "A8": "网侧再优化",
    }
    labels = [f"{key}  {descriptions[key]}" for key in data["ablation"]]
    plan = data["planned_cost"].to_numpy() / 1e4
    emergency = data["emergency_cost"].to_numpy() / 1e4
    total = plan + emergency
    y = np.arange(len(data))

    fig, ax = plt.subplots(figsize=(9.2, 5.5), layout="constrained")
    bars_plan = ax.barh(y, plan, color=COLORS["teal"], height=0.68, label="计划购电费")
    bars_emergency = ax.barh(
        y, emergency, left=plan, color=COLORS["orange"], height=0.68, label="紧急购电费"
    )
    a7_index = int(np.flatnonzero(data["ablation"].to_numpy() == "A7")[0])
    for collection in (bars_plan, bars_emergency):
        collection[a7_index].set_edgecolor(COLORS["red"])
        collection[a7_index].set_linewidth(1.7)
    for i, value in enumerate(total):
        ax.text(value + 18, i, f"{value:.1f}", va="center", fontsize=8.5)
    ax.set_yticks(y, labels)
    ax.get_yticklabels()[a7_index].set_fontweight("bold")
    ax.invert_yaxis()
    ax.set_xlim(0, total.max() * 1.14)
    ax.set_xlabel("全年总费用（万元）")
    ax.set_title("问题2：A0—A8 消融实验费用构成")
    ax.grid(axis="x")
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.13), ncols=2)
    a0 = float(total[0])
    a7 = float(total[a7_index])
    ax.text(
        0.985,
        1.015,
        f"A7 相对 A0 节省 {a0-a7:.1f} 万元（{(a0-a7)/a0:.2%}）",
        transform=ax.transAxes,
        ha="right",
        va="bottom",
        color=COLORS["red"],
        fontsize=9,
        bbox={"facecolor": "white", "edgecolor": COLORS["light"], "boxstyle": "round,pad=0.35"},
    )
    save_pair(fig, "q2_ablation_cost")
    return "q2_ablation_cost"


def plot_q2_monthly() -> str:
    baseline = _read_csv("target/question2/baseline_daily_metrics.csv")
    a7 = _read_csv("target/question2/residual_weighted_causal_daily_metrics.csv")
    for frame in (baseline, a7):
        frame["date"] = pd.to_datetime(frame["date"])
        frame["month"] = frame["date"].dt.month
    fields = ["planned_cost", "emergency_cost"]
    base_month = baseline.groupby("month")[fields].sum().reindex(range(2, 13)) / 1e4
    a7_month = a7.groupby("month")[fields].sum().reindex(range(2, 13)) / 1e4
    months = np.arange(2, 13)
    x = np.arange(len(months))
    width = 0.36

    fig, ax = plt.subplots(figsize=(10.6, 5.4), layout="constrained")
    b1 = ax.bar(
        x - width / 2,
        base_month["planned_cost"],
        width,
        color=COLORS["teal"],
        alpha=0.58,
        hatch="///",
        edgecolor="white",
    )
    b2 = ax.bar(
        x - width / 2,
        base_month["emergency_cost"],
        width,
        bottom=base_month["planned_cost"],
        color=COLORS["orange"],
        alpha=0.58,
        hatch="///",
        edgecolor="white",
    )
    a1 = ax.bar(x + width / 2, a7_month["planned_cost"], width, color=COLORS["teal"])
    a2 = ax.bar(
        x + width / 2,
        a7_month["emergency_cost"],
        width,
        bottom=a7_month["planned_cost"],
        color=COLORS["orange"],
    )
    for bars, totals in (
        ((b1, b2), base_month.sum(axis=1).to_numpy()),
        ((a1, a2), a7_month.sum(axis=1).to_numpy()),
    ):
        top_bars = bars[1]
        for bar, value in zip(top_bars, totals):
            ax.annotate(
                f"{value:.0f}",
                (bar.get_x() + bar.get_width() / 2, value),
                xytext=(0, 3),
                textcoords="offset points",
                ha="center",
                fontsize=7.5,
            )
    handles = [
        Patch(facecolor=COLORS["teal"], label="计划购电费"),
        Patch(facecolor=COLORS["orange"], label="紧急购电费"),
        Patch(facecolor="white", edgecolor=COLORS["gray"], hatch="///", label="A0 基线"),
        Patch(facecolor=COLORS["gray"], label="A7 优化策略"),
    ]
    total_base = baseline["total_cost"].sum() / 1e4
    total_a7 = a7["total_cost"].sum() / 1e4
    ax.text(
        0.015,
        0.975,
        f"全年：{total_base:.1f} → {total_a7:.1f} 万元\n下降 {total_base-total_a7:.1f} 万元（{(total_base-total_a7)/total_base:.2%}）",
        transform=ax.transAxes,
        va="top",
        color=COLORS["red"],
        bbox={"facecolor": "white", "edgecolor": COLORS["light"], "boxstyle": "round,pad=0.35"},
    )
    ax.set_xticks(x, [f"{month}月" for month in months])
    ax.set_ylim(0, max(base_month.sum(axis=1).max(), a7_month.sum(axis=1).max()) * 1.27)
    ax.set_ylabel("月度费用（万元）")
    ax.set_title("问题2：基线 A0 与优化策略 A7 的月度费用对比")
    ax.grid(axis="y")
    ax.legend(handles=handles, ncols=4, loc="upper center")
    save_pair(fig, "q2_monthly_baseline_vs_a7")
    return "q2_monthly_baseline_vs_a7"


def plot_q2_calibration() -> str:
    baseline = _read_csv("target/question2/baseline_daily_metrics.csv")
    a7 = _read_csv("target/question2/residual_weighted_causal_daily_metrics.csv")
    for frame in (baseline, a7):
        frame["date"] = pd.to_datetime(frame["date"])
        frame.sort_values("date", inplace=True)
    fig, axes = plt.subplots(2, 1, figsize=(10.8, 7.2), layout="constrained")
    for frame, label, color in (
        (baseline, "A0 原始等权场景", COLORS["slate"]),
        (a7, "A7 残差加权场景", COLORS["teal"]),
    ):
        rolling = frame["scenario_mean_bias_kwh"].rolling(14, min_periods=1).mean() / 1e3
        axes[0].plot(frame["date"], rolling, label=label, color=color, linewidth=1.4)
    axes[0].axhline(0, color=COLORS["gray"], linewidth=0.8)
    axes[0].set_ylabel("均值偏差14日滚动平均（千kWh/日）")
    axes[0].set_title("场景日总负荷均值偏差（场景均值 − 实际值）")
    axes[0].legend(ncols=2)
    axes[0].grid(axis="y")

    months = np.arange(2, 13)
    x = np.arange(len(months))
    width = 0.36
    base_coverage = baseline.groupby(baseline["date"].dt.month)["scenario_p80_coverage"].mean().reindex(months)
    a7_coverage = a7.groupby(a7["date"].dt.month)["scenario_p80_coverage"].mean().reindex(months)
    axes[1].bar(x - width / 2, base_coverage, width, color=COLORS["slate"], label="A0")
    axes[1].bar(x + width / 2, a7_coverage, width, color=COLORS["teal"], label="A7")
    axes[1].axhline(0.80, color=COLORS["red"], linestyle="--", linewidth=1, label="目标覆盖率 0.80")
    axes[1].set_xticks(x, [f"{month}月" for month in months])
    axes[1].set_ylim(0, 1.03)
    axes[1].set_ylabel("月均 P80 时段覆盖率")
    axes[1].set_xlabel("月份（2025年）")
    axes[1].set_title("P80 场景覆盖实际净负荷的比例")
    axes[1].legend(ncols=3)
    axes[1].grid(axis="y")
    fig.suptitle("问题2：基线 A0 与优化策略 A7 的场景校准", fontsize=12.5)
    save_pair(fig, "q2_scenario_calibration")
    return "q2_scenario_calibration"


def plot_q2_tradeoff() -> str:
    data = _read_csv("target/question2/ablation_summary.csv")
    chosen = ["A0", "A1", "A2", "A5", "A7", "A8"]
    data = data.set_index("ablation").loc[chosen].reset_index()
    x = data["surplus_kwh"].to_numpy() / 1e4
    y = data["emergency_total"].to_numpy() / 1e4
    cost = data["total_cost"].to_numpy() / 1e4
    sizes = 80 + 240 * (cost - cost.min()) / max(np.ptp(cost), 1e-9)
    colors = [COLORS["teal"] if key == "A7" else COLORS["slate"] for key in chosen]
    fig, ax = plt.subplots(figsize=(7.4, 5.4), layout="constrained")
    ax.scatter(x, y, s=sizes, c=colors, alpha=0.85, edgecolors="white", linewidths=0.8)
    for key, xv, yv in zip(chosen, x, y):
        ax.annotate(key, (xv, yv), xytext=(5, 4), textcoords="offset points", fontsize=9)
    ax.set_xlabel("全年富余电量（万kWh）")
    ax.set_ylabel("全年紧急购电量（万kWh）")
    ax.set_title("问题2：代表性策略的富余—紧急购电权衡")
    ax.grid()
    ax.text(
        0.98,
        0.96,
        "点大小表示全年总费用\n青色为选定策略 A7",
        transform=ax.transAxes,
        ha="right",
        va="top",
        bbox={"facecolor": "white", "edgecolor": COLORS["light"], "boxstyle": "round,pad=0.35"},
    )
    save_pair(fig, "q2_surplus_emergency_tradeoff", OPTIONAL_DIR)
    return "q2_surplus_emergency_tradeoff"


def validate_q3(model: pd.DataFrame, policies: pd.DataFrame) -> None:
    expected = {
        "raw_frozen": 17_020_306.6465,
        "residual_frozen": 14_923_649.2865,
        "raw_causal": 16_709_370.6791,
        "residual_causal": 14_641_650.0549,
    }
    indexed = model.set_index("model")
    for key, value in expected.items():
        if not np.isclose(float(indexed.loc[key, "total_cost"]), value, atol=0.02):
            raise ValueError(f"Q3 {key} 总费用未通过校验")
    selected = policies.loc[policies["total_cost"].idxmin(), "policy"]
    if selected != "0+6+12":
        raise ValueError(f"Q3 最优更新时间策略异常：{selected}")


def plot_q3_model_ablation() -> str:
    data = _read_csv("target/question3/model_ablation_summary.csv")
    order = ["raw_frozen", "residual_frozen", "raw_causal", "residual_causal"]
    data = data.set_index("model").loc[order].reset_index()
    policies = _read_csv("target/question3/ablation_summary.csv")
    validate_q3(data, policies)
    labels = ["原始场景\n固定储能", "残差场景\n固定储能", "原始场景\n因果储能", "残差场景\n因果储能"]
    x = np.arange(4)
    colors = [COLORS["slate"], COLORS["slate"], COLORS["slate"], COLORS["teal"]]
    costs = data["total_cost"].to_numpy() / 1e4
    emergency = data["emergency_kwh"].to_numpy() / 1e4

    fig, axes = plt.subplots(2, 1, figsize=(9.2, 7.6), layout="constrained")
    bars = axes[0].bar(x, costs, color=colors, width=0.62)
    _annotate_bars(axes[0], bars, "{:.1f}")
    for idx, value in enumerate(costs):
        text = "基准" if idx == 0 else f"节省 {(costs[0]-value)/costs[0]:.1%}"
        axes[0].text(idx, value * 0.48, text, ha="center", color="white", fontsize=8.5, fontweight="bold")
    axes[0].set_ylim(0, costs.max() * 1.12)
    axes[0].set_ylabel("全年总费用（万元）")
    axes[0].set_title("总费用")
    axes[0].set_xticks(x, ["" for _ in x])
    axes[0].grid(axis="y")

    bars = axes[1].bar(x, emergency, color=colors, width=0.62)
    _annotate_bars(axes[1], bars, "{:.1f}")
    axes[1].set_ylim(0, emergency.max() * 1.18)
    axes[1].set_ylabel("全年紧急购电量（万kWh）")
    axes[1].set_title("紧急购电量")
    axes[1].set_xticks(x, labels)
    axes[1].grid(axis="y")
    fig.suptitle("问题3：场景生成与储能执行机制的模型消融", fontsize=12.5)
    save_pair(fig, "q3_model_ablation")
    return "q3_model_ablation"


def plot_q3_update_policy() -> str:
    data = _read_csv("target/question3/ablation_summary.csv")
    order = ["0", "0+6", "0+6+12", "0+6+12+18", "0+12+18", "0+6+18"]
    data = data.set_index("policy").loc[order].reset_index()
    validate_q3(_read_csv("target/question3/model_ablation_summary.csv"), data)
    costs = data["total_cost"].to_numpy() / 1e4
    emergency = data["emergency_kwh"].to_numpy() / 1e4
    x = np.arange(len(order))
    selected = order.index("0+6+12")
    colors = [COLORS["teal"] if i == selected else COLORS["slate"] for i in range(len(order))]

    fig, axes = plt.subplots(2, 1, figsize=(10, 7.5), layout="constrained")
    bars = axes[0].bar(x, costs, color=colors, width=0.64)
    _annotate_bars(axes[0], bars, "{:.2f}", fontsize=8)
    axes[0].set_ylim(0, costs.max() * 1.14)
    axes[0].set_ylabel("全年总费用（万元）")
    axes[0].set_title("总费用（纵轴从0开始）")
    axes[0].set_xticks(x, ["" for _ in x])
    axes[0].grid(axis="y")
    delta = costs[order.index("0+6+12+18")] - costs[selected]
    axes[0].annotate(
        f"0+6+12 最优\n较加入18点更新低 {delta:.2f} 万元",
        xy=(selected, costs[selected]),
        xytext=(selected + 1.35, costs.max() * 0.76),
        arrowprops={"arrowstyle": "->", "color": COLORS["red"], "lw": 1},
        color=COLORS["red"],
        ha="center",
        bbox={"facecolor": "white", "edgecolor": COLORS["light"], "boxstyle": "round,pad=0.3"},
    )

    bars = axes[1].bar(x, emergency, color=colors, width=0.64)
    _annotate_bars(axes[1], bars, "{:.1f}", fontsize=8)
    axes[1].set_ylim(0, emergency.max() * 1.18)
    axes[1].set_ylabel("全年紧急购电量（万kWh）")
    axes[1].set_title("紧急购电量")
    axes[1].set_xticks(x, order)
    axes[1].set_xlabel("预报更新时间组合（小时）")
    axes[1].grid(axis="y")
    fig.suptitle("问题3：预报更新时间组合消融", fontsize=12.5)
    save_pair(fig, "q3_update_policy")
    return "q3_update_policy"


def plot_q3_forecast_accuracy() -> str:
    data = _read_csv("target/question3/forecast_accuracy.csv")
    x = np.arange(len(data))
    labels = [f"{int(hour)}:00" for hour in data["issue_hour"]]
    fig, axes = plt.subplots(1, 2, figsize=(10.8, 4.6), layout="constrained")
    for ax, prefix, title in (
        (axes[0], "", "各次预报的当日剩余时域"),
        (axes[1], "common_18_24_", "统一的18:00—24:00时域"),
    ):
        mae = data[f"{prefix}MAE_kW"].to_numpy()
        rmse = data[f"{prefix}RMSE_kW"].to_numpy()
        bars1 = ax.bar(x - 0.18, mae, 0.36, color=COLORS["teal"], label="MAE")
        bars2 = ax.bar(x + 0.18, rmse, 0.36, color=COLORS["orange"], label="RMSE")
        _annotate_bars(ax, bars1, "{:.1f}", fontsize=7.5)
        _annotate_bars(ax, bars2, "{:.1f}", fontsize=7.5)
        ax.set_xticks(x, labels)
        ax.set_ylim(0, rmse.max() * 1.25)
        ax.set_xlabel("预报发布时间")
        ax.set_ylabel("光伏功率误差（kW）")
        ax.set_title(title)
        ax.grid(axis="y")
        ax.legend(ncols=2)
    fig.suptitle("问题3：不同发布时间的光伏预报精度", fontsize=12.5)
    save_pair(fig, "q3_forecast_accuracy")
    return "q3_forecast_accuracy"


def _plot_dispatch(record: dict, name: str, price: np.ndarray | None = None) -> None:
    schedule = record["schedule"]
    initial_plan = schedule["initial_plan"]
    initial = np.asarray(initial_plan["grid_kwh"], dtype=float)
    executed = np.asarray(schedule["executed_grid"], dtype=float)
    actual = np.asarray(record["actual_net_load"], dtype=float)
    charge = np.asarray(schedule["executed_charge"], dtype=float)
    discharge = np.asarray(schedule["executed_discharge"], dtype=float)
    soc = np.asarray(schedule["executed_soc_end"], dtype=float)
    adjustment = executed - initial
    starts = tuple(int(item["start_slot"]) for item in schedule["revisions"])
    slots = np.arange(144)
    has_price = price is not None
    rows = 5 if has_price else 4
    heights = [0.75, 1.6, 1.0, 1.0, 1.0] if has_price else [1.6, 1.0, 1.0, 1.0]
    fig, axes = plt.subplots(
        rows,
        1,
        figsize=(11.2, 10.5 if has_price else 9.0),
        sharex=True,
        gridspec_kw={"height_ratios": heights},
        layout="constrained",
    )
    axes = np.atleast_1d(axes)
    offset = 0
    if has_price:
        axes[0].step(slots, price, where="mid", color=COLORS["orange"], linewidth=1.35)
        axes[0].fill_between(slots, 0, price, step="mid", color=COLORS["orange"], alpha=0.10)
        axes[0].set_ylabel("电价\n（元/kWh）")
        axes[0].set_title("目标日动态结算电价")
        axes[0].grid(axis="y")
        offset = 1

    ax = axes[offset]
    ax.plot(slots, actual, color=COLORS["navy"], linewidth=1.25, label="实际净负荷")
    ax.plot(slots, initial, color=COLORS["purple"], linestyle="--", linewidth=1.0, label="0点初始合同")
    ax.step(slots, executed, where="mid", color=COLORS["teal"], linewidth=1.25, label="最终执行合同")
    ax.set_ylabel("电量\n（kWh/10分钟）")
    ax.set_title("实际净负荷与合同购电")
    ax.legend(ncols=3, loc="upper left")
    ax.grid(axis="y")

    ax = axes[offset + 1]
    ax.bar(slots, np.maximum(adjustment, 0), width=1.0, color=COLORS["orange"], label="增购")
    ax.bar(slots, np.minimum(adjustment, 0), width=1.0, color=COLORS["teal"], label="减购")
    ax.axhline(0, color=COLORS["gray"], linewidth=0.7)
    ax.set_ylabel("合同调整\n（kWh/10分钟）")
    ax.set_title("最终执行合同相对0点初始合同的调整")
    ax.legend(ncols=2, loc="upper left")
    ax.grid(axis="y")

    ax = axes[offset + 2]
    ax.bar(slots, charge, width=1.0, color=COLORS["teal"], label="充电")
    ax.bar(slots, -discharge, width=1.0, color=COLORS["purple"], label="放电（负向）")
    ax.axhline(0, color=COLORS["gray"], linewidth=0.7)
    ax.set_ylabel("储能功率\n（kWh/10分钟）")
    ax.set_title("储能充放电")
    ax.legend(ncols=2, loc="upper left")
    ax.grid(axis="y")

    ax = axes[offset + 3]
    initial_soc = float(initial_plan.get("initial_soc_kwh", 6000.0))
    ax.plot(np.arange(145), np.r_[initial_soc, soc], color=COLORS["navy"], linewidth=1.35, label="SOC")
    ax.axhline(1200, color=COLORS["red"], linestyle="--", linewidth=0.9, label="SOC 上下界")
    ax.axhline(10800, color=COLORS["red"], linestyle="--", linewidth=0.9)
    ax.set_ylim(0, 12000)
    ax.set_ylabel("储电量（kWh）")
    ax.set_title("储能荷电状态")
    ax.legend(loc="upper left")
    ax.grid(axis="y")
    _time_axis(ax, xlabel=True)
    _revision_lines(axes, starts)
    day = initial_plan["date"]
    title = "问题4-3：动态电价下典型日滚动调度" if has_price else "问题3：典型日滚动合同与储能执行"
    fig.suptitle(f"{title}（{day}；竖虚线为6点、12点更新边界）", fontsize=12.5)
    save_pair(fig, name)


def plot_q3_dispatch() -> str:
    record = _jsonl_day("target/question3/daily_results.jsonl", "2025-12-21")
    _plot_dispatch(record, "q3_dispatch_2025-12-21")
    return "q3_dispatch_2025-12-21"


def _load_prices(relative: str) -> tuple[pd.DatetimeIndex, list[str], np.ndarray]:
    path = ROOT / relative
    data = json.loads(path.read_text(encoding="utf-8"))
    dates = pd.to_datetime(data["dates"])
    values = np.asarray(data["price_yuan_per_kwh"], dtype=float)
    if values.shape != (len(dates), 144):
        raise ValueError(f"动态电价矩阵形状异常：{values.shape}")
    return dates, data["slot_labels"], values


def plot_q4_prices() -> str:
    dates, _, values = _load_prices("target/question4/question4_3/prices.json")
    fig, axes = plt.subplots(
        2,
        1,
        figsize=(11.2, 7.8),
        gridspec_kw={"height_ratios": [1.55, 1]},
        layout="constrained",
    )
    image = axes[0].imshow(
        values,
        aspect="auto",
        origin="lower",
        interpolation="nearest",
        cmap="YlOrRd",
        rasterized=True,
    )
    month_rows = [idx for idx, day in enumerate(dates) if day.day == 1]
    axes[0].set_yticks(month_rows, [f"{dates[idx].month}月" for idx in month_rows])
    axes[0].set_xticks(
        np.arange(0, 145, 24),
        ["0:00", "4:00", "8:00", "12:00", "16:00", "20:00", "24:00"],
    )
    axes[0].set_xlabel("日内时刻（每个时段10分钟）")
    axes[0].set_ylabel("日期（2025年）")
    axes[0].set_title("每日144点动态电价")
    axes[0].grid(False)
    fig.colorbar(image, ax=axes[0], pad=0.015, label="电价（元/kWh）")

    low = values.min(axis=1)
    high = values.max(axis=1)
    mean = values.mean(axis=1)
    axes[1].fill_between(dates, low, high, color=COLORS["orange"], alpha=0.18, label="日内最低—最高价")
    axes[1].plot(dates, mean, color=COLORS["navy"], linewidth=1.15, label="日均价")
    axes[1].set_xlim(dates[0], dates[-1])
    axes[1].set_ylabel("电价（元/kWh）")
    axes[1].set_xlabel("月份（2025年）")
    axes[1].set_title("逐日电价区间与均值")
    axes[1].set_xticks([dates[idx] for idx in month_rows], [f"{dates[idx].month}月" for idx in month_rows])
    axes[1].legend(ncols=2)
    axes[1].grid(axis="y")
    fig.suptitle("问题4：2025年动态电价的时序分布", fontsize=12.5)
    save_pair(fig, "q4_dynamic_prices")
    return "q4_dynamic_prices"


def _comparison_value(frame: pd.DataFrame, metric: str, column: str) -> float:
    row = frame.loc[frame["metric"] == metric, column]
    if len(row) != 1:
        raise ValueError(f"comparison.csv 缺少唯一指标 {metric}")
    return float(row.iloc[0])


def validate_q4(q42: pd.DataFrame, q43: pd.DataFrame) -> None:
    expected = [
        (q42, "fixed_price", 14_689_283.3613),
        (q42, "dynamic_price", 15_265_670.4564),
        (q43, "fixed_price", 14_641_650.0549),
        (q43, "dynamic_price", 15_192_251.2649),
    ]
    for frame, column, value in expected:
        actual = _comparison_value(frame, "total_cost", column)
        if not np.isclose(actual, value, atol=0.02):
            raise ValueError(f"Q4 {column} 总费用未通过校验：{actual}")


def plot_q4_comparison() -> str:
    q42 = _read_csv("target/question4/question4_2/comparison.csv")
    q43 = _read_csv("target/question4/question4_3/comparison.csv")
    validate_q4(q42, q43)
    frames = [q42, q43]
    x = np.arange(2)
    width = 0.36
    labels = ["Q4-2\n0点固定计划", "Q4-3\n0、6、12点更新"]
    fig, axes = plt.subplots(1, 2, figsize=(10.8, 4.9), layout="constrained")
    for ax, metric, scale, ylabel, title, number_format in (
        (axes[0], "total_cost", 1e4, "全年总费用（万元）", "总费用", "{:.1f}"),
        (axes[1], "emergency_kwh", 1e4, "全年紧急购电量（万kWh）", "紧急购电量", "{:.2f}"),
    ):
        fixed = np.array([_comparison_value(frame, metric, "fixed_price") for frame in frames]) / scale
        dynamic = np.array([_comparison_value(frame, metric, "dynamic_price") for frame in frames]) / scale
        bars_fixed = ax.bar(x - width / 2, fixed, width, color=COLORS["blue"], label="固定电价")
        bars_dynamic = ax.bar(x + width / 2, dynamic, width, color=COLORS["orange"], label="动态电价")
        _annotate_bars(ax, bars_fixed, number_format, fontsize=8)
        _annotate_bars(ax, bars_dynamic, number_format, fontsize=8)
        for idx, (base, changed) in enumerate(zip(fixed, dynamic)):
            ax.text(
                idx,
                max(base, changed) * 1.075,
                f"动态−固定：{(changed-base)/base:+.2%}",
                ha="center",
                color=COLORS["red"] if changed >= base else COLORS["teal"],
                fontsize=8.5,
            )
        ax.set_xticks(x, labels)
        ax.set_ylim(0, max(np.r_[fixed, dynamic]) * 1.22)
        ax.set_ylabel(ylabel)
        ax.set_title(title)
        ax.grid(axis="y")
        ax.legend(ncols=2)
    fig.suptitle("问题4：固定电价与动态电价的全年结果对比", fontsize=12.5)
    save_pair(fig, "q4_fixed_dynamic_comparison")
    return "q4_fixed_dynamic_comparison"


def plot_q4_dispatch() -> str:
    record = _jsonl_day("target/question4/question4_3/daily_results.jsonl", "2025-12-21")
    dates, _, prices = _load_prices("target/question4/question4_3/prices.json")
    matches = np.flatnonzero(dates == pd.Timestamp("2025-12-21"))
    if len(matches) != 1:
        raise ValueError("动态电价数据中未找到唯一的 2025-12-21")
    _plot_dispatch(record, "q4_dispatch_2025-12-21", prices[int(matches[0])])
    return "q4_dispatch_2025-12-21"


def validate_output(name: str, directory: Path = OUTPUT_DIR) -> None:
    png = directory / f"{name}.png"
    pdf = directory / f"{name}.pdf"
    if png.stat().st_size < 10_000 or pdf.stat().st_size < 1_000:
        raise ValueError(f"输出文件过小，可能未正确渲染：{name}")
    with pdf.open("rb") as handle:
        if handle.read(4) != b"%PDF":
            raise ValueError(f"PDF 文件头异常：{pdf}")
    image = plt.imread(png)
    if image.ndim not in (2, 3) or min(image.shape[:2]) < 1000:
        raise ValueError(f"PNG 分辨率不足：{png} -> {image.shape}")


def write_manifest(names: list[str], selected: str, font: str) -> Path:
    lines = [
        "# 论文可视化清单",
        "",
        f"生成范围：`{selected}`；中文字体：`{font}`；PNG 分辨率：320 dpi；同时提供矢量 PDF。",
        "",
        "所有图片仅由现有 CSV/JSON 结果生成，未重新运行优化模型，也未写入任何正式 Excel 文件。",
        "",
        "| 图片 | 数据源 | 核心结论 | 建议章节 | 位置 |",
        "|---|---|---|---|---|",
    ]
    for name in names:
        info = FIGURE_INFO[name]
        folder = "optional/" if name == "q2_surplus_emergency_tradeoff" else ""
        links = f"[{name}.png]({folder}{name}.png) / [PDF]({folder}{name}.pdf)"
        lines.append(
            f"| {links} | {info['sources']} | {info['conclusion']} | {info['section']} | {info['placement']} |"
        )
    lines.extend(["", "## 推荐图注", ""])
    for name in names:
        lines.append(f"- **{name}**：{FIGURE_INFO[name]['caption']}")
        lines.append("")
    if selected in ("all", "q2"):
        lines.extend(
            [
                "## 未生成的候选图",
                "",
                "- `optional/q2_emergency_heatmap_compare`：现有持久化数据只有 A0/A7 的逐日紧急购电总量，没有 A0 的144时段紧急购电矩阵。为遵守“不重跑高成本优化、优先使用现有 CSV/JSON”的要求，本次不绘制该图。",
                "",
            ]
        )
    path = OUTPUT_DIR / "figure_manifest.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="由已落盘结果生成问题2—4论文图片。")
    parser.add_argument(
        "--only",
        choices=("q2", "q3", "q4"),
        help="只生成指定问题的图片；默认生成全部核心图及可用的可选图。",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    selected = args.only or "all"
    font = configure_style()
    names: list[str] = []
    if selected in ("all", "q2"):
        names.extend(
            [
                plot_q2_ablation(),
                plot_q2_monthly(),
                plot_q2_calibration(),
                plot_q2_tradeoff(),
            ]
        )
    if selected in ("all", "q3"):
        names.extend(
            [
                plot_q3_model_ablation(),
                plot_q3_update_policy(),
                plot_q3_forecast_accuracy(),
                plot_q3_dispatch(),
            ]
        )
    if selected in ("all", "q4"):
        names.extend([plot_q4_prices(), plot_q4_comparison(), plot_q4_dispatch()])

    for name in names:
        directory = OPTIONAL_DIR if name == "q2_surplus_emergency_tradeoff" else OUTPUT_DIR
        validate_output(name, directory)
    manifest = write_manifest(names, selected, font)
    print(f"中文字体：{font}")
    print(f"已生成 {len(names)} 张图（{2 * len(names)} 个图像文件）：{OUTPUT_DIR}")
    print(f"清单：{manifest}")


if __name__ == "__main__":
    main()
