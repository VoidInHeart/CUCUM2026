# 论文可视化清单

生成范围：`all`；中文字体：`Microsoft YaHei`；PNG 分辨率：320 dpi；同时提供矢量 PDF。

所有图片仅由现有 CSV/JSON 结果生成，未重新运行优化模型，也未写入任何正式 Excel 文件。

| 图片 | 数据源 | 核心结论 | 建议章节 | 位置 |
|---|---|---|---|---|
| [q2_ablation_cost.png](q2_ablation_cost.png) / [PDF](q2_ablation_cost.pdf) | target/question2/ablation_summary.csv | A7 将总费用由 1760.98 万元降至 1468.93 万元，节省 16.58%。 | 问题2：模型优化与消融实验 | 正文 |
| [q2_monthly_baseline_vs_a7.png](q2_monthly_baseline_vs_a7.png) / [PDF](q2_monthly_baseline_vs_a7.pdf) | target/question2/baseline_daily_metrics.csv；target/question2/residual_weighted_causal_daily_metrics.csv | A7 的全年节省同时来自计划购电费和高惩罚紧急购电费的下降。 | 问题2：优化效果的时间分解 | 正文 |
| [q2_scenario_calibration.png](q2_scenario_calibration.png) / [PDF](q2_scenario_calibration.pdf) | target/question2/baseline_daily_metrics.csv；target/question2/residual_weighted_causal_daily_metrics.csv | 残差加权场景显著修正均值偏差，并使全年 P80 覆盖率接近 0.80。 | 问题2：不确定性场景校准 | 正文 |
| [q2_surplus_emergency_tradeoff.png](optional/q2_surplus_emergency_tradeoff.png) / [PDF](optional/q2_surplus_emergency_tradeoff.pdf) | target/question2/ablation_summary.csv | 各改进策略在富余电量、紧急购电量和总费用间形成清晰权衡，A7 综合表现最佳。 | 问题2：稳健性与权衡 | 附录 |
| [q3_model_ablation.png](q3_model_ablation.png) / [PDF](q3_model_ablation.pdf) | target/question3/model_ablation_summary.csv | 残差场景与因果储能均有收益，二者联合时总费用最低（1464.17万元）。 | 问题3：模型机制消融 | 正文 |
| [q3_update_policy.png](q3_update_policy.png) / [PDF](q3_update_policy.pdf) | target/question3/ablation_summary.csv | 0、6、12点更新组合最优；增加18点更新反而使总费用小幅上升约0.12万元。 | 问题3：更新时间选择 | 正文 |
| [q3_forecast_accuracy.png](q3_forecast_accuracy.png) / [PDF](q3_forecast_accuracy.pdf) | target/question3/forecast_accuracy.csv | 越接近运行时刻，光伏预报误差总体越低；统一18—24点时域下各版本差异较小。 | 问题3：预报误差分析 | 附录（正文可引用） |
| [q3_dispatch_2025-12-21.png](q3_dispatch_2025-12-21.png) / [PDF](q3_dispatch_2025-12-21.pdf) | target/question3/daily_results.jsonl | 6点和12点滚动更新改变后续合同，储能按因果信息执行且 SOC 始终满足边界。 | 问题3：典型日运行机理 | 正文 |
| [q4_dynamic_prices.png](q4_dynamic_prices.png) / [PDF](q4_dynamic_prices.pdf) | target/question4/question4_3/prices.json | 动态电价同时呈现稳定的日内峰谷与明显的跨日波动。 | 问题4：动态电价特征 | 正文 |
| [q4_fixed_dynamic_comparison.png](q4_fixed_dynamic_comparison.png) / [PDF](q4_fixed_dynamic_comparison.pdf) | target/question4/question4_2/comparison.csv；target/question4/question4_3/comparison.csv | 动态电价下 Q4-2 与 Q4-3 总费用分别增加 3.92% 和 3.76%，紧急购电量略有下降。 | 问题4：固定—动态电价对比 | 正文 |
| [q4_dispatch_2025-12-21.png](q4_dispatch_2025-12-21.png) / [PDF](q4_dispatch_2025-12-21.pdf) | target/question4/question4_3/daily_results.jsonl；target/question4/question4_3/prices.json | 滚动合同与储能响应动态价格和最新负荷信息，SOC 全程满足约束。 | 问题4：典型日调度 | 正文 |

## 推荐图注

- **q2_ablation_cost**：问题2消融实验的计划购电费与紧急购电费构成。A7（残差加权场景与因果滚动执行）取得最低总费用。

- **q2_monthly_baseline_vs_a7**：基线 A0 与优化策略 A7 的月度费用构成对比，费用均按计划购电与紧急购电分解。

- **q2_scenario_calibration**：基线与 A7 场景校准对比：上图为14日滚动均值偏差，下图为月均 P80 覆盖率。

- **q2_surplus_emergency_tradeoff**：问题2代表性策略的富余电量—紧急购电量权衡；点大小表示总费用。

- **q3_model_ablation**：问题3四种场景生成与储能执行组合的总费用和紧急购电量对比。

- **q3_update_policy**：不同时刻更新组合下的全年总费用与紧急购电量，青色柱为选定策略0+6+12。

- **q3_forecast_accuracy**：0、6、12、18点发布预报的 MAE 与 RMSE；右图控制为共同的18—24点评价时域。

- **q3_dispatch_2025-12-21**：2025年12月21日问题3典型日：净负荷、初始/最终合同、合同调整、储能功率及 SOC。

- **q4_dynamic_prices**：2025年全年动态电价热力图，以及每日均价和日内最低—最高价区间。

- **q4_fixed_dynamic_comparison**：问题4两种计划机制在固定与动态电价下的总费用和紧急购电量对比。

- **q4_dispatch_2025-12-21**：动态电价下2025年12月21日 Q4-3 典型日调度：价格、合同调整、储能与 SOC。

## 未生成的候选图

- `optional/q2_emergency_heatmap_compare`：现有持久化数据只有 A0/A7 的逐日紧急购电总量，没有 A0 的144时段紧急购电矩阵。为遵守“不重跑高成本优化、优先使用现有 CSV/JSON”的要求，本次不绘制该图。
