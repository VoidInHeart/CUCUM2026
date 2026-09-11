"""从CUCUM2026正式摘要生成独立论文；只写paper目录。"""
from pathlib import Path
import json,csv,shutil,hashlib
ROOT=Path(__file__).resolve().parents[1]; P=ROOT/'paper'
for d in ['sections','figures','data_snapshot','review','output/pdf','build']: (P/d).mkdir(parents=True,exist_ok=True)
def read(path): return json.loads((ROOT/path).read_text(encoding='utf-8'))
def write(name,text): (P/name).write_text(text,encoding='utf-8')
def f(x): return f'{float(x):.4f}'
def pct(x): return f'{100*x:.4f}'
def tex(s): return str(s).replace('_',r'\_').replace('%',r'\%').replace('&',r'\&')
def table(caption,headers,rows,cols=None):
    cols=cols or ('l'+'r'*(len(headers)-1))
    return '\n'+r'\begin{table}[H]\centering\small'+'\n'+r'\caption{'+caption+'}\n'+r'\begin{tabular}{'+cols+r'}\toprule'+'\n'+' & '.join(headers)+r'\\\midrule'+'\n'+'\n'.join(' & '.join(map(str,row))+r'\\' for row in rows)+'\n'+r'\bottomrule\end{tabular}\end{table}'+'\n'
def fig(path,caption,width='.94'):
    return '\n'+r'\begin{figure}[H]\centering\includegraphics[width='+width+r'\textwidth]{figures/'+path+'}\n'+r'\caption{'+caption+r'}\end{figure}'+'\n'
sources=['target/question2/summary.json','target/question3/summary.json','target/question3/ablation_summary.json','target/question3/forecast_accuracy.json','target/question4/question4_2/summary.json','target/question4/question4_3/summary.json','target/question4/question4_2/comparison.json','target/question4/question4_3/comparison.json','target/benchmark/comparison.csv','target/benchmark/cvar_sensitivity.csv','target/benchmark/experiment_summary.md']
manifest=[]
for source in sources:
    dest=source.removeprefix('target/').replace('/','__');shutil.copy2(ROOT/source,P/'data_snapshot'/dest)
    manifest.append({'source':source,'snapshot':dest,'sha256':hashlib.sha256((ROOT/source).read_bytes()).hexdigest()})
write('data_snapshot/manifest.json',json.dumps(manifest,ensure_ascii=False,indent=2))
for name in ['cumcm2026.sty','cumcmthesis.cls','latexmkrc']:
    if not (P/name).exists():shutil.copy2(ROOT.parent/'article'/name,P/name)
figs={
'q1_dispatch.pdf':'question1/figures/dispatch.pdf',
'q2_monthly.pdf':'question2/figures/monthly_costs.pdf',
'q3_dispatch.pdf':'question3/figures/dispatch_2025-12-21.pdf',
'q3_accuracy.pdf':'question3/figures/forecast_accuracy.pdf',
'q4_prices.pdf':'question4/question4_3/figures/dynamic_prices.pdf',
'q4_dispatch.pdf':'question4/question4_3/figures/dispatch_2025-12-21.pdf',
'risk_return.pdf':'benchmark/figures/risk_return.pdf',
}
for dest,src in figs.items():shutil.copy2(ROOT/'target'/src,P/'figures'/dest)
q1=read('paper/review/question1_verified.json');q2=read(sources[0]);q3=read(sources[1]);ab=read(sources[2]);acc=read(sources[3]);q42=read(sources[4]);q43=read(sources[5]);cmp2=read(sources[6]);cmp3=read(sources[7]);audit=read('paper/review/audit_results.json')
a2=q2['annual'];a3=q3['annual'];a42=q42['annual'];a43=q43['annual']
with (ROOT/'target/benchmark/comparison.csv').open(encoding='utf-8-sig') as fp:bench=list(csv.DictReader(fp))
with (ROOT/'target/benchmark/cvar_sensitivity.csv').open(encoding='utf-8-sig') as fp:sens=list(csv.DictReader(fp))

# 题面表1/2的六列结构；第三问上下行区分初始合同与执行合同。
def specified(summary,title,rolling):
    out=r'\subsection{指定日期结果}'+'\n所有电量单位为kWh，费用单位为元，保留四位小数，总量使用未舍入值计算。指定十分钟区间按模板标签查询，时间口径见前文。\n'
    out+=r'\Needspace{140pt}\begingroup\centering\captionof{table}{'+title+r'：指定时段购电及全天合同费用}\fontsize{9}{11}\selectfont\setlength{\tabcolsep}{2pt}\renewcommand{\arraystretch}{1.13}'+'\n'
    for date,s in summary['paper_dates'].items():
        m=s['全天指标'];out+=r'\noindent\begin{minipage}{\textwidth}\centering\textbf{'+date+r'}\par\smallskip'+'\n'+r'\begin{tabularx}{\textwidth}{|Y|Y|Y|Y|Y|Y|}\hline 时间段&购电量&时间段&购电量&时间段&购电量\\\hline'+'\n'
        entries=[]
        for label,vals in s['表1'].items():
            value=(r'\shortstack{'+f(vals['初始计划购电量'])+r'\\'+f(vals['执行合同购电量'])+'}') if rolling else f(vals['计划购电量'])
            entries.extend([label,value])
        for k in (0,6):out+=' & '.join(entries[k:k+6])+r'\\\hline'+'\n'
        e=(r'\shortstack{'+f(m['initial_plan_kwh'])+r'\\'+f(m['executed_adjusted_kwh'])+'}') if rolling else f(m['planned_grid_total'])
        cost=(r'\shortstack{'+f(m['plan_cost'])+r'\\'+f(m['plan_cost']+m['adjustment_cost'])+'}') if rolling else f(m['planned_cost'])
        out+=r'\multicolumn{2}{|c|}{全天合同购电量}&'+e+r'&\multicolumn{2}{c|}{全天合同购电费}&'+cost+r'\\\hline\end{tabularx}\end{minipage}\par\medskip'+'\n'
    out+=(r'\raggedright 注：每格上行为0:00计划，下行为执行合同；下行合同费用为初始计划费加逐次调整净费。' if rolling else r'\raggedright 注：购电量为日前计划，合同费用不含紧急购电费。')+r'\par\endgroup\medskip'+'\n'
    out+=r'\Needspace{140pt}\begingroup\centering\captionof{table}{'+title+r'：指定时段储能充放电及首末储电量}\fontsize{9}{11}\selectfont\setlength{\tabcolsep}{2pt}\renewcommand{\arraystretch}{1.12}'+'\n'
    for date,s in summary['paper_dates'].items():
        out+=r'\noindent\begin{minipage}{\textwidth}\centering\textbf{'+date+r'}\par\smallskip\begin{tabularx}{\textwidth}{|Y|Y|Y|Y|Y|Y|}\hline 时间段&充电量&放电量&时间段&充电量&放电量\\\hline'+'\n'
        entries=[]
        for label,v in s['表2'].items():
            if isinstance(v,dict):entries.extend([label,f(v['累计充电量']),f(v['累计放电量'])])
        for k in (0,6,12):out+=' & '.join(entries[k:k+6])+r'\\\hline'+'\n'
        out+=r'\multicolumn{2}{|c|}{0:00储电量}&'+f(s['表2']['0:00 储电量'])+r'&\multicolumn{2}{c|}{24:00储电量}&'+f(s['表2']['24:00 储电量'])+r'\\\hline\end{tabularx}\end{minipage}\par\medskip'+'\n'
    out+=r'\raggedright 注：四小时内充放电均为正表示不同十分钟时段的累计，不表示同时充放电。\par\endgroup'+'\n'
    dates=list(summary['paper_dates']);events=[summary['paper_dates'][d]['表3'] for d in dates]
    out+=r'\begin{table}[H]\centering\caption{'+title+r'：四个指定日期的紧急购电区间}\label{tab:emergency-'+title+r'}\fontsize{9}{11}\selectfont\setlength{\tabcolsep}{2pt}\begin{tabular}{|lr|lr|lr|lr|}\hline'+'\n'
    head=' & '.join(r'\multicolumn{2}{|c|}{'+d+'}' for d in dates)+r'\\\hline'+'\n'+('时间段&购电量&'*3)+'时间段&购电量'+r'\\\hline'+'\n'
    out+=head
    for i in range(max(map(len,events))):
        cells=[]
        for ev in events:
            cells.extend([tex(ev[i]['label']),f(ev[i]['amount_kwh'])] if i<len(ev) else (['无','0.0000'] if not ev and i==0 else ['','']))
        out+=' & '.join(cells)+r'\\'+'\n'
    out+=r'\hline\end{tabular}\end{table}'+'\n'
    rows=[]
    for date,s in summary['paper_dates'].items():
        m=s['全天指标'];rows.append([date,f(m['actual_grid_energy_kwh'] if rolling else m['total_grid_purchase']),f(m['emergency_kwh'] if rolling else m['emergency_total']),f(m['emergency_cost']),f(m['total_cost'])])
    out+=table(title+'：实际总购电与费用',['日期','实际购电量','紧急购电量','紧急费用','实际总费用'],rows)
    return out+r'\FloatBarrier'+'\n'

front=r'''\section{问题重述与分析}
微网通过外网购电、光伏利用与储能时移满足小区负载。购电计划不足会触发五倍电价紧急补购，过量合同又存在未消纳成本，因此经济性取决于储能调度与信息不确定性的联合处理。依据题目及附件\cite{problem}，四问分别研究固定负载与光伏预报下的确定性计划、未知净负荷下的日前计划、光伏预报更新下的日内调整，以及波动电价下前两类策略的变化。

本文以相同储能物理模型为基础：问题一建立确定性线性规划；问题二利用历史净负荷场景近似未知分布，以日前费用和期望紧急费用联合优化；问题三围绕最新预报叠加历史预测误差，在已执行状态下滚动调整；问题四仅扩展价格维度，以保证比较可解释。评价同时考察实际费用、紧急补购规模及尾部风险，避免仅用求解器目标值判断策略效果。

\section{模型假设与符号说明}
\begin{enumerate}
\item 将每条十分钟功率记录视作该段代表功率，忽略段内变化；光伏小时预报用线性插值在十分钟中点取值。附件标签与内部时段映射差异单独说明。
\item 采用每日首末储电量均为6000 kWh的周期运行边界。该条件强于题目给出的1月1日初值，排除了跨日能量转移；1月仅用于历史窗口初始化，未模拟其逐日储能轨迹。
\item 外网可按题设倍率补足实际缺口，不另设紧急购电容量上限；供能富余不向外网出售。忽略未给定的电池退化费用和设备启停成本。
\item 前31天负载与同日光伏或预测误差的联合变化可近似代表目标日不确定性。极端天气和突发负荷可能超出有限样本覆盖范围。
\item 第四问将附件4目标日完整价格曲线视为给定条件。结论对应已知价格曲线下的调度，未构建未来价格预测模型。
\end{enumerate}
\begin{table}[H]\centering\caption{主要符号}\small
\begin{tabular}{clc}\toprule 符号&含义&单位\\\midrule
$d,t,s$&日期、十分钟时段、历史场景&--\\
$p_{d,t}$&目标日期和交付时段的电价&元/kWh\\
$L,V,N$&负载、光伏及净负荷电量，$N=L-V$&kWh\\
$G,C,D$&合同购电、交流侧充电输入及放电输出&kWh\\
$E$&储电量，百分比SOC为$E/12000$&kWh\\
$U,W$&紧急购电及供能富余&kWh\\
$A^r,B^r$&发布时刻$r$的增购和削减量&kWh\\
$\pi_s$&场景概率，取$1/31$&--\\
$F_d,K_d^r$&实际日费用、一次调整净费用&元\\\bottomrule
\end{tabular}\end{table}

\section{数据预处理与共同约束}
\subsection{数据范围与信息边界}
附件1提供144条电价、负载及光伏预测记录；附件2提供365天实际负载与光伏，附件3每日提供四次未来24小时光伏预报，附件4提供365乘144的电价矩阵。按附件5规定，问题二至四输出2025年2月1日至12月31日334天，1月初始化31天历史窗口。检查数据维数、日期连续性、非负性及有限值，并保持原始行列顺序，不作小时聚合。

对每段取$\Delta t=1/6$小时，$L=P^{\rm L}\Delta t$、$V=P^{\rm PV}\Delta t$。实际数据只在决策冻结后用于结算；第三问在更新时仅额外使用已发布预报和最近已完成记录的光伏观测。加载全年文件本身不等于使用未来信息，关键在于求解器收到的截断场景与当前可用预报。

\subsection{时间标签与统计口径}
内部第$t$段表示从$(t-1)/6$到$t/6$小时，滚动更新在完成36、72个记录后进行。附件记录标记从0:10到0:00+1，模板指定区间按标签逐位置映射；例如模板10:00--10:10查询第60条，而该条在内部结束时刻约定下对应9:50--10:00。四小时统计始终按连续24条记录求和。本研究保留官方模板的既有位置映射，不平移数值，指定区间表与内部物理区间的边界解释仍存在十分钟差异。以下经济性比较均在相同记录位置下进行，不能将这些表理解为统一时标后重新优化的结果。

\subsection{储能物理约束}
充、放电分别按交流侧计量，效率均为0.9，故往返效率为0.81：
\begin{align}
E_t&=E_{t-1}+0.9C_t-D_t/0.9,\\
1200\leq E_t&\leq10800,\quad 0\leq C_t,D_t\leq5000\Delta t,\\
E_0&=E_{144}=6000.\label{eq:boundary}
\end{align}
外网购电、供能富余及紧急购电均非负。日内滚动时初始储电量由已执行轨迹继承，不能重置为6000。各问目标均加入$\varepsilon\sum(C+D)$，$\varepsilon=10^{-8}$，用于减少冗余吞吐；报告的实际费用剔除该项。小惩罚不等价于严格的充放电互斥约束，需事后核验。

\subsection{评价指标}
主要报告合同费用、紧急购电量与费用、实际总费用、发生紧急购电的天数以及日费用尾部指标。紧急电量占比是补购电量与实际外网购电总量之比，不能直接视作负载满足概率。因缺口由外网补足，本模型中的紧急事件表示计划偏差风险，不表示最终停电。供能富余可能含已支付的合同电量，不能全部解释为弃光。
'''
write('sections/front.tex',front)

p1=r'''\section{问题一：确定性储能经济调度}
\subsection{目标与求解}
已知负载与光伏预测时，确定144个时段的购电与充放电量，以
\begin{equation}\min J=\sum_tp_tG_t+\varepsilon\sum_t(C_t+D_t)\end{equation}
为目标，除共同储能约束外，满足逐段平衡
\begin{equation}G_t+V_t+D_t=L_t+C_t+W_t.\label{eq:q1balance}\end{equation}
$W_t$不获得售电收入。全部变量为连续变量，模型为线性规划，采用SciPy调用HiGHS求解。最优性限定于给定初始状态、输入预测和上述约束下的模型；并不表示考虑预测误差后的实际最优。报告购电费用$F=\sum p_tG_t$，不包含辅助惩罚。

\subsection{指定时段结果与储能策略}
'''
t=q1['table1'];entries=list(t.items())[:6]
p1+=r'\begin{table}[H]\centering\caption{问题一：指定时段与全天购电结果}\small\begin{tabularx}{\textwidth}{|Y|Y|Y|Y|Y|Y|}\hline 时间段&购电量&时间段&购电量&时间段&购电量\\\hline'+'\n'
for k in (0,3):p1+=' & '.join(v for label,val in entries[k:k+3] for v in (label,f(val)))+r'\\\hline'+'\n'
p1+=r'\multicolumn{2}{|c|}{全天购电量/kWh}&'+f(t['全天购电量'])+r'&\multicolumn{2}{c|}{全天购电费/元}&'+f(t['全天购电费'])+r'\\\hline\end{tabularx}\end{table}'+'\n'
p1+=table('问题一：储能充放电量（kWh）',['时间段','充电量','放电量'],[[label,f(v['累计充电量']),f(v['累计放电量'])] for label,v in q1['table2'].items() if isinstance(v,dict)])
p1+='日初与日末均为6000 kWh。凌晨低价阶段储能集中补能，日间吸收光伏富余，在高价时段释放电能。0:00--4:00累计充电4500 kWh；部分日间指定时段购电为零，体现光伏与储能共同承担负载，而非负载消失。\n'
p1+=fig('q1_dispatch.pdf','问题一的购电、光伏与储能调度；横轴按原始记录位置绘制')
p1+=r'\subsection{经济性与能量守恒}'+'\n'
p1+=f"无储能基准逐段购入正净负荷，购电量{f(q1['baseline_kwh'])} kWh，费用{f(q1['baseline_cost'])}元。储能优化使费用减少{f(q1['baseline_cost']-t['全天购电费'])}元，降幅{pct(1-t['全天购电费']/q1['baseline_cost'])}\\%。该收益同时包含价格时移和光伏消纳改善，并非只来源于峰谷套利。\n"
p1+=r'''对状态转移求和，周期边界给出$\sum D_t=0.81\sum C_t$。逐段供需平衡求和后，外网购电等于净负荷加储能损耗及供能富余。当前重算解满足设备容量、功率、边界和能量平衡，且没有超过$10^{-6}$ kWh阈值的同时充放电。该检验支持本算例的物理可行性，不能代替任意参数下的互斥约束证明。
\FloatBarrier
'''
write('sections/problem1.tex',p1)

p2=r'''\section{问题二：历史场景下的日前随机规划}
\subsection{场景构造与决策机制}
目标日$d$在0:00尚不知道实际净负荷，选择前31天整日曲线形成$\mathcal S_d=\{d-31,\ldots,d-1\}$，令$N_{d,t}^{(s)}=N_{s,t}$、$\pi_s=1/31$。同一天负载与光伏保持配对，不单独打乱，以保留历史联合变化。等权样本平均近似把未知分布下的期望费用转化为有限场景优化。

第一阶段的$G_t,C_t,D_t,E_t$在场景间共享，当日0:00一并确定；第二阶段的紧急购电$U_t^{(s)}$与富余$W_t^{(s)}$随场景变化。场景约束为
\begin{equation}G_t+D_t-C_t+U_t^{(s)}-W_t^{(s)}=N_{d,t}^{(s)}.\end{equation}
结合共同储能约束，目标为
\begin{equation}\min J_d=\sum_tp_tG_t+\sum_s\pi_s\sum_t5p_tU_t^{(s)}+\varepsilon\sum_t(C_t+D_t).\end{equation}
程序保留显式富余变量，构造稀疏场景平衡等式。一天的储能计划也在场景间共享，因此模型不会在事后为每个真实场景另选一套储能轨迹。

固定充放电、忽略购电非负边界并假设单段净需求$X$连续时，$pG+5p\mathbb E[(X-G)^+]$的一阶条件给出$\Pr(X\leq G)=0.8$。五倍紧急电价因此使计划偏向较高需求分位；实际离散场景和跨段储能约束下，不能用逐段80\%分位曲线替代联合随机规划。

\subsection{实际结算与日际边界}
计划冻结后，定义$B_t=G_t+D_t-C_t$，实际紧急购电为$U_t^{\rm act}=[N_{d,t}-B_t]^+$，供能富余为$W_t^{\rm act}=[B_t-N_{d,t}]^+$。实际费用和总外网购电量分别为
\begin{equation}F_d=\sum_tp_tG_t+\sum_t5p_tU_t^{\rm act},\qquad Q_d=\sum_t(G_t+U_t^{\rm act}).\end{equation}
计划富余不退费，紧急电量不再重复计收普通价格。日前场景期望与事后真实费用分别统计。每日固定6000 kWh边界使日际SOC连续，但不等同于允许跨日储能的全年联合优化。
'''
p2+=specified(q2,'问题二',False)
p2+=r'\subsection{全期结果与风险解释}'+'\n'
p2+=table('问题二：334天结果汇总',['指标','数值'],[['计划购电量/kWh',f(a2['planned_grid_total'])],['紧急购电量/kWh',f(a2['emergency_total'])],['实际总购电量/kWh',f(a2['total_grid_purchase'])],['计划费/元',f(a2['planned_cost'])],['紧急费/元',f(a2['emergency_cost'])],['实际总费用/元',f(a2['total_cost'])],['发生紧急购电天数',a2['emergency_days']]])
p2+=f"紧急电量占比为{pct(a2['emergency_total']/a2['total_grid_purchase'])}\\%，费用占比却为{pct(a2['emergency_cost']/a2['total_cost'])}\\%，反映惩罚倍率和缺口时刻电价的共同作用。249天发生补购，低紧急电量占比不表示低事件频率。6月21日没有补购，但该月整体风险仍可能较高，单个指定日期不能代表整月。\n"
p2+=fig('q2_monthly.pdf','问题二的月度计划费用与紧急费用')
p2+=r'''风险来自历史场景对当前净负荷的覆盖不足。增加备购可以减少紧急费用，却可能扩大已支付合同的供能富余，因此需要联合权衡。与确定性均值、分位数及风险规避方法的同信息对照见后文，不能仅凭本模型可行就宣称其实际费用在所有策略中最低。
\FloatBarrier
'''
write('sections/problem2.tex',p2)

# 保留article第三问前半的严谨论证，替换实际实现差异。
article_snapshot=P/'data_snapshot/article_problem3_source.tex'
if not article_snapshot.exists():shutil.copy2(ROOT.parent/'article/sections/problem3.tex',article_snapshot)
orig=article_snapshot.read_text(encoding='utf-8')
start=orig.index(r'\subsection{建模思路');end=orig.index(r'\subsection{实际费用与实现差异比较}')
p3=orig[start:end]
old_start=p3.index('正文采用端点采样');old_end=p3.index('\n\n对历史日期',old_start)
p3=p3[:old_start]+r'本文在十分钟区间中点采样，$\widehat P^{10}_{d,r,t}=\widetilde P_{d,r}((t-\tau_r-1/2)\Delta t)$。历史预测误差采用相同插值方式计算，保证场景、优化和误差评价口径一致。'+p3[old_end:]
p3=p3.replace(r'\varepsilon=10^{-7}',r'\varepsilon=10^{-8}')
p3=p3.replace('0:00代码另对购电量加入$10^{-9}$系数增量，报告费用均剔除这些数值辅助项。','报告费用剔除数值辅助惩罚。')
v0=p3.index('剩余时段数为$H$时');v1=p3.index('对所选预报集合',v0)
p3=p3[:v0]+'求解器显式保留场景供能富余变量，以稀疏等式矩阵调用HiGHS；正文中的正缺口不等式是等价数学表述。'+p3[v1:]
p3=r'\section{问题三：预报更新下的滚动随机规划}'+'\n'+p3
p3+=r'''\subsection{实际费用与合同量的区分}
将各阶段执行片段拼接为$G^{\rm exec},C^{\rm exec},D^{\rm exec}$，实际缺口为
\begin{equation}U_{d,t}^{\rm act}=[N_{d,t}-G_{d,t}^{\rm exec}-D_{d,t}^{\rm exec}+C_{d,t}^{\rm exec}]^+.\end{equation}
日费用为$F_d=\sum_tp_tG_{d,t}^0+\sum_rK_d^r+\sum_t5p_tU_{d,t}^{\rm act}$。实际总外网购电量为$\sum_t(G_{d,t}^{\rm exec}+U_{d,t}^{\rm act})$，与初始合同总量、执行合同总量不同。各更新阶段以相同交付时段电价结算，逐次退款不等于仅对最终与初始合同的差额结算。
'''
p3+=specified(q3,'问题三',True)
p3+=fig('q3_dispatch.pdf','12月21日三时刻策略执行轨迹，6点和12点后仅调整未执行部分')
p3+=r'\subsection{预报时刻的经济价值}'+'\n'
p3+=table('中点插值下六种预报组合的334天回测',['预报组合','总费用/元','紧急电量/kWh','相对仅0点节省/元'],[[x['policy'],f(x['total_cost']),f(x['emergency_kwh']),f(x['savings_vs_0_yuan'])] for x in ab])
ap={x['policy']:x for x in ab}
p3+=f"沿0点、加入6点、再加入12点的顺序，费用分别减少{f(ap['0']['total_cost']-ap['0+6']['total_cost'])}元和{f(ap['0+6']['total_cost']-a3['total_cost'])}元。进一步加入18点增加{f(ap['0+6+12+18']['total_cost']-a3['total_cost'])}元。由四时刻集合删除6点和12点，分别增加{f(ap['0+12+18']['total_cost']-ap['0+6+12+18']['total_cost'])}元和{f(ap['0+6+18']['total_cost']-ap['0+6+12+18']['total_cost'])}元。因此当前回测支持保留6点、12点。\n"
p3+=r'''18点的费用变化相对于全期费用极小，应表述为“本次回测未见额外经济收益”，不应认为18点预报普遍无用。六种组合未穷举所有子集，且策略在同年回测中比较并选择，仍需独立验证期判断泛化效果。
\subsection{共同窗口预测误差与离散稳健性}
用MAE与RMSE评价光伏功率预报，避免夜间真值为零时MAPE失真。不同发布时间的剩余窗口长度不同，不能直接把RMSE下降全部归因于预报更新。固定18:00--24:00共同窗口后，各组均使用12024个样本。
'''
p3+=table('不同预报的功率误差（kW）',['发布时间','剩余窗口样本数','剩余RMSE','共同窗口RMSE'],[[str(x['issue_hour'])+':00',x['samples'],f(x['RMSE_kW']),f(x['common_18_24_RMSE_kW'])] for x in acc])
p3+=f"12点到18点在共同窗口的RMSE仅改善{f(acc[2]['common_18_24_RMSE_kW']-acc[3]['common_18_24_RMSE_kW'])} kW。误差更小不保证合同调整与紧急费用之和更低，经济价值仍需通过完整执行评价。\n"
p3+=fig('q3_accuracy.pdf','预报误差比较：剩余窗口与共同晚间窗口分别统计')
p3+=r'''作为离散口径对照，既有端点三时刻实现的费用为17013832.1962元，比中点实现低6474.4504元，约0.0380\%。该差异同时受到采样与数值实现影响，不能证明端点插值普遍更好。两种实现均支持当前三时刻选择；本文主结果、第四问和算法对照统一采用中点实现，端点结果只作为稳健性补充。
\subsection{全期结果与收益分解}
'''
p3+=table('问题三：334天正式主策略汇总',['指标','数值'],[['初始合同量/kWh',f(a3['initial_plan_kwh'])],['执行合同量/kWh',f(a3['executed_adjusted_kwh'])],['紧急购电量/kWh',f(a3['emergency_kwh'])],['实际总购电量/kWh',f(a3['actual_grid_energy_kwh'])],['初始计划费/元',f(a3['plan_cost'])],['调整净费/元',f(a3['adjustment_cost'])],['紧急费/元',f(a3['emergency_cost'])],['实际总费/元',f(a3['total_cost'])]])
p3+=f"相对问题二，费用减少{f(a2['total_cost']-a3['total_cost'])}元，降幅{pct(1-a3['total_cost']/a2['total_cost'])}\\%；紧急电量减少{pct(1-a3['emergency_kwh']/a2['emergency_total'])}\\%。其中由问题二到仅0点预报节省{f(a2['total_cost']-ap['0']['total_cost'])}元，再引入6点、12点滚动更新节省{f(ap['0']['total_cost']-a3['total_cost'])}元。这区分了初始预报信息与日内调整的收益，不能把全部差异归因于滚动控制。仍有243天发生紧急补购，说明策略减少费用和补购规模，并未消除预测偏差。\n"
p3+=r'\FloatBarrier'+'\n';write('sections/problem3.tex',p3)

p4=r'''\section{问题四：波动电价下的策略比较}
\subsection{价格信息与模型修正}
将固定分时电价$p_t$推广为目标日期的$p_{d,t}$。附件4价格曲线作为给定条件输入，而负载、光伏仍保持原有信息约束。365天日期与144个时间列严格与附件2对齐；1月价格不计入334天正式结果。若未来价格未知，则需另建预测或随机价格场景，超出当前基础方案。

问题4-2将第二问目标改为$\sum_tp_{d,t}G_t+\sum_s\pi_s\sum_t5p_{d,t}U_t^{(s)}+\varepsilon\sum_t(C_t+D_t)$，其他约束不变。问题4-3同样替换初始计划、紧急补购与调整交易的价格：
\begin{equation}K_d^r=\sum_{t\in\mathcal T_r}p_{d,t}(1.5A_t^r-0.5B_t^r).\end{equation}
历史窗口、中点插值、设备参数及每日边界均保持一致，正式4-3继续采用0、6、12点策略。固定价格基线使用同一策略，避免把更新时间变化混入价格机制比较。
\subsection{年度结果与经济机制}
'''
p4+=table('固定与波动价格下的334天对比',['策略','总费用/元','紧急电量/kWh','紧急费/元'],[['问题二',f(a2['total_cost']),f(a2['emergency_total']),f(a2['emergency_cost'])],['问题4-2',f(a42['total_cost']),f(a42['emergency_total']),f(a42['emergency_cost'])],['问题三',f(a3['total_cost']),f(a3['emergency_kwh']),f(a3['emergency_cost'])],['问题4-3',f(a43['total_cost']),f(a43['emergency_kwh']),f(a43['emergency_cost'])]])
p4+=f"波动价格下，日前策略费用增加{f(a42['total_cost']-a2['total_cost'])}元（{pct(a42['total_cost']/a2['total_cost']-1)}\\%），滚动策略增加{f(a43['total_cost']-a3['total_cost'])}元（{pct(a43['total_cost']/a3['total_cost']-1)}\\%）。在相同波动价格环境中，4-3比4-2节省{f(a42['total_cost']-a43['total_cost'])}元，降幅{pct(1-a43['total_cost']/a42['total_cost'])}\\%。该差异体现新增预报、场景构造及滚动交易的综合价值。\n"
p4+=r'''两组动态策略的紧急电量略低于固定价格基线，但紧急费用更高，说明缺口出现在哪个价格时段同样重要。平均电价降低也不能保证总费用降低，因为费用取决于购电量与逐时价格的配对及五倍补购。充放电时移还受到0.81往返效率约束；简化的无其他约束套利条件为高价超过低价的$1/0.81$倍，完整模型还需计入供能风险与容量机会成本。
'''
p4+=fig('q4_prices.pdf','附件4的动态价格分布与日内波动特征')
p4+=f"4-3中价格峰谷差与储能吞吐量的描述性相关系数为{f(cmp3['price_range_pearson_correlation']['battery_throughput_kwh'])}，未显示明显正相关。因此不能将“峰谷差越大必然充放电越多”写成当前数据结论。相关统计也不构成价格波动影响的因果识别。\n"
p4+=specified(q42,'问题4-2',False)
p4+=specified(q43,'问题4-3',True)
p4+=fig('q4_dispatch.pdf','波动价格下12月21日的滚动合同与储能执行策略')
p4+=r'\FloatBarrier'+'\n';write('sections/problem4.tex',p4)

ev=r'''\section{算法对照、敏感性与模型检验}
\subsection{同信息日前方法与滚动信息价值}
在相同334天、设备参数和固定电价下，DET使用前31天净负荷均值，Q80使用逐段80\%分位数，二者均调用确定性储能LP；SAA直接使用问题二，CVaR在同一历史场景上引入紧急费用尾部惩罚。上述四者在0:00拥有相同历史信息。SAA-MPC使用问题三的已发布光伏预报及日内更新，因此在表中单列为信息与机制拓展，不能用其差异证明纯算法优势。
'''
ev+=table('预设主方法的费用与风险比较',['方法','总费用/万元','紧急电量/万kWh','紧急天数','日费CVaR95/元'],[[tex(x['method']),f(float(x['total_cost'])/1e4),f(float(x['emergency_kwh'])/1e4),x['emergency_days'],f(x['cvar95_daily_cost'])] for x in bench])
ev+=r'''在预设静态主比较中，SAA的实际费用最低；Q80比SAA高约0.716\%，说明较高分位数虽然有经济解释，仍不能替代跨时段联合优化。DET的补购费用较大，反映均值计划难以应对非对称缺口损失。SAA-MPC比SAA降低费用约3.347\%，收益来源的进一步分解见第三问。

\subsection{CVaR风险规避与参数敏感性}
设历史场景全天紧急费用为$L_s=\sum_t5p_tU_t^{(s)}$，引入阈值$z$和超额损失$\xi_s$：
\begin{align}
\operatorname{CVaR}_{\alpha}(L)&=z+\frac{1}{1-\alpha}\sum_s\pi_s\xi_s,\\
\xi_s&\geq L_s-z,\quad\xi_s\geq0.
\end{align}
目标为计划费加$(1-\lambda)\mathbb E[L]+\lambda\operatorname{CVaR}_{\alpha}(L)$和微小吞吐惩罚；$z$不限制符号。预设主参数为$\alpha=0.95,\lambda=0.50$，$\lambda=0$退化为SAA。优化对象是紧急费用，表中的“日费CVaR95”则为执行后实际总费用的尾部统计，二者不可混淆。

主CVaR相对SAA增加总费用约0.278\%，紧急电量减少60.704\%，日费用CVaR95下降17.586\%，体现用较高合同费用换取尾部风险降低。经验日费CVaR95按最差5\%概率质量加权，334天对应16.7天，边界样本只取剩余权重。
'''
ev+=table('CVaR参数敏感性：334天实际运行指标',[r'$\alpha$',r'$\lambda$','总费/万元','紧急量/万kWh','日费CVaR95/元'],[[x['alpha'],x['lambda'],f(float(x['total_cost'])/1e4),f(float(x['emergency_kwh'])/1e4),f(x['cvar95_daily_cost'])] for x in sens])
ev+=r'''12组参数预先固定，用于展示权衡而不根据全年结果重新挑选主参数。其中存在费用低于SAA的组合，因此不能宣称SAA优于所有风险规避参数。31个等权场景下，$\alpha=0.99$的尾部不足一个完整场景，其CVaR等于样本最大损失；高置信度并不意味着拥有充分的极端事件信息。样本外实际费用也无需随风险权重单调变化。
'''
ev+=fig('risk_return.pdf','预设方法的实际费用与尾部风险；MPC包含额外信息')
ev+=r'\subsection{可行性、结算与复现检验}'+'\n'
ev+=table('本次合并核验的最大绝对残差（kWh）',['模型','供需平衡','储能转移','首末边界','同时充放电时段'],[[k,f"{v['balance']:.2e}",f"{v['soc']:.2e}",f"{v['daily_boundary']:.2e}",v['simultaneous_slots']] for k,v in audit['physical'].items()])
ev+=r'''本次核验重算第一问和第二问334天，对第三问全期存档检查物理约束、合同恒等式及结算，并独立重算四个指定日期；第四问核对全部存档及原始价格快照。年度工作簿逐时计划、执行合同、四小时储能汇总、紧急区间与日费用均作核对。不同求解器版本可能返回等价最优解；对第二问出现差异的日期固定正式合同及四小时储能汇总重求解，核对其可行性与原最优目标，而不以新数组覆盖正式结果。

第三问19项现有测试通过，覆盖中点插值、未来实际与未发布预报隔离、执行冻结、SOC衔接、退款结算和结果导出。算法对比及12组敏感性使用归档实验结果\cite{experiment}，本次不冒称重新运行全部敏感性实验。单次运行耗时受环境影响，不作为跨硬件性能保证。

\section{模型评价与结论}
\subsection{模型优点与局限}
模型以共同线性储能约束贯穿四问，场景与真实结算分离，逐次合同调整与已执行SOC衔接清楚，便于复现及定位信息价值。正文同时给出指定日期、全期和风险对照，避免只用少量典型日支持总体结论。

局限在于：每日固定边界限制跨日调度；31天等权窗口对快速变化和尾部风险覆盖有限；未考虑电池退化、外网功率限制与未来价格预测；当前LP未显式加入互斥约束；时间标签与内部时段解释仍需最终确认。滚动求解的一系列两阶段LP不等于完整多阶段场景树，单次LP最优不代表全年实际费用全局最优。未来可引入独立验证期、季节性窗口、跨日滚动边界和电池退化成本，比较收益是否足以抵消新增复杂度。

\subsection{主要结论与运行启示}
'''
ev+=f"确定性条件下，储能使示例日购电费降至{f(t['全天购电费'])}元，较无储能基准节省26.8981\\%。对334天未知净负荷，SAA日前策略费用为{f(a2['total_cost'])}元；引入光伏预报与三时刻滚动调整后为{f(a3['total_cost'])}元，下降{pct(1-a3['total_cost']/a2['total_cost'])}\\%。6点与12点更新在当前回测具有明确经济收益，18点未显示额外收益。\n\n波动电价下，4-2和4-3费用分别为{f(a42['total_cost'])}元和{f(a43['total_cost'])}元，同价格环境中滚动策略仍有综合经济优势。运行决策应同时关注缺口发生时刻的电价、合同富余成本与尾部风险，不能仅以平均电价、平均净负荷或最低单日费用制定策略。上述结论均限定于当前数据、价格信息假设和周期储能边界。\n"
ev+=r'\FloatBarrier'+'\n';write('sections/evaluation.tex',ev)

abstract=f'''针对微网在光伏与负载不确定性下的购电和储能协同调度，本文构建确定性线性规划、历史场景随机规划及预报更新下的滚动优化体系，并在统一物理参数、交易结算与信息边界下比较固定和波动电价策略。

问题一将全天划分为144个十分钟时段，在逐段供需平衡、容量功率和首末储电量约束下最小化购电费。示例日费用为{f(t['全天购电费'])}元，相对无储能基准降低26.8981\\%。问题二以此前31天配对净负荷构造等概率场景，联合优化日前计划与五倍电价紧急补购风险，2025年2月至12月334天实际费用为{f(a2['total_cost'])}元。

问题三对小时光伏预报作中点插值，叠加同日历史预测误差，并在已执行储电量及前版合同基础上逐次调整。六种预报组合回测支持0、6、12点策略，实际费用为{f(a3['total_cost'])}元，较问题二减少{pct(1-a3['total_cost']/a2['total_cost'])}\\%。共同晚间窗口误差分析表明，预报精度的微小改善不必然带来经济收益，当前18点更新未显示额外节省。问题四保持策略与场景方法不变，采用给定动态电价曲线，日前与滚动策略费用分别为{f(a42['total_cost'])}元和{f(a43['total_cost'])}元。

同信息算法对照表明，联合随机优化优于本次均值和80\\%分位主基准；风险规避模型以小幅费用增加换取紧急购电和尾部费用下降。物理、结算及信息隔离检验支持策略的可行性与可复核性。结论适用于每日固定储电量边界和给定价格条件，尚需跨期验证及统一时间标签解释后进一步推广。
'''
main=r'''% !TeX program = xelatex
\documentclass[withoutpreface,bwprint]{cumcmthesis}
\usepackage{cumcm2026}
\usepackage{placeins,url,needspace}
\raggedbottom
\setlength{\emergencystretch}{2em}
\title{基于历史场景与滚动预报的微网购电及储能调度}
\tihao{C}\baominghao{}\schoolname{}\membera{}\memberb{}\memberc{}\supervisor{}
\yearinput{2026}\monthinput{9}\dayinput{}
\begin{document}\maketitle
\begin{abstract}
'''+abstract+r'''
\keywords{微网调度\quad 随机规划\quad 滚动优化\quad 光伏预报\quad 条件风险价值}
\end{abstract}
\input{sections/front}
\input{sections/problem1}
\input{sections/problem2}
\input{sections/problem3}
\input{sections/problem4}
\input{sections/evaluation}
\CumcmAIUsed{论文材料比较、计算口径核对、文字整合与排版。完整使用记录需由参赛队结合实际使用过程核实并随支撑材料提供}
\begin{thebibliography}{9}
\bibitem{problem} 2026年高教社杯全国大学生数学建模竞赛C题：微网与外部电网电力调控策略及附件1--5[Z]. 用户提供的赛题与数据材料, 2026.
\bibitem{experiment} CUCUM2026项目. 固定分时电价算法对比实验[Z]. 本地实验记录，评估期2025-02-01至2025-12-31, 2026.
\end{thebibliography}
\clearpage\begin{appendices}
\section{结果与复现材料索引}
本论文的正式计算来源统一位于CUCUM2026。五份结果文件均位于\path{target/}下的“附件5”目录，文件名为\path{result1.xlsx}、\path{result2.xlsx}、\path{result3.xlsx}、\path{result4-2.xlsx}和\path{result4-3.xlsx}。问题一至四求解入口分别为\path{run_question1.py}、\path{run_question2.py}、\path{run_question3.py}和\path{run_question4.py}。算法实验入口为\path{run_benchmark.py}，依赖见项目根目录\path{requirements.txt}，完整源代码位于\path{src/}。

\section{论文材料来源与核验范围}
正文图表由当前正式摘要和实验数据生成，数值快照及SHA-256见\path{paper/data_snapshot/manifest.json}。独立口径核对与逐节合并记录位于\path{paper/review/}；本次可执行核验、结果及第三问测试日志分别为\path{paper/audit_sources.py}、\path{paper/review/audit_results.json}和\path{paper/review/tests_question3.log}。PDF编译不运行优化器。

\section{初稿使用说明}
本稿用于统一论文内容和结果，学术方法参考文献、队伍完整AI使用记录及最终格式核查仍需补齐。已披露的时间标签解释及每日闭环、价格已知假设须在最终提交前确认。当前附录提供代码和结果索引，最终提交时应依适用要求补齐完整程序附录与独立支撑文件。源文件和完整工程均保留，便于后续完善。
\end{appendices}\end{document}
'''
write('main.tex',main)
write('README.md','''# 独立合并论文初稿

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
''')
print('Draft generated under',P)
