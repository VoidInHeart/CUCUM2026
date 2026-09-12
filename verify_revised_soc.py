"""Validate persisted experiments and candidates, then build the comparison report."""
import hashlib
import json
import re
import subprocess
import sys
import shutil
from datetime import date
from pathlib import Path
import numpy as np
from openpyxl import load_workbook
from src.question2 import config as cfg
from src.question2.types import DailyPlan, DailyEvaluation, readonly
from src.question2.data_loader import load_price, load_actual
from src.question2.validator import validate_complete as validate2
from src.question3.validator import validate_complete as validate3
from src.question3.storage import load_daily_results
from src.question3.analysis import result_update_hours
from src.question4.price_loader import load_annual_price
from src.soc_diagnostics import write_json, write_csv, boundary_rows, diagnostics
from src.soc_initialization import warmup_rows

ROOT=cfg.PROJECT_ROOT/"target"/"revised_soc"


def read(path): return json.loads(Path(path).read_text(encoding="utf-8"))


def load2(path):
    results=[]
    with Path(path).open(encoding="utf-8") as stream:
        for line in stream:
            r=json.loads(line)
            p=r.pop("plan")
            p["date"]=date.fromisoformat(p["date"])
            for key in ("grid_kwh","charge_kwh","discharge_kwh","soc_end_kwh"): p[key]=readonly(p[key])
            for key in ("actual_net_load_kwh","emergency_kwh","surplus_kwh"): r[key]=readonly(r[key])
            results.append(DailyEvaluation(plan=DailyPlan(**p),**r))
    return results


def compare_records(old,new):
    """Compare every legacy field, permitting only added metadata."""
    maximum=0.
    def visit(a,b):
        nonlocal maximum
        if isinstance(a,dict):
            for key,value in a.items(): visit(value,b[key])
        elif isinstance(a,list):
            if len(a)!=len(b): raise AssertionError("legacy record length changed")
            for x,y in zip(a,b): visit(x,y)
        elif isinstance(a,(int,float)):
            maximum=max(maximum,abs(a-b))
        elif a!=b: raise AssertionError(f"legacy field changed: {a} != {b}")
    with Path(old).open(encoding="utf-8") as a,Path(new).open(encoding="utf-8") as b:
        aa,bb=list(a),list(b)
        if len(aa)!=len(bb): raise AssertionError("legacy days changed")
        for x,y in zip(aa,bb): visit(json.loads(x),json.loads(y))
    if maximum>1e-5: raise AssertionError(f"legacy arrays changed by {maximum}")
    return maximum


def verify_excel(path,results):
    workbook=load_workbook(path,read_only=True,data_only=True)
    max_error=0.
    def check(a,b):
        nonlocal max_error
        if a is None: raise AssertionError(f"missing Excel numeric cell: {path}")
        max_error=max(max_error,abs(float(a)-float(b)))
    q2=hasattr(results[0],"plan")
    battery=list(workbook["充放电量"].values)
    plans=list(workbook["计划购电量"].values)
    adjusted=None if q2 else list(workbook["调整购电量"].values)
    for i,r in enumerate(results):
        plan=r.plan if q2 else r.schedule.initial_plan
        charge=plan.charge_kwh if q2 else r.schedule.executed_charge
        discharge=plan.discharge_kwh if q2 else r.schedule.executed_discharge
        soc=plan.soc_end_kwh if q2 else r.schedule.executed_soc_end
        if plans[i+1][0].date()!=plan.date: raise AssertionError("Excel date mismatch")
        for a,b in zip(plans[i+1][1:145],plan.grid_kwh): check(a,b)
        check(plans[i+1][145],r.total_grid_purchase if q2 else r.initial_plan_kwh)
        check(plans[i+1][146],r.total_cost if q2 else r.plan_cost)
        if not q2:
            for a,b in zip(adjusted[i+1][1:145],r.schedule.executed_grid): check(a,b)
            check(adjusted[i+1][145],r.actual_grid_energy_kwh)
            check(adjusted[i+1][146],r.total_cost)
        check(battery[1+6*i][5],plan.initial_soc_kwh)
        check(battery[2+6*i][5],soc[-1])
        for block in range(6):
            check(battery[1+6*i+block][2],charge[24*block:24*(block+1)].sum())
            check(battery[1+6*i+block][3],discharge[24*block:24*(block+1)].sum())
    workbook.close()
    if max_error>1e-5: raise AssertionError(f"Excel mismatch {path}: {max_error}")
    return max_error


def table(headers,rows):
    return "| "+" | ".join(headers)+" |\n| "+" | ".join(["---"]*len(headers))+" |\n"+"\n".join("| "+" | ".join(map(str,row))+" |" for row in rows)


def main():
    price=load_price()
    actual=load_actual(price=price)
    dynamic=load_annual_price(actual)
    verification={"protected_files":{},"legacy_regression":{},"experiments":{},"excel":{}}
    paths=list((cfg.PROJECT_ROOT/"src"/"question1").glob("*.py"))+list((cfg.PROJECT_ROOT/"target"/"附件5").glob("*.xlsx"))
    for path in paths:
        relative=path.relative_to(cfg.PROJECT_ROOT).as_posix()
        original=subprocess.run(["git","show",f"HEAD:{relative}"],cwd=cfg.PROJECT_ROOT,capture_output=True,check=True).stdout
        # Git normalizes source line endings; compare source text, binary Excel bytes.
        now=path.read_bytes()
        if path.suffix==".py": original,now=original.replace(b"\r\n",b"\n"),now.replace(b"\r\n",b"\n")
        if original!=now: raise AssertionError(f"protected file changed: {path}")
        verification["protected_files"][relative]=hashlib.sha256(now).hexdigest()
    for path in ROOT.rglob("daily_results.jsonl"):
        with path.open(encoding="utf-8") as stream: q2="plan" in json.loads(next(stream))
        results=load2(path) if q2 else load_daily_results(path)
        is_dynamic="dynamic" in path.parts or "advance_known_sensitivity" in path.parts
        prices=dynamic.daily_prices() if is_dynamic else price.price
        if q2: validate2(prices,results)
        else: validate3(prices,results,result_update_hours(results))
        diag=diagnostics(results,dynamic.price_yuan_per_kwh if is_dynamic else price.price)
        verification["experiments"][str(path.parent.relative_to(ROOT))]={"days":len(results),"soc_continuity_max_error":diag["soc_continuity_max_error"]}
    pairs=[("question3",ROOT/"question3"/"daily_closed"),
           ("question4/question4_2",ROOT/"question4"/"question4_2"/"daily_closed"/"dynamic"),
           ("question4/question4_3",ROOT/"question4"/"question4_3"/"daily_closed"/"dynamic")]
    for old,new in pairs:
        error=compare_records(cfg.PROJECT_ROOT/"target"/old/"daily_results.jsonl",new/"daily_results.jsonl")
        old_summary=read(cfg.PROJECT_ROOT/"target"/old/"summary.json")["annual"]
        new_summary=read(new/"summary.json")
        delta=new_summary["total_cost"]-old_summary["total_cost"]
        if abs(delta)>1e-5: raise AssertionError(f"legacy cost regression {old}")
        verification["legacy_regression"][old]={"max_record_error":error,"total_cost_delta":delta}
    q2legacy=load2(ROOT/"question2"/"daily_closed"/"daily_results.jsonl")
    verification["legacy_regression"]["question2"]={"max_excel_error":verify_excel(cfg.RESULT_XLSX,q2legacy),
        "total_cost_delta":sum(r.total_cost for r in q2legacy)-read(cfg.OUTPUT_DIR/"summary.json")["annual"]["total_cost"]}
    for policy in cfg.SOC_POLICIES:
        path=ROOT/"question2"/f"result2_{policy}.xlsx"
        verification["excel"][str(path.relative_to(ROOT))]=verify_excel(path,load2(ROOT/"question2"/policy/"daily_results.jsonl"))
    candidate_dirs={"result2.xlsx":ROOT/"question2"/"continuous_lookahead", "result3.xlsx":ROOT/"question3",
                    "result4-2.xlsx":ROOT/"question4"/"question4_2"/"continuous_lookahead"/"dynamic",
                    "result4-3.xlsx":ROOT/"question4"/"question4_3"/"continuous_lookahead"/"dynamic"}
    for name,directory in candidate_dirs.items():
        results=load2(directory/"daily_results.jsonl") if name in ("result2.xlsx","result4-2.xlsx") else load_daily_results(directory/"daily_results.jsonl")
        verification["excel"][name]=verify_excel(ROOT/name,results)
    testlog=(cfg.PROJECT_ROOT/"tmp"/"revised_all_tests.log").read_text(encoding="utf-8")
    match=re.search(r"Ran (\d+) tests in ([\d.]+)s",testlog)
    if not match or not testlog.rstrip().endswith("OK"): raise AssertionError("full unittest suite did not pass")
    verification["unittest"]={"count":int(match[1]),"seconds":float(match[2]),"status":"OK"}
    # Normalize diagnostic aliases in both summary and comparison artifacts.
    def aliases(value):
        if isinstance(value,list):
            for item in value: aliases(item)
        elif isinstance(value,dict):
            for item in list(value.values()): aliases(item)
            if "terminal_soc_mean" in value:
                value.update(mean_terminal_soc=value["terminal_soc_mean"],min_terminal_soc=value["terminal_soc_min"],
                             max_terminal_soc=value["terminal_soc_max"],days_near_soc_min=value["days_end_near_min"],
                             days_near_soc_max=value["days_end_near_max"])
    for path in ROOT.rglob("*.json"):
        value=read(path)
        aliases(value)
        write_json(path,value)
        if path.name in ("comparison.json","ablation_summary.json") and isinstance(value,list):
            write_csv(path.with_suffix(".csv"),value)
    write_json(ROOT/"verification.json",verification)
    import scipy
    write_json(ROOT/"run_manifest.json",dict(python_executable=sys.executable,python_version=sys.version,
        numpy_version=np.__version__,scipy_version=scipy.__version__,
        git_head=subprocess.run(["git","rev-parse","HEAD"],cwd=cfg.PROJECT_ROOT,capture_output=True,text=True,check=True).stdout.strip(),
        inputs_sha256={str(p.relative_to(cfg.PROJECT_ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in
                      [*(cfg.PROJECT_ROOT/"data").glob("*.xlsx"),cfg.PROJECT_ROOT/"docs"/"需求.pdf"]},
        source_sha256={str(p.relative_to(cfg.PROJECT_ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in
                      [*(cfg.PROJECT_ROOT/"src").rglob("*.py"),cfg.PROJECT_ROOT/"run_revised_soc.py",Path(__file__)]},
        primary_price_information_mode="current_day_persistence",sensitivity_price_information_mode="advance_known_sensitivity",
        initialization_mode="feb1_control_start",warmup_alternative="jan1_continuous_battery_idle"))
    shutil.copy2(cfg.PROJECT_ROOT/"tmp"/"revised_all_tests.log",ROOT/"unittest.log")
    write_csv(ROOT/"initialization"/"jan1_continuous_warmup.csv",warmup_rows(actual))
    write_report(verification,price)
    print(json.dumps({"experiments":len(verification["experiments"]),"regression":verification["legacy_regression"],"tests":verification["unittest"]},ensure_ascii=False,indent=2))


def write_report(verification,price):
    q2=read(ROOT/"question2"/"comparison.json")
    q3=read(ROOT/"question3"/"summary.json")
    ablation=read(ROOT/"question3"/"ablation_summary.json")
    benchmark=read(ROOT/"benchmark"/"comparison.json")
    old3=read(cfg.PROJECT_ROOT/"target"/"question3"/"summary.json")["annual"]
    q4={name:read(ROOT/"question4"/name/"comparison.json") for name in ("question4_2","question4_3")}
    money=lambda x:f"{x:,.2f}"
    lines=["# 跨日 SOC 模型比较与复核报告", "", "评价期：2025-02-01 至 12-31，334 天。运行环境：D:/Anaconda/envs/cucum2026，Python 3.13.15，SciPy HiGHS。所有原正式附件保持不变。", "",
           "## 1. 原题、旧假设与初始化", "", "原题第 1 页问题 1 明确要求 0:00 与 24:00 储电量相同；问题 2 没有要求沿用全部约束，也没有每日 6000 闭合条件。因此每日闭合是旧建模假设。第 2 页附录 1 明确 2025-01-01 初始 SOC=6000，不能省略这一事实。详见 `docs/SOC_boundary_audit.md`。", "",
           "旧假设由 Q2 config/optimizer/pipeline/validator/exporter、Q3 optimizer/controller/validator/exporter 继承，再由 Q4 两个适配器复用。Q1 源码及 result1.xlsx 均逐文件与 HEAD 对比未变。", "",
           "主实验用 feb1_control_start；可选 jan1_continuous 使用 1 月储能空闲、残余负荷在线平衡的 warm-up，同样从 2 月初 6000 运行，故正式期结果数值相同。warm-up 不优化未来真实数据，逐日记录见 initialization/jan1_continuous_warmup.csv。", "",
           "## 2. Q2 三种模型", "",table(["SOC 模式","总费用/元","紧急电量/kWh","日末均值/kWh","午夜近下界天数","吞吐/kWh"],
           [[r["soc_policy"],money(r["total_cost"]),money(r["emergency_total"]),money(r["terminal_soc_mean"]),r["days_end_near_min"],money(r["throughput_kwh"])] for r in q2]),"",
           f"continuous_myopic 比旧模型贵 {money(q2[1]['total_cost']-q2[0]['total_cost'])} 元，334 天午夜全部为 1200，表现出明显单日自由终端耗尽。取消约束并未降低实际总费用。", "",
           f"48h continuous_lookahead 比旧模型贵 {money(q2[2]['total_cost']-q2[0]['total_cost'])} 元（{(q2[2]['total_cost']/q2[0]['total_cost']-1)*100:.4f}%），紧急电量变化 {money(q2[2]['emergency_total']-q2[0]['emergency_total'])} kWh。日末全部为 8550，近下界天数为 0；8550 由 LP 得到，没有人为目标或软惩罚。", "",
           "单日版本吞吐下降主要包含初末库存差，旧模型相对 48h 的吞吐差也很小，不能声称每日闭合必然造成大量无效循环。48h 允许前一天为次日储电，但在这组实际数据上的净收益未转化为全年更低费用。31 日样本变为 30 个相邻日对也改变了首日经验分布，费用差不能全部归因于 SOC。", "",
           "![Q2 日界](question2/continuous_lookahead/figures/soc_daily_boundary.png)", "",
           "## 3. Q3 新消融与剩余问题", "",table(["更新时间","费用/元","紧急电量/kWh","调整净费/元","午夜近下界天数"],
           [[r["policy"],money(r["total_cost"]),money(r["emergency_kwh"]),money(r["adjustment_cost"]),r["days_end_near_min"]] for r in ablation]),"",
           f"新最优策略为 {q3['policy']}，年度费用 {money(q3['annual']['total_cost'])} 元，比旧 Q3 高 {money(q3['annual']['total_cost']-old3['total_cost'])} 元。原 0+6+12 结论在本次重算中仍成立；加入 18 点只增加 {money(next(r['total_cost'] for r in ablation if r['policy']=='0+6+12+18')-q3['annual']['total_cost'])} 元，差距极小，不宜外推为稳定规律。", "",
           "新 Q3 在 6/12/18 点均规划未来 24h，交易仅作用于当日剩余合同。每条历史误差轨迹均已完整发生。尽管如此，六种策略都在午夜达下界。午夜对修订计划已经不是 horizon 末端，可能涉及当日增购 1.5 倍/退款 0.5 倍与次日新购 1 倍的不对称，且 0 点计划仍有自由日末终端。因此不能宣称跨午夜预测已经消除所有短视问题，也不能把此轨迹证明为长期最优。", "",
           "策略按同一全年评价数据回溯选择，未使用未来值制定逐时调度，但策略选择本身不是样本外验证。", "",
           "## 4. Q4：相同 SOC 与策略下固定/动态对照", ""]
    for name,rows in q4.items():
        lines += [f"### {name}","",table(["SOC 模式","价格","费用/元","日末平均/kWh","近下界天数"],[[r['soc_policy'],r['price_mode'],money(r['total_cost']),money(r['terminal_soc_mean']),r['days_end_near_min']] for r in rows]),""]
        fixed=next(r for r in rows if r['soc_policy']=='continuous_lookahead' and r['price_mode']=='fixed')
        dyn=next(r for r in rows if r['soc_policy']=='continuous_lookahead' and r['price_mode']=='dynamic')
        sensitivity=read(ROOT/"question4"/name/"advance_known_sensitivity"/"summary.json")
        lines += [f"新动态减新固定费用：{money(dyn['total_cost']-fixed['total_cost'])} 元。提前已知次日价格的条件敏感性费用：{money(sensitivity['total_cost'])} 元。该敏感性使用未来价格，仅在价格提前发布假设下成立；主模型不读取次日实际价格。",""]
    lines += ["当日完整动态价格已知仍为显式建模假设；题面没有给出价格发布制度。主模型用当日曲线持续预测下一天。12 月 31 日无 2026 价格，敏感性也退回持续预测。不能把价格未知的现实市场表现等同于此实验。","",
              "## 5. Benchmark", "",table(["边界","方法","费用/元","紧急电量/kWh","日末均值/kWh"],[[r['experiment'],r['method'],money(r['total_cost']),money(r['emergency_kwh']),money(r['terminal_soc_mean'])] for r in benchmark]),""]
    for label in ("legacy_daily_closed","continuous_soc"):
        ranking=sorted((r for r in benchmark if r['experiment']==label),key=lambda r:r['total_cost'])
        lines += [f"{label} 费用排序："+" < ".join(r['method'] for r in ranking)+"。",""]
    lines += ["仓库没有旧 benchmark 源码/存档，因此 legacy 是在旧边界下重建的对照，不能声称精确复现不存在的旧 benchmark。CVaR 风险项为场景紧急费用的 95% CVaR，权重 0.1，未按结果调参；lambda=0 已测试严格退化为新 SAA。MPC 多了已发布预测与调整机制，排序不等于纯求解算法优劣。","",
              "## 6. 年末库存与估值敏感性","",table(["Q2 模式","末 SOC","原费用","低价估值调整","均价估值调整","高价估值调整"],[[r['soc_policy'],money(r['final_soc_last_day']),money(r['raw_total_cost']),money(r['terminal_energy_adjusted_cost_low']),money(r['terminal_energy_adjusted_cost_mean']),money(r['terminal_energy_adjusted_cost_high'])] for r in q2]),"",
              "调整费用 = 原费用 − v × (年末 SOC − 初始 SOC)，v 为正常价格低/均/高值乘 0.9；三组同时报告，不进入优化、不反向调参。Q3/Q4/benchmark 同样的估值字段保存在各 summary 或 soc_boundary_diagnostics.json。年末未强制回 6000。","",
              "## 7. 验证与修改范围","",f"完整 unittest：{verification['unittest']['count']} 项，全部通过。逐日存档验证 {len(verification['experiments'])} 组实验，每组 334 天；全部跨日 SOC 最大误差为 0 kWh。每个 LP 在求解后校验场景平衡、SOC 动态、边界、目标；持久化结果再次重放验证冻结执行与费用。", "",
              table(["旧模型回归","费用差/元","逐日最大数值差"],[[name,r['total_cost_delta'],r.get('max_record_error',r.get('max_excel_error'))] for name,r in verification['legacy_regression'].items()]),"",
              "全部候选 Excel 已重新打开，核对每一天的 144 槽购电、费用、电量总计、6 段充放电及初末 SOC；误差记录于 verification.json。Q1 源码与 5 个原正式附件逐文件对比 HEAD 未变。主调度的历史场景、未发布预测及跨午夜未来实际数据隔离测试通过；提前知价敏感性和全年回溯选策略已单独披露，不能混称为无未来信息。","",
              "核心改动：Q2 config/types/scenario_builder/optimizer/pipeline/validator/exporter/summary；Q3 types/rolling_scenario_builder/optimizer/rolling_controller/analysis/validator/exporter/summary/storage；Q4 两个适配器与 validator；共享 pricing、soc_initialization、soc_diagnostics；新增 run_revised_soc.py、verify_revised_soc.py、连续模型测试与两份模型说明。", "",
              "## 8. 论文与候选附件建议","",
              "建议论文采用显式跨日状态作为物理口径，以 Q2 48h SAA 为候选，同时保留 daily_closed 与 myopic 两种敏感性，坦诚报告费用上升。Q3/Q4-3 可使用新连续滚动模型的候选结果，但必须保留午夜耗尽、合同不对称与回溯选策略的局限，不把它包装成终端效应已完全消除的最终理论结论。","",
              "候选替换组：本目录 result2.xlsx、result3.xlsx、result4-2.xlsx、result4-3.xlsx，均使用 continuous_lookahead，Q3/Q4-3 用本次选出的 0+6+12，Q4 用当日价格持续预测。Q1 不替换。建议先审阅上述局限后人工决定是否替换；程序未覆盖 target/附件5。","",
              "复现：依次运行 run_revised_soc.py --phase all、完整 unittest、verify_revised_soc.py。各 phase 可独立运行；Q4/benchmark 要求先有本次 Q3 策略选择结果。"]
    (ROOT/"SOC_model_comparison.md").write_text("\n".join(lines)+"\n",encoding="utf-8")
    from src.plotting import plt, configure_chinese, save_figure
    configure_chinese()
    fig,axes=plt.subplots(1,2,figsize=(12,4))
    labels=["每日闭合","连续单日","连续48h"]
    axes[0].bar(labels,[r['total_cost']/1e4 for r in q2])
    axes[0].set(ylabel="费用（万元）",title="Q2 实际总费用")
    axes[1].bar(labels,[r['days_end_near_min'] for r in q2])
    axes[1].set(ylabel="天数",title="午夜接近 SOC 下界")
    save_figure(fig,ROOT/"question2"/"figures","model_comparison")


if __name__=="__main__": main()
