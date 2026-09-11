# 独立合并论文初稿

论文主文件为main.tex；编译后的PDF位于output/pdf/main.pdf。此目录是CUCUM2026中的统一论文入口，不依赖article进行编译；article只作为本次内容来源保留。

## 三个阶段材料

1. review/01_逐节合并清单.md
2. review/02_关键计算口径核对.md，以及audit_results.json、测试日志。
3. main.tex、sections/、figures/和output/pdf/main.pdf。

## 统一口径

主结果使用CUCUM2026正式输出，中点插值、0/6/12更新、1e-8吞吐惩罚；第三问至第四问和benchmark使用同一结果链。保留article的信息边界、条件性最优、共同窗口误差、逐次退款和局限分析。旧端点结果只用于离散稳健性补充。

## 复现

在paper目录使用XeLaTeX两次编译main.tex，输出目录指定output/pdf。所有正文图和依赖样式均在paper内。build_draft.py可从当前CUCUM2026摘要重新生成正文及数值表；生成前需有review/audit_results.json。audit_sources.py只读正式结果并在review中记录证据，不调用正式导出接口。

## 待终稿阶段处理

- 时间标签与内部区间有十分钟边界差异，本次保留正式结果并披露，未平移。
- 补充经核实的学术方法文献及完整AI使用记录；当前只引用实际提供的赛题与本地实验报告。
- 按适用比赛规范最终核查篇幅、完整程序附录和支撑材料要求。本稿不冒称最终提交版。
- CVaR及12组敏感性是当前工程的归档实验，不是本次重新运行。
