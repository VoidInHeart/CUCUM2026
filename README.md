# 微网购电策略：问题1、问题2与问题3

使用 Python 3.13 与 SciPy HiGHS。Windows PowerShell 在项目根目录执行：

```powershell
& 'D:\Anaconda\envs\cucum2026\python.exe' -m pip install -r requirements.txt
& 'D:\Anaconda\envs\cucum2026\python.exe' run_question1.py
& 'D:\Anaconda\envs\cucum2026\python.exe' run_question2.py --strategy compare --no-plots
& 'D:\Anaconda\envs\cucum2026\python.exe' run_question3.py
```

也可从任意目录使用运行脚本的绝对路径；数据路径根据源码位置定位。

问题1只生成图表、保留现有正式 Excel：

```powershell
& 'D:\Anaconda\envs\cucum2026\python.exe' run_question1.py --plot-only
```

问题2默认使用固定原计划购电合同的逐10分钟因果储能MPC；`--strategy baseline` 精确复现
原冻结储能结果，`--strategy compare` 用同一组合同并列回测 A0/A1，并输出消融比较。
程序串行求解全部334天，逐日打印进度，生成 Excel、论文摘要和图表。
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
| `target/question2/ablation_summary.json/.csv` | A0冻结储能与A1因果储能的年度费用差异 |
| `target/question2/*_daily_metrics.csv` | compare模式下两种策略的逐日结算明细 |
| `target/question2/figures/` | 全年趋势、月度费用、紧急购电热力图和四个指定日期调度图 |

图表同时保存 PNG 和矢量 PDF。显式使用微软雅黑，并依次回退至黑体、Noto Sans CJK SC、
思源黑体或宋体；没有可用中文字体会报错。设置 `axes.unicode_minus=False`，确保负数可显示。

## 问题2模型与结果口径

- 每天只向计划求解器传入此前31天的完整净负荷曲线，场景等权。
- 第一阶段购电、充电、放电、SOC 在场景之间共享；紧急购电、富余电量是第二阶段变量。
- 每日初末 SOC 均为6000 kWh；效率、功率及 SOC 边界复用问题1参数。
- A0计划求解器不接收全年真实数据并冻结全部数组。A1保持同一个0:00购电合同，在每个slot只加入
  当期实际净负荷；未来基准来自0:00冻结计划隐含的净供能曲线，滚动LP按5倍逐时电价优化，
  只执行首步并保证每日终端SOC仍为6000。
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
问题3另包含预报分组与中点插值、未发布预报隔离、历史误差防泄漏、滚动SOC连续、
执行冻结、调整退款、四张官方表及导出失败保护。问题4另检验动态电价日期/时段对齐、
逐时目标系数与结算、固定电价回归、选定更新策略和官方结果失败保护。

## 问题3：滚动优化与消融实验

读取附件1电价、附件2实际负载/PV和附件3的365天×4次预报。
预报1小时代表发布后1小时；插值以当前时刻之前最后一个已观测PV值为零时距锚点，
0:00锚点固定为0，在10分钟区间中点取值。此前31天的同日负载与同一发布时间预报误差
保持配对，构成等权场景。历史误差按需缓存并强制检查历史日期早于目标日期。

官方主策略为消融选定的 `Q3_FINAL_UPDATE_HOURS=(0,6,12)`，与第四问保持一致。
每次优化只覆盖剩余时域，SOC从已执行段末继承，终端回到6000 kWh。
0:00原始计划和两次revision保持独立：6:00与0:00版结算，12:00与6:00版结算；
12:00计划覆盖当天剩余时段，主运行不在18:00调整。
现金流为 `1.5 × 电价 × 增购量 − 0.5 × 电价 × 减购量`；负值是退款。
总费用为初始计划费加全部调整净费用，再加5倍电价的实际紧急购电费。

默认完整运行六种策略：`(0,)`、`(0,6)`、`(0,6,12)`、`(0,6,12,18)`、`(0,12,18)`、`(0,6,18)`。
全部策略均使用相同334天、相同历史窗口和结算参数。主结果固定采用已经选定的三时刻策略，
不在每次运行时重新选择策略。四时刻策略保留为消融对照；
`ISSUE_HOURS=(0,6,12,18)`仍表示附件3全部预报发布时间，用于输入校验和预测精度评价。
比较包含逐步增加更新和逐一删除更新，保留负的费用节省值。
约5344次LP串行求解，无商业求解器依赖。

| 问题3输出 | 内容 |
| --- | --- |
| `target/附件5/result3.xlsx` | 四张官方工作表，仅主策略填写 |
| `target/question3/summary.json` | 主策略标识、2—12月指标及四个指定日期的表1/2/3 |
| `target/question3/daily_results.jsonl` | 334天完整初始计划、所有revision、执行策略和实际结算 |
| `target/question3/ablation_summary.csv` / `.json` | 六种策略年度费用、电量和增减购交易量 |
| `target/question3/policy_daily_metrics.csv` | 六种策略逐日指标，便于复核累计节省 |
| `target/question3/forecast_accuracy.csv` / `.json` | 各发布时刻的MAE/RMSE与样本数 |
| `target/question3/figures/` | 正式策略、四个指定日期、消融对比、更新价值与预测精度图（PNG/PDF） |

`计划购电量` B:EO、EP和EQ分别是0:00原始合同、合同总量和初始计划费。
`调整购电量` B:EO是每段执行时生效的最新合同；EP是执行合同加紧急购电总量；EQ是含调整交易的总费用。
充放电表用最终执行策略，紧急区间复用问题2合并算法。Excel继续按位置映射，保留官方时间标签。
问题3内部以slot0=0:00—0:10、slot36=6:00—6:10的设计约定建模；模板日界标签不参与优化索引。

预测精度的“剩余时域”样本数随发布时间不同，不能仅凭较短时域的RMSE断言经济价值更高。
另报告所有预报在统一18:00—24:00时域的误差。未来实际值仅用于执行结算与离线精度分析，不回流优化。

可用 `--no-plots` 跳过图表，或对已保存结果使用 `--plots-only` 重绘（不重算、不覆盖正式Excel）。
默认求解、结算、全年校验及导出统一采用三时刻策略；四时刻对照必须显式传入更新时间。
旧四时刻存档不能通过默认三时刻校验，重绘也不会将它误标为三时刻结果。
切换前的官方Excel和完整分析目录已归档到`target/backups/question3_four_updates_*/`，
各备份目录的`manifest.json`保存文件SHA-256，便于复核历史版本。
备份文件禁用Git换行转换，确保跨平台检出后仍可按原始哈希校验。
结果存档用于复核，不作为跨参数复用的断点缓存；常规运行重新求解全部策略。
任一日期或策略求解/校验失败即终止，正式Excel只在全部成功后原子替换。

## 问题4：动态电价适配与对比

```powershell
# 两个模型及对应固定电价基线，默认生成中文PNG/PDF图表
& 'D:\Anaconda\envs\cucum2026\python.exe' -X utf8 run_question4.py

# 独立入口；也支持 python -m src.question4.question4_2 / question4_3
& 'D:\Anaconda\envs\cucum2026\python.exe' -X utf8 run_question4_2.py
& 'D:\Anaconda\envs\cucum2026\python.exe' -X utf8 run_question4_3.py

# 只根据已验证存档重绘，不求解、不改写官方Excel
& 'D:\Anaconda\envs\cucum2026\python.exe' -X utf8 run_question4.py --plots-only
```

附件4严格加载为365天×144点，逐日核对附件2日期和原始时间列顺序，保留末列`0:00+1`。
题目给定的目标日完整价格曲线用于所有计划、调整及紧急购电费用，不新增价格预测模型。
历史31天场景、光伏预测插值、历史误差配对、滚动SOC和冻结执行均复用已有实现，优化器未复制。
计划费按目标时段价格，增购按1.5倍、减购按0.5倍退款，紧急购电按5倍逐时价格结算。

4-3固定采用第三问消融选定的`Q3_FINAL_UPDATE_HOURS=(0,6,12)`；18点预测不进入第四问求解。
固定电价对比基线也用`(0,6,12)`重新计算，与第三问当前官方主结果一致。
第四问价格比较中，更新策略保持一致；第三问四时刻历史结果保留在备份和消融对照中。
附件1价格仅用于固定电价比较基线和回归测试，第四问正式计划使用附件4价格。

| 问题4输出 | 内容 |
| --- | --- |
| `target/附件5/result4-2.xlsx` | 复用第二问三表语义，EP含紧急量，EQ含紧急费 |
| `target/附件5/result4-3.xlsx` | 复用第三问四表语义，调整表保存最终生效合同，EQ含全部调整净费用 |
| `target/question4/question4_2/` | 4-2完整结果、价格快照、摘要与固定价格比较 |
| `target/question4/question4_3/` | 4-3完整计划、两次revision、最终执行、价格快照与比较 |
| 各模型目录的`summary.json` | 年度指标、四个指定日期表1/2/3及144点动态电价 |
| `comparison.json` / `.csv` | 固定/动态价格费用、电量、充放电量等指标的绝对和相对变化 |
| `daily_metrics.csv` / `fixed_price_daily_metrics.csv` | 两种价格下334天的运行指标，含日均/最低/最高/价差/标准差 |
| `daily_results.jsonl` / `prices.json` / `manifest.json` | 完整审计记录、365×144价格快照和输入哈希 |
| 各模型目录的`figures/` | 价格热力图、全年费用比较、四个指定日期调度和价格波动关系，每图PNG/PDF两版 |

年度汇总均指正式输出期2025年2月1日至12月31日，共334天；1月仅供历史场景使用。
费用变化定义为“动态 − 固定”，相对变化除以固定值；基线为零时相对变化写为JSON null/CSV空白。
价格价差与运行指标的相关系数仅作描述性分析，不作因果解释。
图表显式声明中文字体并设置负号显示，沿用项目统一的Matplotlib配置。

联合入口只在两个动态模型和对应固定基线全部成功、验证及绘图完成后替换第四问正式Excel。
单独入口只输出选定模型。`--no-plots`跳过绘图，`--debug`显示各滚动阶段及LP残差。
重绘时核对价格快照、输入SHA-256、策略和全部物理/费用约束；输入变化时须重新运行。
存档不作为求解缓存。第四问结果写入`target/`，运行第四问不修改前三问正式Excel。
私有仓库同时保留代码、正式结果、图表、验证日志和历史备份，便于复现与对照。
