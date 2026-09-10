"""正式策略、更新时间消融及预报误差的中文PNG/PDF图。"""
import numpy as np
from ..plotting import configure_chinese, plt, save_figure
import matplotlib.dates as mdates

from . import config as cfg


def plot_results(results, ablations, policy_daily_rows, accuracy, directory=cfg.OUTPUT_DIR / "figures"):
    configure_chinese()
    dates = [result.schedule.date for result in results]
    fig, axes = plt.subplots(3, 1, figsize=(12, 10), sharex=True, layout="constrained")
    for key, label, color in (("initial_plan_kwh", "0:00计划量", "#76549b"),
                              ("executed_adjusted_kwh", "执行合同量", "#168c91"),
                              ("actual_grid_energy_kwh", "实际外网总量", "#263b62")):
        axes[0].plot(dates, np.array([getattr(r, key) for r in results]) / 1000, label=label, color=color, lw=1.3)
    axes[0].set(ylabel="电量（千kWh）", title="问题3：四时刻滚动策略的全年执行结果（2—12月）")
    axes[0].legend(ncols=3)
    axes[1].plot(dates, np.array([r.total_cost for r in results]) / 10000, label="总费用", color="#263b62")
    axes[1].fill_between(dates, np.array([r.emergency_cost for r in results]) / 10000, label="紧急购电费", color="#c36a42", alpha=0.7)
    axes[1].set(ylabel="费用（万元）")
    axes[1].legend(ncols=2)
    cash = np.array([r.adjustment_cost for r in results]) / 10000
    axes[2].bar(dates, cash, color=np.where(cash >= 0, "#c36a42", "#168c91"), width=1)
    axes[2].axhline(0, color="#555555", lw=0.8)
    axes[2].set(ylabel="调整净现金流（万元）", xlabel="日期；负现金流表示净退款")
    axes[2].xaxis.set_major_locator(mdates.MonthLocator())
    axes[2].xaxis.set_major_formatter(mdates.DateFormatter("%m月"))
    axes[2].set_xlim(dates[0], dates[-1])
    paths = save_figure(fig, directory, "annual_overview")

    slots = np.arange(144)
    for result in results:
        s = result.schedule
        if s.date not in cfg.PAPER_DATES:
            continue
        fig, axes = plt.subplots(4, 1, figsize=(12, 11), layout="constrained")
        axes[0].plot(slots, s.initial_plan.grid_kwh, label="0:00合同计划", color="#76549b", alpha=0.75)
        axes[0].step(slots, s.executed_grid, where="mid", label="执行合同", color="#168c91")
        axes[0].plot(slots, result.actual_net_load, label="实际净负荷", color="#263b62")
        axes[0].set(ylabel="电量（kWh）", title=f"问题3：{s.date} 滚动合同与储能执行")
        axes[0].legend(ncols=3)
        axes[1].bar(slots, result.real_emergency, label="紧急购电", color="#c36a42")
        axes[1].bar(slots, -result.real_surplus, label="富余电量（负向显示）", color="#d49a18")
        axes[1].set(ylabel="电量（kWh）")
        axes[1].legend(ncols=2)
        axes[2].bar(slots, s.executed_charge, label="充电", color="#168c91")
        axes[2].bar(slots, -s.executed_discharge, label="放电（负向显示）", color="#76549b")
        axes[2].set(ylabel="电量（kWh）")
        axes[2].legend(ncols=2)
        axes[3].plot(np.arange(145), np.r_[cfg.INITIAL_SOC_KWH, s.executed_soc_end], color="#263b62")
        for bound in (cfg.SOC_MIN_KWH, cfg.SOC_MAX_KWH):
            axes[3].axhline(bound, color="#b34c4c", ls="--", lw=1)
        axes[3].set(ylabel="储电量（kWh）", xlabel="slot边界（0=0:00，36=6:00，72=12:00，108=18:00）")
        for ax in axes:
            ax.set_xlim(0, 144)
            ax.set_xticks(np.arange(0, 145, 24))
            for boundary in (36, 72, 108):
                ax.axvline(boundary, ls=":", color="#888888", lw=0.8)
        paths += save_figure(fig, directory, f"dispatch_{s.date}")

    labels = [row["policy"] for row in ablations]
    positions = np.arange(len(labels))
    colors = ["#168c91" if label == "0+6+12+18" else "#8192ad" for label in labels]
    fig, axes = plt.subplots(2, 2, figsize=(13, 9), layout="constrained")
    for ax, field, title, unit in ((axes[0, 0], "total_cost", "全年实际总费用", "万元"),
                                    (axes[0, 1], "emergency_kwh", "全年紧急购电量", "万kWh"),
                                    (axes[1, 0], "adjustment_cost", "全年调整净费用（负值为退款）", "万元")):
        values = np.array([row[field] for row in ablations]) / 10000
        ax.bar(positions, values, color=colors)
        ax.axhline(0, color="#555555", lw=0.8)
        ax.set(title=title, ylabel=unit)
        if field == "total_cost":
            ax.set_ylim(0, values.max() * 1.1)
            for x, value in zip(positions, values):
                ax.annotate(f"{value:.2f}", (x, value), xytext=(0, 4), textcoords="offset points",
                            ha="center", fontsize=9)
    axes[1, 1].bar(positions - 0.18, np.array([row["up_adjust_kwh"] for row in ablations]) / 10000,
                   0.36, label="增购", color="#c36a42")
    axes[1, 1].bar(positions + 0.18, np.array([row["down_adjust_kwh"] for row in ablations]) / 10000,
                   0.36, label="减购", color="#168c91")
    axes[1, 1].set(title="全年合同调整交易量", ylabel="万kWh")
    axes[1, 1].legend()
    for ax in axes.flat:
        ax.set_xticks(positions, labels, rotation=20)
        ax.set_xlabel("预报更新时间组合（小时）")
    fig.suptitle("问题3：更新时间消融实验（相同334天、相同结算口径）")
    paths += save_figure(fig, directory, "ablation_comparison")

    by_policy = {row["policy"]: row for row in ablations}
    daily = {policy: [row for row in policy_daily_rows if row["policy"] == policy] for policy in labels}
    baseline = np.cumsum([float(row["total_cost"]) for row in daily["0"]])
    fig, axes = plt.subplots(1, 2, figsize=(13, 5), layout="constrained")
    for policy in labels:
        if policy == "0": continue
        savings = baseline - np.cumsum([float(row["total_cost"]) for row in daily[policy]])
        axes[0].plot(dates, savings / 10000, label=policy)
    axes[0].axhline(0, color="#555555", lw=0.8)
    axes[0].set(title="相对仅0:00计划的累计节省", ylabel="累计节省（万元）", xlabel="日期")
    axes[0].legend(ncols=2, fontsize=9)
    axes[0].xaxis.set_major_locator(mdates.MonthLocator(interval=2))
    axes[0].xaxis.set_major_formatter(mdates.DateFormatter("%m月"))
    axes[0].set_xlim(dates[0], dates[-1])
    full = by_policy["0+6+12+18"]["total_cost"]
    values = [(by_policy[policy]["total_cost"] - full) / 10000 for policy in ("0+12+18", "0+6+18", "0+6+12")]
    axes[1].bar(["保留6:00", "保留12:00", "保留18:00"], values,
                 color=["#168c91" if value >= 0 else "#c36a42" for value in values])
    axes[1].axhline(0, color="#555555", lw=0.8)
    for x, value in enumerate(values):
        axes[1].annotate(f"{value * 10000:,.2f}元", (x, value),
                         xytext=(0, 6 if value >= 0 else -16), textcoords="offset points",
                         ha="center", fontsize=10, color="#168c91" if value >= 0 else "#c36a42")
    axes[1].margins(y=0.12)
    axes[1].set(title="单次更新的经济贡献", ylabel="删去该更新的费用 − 完整策略费用（万元）",
                xlabel="其余更新时间保持不变；正值表示该次更新节省费用")
    paths += save_figure(fig, directory, "ablation_value")

    fig, axes = plt.subplots(1, 2, figsize=(12, 5), layout="constrained")
    x = np.arange(4)
    for ax, prefix, title in ((axes[0], "", "各次预报的当日剩余时域"),
                              (axes[1], "common_18_24_", "统一比较18:00—24:00时域")):
        ax.bar(x - 0.18, [row[prefix + "MAE_kW"] for row in accuracy], 0.36, label="MAE", color="#168c91")
        ax.bar(x + 0.18, [row[prefix + "RMSE_kW"] for row in accuracy], 0.36, label="RMSE", color="#c36a42")
        ax.set(xticks=x, xticklabels=["0:00", "6:00", "12:00", "18:00"], title=title,
               ylabel="光伏功率误差（kW）", xlabel="预报发布时间")
        ax.legend()
        ax.set_ylim(0, max(row[prefix + "RMSE_kW"] for row in accuracy) * 1.3 or 1)
    fig.suptitle("问题3：预报精度分析（区间中点插值；2—12月实际数据评价）")
    return paths + save_figure(fig, directory, "forecast_accuracy")
