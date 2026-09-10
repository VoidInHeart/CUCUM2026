"""问题1调度、储能和分段充放电图，输出 PNG 与矢量 PDF。"""
from pathlib import Path
import numpy as np

from ..plotting import configure_chinese, plt, save_figure
from . import config as cfg
from .data_loader import Question1Input
from .optimizer import Question1Solution
from .summary import BLOCK_LABELS
from .validator import validate_solution


def plot_results(data: Question1Input, solution: Question1Solution,
                 directory: Path = cfg.PROJECT_ROOT / "target" / "question1" / "figures") -> list[Path]:
    validate_solution(data, solution)
    configure_chinese()
    slots = np.arange(cfg.N_SLOTS)
    fig, axes = plt.subplots(3, 1, figsize=(12, 10), layout="constrained")
    axes[0].plot(slots, data.load_kw, label="负载", color="#263b62")
    axes[0].plot(slots, data.pv_kw, label="光伏预测", color="#d49a18")
    axes[0].step(slots, solution.grid_purchase_kwh / cfg.TIME_STEP_HOURS, where="mid",
                 label="计划购电等效功率", color="#168c91")
    axes[0].set(ylabel="功率（kW）", title="问题1：日前购电与储能调度")
    axes[0].legend(ncols=3)
    axes[1].bar(slots, solution.charge_kwh, label="充电", color="#168c91")
    axes[1].bar(slots, -solution.discharge_kwh, label="放电（负向显示）", color="#c36a42")
    axes[1].set(ylabel="每时段电量（kWh）")
    axes[1].legend(ncols=2)
    axes[2].plot(np.arange(145), np.r_[cfg.INITIAL_SOC_KWH, solution.soc_end_kwh], color="#263b62")
    for bound in (cfg.SOC_MIN_KWH, cfg.SOC_MAX_KWH):
        axes[2].axhline(bound, ls="--", color="#b34c4c", lw=1)
    axes[2].set(ylabel="储电量（kWh）", xlabel="slot 边界序号（每步10分钟；0为初始状态）")
    for ax in axes:
        ax.set_xlim(0, 144)
        ax.set_xticks(np.arange(0, 145, 24))
    paths = save_figure(fig, directory, "dispatch")
    fig, axes = plt.subplots(1, 2, figsize=(13, 4.6), layout="constrained")
    axes[0].plot(slots, data.price, color="#76549b")
    axes[0].set(xlabel="slot 序号（保持附件原顺序）", ylabel="电价（元/kWh）", title="日电价曲线")
    blocks = np.arange(6)
    axes[1].bar(blocks - 0.18, solution.charge_kwh.reshape(6, 24).sum(axis=1), 0.36, label="充电", color="#168c91")
    axes[1].bar(blocks + 0.18, solution.discharge_kwh.reshape(6, 24).sum(axis=1), 0.36, label="放电", color="#c36a42")
    axes[1].set(xticks=blocks, xticklabels=BLOCK_LABELS, ylabel="电量（kWh）", title="每24个slot累计充放电量")
    axes[1].tick_params(axis="x", rotation=25)
    axes[1].legend()
    return paths + save_figure(fig, directory, "price_and_blocks")
