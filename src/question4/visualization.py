"""中文论文图：动态价格、同策略费用对比、典型日执行及价格波动关系。"""
from datetime import date
from pathlib import Path
import numpy as np

# 先加载公共绘图模块，统一Agg、中文字体、负号和缓存目录。
from ..plotting import plt, configure_chinese, save_figure
import matplotlib.dates as mdates
from . import config as cfg
from .price_loader import get_daily_price

BLUE, ORANGE, GREEN, RED = "#27649b", "#dc8526", "#34805d", "#c64a47"


def _date_axis(ax):
    ax.set_xlim(cfg.OUTPUT_DATES[0], cfg.OUTPUT_DATES[-1])
    ax.xaxis.set_major_locator(mdates.MonthLocator(bymonth=(2, 4, 6, 8, 10, 12)))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%m月"))


def plot_prices(model, prices, rows, directory):
    dates = [date.fromisoformat(row["date"]) for row in rows]
    values = np.array([get_daily_price(prices, day) for day in dates])
    fig, axes = plt.subplots(2, 1, figsize=(13, 8), gridspec_kw={"height_ratios": [1.5, 1]}, layout="constrained")
    heat = axes[0].imshow(values, aspect="auto", origin="lower", extent=(0, 144, 0, len(dates)), cmap="YlOrRd")
    ticks = [i for i, day in enumerate(dates) if day.day == 1]
    axes[0].set(yticks=ticks, yticklabels=[f"{dates[i].month}月" for i in ticks], xticks=np.arange(0,145,24),
                xlabel="日内 slot 序号（原始列顺序）", ylabel="日期", title="每日144点结算电价")
    fig.colorbar(heat, ax=axes[0], label="元/kWh", pad=0.02)
    axes[1].fill_between(dates, values.min(axis=1), values.max(axis=1), color=ORANGE, alpha=.2, label="日内最低—最高价")
    axes[1].plot(dates, values.mean(axis=1), color=BLUE, lw=1.2, label="日均价")
    axes[1].set(ylabel="元/kWh", title="逐日电价区间与均值")
    axes[1].legend(ncol=2)
    _date_axis(axes[1])
    fig.suptitle(f"问题{model}｜动态电价分布（2025年2—12月）", fontsize=16)
    save_figure(fig, directory, "dynamic_prices")


def plot_comparison(model, rows, fixed_rows, comparison, directory):
    dates = [date.fromisoformat(row["date"]) for row in rows]
    dynamic = np.array([row["total_cost"] for row in rows])
    fixed = np.array([row["total_cost"] for row in fixed_rows])
    fig, axes = plt.subplots(2, 2, figsize=(14, 9), layout="constrained")
    axes[0,0].plot(dates, fixed/1e4, lw=1, color=BLUE, label="固定电价")
    axes[0,0].plot(dates, dynamic/1e4, lw=1, color=ORANGE, alpha=.85, label="动态电价")
    axes[0,0].set(ylabel="万元/日", title="同策略下的逐日总费用")
    axes[0,0].legend(ncol=2)
    difference = np.cumsum(dynamic-fixed)/1e4
    axes[0,1].plot(dates, difference, color=RED)
    axes[0,1].axhline(0, color="gray", lw=.8)
    axes[0,1].set(ylabel="万元", title="累计费用变化（动态 − 固定）")
    for ax in axes[0]: _date_axis(ax)
    keys = ("plan_cost", "adjustment_cost", "emergency_cost", "total_cost")
    labels = ("初始计划费", "调整净费用", "紧急购电费", "总费用")
    x = np.arange(4)
    for offset, field, label, color in ((-.2, "fixed_price", "固定电价", BLUE), (.2, "dynamic_price", "动态电价", ORANGE)):
        bars = axes[1,0].bar(x+offset, [comparison[field][k]/1e4 for k in keys], width=.38, color=color, label=label)
        axes[1,0].bar_label(bars, fmt="%.1f", fontsize=9, padding=3)
    axes[1,0].axhline(0, color="gray", lw=.8)
    axes[1,0].set(xticks=x, xticklabels=labels, ylabel="万元", title="全年费用组成（调整净费用保留退款符号）")
    axes[1,0].margins(y=.16)
    for values, label, color in ((fixed_rows, "固定电价", BLUE), (rows, "动态电价", ORANGE)):
        axes[1,1].plot(dates, np.cumsum([r["emergency_kwh"] for r in values])/1e4, color=color, label=label)
    axes[1,1].set(ylabel="万kWh", title="累计实际紧急购电量")
    axes[1,1].legend(ncol=2)
    _date_axis(axes[1,1])
    policy = "0点全天计划" if model == "4-2" else "0、6、12点更新"
    cost = next(row for row in comparison["changes"] if row["metric"] == "total_cost")
    percent = f"{cost['relative_change']:+.2%}" if cost["relative_change"] is not None else "基线为零"
    fig.suptitle(f"问题{model}｜固定与动态电价比较 · {policy} · 总费用变化 {percent}", fontsize=16)
    save_figure(fig, directory, "annual_comparison")


def plot_dispatch(model, prices, results, directory):
    for result in results:
        if model == "4-2":
            s = result.plan
            day, initial, executed = s.date, s.grid_kwh, s.grid_kwh
            c, d, soc = s.charge_kwh, s.discharge_kwh, s.soc_end_kwh
            actual, emergency = result.actual_net_load_kwh, result.emergency_kwh
            hours = ()
        else:
            s = result.schedule
            day, initial, executed = s.date, s.initial_plan.grid_kwh, s.executed_grid
            c, d, soc = s.executed_charge, s.executed_discharge, s.executed_soc_end
            actual, emergency = result.actual_net_load, result.real_emergency
            hours = cfg.Q4_3_UPDATE_HOURS[1:]
        if day not in cfg.PAPER_DATES: continue
        t = np.arange(144)
        fig, axes = plt.subplots(4, 1, figsize=(14, 11), sharex=True, layout="constrained")
        axes[0].step(t, get_daily_price(prices, day), where="mid", color=ORANGE, label="目标日动态电价")
        axes[0].set(ylabel="元/kWh")
        axes[1].plot(t, actual, color="gray", lw=1, alpha=.8, label="实际净负荷")
        if model == "4-3": axes[1].plot(t, initial, color=BLUE, lw=1, ls="--", label="0点初始合同")
        axes[1].plot(t, executed, color=GREEN, lw=1.2, label="执行合同购电量" if model == "4-3" else "计划购电量")
        axes[1].fill_between(t, 0, emergency, color=RED, alpha=.4, label="实际紧急购电")
        axes[1].set(ylabel="kWh/10分钟")
        axes[1].margins(y=.18)
        axes[2].bar(t, c, width=1, color=BLUE, label="充电")
        axes[2].bar(t, -d, width=1, color=ORANGE, label="放电（向下）")
        axes[2].axhline(0, color="gray", lw=.6)
        axes[2].set(ylabel="kWh/10分钟")
        axes[3].plot(np.arange(145), np.r_[6000,soc], color=GREEN, label="执行SOC")
        axes[3].axhline(1200, color="gray", ls="--", lw=.8, label="SOC上下界")
        axes[3].axhline(10800, color="gray", ls="--", lw=.8)
        axes[3].set(ylabel="kWh", ylim=(0,12000), xlim=(0,144), xticks=np.arange(0,145,24),
                    xlabel="日内 slot 序号（slot 36、72 分别为模型6点、12点边界）" if hours else "日内 slot 序号（原始列顺序）")
        for ax in axes:
            for hour in hours: ax.axvline(hour*6, color="gray", ls=":", lw=1)
            ax.legend(loc="upper left", ncol=4, fontsize=9)
        extra = f"；调整净费用 {result.adjustment_cost:,.2f} 元" if model == "4-3" else ""
        fig.suptitle(f"问题{model}｜{day} 调度与结算\n全天总费用 {result.total_cost:,.2f} 元{extra}", fontsize=15)
        save_figure(fig, directory, f"dispatch_{day}")


def plot_relationships(model, rows, comparison, directory):
    x = np.array([row["price_range"] for row in rows])
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.7), layout="constrained")
    for ax, key, label in zip(axes, ("battery_throughput_kwh", "total_cost", "emergency_cost"),
                               ("电池充放电吞吐量（万kWh）", "全天总费用（万元）", "紧急购电费用（万元）")):
        ax.scatter(x, np.array([r[key] for r in rows])/1e4, s=14, alpha=.55, color=BLUE, edgecolors="none")
        correlation = comparison["price_range_pearson_correlation"][key]
        title = f"Pearson r = {correlation:.3f}" if correlation is not None else "常量序列，相关系数未定义"
        ax.set(xlabel="日内价差（元/kWh）", ylabel=label, title=title)
    fig.suptitle(f"问题{model}｜价格波动与运行指标（描述性相关，不表示因果关系）", fontsize=15)
    save_figure(fig, directory, "price_relationships")


def plot_results(model, prices, results, rows, fixed_rows, comparison, directory):
    configure_chinese()
    directory = Path(directory)
    plot_prices(model, prices, rows, directory)
    plot_comparison(model, rows, fixed_rows, comparison, directory)
    plot_dispatch(model, prices, results, directory)
    plot_relationships(model, rows, comparison, directory)
