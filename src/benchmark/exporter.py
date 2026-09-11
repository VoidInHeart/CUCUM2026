"""CSV/JSON、可复核环境信息和由实际结果生成的实验说明。"""
from dataclasses import asdict
from datetime import datetime, timezone
import csv
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import tempfile

from . import config as cfg
from .metrics import summarize, add_relative_changes
from .validator import require_baselines, sha256


def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def write_csv(path, rows, fieldnames=None):
    fields = fieldnames or list(dict.fromkeys(key for row in rows for key in row))
    with Path(path).open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def provenance():
    root = cfg.physical.PROJECT_ROOT
    files = [*sorted((root / "src").rglob("*.py")), root / "run_benchmark.py", root / "requirements.txt"]
    def git(*args):
        result = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, encoding="utf-8", check=True)
        return result.stdout.strip()
    return {"created_at_utc": datetime.now(timezone.utc).isoformat(),
            "python": sys.version, "executable": sys.executable, "platform": platform.platform(),
            "processor": platform.processor(), "logical_cpu_count": os.cpu_count(),
            "packages": {name: importlib.metadata.version(name) for name in ("numpy", "scipy", "pandas", "openpyxl", "matplotlib")},
            "git_head": git("rev-parse", "HEAD"), "git_status": git("status", "--short"),
            "input_sha256": {str(path.relative_to(root)).replace("\\", "/"): sha256(path)
                             for path in (cfg.physical.PRICE_XLSX, cfg.physical.ACTUAL_XLSX, root / "data" / "附件3.xlsx")},
            "source_sha256": {str(path.relative_to(root)).replace("\\", "/"): sha256(path) for path in files},
            "design": {"dates": [str(cfg.OUTPUT_DATES[0]), str(cfg.OUTPUT_DATES[-1])], "days": len(cfg.OUTPUT_DATES),
                       "history_window_days": cfg.physical.HISTORY_WINDOW_DAYS, "price": "attachment1_fixed_time_of_use",
                       "slots_per_day": cfg.physical.N_SLOTS, "main_alpha": cfg.MAIN_ALPHA, "main_lambda": cfg.MAIN_LAMBDA,
                       "mpc_update_hours": list(cfg.Q3_FINAL_UPDATE_HOURS),
                       "sensitivity_alphas": cfg.SENSITIVITY_ALPHAS, "sensitivity_lambdas": cfg.SENSITIVITY_LAMBDAS,
                       "physical_parameters": {key: getattr(cfg.physical, key) for key in (
                           "SOC_MIN_KWH", "SOC_MAX_KWH", "INITIAL_SOC_KWH", "FINAL_SOC_KWH", "ETA_CHARGE", "ETA_DISCHARGE",
                           "BATTERY_ENERGY_MAX_PER_SLOT_KWH", "EPS_THROUGHPUT", "EMERGENCY_PRICE_MULTIPLIER", "TIME_STEP_HOURS")}},
            "runtime_scope": "time.perf_counter; serial 334-day scenario construction, optimization, actual settlement, validation and daily records; excludes shared input loading, baseline comparison, statistics, export and plots; no day-result cache"}


def result_table(rows):
    lines = ["| 方法 | 总费用/元 | 合同费用/元 | 紧急费用/元 | 紧急量/kWh | 紧急天数 | 日费用CVaR95/元 | 秒 |",
             "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for row in rows:
        lines.append(f"| {row['method']} | {row['total_cost']:.2f} | {row['contract_cost']:.2f} | {row['emergency_cost']:.2f} | "
                     f"{row['emergency_kwh']:.2f} | {row['emergency_days']} | {row['cvar95_daily_cost']:.2f} | {row['total_runtime_seconds']:.3f} |")
    return "\n".join(lines)


def summary_markdown(comparison, sensitivity, metadata, baselines):
    env = metadata
    lines = ["# 固定分时电价算法对比实验", "",
             f"评估期：{cfg.OUTPUT_DATES[0]} 至 {cfg.OUTPUT_DATES[-1]}，{len(cfg.OUTPUT_DATES)}天；1月只提供初始历史窗口。",
             "电价、实际数据、储能参数、5倍紧急购电结算均复用原工程；时间维度保持附件的144个10分钟slot，不聚合或重排。", "",
             "## 实验环境", "", f"- Python：{env['python'].splitlines()[0]}", f"- 可执行文件：`{env['executable']}`",
             f"- 系统：{env['platform']}；CPU：{env['processor']}；逻辑核数：{env['logical_cpu_count']}",
             f"- 依赖：{', '.join(f'{k}={v}' for k, v in env['packages'].items())}",
             f"- 基础提交：`{env['git_head']}`；本次源码和输入SHA-256见 `manifest.json`。", "",
             "## 方法与信息集合", "",
             "1. DET：此前31天每个slot净负荷的均值，复用问题1确定性储能LP。",
             "2. Q80：相同窗口的 `np.quantile(..., 0.8, axis=0, method=\"linear\")` 曲线，复用同一LP。这是具有经济解释的分位数启发式，不等价于完整随机规划。",
             "3. SAA：直接调用问题2年度流水线、31日等权场景求解器、结算和验证。",
             "4. CVaR95-L50：在问题2原约束矩阵上增加eta及每场景xi，alpha=0.95、lambda=0.50预先固定。lambda=0直接调用原SAA；12组灵敏度结果不用于重选主参数。",
             "5. SAA-MPC：直接调用问题3正式0+6+12控制器，6点、12点修订，18点预报不参与。", "",
             "前四种方法是严格公平的0:00日前计划比较，求解器只接收目标日前31天历史数据。",
             "SAA-MPC属于日内信息更新价值实验：0点计划已使用问题3当日已发布PV预报，6点和12点又接收新预报及合法已观测锚点。",
             "因此SAA-MPC相对SAA的差异包含预报信息、场景构造、滚动修订和交易规则的共同作用，不能完全归因于优化算法，也不能仅归因于两次日内更新。", "",
             "## 费用、风险与计时口径", "",
             "静态方法先冻结计划，再按真实净负荷计算 `E=max(N_real-(G+D-C),0)`。计划费加5倍电价紧急费得到实际总费用。",
             "MPC沿用原交易现金流：增购1.5倍、减购0.5倍退款。统一 `contract_cost=plan_cost+adjustment_cost`、`total_cost=contract_cost+emergency_cost`，静态方法调整费为0。",
             "CVaR优化损失是每个历史场景全天紧急购电费用 `L_s=5*sum(q_t*E_st)`，不是总费用或单slot损失。",
             "优化目标为计划费 + (1-lambda)*E[L] + lambda*(eta+sum(pi_s*xi_s)/(1-alpha)) + 原吞吐量微小惩罚；正式结算不含该惩罚。",
             "历史分布只有31个等权场景：alpha=0.90、0.95分别对应最差3.1、1.55个场景的概率质量；alpha=0.99的CVaR等于样本最大损失。",
             "p95以NumPy linear分位数计算；CVaR95使用最差5%经验概率质量的平均值，边界日按剩余权重计入（334天对应16.7天），不简单平均所有超过p95的日期。",
             "所有实际尾部指标只在全年执行后离线统计，不反馈优化。紧急天数沿用原模型：至少一个slot紧急量大于原EMERGENCY_TOL。",
             "吞吐量=交流侧充电量+放电量。变化率=(方法-基线)/基线×100%，负值表示减少；零分母或缺失参考方法记为JSON null/CSV空白。",
             "计时使用time.perf_counter，覆盖每种方法完整334天的场景构造、求解、结算、校验和统一日记录；排除公共加载、基线比对、汇总及出图。",
             "各方法串行重新求解，不复用日结果缓存；相同CVaR主参数在灵敏度表中直接引用主实验同一轮完整运行。运行时间是本机单次测量，含首次结构构造开销。", "",
             "## 主结果", "", result_table(comparison), "", "## 由本次实际结果得出的观察", ""]
    static = [row for row in comparison if row["method"] != "SAA-MPC"]
    if static:
        lowest = min(static, key=lambda r: r["total_cost"])
        lines.append(f"当前已运行的静态方法中，实际总费用最低的是{lowest['method']}，为{lowest['total_cost']:.2f}元。这是该年度样本外结果，不构成一般性优越保证。")
    refs = {row["method"]: row for row in comparison}
    if "SAA" in refs:
        for name in ("DET", "Q80", "CVaR95-L50", "SAA-MPC"):
            if name in refs:
                row = refs[name]
                lines.append(f"{name}相对SAA：总费用变化{row['total_cost_change_vs_saa_pct']:+.3f}%；紧急购电量变化{row['emergency_kwh_change_vs_saa_pct']:+.3f}%；日费用CVaR95变化{row['cvar95_daily_cost_change_vs_saa_pct']:+.3f}%。")
    lines += ["", "## CVaR灵敏度（仅作风险—收益分析）", ""]
    if sensitivity:
        lines += [result_table(sensitivity), ""]
        for key, label in (("total_cost", "实际总费用/元"), ("emergency_kwh", "紧急量/kWh"), ("cvar95_daily_cost", "日费用CVaR95/元")):
            values = [row[key] for row in sensitivity]
            lines.append(f"12组参数的{label}范围为{min(values):.2f}—{max(values):.2f}。")
        lines.append("这些范围是描述性结果；不要求样本外实际费用随lambda单调变化，也不据此更换CVaR95-L50主参数。")
    else:
        lines.append("本次使用--skip-sensitivity，未运行灵敏度实验。")
    lines += ["", "## 基线复现与产物", ""]
    for method, report in baselines.items():
        cost = report["annual"]["total_cost"]
        lines.append(f"- {method}：官方总费用{cost['official']:.9f}元，重算{cost['computed']:.9f}元，绝对误差{cost['absolute_error']:.3g}元；全部{report['daily_rows_checked']}日指标通过，最大日指标误差{report['max_daily_absolute_error']:.3g}。")
    lines += ["- 基线容差、年度逐项对照和官方输入哈希见 `baseline_validation.json`。",
              "- 正式结果保护检查见 `preservation.json`；本框架只在target/benchmark写出。",
              "- `comparison.csv/json`、`daily_metrics.csv`、`runtime.csv`、`cvar_sensitivity.csv/json`、`cvar_sensitivity_daily_metrics.csv`保存完整指标。",
              "- 图表位于 `figures/`，PNG及矢量PDF使用同一数据；MPC用独立标记表示信息集合不同。",
              "- 新增测试覆盖lambda=0、人工最优值、静态防泄漏、18点预报隔离和全年基线；完整测试须运行 `python -X utf8 -m unittest discover -s tests -v`，实际执行日志单独保存，不在报告中预写测试成功。", ""]
    return "\n".join(lines)


def export_results(runs, sensitivity_runs, baselines, metadata, preservation, *, no_plots=False, directory=cfg.OUTPUT_DIR):
    require_baselines(baselines)
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    comparison = add_relative_changes([summarize(run) for run in runs])
    sensitivity = []
    for alpha, weight, run in sensitivity_runs:
        sensitivity.append({"alpha": alpha, "lambda": weight, **summarize(run)})
    sensitivity = add_relative_changes(sensitivity, comparison)
    # 先全部生成到临时目录；基线、数据或绘图失败时不发布不完整的新表。
    with tempfile.TemporaryDirectory(prefix=".staging-", dir=directory) as temporary:
        stage = Path(temporary)
        write_csv(stage / "comparison.csv", comparison)
        write_json(stage / "comparison.json", comparison)
        write_csv(stage / "daily_metrics.csv", [asdict(row) for run in runs for row in run.daily])
        runtime = [{key: row[key] for key in ("method", "days", "total_runtime_seconds", "mean_runtime_per_day_ms")} for row in comparison]
        write_csv(stage / "runtime.csv", runtime)
        write_csv(stage / "cvar_sensitivity.csv", sensitivity, list(sensitivity[0]) if sensitivity else ["alpha", "lambda", "method"])
        write_json(stage / "cvar_sensitivity.json", sensitivity)
        sensitivity_daily = [{"alpha": alpha, "lambda": weight, **asdict(row)} for alpha, weight, run in sensitivity_runs for row in run.daily]
        write_csv(stage / "cvar_sensitivity_daily_metrics.csv", sensitivity_daily,
                  list(sensitivity_daily[0]) if sensitivity_daily else ["alpha", "lambda", "method", "date"])
        write_json(stage / "baseline_validation.json", baselines)
        write_json(stage / "preservation.json", preservation)
        (stage / "experiment_summary.md").write_text(summary_markdown(comparison, sensitivity, metadata, baselines), encoding="utf-8")
        if not no_plots:
            from .visualization import plot_results
            plot_results(comparison, sensitivity, baselines, stage / "figures")
        metadata = {**metadata, "methods": [run.method for run in runs], "sensitivity_count": len(sensitivity),
                    "artifacts_sha256": {path.relative_to(stage).as_posix(): sha256(path) for path in sorted(stage.rglob("*")) if path.is_file()}}
        write_json(stage / "manifest.json", metadata)
        for path in sorted(stage.rglob("*")):
            if path.is_file() and path.name != "manifest.json":
                destination = directory / path.relative_to(stage)
                destination.parent.mkdir(parents=True, exist_ok=True)
                os.replace(path, destination)
        # 清理上轮图名仅限框架自身六类已知图，防止--no-plots/跳过灵敏度时展示旧数据。
        for name in cfg.FIGURE_NAMES:
            for suffix in ("png", "pdf"):
                relative = f"figures/{name}.{suffix}"
                if relative not in metadata["artifacts_sha256"]:
                    (directory / relative).unlink(missing_ok=True)
        (directory / "figures").mkdir(exist_ok=True)
        os.replace(stage / "manifest.json", directory / "manifest.json")
    return comparison, sensitivity
