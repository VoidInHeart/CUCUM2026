# C题跨日 SOC 连续化重构：Codex 长任务书

> 仓库：`VoidInHeart/CUCUM2026`
>
> 工作方式：我会从当前仓库新检出一个独立分支。请只在该分支上工作，不要直接修改主分支。
>
> 本任务的核心原因：现有问题2、问题3、问题4均继承了“每天 0:00 SOC=6000 kWh、24:00 SOC=6000 kWh”的日闭合设定，但重新审题后发现，第一问明确要求日初、日末储电量相同，而第二问及后续问题未必明确要求“每天都重新回到 6000 kWh”。因此需要把“第一问的日闭合约束”与“后续问题的跨日物理状态”拆开，重新建立允许 SOC 跨日连续传递的模型，并完整重算后续结果。

---

# 0. 在写代码之前先做题意审计

不要一上来改代码。

请首先阅读仓库中的原始题目 PDF、已有建模说明、README 和现有实现，重点确认以下文字：

1. 第一问是否明确要求 0:00 与 24:00 储电量相同；
2. 第二问是否明确写了“沿用第一问全部约束”；
3. 第二问是否只给出了储能初始状态，而没有要求每天 24:00 回到初始状态；
4. 第三问是否明确规定调整范围只到当天 24:00，还是只说利用 0/6/12/18 点发布的未来 24 小时预测进行滚动调整；
5. 第四问是否只是将第二、三问置于动态电价下重新求解。

请在：

```text
docs/SOC_boundary_audit.md
```

中记录题目原文对应位置、你的解释以及最终采用的建模假设。

不要把“现有代码这样写”当作题意证据。

---

# 1. 当前实现中已经确认的问题

现有代码的结构大致如下。

问题2：

```text
src/question2/config.py
```

从问题1继承：

```text
INITIAL_SOC_KWH = 6000
FINAL_SOC_KWH = 6000
```

问题2 `optimizer.py` 每天建立独立 LP，右端包含：

```text
INITIAL_SOC_KWH
...
FINAL_SOC_KWH
```

因此每天都被强制：

$$
SOC_{d,0}=6000,
\qquad
SOC_{d,24}=6000.
$$

问题3：

```text
src/question3/config.py
```

继续从问题2导入：

```text
INITIAL_SOC_KWH
FINAL_SOC_KWH
```

问题3 `optimizer.py` 中：

```python
h = 144 - start
```

每次 0:00、6:00、12:00、18:00 的优化都只覆盖“当前时刻到当天 24:00”，并且 RHS 最后仍放入：

```text
FINAL_SOC_KWH
```

即每次滚动修订最终都把当天 24:00 锁回 6000。

问题4-2：

```text
src/question4/question4_2.py
```

直接复用问题2 `pipeline.solve_day/run_annual`。

问题4-3：

```text
src/question4/question4_3.py
```

直接复用问题3滚动控制器。

因此，一旦“每日必须回 6000”这个假设被取消，下列结果都受影响：

```text
问题2
问题3
问题3更新时间消融
问题4-2
问题4-3
benchmark 中 DET
benchmark 中 Q80
benchmark 中 SAA
benchmark 中 CVaR-SAA
benchmark 中 SAA-MPC
```

问题1不要修改，因为问题1的日闭合约束是题目明确给出的。

---

# 2. 本次重构的首要原则

本任务不是“简单删除 FINAL_SOC_KWH”。

真正要实现的是：

$$
\boxed{
SOC_{d+1,0}=SOC_{d,24}
}
$$

也就是说：

> 电池是同一块真实电池，今天晚上剩多少电，明天早上就从多少电开始。

禁止出现：

```text
2月1日 24:00 = 3200
2月2日 0:00 = 6000
```

这种物理上凭空恢复电量的情况。

新的核心状态应该是：

```text
current_soc_kwh
```

它由上一段已经执行的充放电结果决定，而不是每天从 config 中重置。

---

# 3. 初始 SOC 的口径

当前正式输出从：

```text
2025-02-01
```

开始，1 月主要用于提供 31 天历史样本。

本次重构默认采用以下主口径：

```text
2025-02-01 00:00
SOC = 6000 kWh
```

然后从 2 月 1 日起一直连续传递到 12 月 31 日。

原因是当前正式评价期为 2—12 月，而 1 月没有问题2正式决策输出；这样可以在不引入“如何重建 1 月历史储能运行”的额外假设下，公平比较旧模型和新模型。

但是：

如果原题明确要求“2025-01-01 00:00 SOC=6000 且储能从 1 月 1 日开始连续运行”，请不要静默忽略。请在审计文档中说明，并额外实现一个可选初始化模式：

```text
initialization_mode = "feb1_control_start"
initialization_mode = "jan1_continuous"
```

如果实现 `jan1_continuous`，不要使用未来真实数据构造一个“全知全能”的 1 月最优轨迹。请明确设计并记录 warm-up 策略。

主实验优先使用：

```text
feb1_control_start
```

除非题目原文清楚否定该口径。

---

# 4. 必须保留旧模型作为 legacy baseline

不要直接覆盖掉旧逻辑后就无法复现原结果。

请把 SOC 边界策略显式参数化，例如：

```python
soc_policy = "daily_closed"
soc_policy = "continuous"
```

其中：

```text
daily_closed
```

必须能够精确复现当前正式结果：

$$
SOC_{d,0}=SOC_{d,24}=6000.
$$

而：

```text
continuous
```

采用新的跨日连续状态：

$$
SOC_{d+1,0}=SOC_{d,24}.
$$

旧模型用于：

- 回归测试；
- 新旧口径敏感性分析；
- 防止重构引入其他无关数值变化。

不要删除 `FINAL_SOC_KWH`，但把它标记为只属于：

```text
问题1
legacy daily_closed 模式
```

不要继续把它当作问题2—4默认的每日物理条件。

---

# 5. 第一阶段先只改问题2，不要一口气改完全部模型

虽然最终要重跑问题2—4，但代码实施请分阶段。

先把问题2的新 SOC 机制做正确，验证通过以后，再把公共接口向问题3和问题4传播。

新的问题2日求解接口建议从：

```python
solve(price, scenarios)
```

改成类似：

```python
solve(
    price,
    scenarios,
    initial_soc_kwh,
    terminal_mode=...
)
```

不要让优化器自己从全局 config 偷拿“今天初始 SOC”。

也就是说：

> 初始 SOC 必须是显式函数参数。

这样才能真正实现跨日状态传递，也能让问题3 6:00、12:00 的边界状态复用同一个底层接口。

---

# 6. 问题2：新的连续 SOC 主模型

先实现最直接的物理连续版本。

对于第一个正式控制日：

$$
SOC_{1,0}=6000.
$$

当天优化中：

$$
SOC_{t}
=
SOC_{t-1}
+
\eta_c C_t
-
\frac{D_t}{\eta_d}
$$

继续保持：

$$
1200\le SOC_t\le10800
$$

和原充放电功率限制。

但是不要再强制：

$$
SOC_{d,24}=6000.
$$

当天真实执行完成后，得到：

$$
SOC_{d,24}^{exec}.
$$

下一天：

$$
SOC_{d+1,0}
=
SOC_{d,24}^{exec}.
$$

由于当前问题2的计划充电、放电是确定执行的，SOC 轨迹由计划 $C_t,D_t$ 决定，因此“实际日末 SOC”应与计划 SOC 一致；紧急购电与富余用于平衡实际净负荷，不应凭空改变电池 SOC。

请在 validator 中明确验证这一点。

---

# 7. 必须做“终端效应”诊断

取消每日 6000 闭合以后，单日优化可能出现短视问题：

> 因为模型只优化今天，它可能认为 24:00 以后电池中的能量没有价值，因此倾向于在当天结束前把 SOC 放到下界。

所以不要只跑出结果就认为模型合理。

必须输出以下诊断指标：

```text
terminal_soc_mean
terminal_soc_median
terminal_soc_min
terminal_soc_max
terminal_soc_p05
terminal_soc_p95
days_terminal_soc_near_min
days_terminal_soc_near_max
soc_start_end_delta_mean
```

并生成：

```text
target/question2_continuous/figures/soc_daily_boundary.png
target/question2_continuous/figures/soc_daily_boundary.pdf
```

横轴为日期，至少展示：

```text
每日0:00 SOC
每日24:00 SOC
SOC_MIN
SOC_MAX
```

定义：

```text
near_min := SOC <= SOC_MIN + 1% * capacity
near_max := SOC >= SOC_MAX - 1% * capacity
```

如果大量日期的 24:00 SOC 都贴着 1200 kWh，下结论时必须明确：

> 这很可能是单日有限时域的终端效应，而不是“真实最合理的跨日储能策略”。

---

# 8. 不要立即用人为的 6000 软约束掩盖终端效应

不要为了让图好看，直接加入：

$$
|SOC_{24}-6000|
$$

惩罚。

也不要未经论证就给：

```text
terminal_soc_target = 6000
```

因为这会把原来的硬约束换成一个人为软约束，本质上仍然默认“每天应该回6000”。

如果 continuous 单日模型出现明显的下界耗尽，请实现一个额外的：

```text
continuous_lookahead
```

模式，而不是直接把 daily_closed 换个名字。

---

# 9. 推荐的终端效应修正：48小时滚动 SAA

如果单日 continuous 模型出现明显短视，推荐将问题2的主修正版升级为：

$$
\boxed{
\text{跨日 SOC 连续}
+
\text{48小时滚动 SAA}
}
$$

每天 0:00 不只优化今天 24 小时，而是优化：

```text
今天 + 明天
```

共：

$$
288
$$

个 10 分钟 slot。

但是只真正执行前：

$$
144
$$

个 slot。

第二天 0:00 重新构造历史场景、重新求解，然后继续滚动。

这相当于：

```text
今天考虑到明天，但不承诺明天的旧计划。
```

这样模型在今天 24:00 时会知道：

> 电池明天还要继续使用，

因此不会天然把午夜 SOC 当成零价值。

---

# 10. 48小时 SAA 场景不能使用未来真实数据

这是最重要的防泄漏要求。

目标日为 $d$ 时，只允许使用：

$$
d-31,\ldots,d-1
$$

已经发生的 31 天。

要从这 31 天中构造连续 48h 历史轨迹，可以使用其中的相邻日对：

```text
(d-31,d-30)
(d-30,d-29)
...
(d-2,d-1)
```

共：

$$
30
$$

个 48h 场景。

每个概率：

$$
1/30.
$$

不要为了维持“31个场景”而复制某一天、循环拼接或读取目标日。

新的场景形状：

```text
(30, 288)
```

建议新增明确的数据类型，例如：

```python
MultiDayScenarioSet
```

不要偷偷复用现有 `(31,144)` 类型后到处加特殊判断。

---

# 11. 48小时价格处理

问题2的固定分时电价每天重复，所以 48h 价格可以直接拼：

```python
price_48h = np.tile(price_24h, 2)
```

问题4-2以后改成动态电价时，不能这么做。

对于问题4-2，48h horizon 应使用：

```text
目标日 d 的动态价格
+
目标日 d+1 的动态价格
```

但是必须确认题目在 d 日 0:00 是否允许知道 d+1 的完整动态价格。

如果题面只给“当日电价已知”，而不是未来两日电价已知，则问题4-2不能无条件采用48h已知价格。

遇到这种情况，不要偷偷看附件4的 d+1 真实价格。

请在 `SOC_boundary_audit.md` 中记录信息可用性，并为 Q4-2 选择不泄漏未来价格的终端处理。

---

# 12. 连续模型的执行语义

48h 求解器输出：

```text
grid[288]
charge[288]
discharge[288]
soc[288]
```

但是当前日正式执行只使用：

```text
0:144
```

后 144 slot 只是 continuation plan：

```text
用于给今天午夜 SOC 定价
不作为明日正式合同
不写入 result2.xlsx
```

实际结算仍只对目标日进行。

下一天重新优化。

---

# 13. 问题2需要保留三种 SOC 版本进行对照

最终至少支持：

```text
daily_closed
continuous_myopic
continuous_lookahead
```

含义：

### daily_closed

当前旧模型：

$$
SOC_{0}=SOC_{24}=6000.
$$

### continuous_myopic

跨日传递，但每天只优化24小时，不设日末闭合。

用于诊断“取消日闭合以后是否出现短视耗尽”。

### continuous_lookahead

跨日传递，并使用48h滚动 SAA，只执行前24h。

如果题目和信息可用性允许，优先将这一模式作为新的候选正式模型。

不要删掉另外两种，它们本身是非常有价值的敏感性实验。

---

# 14. 问题2输出不要直接覆盖旧正式结果

先输出到新的目录：

```text
target/revised_soc/question2/
```

至少包含：

```text
daily_closed/
continuous_myopic/
continuous_lookahead/
comparison.csv
comparison.json
figures/
```

正式 Excel 先生成：

```text
target/revised_soc/question2/result2_daily_closed.xlsx
target/revised_soc/question2/result2_continuous_myopic.xlsx
target/revised_soc/question2/result2_continuous_lookahead.xlsx
```

在模型验证和比较完成以前：

```text
不要覆盖 target/附件5/result2.xlsx
```

---

# 15. 问题2必须比较哪些结果

至少比较：

```text
总计划购电量
紧急购电量
总购电量
计划费用
紧急购电费用
总费用
紧急购电天数
紧急购电时段数
充电总量
放电总量
储能吞吐量
SOC均值
日末SOC分布
贴SOC下界天数
贴SOC上界天数
```

重点分析：

1. daily_closed 是否因为每天强制回6000而增加无必要循环；
2. continuous_myopic 是否大量在午夜耗尽；
3. continuous_lookahead 是否缓解该终端效应；
4. 新模型是否减少/增加紧急购电；
5. 新模型是否通过跨日搬移电量获得收益。

---

# 16. 问题3不能简单继承旧 INITIAL_SOC=6000

问题2新模型验证完后，再改问题3。

当前问题3每天：

```python
solve_initial_plan(...)
```

内部直接：

```text
initial_soc = cfg.INITIAL_SOC_KWH
```

请重构为显式：

```python
solve_initial_plan(
    price,
    scenarios,
    initial_soc_kwh
)
```

每天 0:00 的初始 SOC 必须来自：

```text
前一天实际执行结束 SOC
```

而不是6000常量。

6:00、12:00、18:00 的 revision 继续从“已执行段最后 SOC”继承，这一部分现有代码思路可以保留。

---

# 17. 问题3必须重新考虑滚动 horizon

当前问题3：

```python
h = 144 - start
```

因此：

```text
0:00  看24h
6:00  只看18h
12:00 只看12h
18:00 只看6h
```

并且最后都强制回当天24:00的6000。

取消日末闭合后，这个设计会产生更严重的午夜终端效应。

附件3的语义是：

> 每个发布时间给出未来24小时光伏预测。

因此请优先研究并实现新的：

```text
issue-relative 24h rolling horizon
```

即：

```text
0:00  → 未来24h
6:00  → 未来24h（到次日6:00）
12:00 → 未来24h（到次日12:00）
18:00 → 未来24h（到次日18:00）
```

这样更符合附件3本身“未来24小时预测”的信息结构，也天然给午夜SOC提供跨日价值。

---

# 18. 问题3的跨午夜数据结构需要重新设计

当前很多数组默认：

```text
一天144槽
start:144
```

新的 issue-relative horizon 固定可为：

```text
144槽，从发布时间起向后24小时
```

请不要强行用大量 `%144` 索引把所有东西缝在旧结构里。

建议区分：

```text
issue-relative horizon
calendar-day execution
```

例如新增：

```python
RollingHorizonPlan
```

包含：

```text
issue_datetime
horizon_slot_datetimes
grid_kwh
charge_kwh
discharge_kwh
soc_end_kwh
```

实际输出 result3 时仍按日历日切片写入官方模板。

---

# 19. 问题3仍然必须严格防未来泄漏

新的跨午夜 horizon 不能使用未来真实负荷/PV。

允许的信息：

```text
过去历史实际数据
当前发布时间已经发布的附件3预测
当前时刻之前已经观测到的数据
已知合同/电价信息
当前真实SOC
```

不允许：

```text
当前发布时间之后的真实PV
当前发布时间之后的真实负荷
尚未发布的6/12/18点预测
```

必须扩充现有防泄漏测试覆盖跨午夜时段。

---

# 20. 问题3调整合同的语义必须审题确认

不要默认“6:00发布的24小时预测意味着可以修改次日0:00以后的购电合同”。

请重新核对题面。

如果题目规定日内调整只作用于：

```text
当天剩余合同
```

那么：

- 优化 horizon 可以跨午夜，用于 SOC continuation value；
- 但 adjustment 交易变量 `up/down` 只能作用于当天剩余合同；
- 次日合同由次日0:00的新计划决定。

也就是说要区分：

```text
physical planning horizon
contract adjustment horizon
```

不要把二者混为一谈。

如果题目允许调整未来24小时合同，再按题意扩大交易范围。

这项结论必须写入：

```text
docs/SOC_boundary_audit.md
```

---

# 21. 问题3正式更新时间必须重新消融

当前正式策略：

```text
0+6+12
```

是基于旧的“每日6000闭合”模型消融得到的。

修改 SOC 机制以后，不能继续假设：

```text
0+6+12 仍然最优
```

必须重新完整运行原六种策略：

```text
(0,)
(0,6)
(0,6,12)
(0,6,12,18)
(0,12,18)
(0,6,18)
```

并重新比较：

```text
总费用
紧急购电
调整费用
增购量
减购量
日费用风险
SOC轨迹
```

重新选出新的正式策略。

如果仍然是：

```text
0+6+12
```

也必须是新实验重新得到的结论，而不是沿用旧结果。

---

# 22. 问题3输出目录

先写到：

```text
target/revised_soc/question3/
```

保留：

```text
policy_daily_metrics.csv
ablation_summary.csv
ablation_summary.json
forecast_accuracy.csv
summary.json
daily_results.jsonl
figures/
```

新增：

```text
soc_continuity.csv
soc_boundary_diagnostics.json
```

其中每天至少记录：

```text
date
soc_00
soc_06
soc_12
soc_18
soc_24
selected_policy
```

---

# 23. 问题4-2需要基于“新问题2”重新跑

当前 4-2 完全复用问题2 pipeline。

新版本仍然应尽量复用问题2，而不是复制代码。

即：

```text
Q4-2
=
新问题2 SOC连续模型
+
附件4动态电价
```

不要让 Q4-2 和 Q2 的 SOC 机制再次分叉。

如果最终 Q2 选择：

```text
continuous_lookahead
```

则 Q4-2 应使用相同的状态传递逻辑。

但是如前所述：

> 动态电价的未来可知范围必须按题意处理。

禁止为了48h lookahead直接偷用下一天尚不可知的真实动态价格。

如果题面明确附件4价格提前可知，则可以使用；否则需要单独设计价格 continuation 方案。

---

# 24. 问题4-3需要基于“新问题3”重新跑

当前 4-3 完全复用问题3滚动控制器。

新版本保持同样的软件设计：

```text
Q4-3
=
新问题3滚动控制器
+
附件4动态电价
```

不要复制一套新的 rolling controller。

新的 4-3 必须继承：

```text
跨日SOC连续
新选定更新时间策略
新的滚动 horizon 语义
新的防未来泄漏约束
```

然后重新计算动态电价下的所有结果。

---

# 25. 第四问固定电价对照也必须一起重算

当前第四问 comparison 依赖旧 Q2/Q3 baseline。

修改 SOC 机制以后，固定电价 baseline 也变了。

因此：

```text
Q4-2 fixed baseline
Q4-3 fixed baseline
```

必须重新求解。

不能拿旧的：

```text
17,609,791...
17,020,306...
```

直接与新动态电价模型比较。

比较必须始终是：

```text
相同SOC模型
相同滚动策略
只改变固定/动态价格
```

---

# 26. benchmark 全部需要重跑

当前 benchmark：

```text
DET
Q80
SAA
CVaR-SAA
SAA-MPC
```

全部依赖问题2/3的储能边界条件。

因此新的 benchmark 必须在 SOC 连续模型上重新运行。

但是请保留旧 benchmark 为：

```text
legacy_daily_closed
```

新增：

```text
continuous_soc
```

结果不要覆盖。

建议目录：

```text
target/revised_soc/benchmark/
```

主 comparison 至少增加字段：

```text
soc_policy
terminal_mode
initial_soc_policy
mean_terminal_soc
min_terminal_soc
max_terminal_soc
days_near_soc_min
days_near_soc_max
```

---

# 27. DET / Q80 在新 SOC 机制下也必须状态连续

DET 和 Q80 不能仍然每天从6000开始。

它们应该和 SAA 使用相同：

```text
current_soc_kwh
```

状态。

如果使用48h lookahead：

- DET 用历史均值构造48h continuation；
- Q80 用相应分位数构造48h continuation；
- SAA 用30条历史连续两日场景；
- CVaR 基于同一多日场景做风险优化。

保持公平比较。

---

# 28. CVaR 模型也必须重构 terminal/state 接口

CVaR 不要复制一套 SOC 逻辑。

应继续在新的 SAA LP 基础上增加：

```text
eta
xi_s
```

并验证：

```text
lambda=0
```

严格退化到“新 SAA”，而不是旧 daily_closed SAA。

新增回归测试：

```text
new CVaR(lambda=0)
==
new SAA
```

在浮点容差内一致。

---

# 29. 最重要的测试：跨日 SOC 连续

新增自动测试：

假设某天求得：

$$
SOC_{d,24}=x.
$$

则下一天求解输入必须严格：

$$
SOC_{d+1,0}=x.
$$

测试至少覆盖：

```text
问题2
问题3
问题4-2
问题4-3
benchmark adapter
```

不能只检查 summary，要直接检查逐日对象。

---

# 30. 不允许出现的错误

以下情况一旦出现，测试必须失败：

```text
每天重新把SOC设为6000
上一日SOC和下一日初始SOC不一致
问题3 0:00仍然隐式读取cfg.INITIAL_SOC_KWH
问题3 revision覆盖已执行段
Q4-2绕过新Q2逻辑
Q4-3绕过新Q3逻辑
benchmark继续引用旧baseline结果
```

---

# 31. 边界条件测试

至少人工构造以下情况：

### Case A：初始 SOC = 6000

验证正常求解。

### Case B：初始 SOC = 1200

必须仍可求解，且不能立即放电超过物理能力。

### Case C：初始 SOC = 10800

必须仍可求解，且不能继续充到上界以上。

### Case D：跨日

第一天刻意让最终SOC不等于6000，确认第二天继承该值。

### Case E：continuous_myopic

确认不再偷偷存在：

```text
SOC_24 = 6000
```

约束。

---

# 32. 旧模型必须精确回归

在：

```text
soc_policy="daily_closed"
```

时，问题2、3、4和 benchmark 必须在容差内复现当前主分支正式结果。

这是为了证明：

> 重构只是增加了新的SOC状态机制，没有意外改坏其他数学逻辑。

至少验证：

```text
Q2 total_cost
Q2 emergency_kwh
Q3 total_cost
Q3 emergency_kwh
Q3 selected policy
Q4-2 total_cost
Q4-3 total_cost
```

以及关键逐日数组。

---

# 33. 新旧模型比较必须单独生成报告

生成：

```text
target/revised_soc/SOC_model_comparison.md
```

至少回答：

1. 原模型为什么每天回6000；
2. 新模型为什么允许跨日；
3. 哪个约束来自题面，哪个属于建模假设；
4. continuous_myopic 是否出现终端耗尽；
5. continuous_lookahead 是否缓解；
6. Q2费用变化；
7. Q3最优更新时间是否变化；
8. Q4动态价格结论是否变化；
9. benchmark排序是否变化；
10. 是否建议最终论文采用新模型。

不要只输出数字，要写解释。

---

# 34. 需要重新生成的正式候选文件

在 revised_soc 目录生成候选版：

```text
result2.xlsx
result3.xlsx
result4-2.xlsx
result4-3.xlsx
```

但在整个任务完成以前，不要覆盖：

```text
target/附件5/
```

最后只在报告中告诉我：

```text
哪一组候选结果建议替换正式文件
```

让我人工决定是否覆盖。

---

# 35. 问题1保持完全不变

问题1是重要回归基线。

不要修改：

```text
问题1的0:00/24:00相同SOC约束
result1.xlsx
问题1求解器数学语义
```

如果因为共享 config 重构导致问题1结果变化，视为失败。

问题1原结果必须精确回归。

---

# 36. 配置重构建议

请把现在混在一起的：

```text
INITIAL_SOC_KWH
FINAL_SOC_KWH
```

语义拆清。

建议类似：

```python
BATTERY_REFERENCE_SOC_KWH = 6000
CONTROL_START_SOC_KWH = 6000
```

而：

```text
DAILY_FINAL_SOC_KWH
```

只存在于：

```text
question1
legacy daily_closed
```

新模型不要通过名称含糊的 `FINAL_SOC_KWH` 继续隐式引用。

---

# 37. 类型系统重构建议

建议 `DailyPlan` 增加：

```text
initial_soc_kwh
terminal_soc_kwh
soc_policy
```

问题3的计划对象也要显式记录：

```text
initial_soc_kwh
terminal_soc_kwh
issue_datetime
```

这样 summary 和 validator 不需要去猜：

> 这一天到底从多少SOC开始。

所有状态信息应随结果对象保存。

---

# 38. summary 必须把 SOC 说清楚

新的年度 summary 至少加入：

```text
initial_soc_first_day
final_soc_last_day
mean_daily_start_soc
mean_daily_end_soc
min_soc
max_soc
days_end_near_min
days_end_near_max
soc_continuity_max_error
soc_policy
terminal_mode
```

不要只保留费用指标。

---

# 39. Excel 的储电量字段要使用真实日界 SOC

现有 result2/result3 的“充放电量”表里可能默认：

```text
0:00储电量=6000
24:00储电量=6000
```

新模型必须改成：

```text
当天真实0:00 SOC
当天真实24:00 SOC
```

例如：

```text
2月1日 0:00 = 6000
2月1日 24:00 = 4387
2月2日 0:00 = 4387
```

必须在 Excel 中连续一致。

不要只改内部模型而继续把模板填成6000。

---

# 40. 终端年度边界需要显式处理

12月31日以后没有继续评价。

如果连续模型在最后一天把电池全部放空，会产生有限评价期的“年末清仓”效应。

不要静默忽略。

至少提供两个年度统计：

```text
raw_total_cost
terminal_energy_adjusted_cost
```

其中 `terminal_energy_adjusted_cost` 可以用明确写出的 salvage value 对年末剩余 SOC 做价值调整。

但是 salvage value 的定义必须透明，不得为了得到某个结论调参。

更保守的做法是同时报告：

```text
12月31日24:00 SOC
```

并将年末边界效应作为模型局限。

不要未经题意支持直接重新强制：

```text
12月31日 SOC = 6000
```

如果要做该敏感性实验，请命名：

```text
global_terminal_closed
```

并与主 continuous 结果分开。

---

# 41. 如果实现 salvage value，必须做敏感性分析

如果确实需要 terminal salvage value，可以考虑基于正常购电价格的可解释范围，例如：

```text
低谷价格 × 可回收效率
平均价格 × 可回收效率
高峰价格 × 可回收效率
```

但这只能作为敏感性分析。

禁止根据最终全年费用反向选择最“好看”的 salvage 系数。

---

# 42. 不要使用遗传算法、粒子群等替代 HiGHS

本次问题仍然主要是线性或可线性化的。

不要因为 SOC 跨日就换成：

```text
GA
PSO
SA
RL
```

核心求解器继续优先：

```python
scipy.optimize.linprog(method="highs")
```

真正改变的是：

```text
状态传递
优化 horizon
场景维度
终端处理
```

而不是搜索算法。

---

# 43. 性能优化

48h SAA 会增大 LP。

请继续使用：

```text
scipy.sparse
结构矩阵缓存
lru_cache
```

缓存维度可以按：

```text
horizon_slots
scenario_count
adjustment_mode
```

区分。

不要每一天从 Python 双重循环重新构建完全相同的稀疏结构。

---

# 44. 运行失败策略

任意一天、任意策略：

```text
LP失败
SOC连续性失败
数据泄漏检查失败
约束残差失败
Excel导出失败
```

都必须立即终止对应实验。

不要：

```text
跳过一天
用旧结果补一天
用0填一天
```

---

# 45. 建议的开发阶段

请按以下顺序执行，不要同时大改所有模块。

## Phase A：题意审计

输出：

```text
docs/SOC_boundary_audit.md
```

## Phase B：SOC接口重构

让问题2 solver 显式接受 `initial_soc_kwh`，保留 daily_closed 回归模式。

## Phase C：问题2 continuous_myopic

实现跨日状态传递，跑完334天，做终端效应诊断。

## Phase D：问题2 continuous_lookahead

如果 myopic 有明显终端耗尽，实现48h滚动 SAA。

## Phase E：问题2模型对比

生成新旧结果比较，确定候选主模型。

## Phase F：问题3重构

把0点初始SOC改成跨日传入，重构滚动 horizon，重新跑消融。

## Phase G：问题4

4-2复用新Q2，4-3复用新Q3。

## Phase H：benchmark

重新运行 DET/Q80/SAA/CVaR/MPC。

## Phase I：完整测试和报告

生成 revised_soc 总结，不覆盖旧正式结果。

---

# 46. 完整测试

最终执行：

```powershell
python -X utf8 -m unittest discover -s tests -v
```

要求：

- 原有测试全部通过；
- 新测试全部通过；
- daily_closed 精确复现旧结果；
- continuous 模式通过SOC连续性测试；
- 问题1结果不变；
- 防未来泄漏测试通过。

---

# 47. 新增测试建议

至少新增：

```text
test_soc_continuity_question2
test_soc_continuity_question3
test_soc_continuity_question42
test_soc_continuity_question43
test_no_daily_reset_in_continuous_mode
test_daily_closed_regression
test_initial_soc_parameter_is_used
test_terminal_soc_not_forced_in_continuous
test_48h_scenario_uses_only_past_days
test_48h_scenario_shape
test_mpc_cross_midnight_no_future_actual
test_issue_18_forecast_isolation
test_excel_soc_boundary_continuity
test_question1_unchanged
test_cvar_lambda_zero_matches_new_saa
```

---

# 48. 输出目录建议

```text
target/revised_soc/
├── question2/
│   ├── daily_closed/
│   ├── continuous_myopic/
│   ├── continuous_lookahead/
│   └── comparison.*
├── question3/
│   ├── ...
│   └── ablation_summary.*
├── question4/
│   ├── question4_2/
│   └── question4_3/
├── benchmark/
├── figures/
└── SOC_model_comparison.md
```

不要把所有新结果混回旧的：

```text
target/question2
target/question3
target/question4
```

---

# 49. 最终向我汇报的内容

任务完成后，最终回复必须明确回答：

1. 原题对第二问的SOC日界条件到底怎么写；
2. 你认为每日6000闭合是题目要求还是旧建模假设；
3. 哪些代码原先继承了该假设；
4. 你具体修改了哪些文件；
5. continuous_myopic 的SOC轨迹是否出现午夜耗尽；
6. 是否实现 continuous_lookahead；
7. 新问题2年度结果与旧结果差多少；
8. 新问题3重新消融后哪组更新时间最优；
9. 原来的 `0+6+12` 是否仍然成立；
10. 新问题4-2、4-3结果；
11. 新 benchmark 五种方法结果；
12. Q1是否保持完全不变；
13. daily_closed 是否精确复现旧Q2-Q4；
14. 所有跨日SOC连续误差最大是多少；
15. 是否存在任何未来数据泄漏；
16. unittest总数和结果；
17. 你建议最终论文采用哪种 SOC 模型；
18. 哪些 revised_soc Excel 建议替换正式附件。

---

# 50. 最终建模目标

这次重构的目标不是为了“让费用更低”。

真正目标是让模型满足：

$$
\boxed{
\text{题意一致}
+
\text{物理连续}
+
\text{时间因果正确}
+
\text{无未来泄漏}
}
$$

尤其要避免两个极端：

第一种：

$$
\boxed{
\text{每天无依据地把SOC重置到6000}
}
$$

第二种：

$$
\boxed{
\text{取消终端约束后每天24:00把电池短视地放空}
}
$$

因此最终模型应该在不人为恢复每日6000的前提下，让储能真正成为一个跨日状态变量。

数学上仍优先保持：

$$
\boxed{
\text{线性规划 / 随机线性规划 / 滚动线性规划}
}
$$

求解器继续使用 HiGHS。

不要为了跨日 SOC 引入没有必要的启发式算法。

---

# 51. 特别强调：不要直接把旧论文数字当作真值

完成新模型后，以下数字全部视为 legacy，仅用于回归对照：

```text
问题2原年度费用
问题3原0+6+12结果
问题3原消融排序
问题4原固定/动态价格比较
原benchmark结果
```

新模型必须重新计算。

如果新的结果和旧结果差异很大，不要手工校准去靠近旧结果。

先检查：

```text
题意
SOC连续性
终端效应
未来泄漏
价格信息范围
结算定义
```

确认模型正确以后，接受新的数值结果。

---

# 52. 工作纪律

请在实际改代码前先给出一个简短实施计划，然后直接执行，不要停下来反复向我确认小问题。

如果题面存在真正无法判定的关键歧义：

1. 在审计文档中写清楚；
2. 实现两个可切换口径；
3. 分别跑结果；
4. 最终把差异报告给我。

不要用未经说明的隐含假设替我做决定。

本任务完成的标准不是“代码能跑”，而是：

> 我能够清楚地知道：每日6000闭合到底影响了哪些结论，取消该假设以后，跨日SOC如何真实传递，新的Q2/Q3/Q4/benchmark结果是否仍然成立，以及最终哪一种建模口径最值得写进论文。
