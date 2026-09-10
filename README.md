# 微网日前购电策略：问题1与问题2

使用 Python 3.13 与 SciPy HiGHS。Windows PowerShell 在项目根目录执行：

```powershell
& 'D:\Anaconda\envs\cucum2026\python.exe' -m pip install -r requirements.txt
& 'D:\Anaconda\envs\cucum2026\python.exe' run_question1.py
& 'D:\Anaconda\envs\cucum2026\python.exe' run_question2.py
```

也可从任意目录使用运行脚本的绝对路径；数据路径根据源码位置定位。

问题1只生成图表、保留现有正式 Excel：

```powershell
& 'D:\Anaconda\envs\cucum2026\python.exe' run_question1.py --plot-only
```

问题2默认串行求解全部334天，逐日打印进度，生成 Excel、论文摘要和图表。
`--no-plots` 可跳过图表；`--debug` 显示独立约束校验残差。

## 输入和输出

需要自行保留官方输入及模板：

- 问题1：`data/附件1.xlsx`、`target/附件5/result1.xlsx`。
- 问题2：`data/附件1.xlsx`、`data/附件2.xlsx`、`target/附件5/result2.xlsx`。

程序不重新创建缺失的官方模板。输入、题目文档与运行结果不纳入代码提交；
`target/` 和 `tmp/` 已被 Git 忽略。

| 输出 | 内容 |
| --- | --- |
| `target/附件5/result1.xlsx` | 问题1正式结果 |
| `target/question1/figures/` | 调度/SOC、电价与分段充放电图 |
| `target/附件5/result2.xlsx` | 问题2正式结果，三个官方工作表 |
| `target/question2/summary.json` | 2—12月汇总，四个指定日期的表1/2/3数据 |
| `target/question2/daily_metrics.csv` | 334天计划、紧急和实际总购电量与费用 |
| `target/question2/figures/` | 全年趋势、月度费用、紧急购电热力图和四个指定日期调度图 |

图表同时保存 PNG 和矢量 PDF。显式使用微软雅黑，并依次回退至黑体、Noto Sans CJK SC、
思源黑体或宋体；没有可用中文字体会报错。设置 `axes.unicode_minus=False`，确保负数可显示。

## 问题2模型与结果口径

- 每天只向计划求解器传入此前31天的完整净负荷曲线，场景等权。
- 第一阶段购电、充电、放电、SOC 在场景之间共享；紧急购电、富余电量是第二阶段变量。
- 每日初末 SOC 均为6000 kWh；效率、功率及 SOC 边界复用问题1参数。
- 计划求解器不接收全年真实数据。计划数组冻结后，再由评价模块接收当天实际净负荷。
- LP 的全部场景平衡在二阶段变量丢弃前独立校验，实际结算也独立校验。
- `计划购电量` 表 B:EO 是计划量；EP 是计划量加实际紧急量；EQ 是计划费加5倍电价的紧急购电费。
- 正式费用不含 `1e-8` 的吞吐量辅助惩罚。`expected_objective` 包含该项，仅作模型诊断。
- 时间按原始位置对应，图表用 slot 序号；论文表1和紧急区间从模板标签查找或拼接，保留 `+1`。
- 充放电表按每24个slot累计，每日6行；连续紧急区间按 `>1e-6 kWh` 合并。
- 任何一天求解或验证失败都会停止，不替换正式结果。模板导出使用同目录临时文件和原子替换。

CSV 字段 `planned_grid_total`、`emergency_total`、`total_grid_purchase` 的单位为 kWh；
`planned_cost`、`emergency_cost`、`total_cost` 的单位为元。全年指标实际对应正式输出期2—12月，
1月仅作为初始历史窗口。

## 验证

```powershell
& 'D:\Anaconda\envs\cucum2026\python.exe' -X utf8 -m unittest discover -s tests -v
```

测试包含问题1参考值、防未来泄漏扰动、已知最优解、储能和场景平衡、5倍结算、
午夜区间合并、全年334日求解、模板展开及原子保存失败保护。测试中的 Excel 写入均在临时目录。
问题3和问题4未实现。
