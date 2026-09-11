"""论文PNG/PDF；同信息静态比较与滚动信息实验用独立视觉标记。"""
from pathlib import Path
import numpy as np

from ..plotting import configure_chinese, plt, save_figure
from .validator import require_baselines
from . import config as cfg

FIGURE_NAMES = cfg.FIGURE_NAMES
COLORS = {"DET": "#60758C", "Q80": "#51A4A2", "SAA": "#2864A0", "CVaR95-L50": "#8061A7", "SAA-MPC": "#DD8A3A"}


def decorate_methods(ax, rows):
    ax.set_xticks(range(len(rows)), [row["method"] for row in rows], rotation=12)
    mpc = next((i for i, row in enumerate(rows) if row["method"] == "SAA-MPC"), None)
    if mpc is not None:
        if mpc:
            ax.axvline(mpc - 0.5, color="#666666", ls="--", lw=1)
        if mpc + 1 < len(rows):
            ax.axvline(mpc + 0.5, color="#666666", ls="--", lw=1)
    ax.set_axisbelow(True)


def finish(fig, directory, name):
    fig.text(0.5, 0.01, "固定电价 · 2025年2—12月（334天） | SAA-MPC为信息更新实验，信息集合不同",
             ha="center", fontsize=9, color="#555555")
    fig.tight_layout(rect=(0, .05, 1, .97))
    return save_figure(fig, directory, name)


def plot_results(comparison, sensitivity, baselines, directory=cfg.OUTPUT_DIR / "figures"):
    require_baselines(baselines)
    if not comparison:
        raise ValueError("cannot plot empty benchmark comparison")
    configure_chinese()
    plt.rcParams.update({"savefig.dpi": 300, "font.size": 10, "axes.titleweight": "bold"})
    directory = Path(directory)
    x = np.arange(len(comparison))
    colors = [COLORS[row["method"]] for row in comparison]
    paths = []

    fig, ax = plt.subplots(figsize=(9, 5))
    bars = ax.bar(x, [r["total_cost"] / 1e4 for r in comparison], color=colors, width=.6)
    for bar, row in zip(bars, comparison):
        if row["method"] == "SAA-MPC": bar.set_hatch("//")
    ax.bar_label(bars, fmt="%.2f", padding=5)
    decorate_methods(ax, comparison)
    ax.set(ylabel="实际总费用（万元）", title="算法对比：年度实际总费用")
    ax.set_ylim(0, max(r["total_cost"] / 1e4 for r in comparison) * 1.16)
    paths += finish(fig, directory, "annual_total_cost")

    fig, ax = plt.subplots(figsize=(9, 5))
    contract = np.array([r["contract_cost"] for r in comparison]) / 1e4
    emergency = np.array([r["emergency_cost"] for r in comparison]) / 1e4
    ax.bar(x, contract, label="合同费 = 计划费 + 调整净费", color="#3476A8", width=.6)
    bars = ax.bar(x, emergency, bottom=contract, label="实际紧急购电费", color="#E89A62", width=.6)
    ax.bar_label(bars, labels=[f"{100*r['emergency_cost']/r['total_cost']:.1f}%" if r['total_cost'] else "0%" for r in comparison], padding=4)
    decorate_methods(ax, comparison)
    ax.set(ylabel="费用（万元）", title="费用构成（顶部标注紧急费用占比）")
    ax.set_ylim(0, max(contract + emergency) * 1.2)
    ax.legend(loc="upper left", ncols=2, frameon=False)
    paths += finish(fig, directory, "cost_components")

    fig, axes = plt.subplots(1, 2, figsize=(12, 5))
    bars = axes[0].bar(x, [r["emergency_kwh"] / 1e4 for r in comparison], color=colors)
    axes[0].bar_label(bars, labels=[f"{r['emergency_days']}天" for r in comparison], padding=5)
    axes[0].set(ylabel="年度紧急购电量（万kWh）", title="紧急购电规模与发生天数")
    axes[0].set_ylim(0, max(r["emergency_kwh"] / 1e4 for r in comparison) * 1.2)
    axes[1].bar(x - .18, [r["p95_daily_emergency_kwh"] for r in comparison], .36, color="#589FAC", label="日紧急量 P95")
    axes[1].bar(x + .18, [r["cvar95_daily_emergency_kwh"] for r in comparison], .36, color="#8163A4", label="日紧急量 CVaR95")
    axes[1].set(ylabel="日紧急购电量（kWh）", title="样本外尾部风险")
    axes[1].legend(frameon=False)
    for ax in axes: decorate_methods(ax, comparison)
    paths += finish(fig, directory, "emergency_risk")

    fig, axes = plt.subplots(1, 2, figsize=(12, 5))
    for ax, risk, label in ((axes[0], "cvar95_daily_cost", "日费用 CVaR95（万元）"),
                            (axes[1], "cvar95_daily_emergency_kwh", "日紧急量 CVaR95（万kWh）")):
        for i, row in enumerate(comparison):
            mpc = row["method"] == "SAA-MPC"
            ax.scatter(row["total_cost"] / 1e4, row[risk] / 1e4, s=100 if mpc else 75,
                       marker="D" if mpc else "o", color=COLORS[row["method"]], edgecolor="white", linewidth=.6)
            offsets = {"DET": (10, 9), "Q80": (18, 19), "SAA": (32, -2),
                       "CVaR95-L50": (16, -10), "SAA-MPC": (-68, -13)}
            ax.annotate(row["method"], (row["total_cost"] / 1e4, row[risk] / 1e4),
                        xytext=offsets[row["method"]], textcoords="offset points", fontsize=9,
                        arrowprops={"arrowstyle": "-", "color": "#777777", "lw": .6})
        ax.set(xlabel="年度实际总费用（万元）", ylabel=label)
        ax.margins(x=.3, y=.25)
    axes[0].set_title("成本与费用尾部风险（越靠左下越低）")
    axes[1].set_title("成本与紧急购电尾部风险")
    paths += finish(fig, directory, "risk_return")

    if sensitivity:
        if len(sensitivity) != len(cfg.SENSITIVITY_ALPHAS) * len(cfg.SENSITIVITY_LAMBDAS):
            raise ValueError("sensitivity plot requires the complete prespecified grid")
        fig, axes = plt.subplots(2, 2, figsize=(12, 8))
        for ax, key, unit, scale in zip(axes.ravel(),
                ("total_cost", "emergency_kwh", "cvar95_daily_cost", "cvar95_daily_emergency_kwh"),
                ("年度总费用（万元）", "年度紧急量（万kWh）", "日费用CVaR95（万元）", "日紧急量CVaR95（万kWh）"),
                (1e4, 1e4, 1e4, 1e4)):
            lookup = {(r["alpha"], r["lambda"]): r[key] / scale for r in sensitivity}
            matrix = np.array([[lookup[a, w] for w in cfg.SENSITIVITY_LAMBDAS] for a in cfg.SENSITIVITY_ALPHAS])
            im = ax.imshow(matrix, cmap="YlGnBu", aspect="auto")
            fig.colorbar(im, ax=ax, shrink=.78)
            ax.set_xticks(range(len(cfg.SENSITIVITY_LAMBDAS)), [f"{w:.2f}" for w in cfg.SENSITIVITY_LAMBDAS])
            ax.set_yticks(range(len(cfg.SENSITIVITY_ALPHAS)), [f"{a:.2f}" for a in cfg.SENSITIVITY_ALPHAS])
            ax.set(xlabel="lambda", ylabel="alpha", title=unit)
            ax.grid(False)
            for i in range(matrix.shape[0]):
                for j in range(matrix.shape[1]):
                    color = "white" if matrix[i, j] > (matrix.min() + matrix.max()) / 2 else "#222222"
                    ax.text(j, i, f"{matrix[i,j]:.2f}", ha="center", va="center", color=color)
            from matplotlib.patches import Rectangle
            ax.add_patch(Rectangle((.5, .5), 1, 1, fill=False, edgecolor="#EC705A", lw=2.5))
        fig.suptitle("CVaR参数灵敏度：红框为预先固定主参数（0.95, 0.50）", fontsize=13)
        paths += finish(fig, directory, "cvar_sensitivity")

    fig, ax = plt.subplots(figsize=(9, 5))
    bars = ax.bar(x, [r["total_runtime_seconds"] for r in comparison], color=colors, width=.6)
    for bar, row in zip(bars, comparison):
        if row["method"] == "SAA-MPC": bar.set_hatch("//")
    ax.bar_label(bars, labels=[f"{r['total_runtime_seconds']:.2f} s\n{r['mean_runtime_per_day_ms']:.1f} ms/日" for r in comparison], padding=5)
    ax.set(ylabel="完整334天运行时间（秒，对数轴）", title="串行计算时间：场景构造、优化、结算与校验", yscale="log")
    decorate_methods(ax, comparison)
    ax.set_ylim(max(min(r["total_runtime_seconds"] for r in comparison) / 2, .001), max(r["total_runtime_seconds"] for r in comparison) * 3)
    paths += finish(fig, directory, "runtime")
    return paths
