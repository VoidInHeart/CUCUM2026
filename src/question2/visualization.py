"""全年与指定日期结果可视化，所有电量采用交流侧 kWh。"""
from pathlib import Path
import numpy as np
from ..plotting import configure_chinese, plt, save_figure
import matplotlib.dates as mdates
from . import config as cfg
from .types import DailyEvaluation


def plot_results(evaluations: list[DailyEvaluation], directory: Path = cfg.OUTPUT_DIR / "figures") -> list[Path]:
    configure_chinese()
    dates = [item.plan.date for item in evaluations]
    planned = np.array([item.planned_grid_total for item in evaluations])
    emergency = np.array([item.emergency_total for item in evaluations])
    planned_cost = np.array([item.planned_cost for item in evaluations])
    emergency_cost = np.array([item.emergency_cost for item in evaluations])
    fig, axes = plt.subplots(3, 1, figsize=(12, 10), sharex=True, layout="constrained")
    axes[0].plot(dates, planned / 1000, label="计划购电量", color="#168c91")
    axes[0].plot(dates, (planned + emergency) / 1000, label="实际外网总购电量", color="#263b62", alpha=0.75)
    axes[0].set(ylabel="电量（千kWh）", title="问题2：2025年2—12月逐日购电与费用")
    axes[0].legend(ncols=2)
    axes[1].bar(dates, emergency / 1000, color="#c36a42", width=1)
    axes[1].set(ylabel="紧急购电量（千kWh）")
    axes[2].stackplot(dates, planned_cost / 10000, emergency_cost / 10000,
                      labels=["计划购电费", "紧急购电费"], colors=["#168c91", "#c36a42"])
    axes[2].set(ylabel="费用（万元）", xlabel="日期")
    axes[2].legend(ncols=2)
    axes[2].xaxis.set_major_locator(mdates.MonthLocator())
    axes[2].xaxis.set_major_formatter(mdates.DateFormatter("%m月"))
    axes[2].set_xlim(dates[0], dates[-1])
    paths = save_figure(fig, directory, "annual_overview")

    months = np.arange(2, 13)
    monthly_plan = np.array([sum(item.planned_cost for item in evaluations if item.plan.date.month == month) for month in months]) / 10000
    monthly_emergency = np.array([sum(item.emergency_cost for item in evaluations if item.plan.date.month == month) for month in months]) / 10000
    fig, ax = plt.subplots(figsize=(11, 5), layout="constrained")
    ax.bar(months, monthly_plan, label="计划购电费", color="#168c91")
    ax.bar(months, monthly_emergency, bottom=monthly_plan, label="紧急购电费（5倍电价）", color="#c36a42")
    ax.set(xticks=months, xticklabels=[f"{month}月" for month in months], ylabel="费用（万元）", title="问题2：月度购电费用构成")
    ax.legend()
    paths += save_figure(fig, directory, "monthly_costs")

    fig, ax = plt.subplots(figsize=(12, 7), layout="constrained")
    heatmap = np.array([item.emergency_kwh for item in evaluations])
    mesh = ax.imshow(heatmap, aspect="auto", interpolation="nearest", cmap="YlOrRd")
    month_rows = [i for i, day in enumerate(dates) if day.day == 1]
    ax.set(yticks=month_rows, yticklabels=[dates[i].strftime("%m-%d") for i in month_rows],
           xticks=np.arange(0, 144, 24), xlabel="slot 序号（保持官方模板列顺序）", ylabel="日期（2025年）",
           title="问题2：紧急购电时段分布")
    ax.grid(False)
    fig.colorbar(mesh, ax=ax, label="每时段紧急购电量（kWh）")
    paths += save_figure(fig, directory, "emergency_heatmap")

    slots = np.arange(144)
    for item in evaluations:
        if item.plan.date not in cfg.PAPER_DATES:
            continue
        plan = item.plan
        scheduled = plan.grid_kwh + plan.discharge_kwh - plan.charge_kwh
        fig, axes = plt.subplots(4, 1, figsize=(12, 11), layout="constrained")
        axes[0].plot(slots, item.actual_net_load_kwh, label="实际净负荷", color="#263b62")
        axes[0].step(slots, scheduled, where="mid", label="计划净供电", color="#168c91")
        axes[0].step(slots, plan.grid_kwh, where="mid", label="计划外网购电", color="#76549b", alpha=0.7)
        axes[0].set(ylabel="电量（kWh）", title=f"问题2：{plan.date} 调度与实际结算")
        axes[0].legend(ncols=3)
        axes[1].bar(slots, item.emergency_kwh, label="紧急购电", color="#c36a42")
        axes[1].bar(slots, -item.surplus_kwh, label="富余电量（负向显示）", color="#d49a18")
        axes[1].set(ylabel="电量（kWh）")
        axes[1].legend(ncols=2)
        axes[2].bar(slots, plan.charge_kwh, label="充电", color="#168c91")
        axes[2].bar(slots, -plan.discharge_kwh, label="放电（负向显示）", color="#76549b")
        axes[2].set(ylabel="电量（kWh）")
        axes[2].legend(ncols=2)
        axes[3].plot(np.arange(145), np.r_[cfg.INITIAL_SOC_KWH, plan.soc_end_kwh], color="#263b62")
        for bound in (cfg.SOC_MIN_KWH, cfg.SOC_MAX_KWH):
            axes[3].axhline(bound, color="#b34c4c", ls="--", lw=1)
        axes[3].set(ylabel="储电量（kWh）", xlabel="slot 边界序号（每步10分钟；0为初始状态）")
        for ax in axes:
            ax.set_xlim(0, 144)
            ax.set_xticks(np.arange(0, 145, 24))
        paths += save_figure(fig, directory, f"dispatch_{plan.date}")
    return paths
