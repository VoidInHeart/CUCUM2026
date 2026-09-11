"""不求解、不写正式结果；核对论文数据快照与指定日期原表。"""
from pathlib import Path
import json,hashlib,re
from openpyxl import load_workbook
from pypdf import PdfReader
P=Path(__file__).resolve().parent;ROOT=P.parent
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
checks={}
for row in read(P/'data_snapshot/manifest.json'):
    assert sha(ROOT/row['source'])==sha(P/'data_snapshot'/row['snapshot'])==row['sha256']
checks['snapshots']='passed'
errors={}
for name,folder,rolling in [('result2','question2',False),('result3','question3',True),('result4-2','question4/question4_2',False),('result4-3','question4/question4_3',True)]:
    summary=read(ROOT/'target'/folder/'summary.json');wb=load_workbook(ROOT/f'target/附件5/{name}.xlsx',read_only=True,data_only=True)
    plan=list(wb['计划购电量'].values);idx={str(row[0])[:10]:i for i,row in enumerate(plan[1:],1)};labels=list(plan[0]);batt=list(wb['充放电量'].values)
    adjusted=list(wb['调整购电量'].values) if rolling else None
    e=0
    for day,s in summary['paper_dates'].items():
        i=idx[day]
        for label,v in s['表1'].items():
            col=labels.index(label)
            e=max(e,abs(plan[i][col]-v['初始计划购电量' if rolling else '计划购电量']))
            if rolling:e=max(e,abs(adjusted[i][col]-v['执行合同购电量']))
        for k,(label,v) in enumerate((a,b) for a,b in s['表2'].items() if isinstance(b,dict)):
            row=batt[(i-1)*6+k+1];assert row[1]==label
            e=max(e,abs(row[2]-v['累计充电量']),abs(row[3]-v['累计放电量']))
        m=s['全天指标'];costrow=adjusted[i] if rolling else plan[i];e=max(e,abs(costrow[146]-m['total_cost']))
    assert e<1e-6,(name,e);errors[name]=e;wb.close()
checks['specified_table_source_max_errors']=errors
logs={}
for name,n in [('tests_question3.log',19),('tests_question4_models.log',9),('tests_question4_prices.log',6)]:
    content=(P/'review'/name).read_text(encoding='utf-8');assert f'Ran {n} tests' in content and content.strip().endswith('OK');logs[name]=n
checks['tests']=logs
log=(P/'output/pdf/main.log').read_text(encoding='utf-8',errors='replace')
for bad in ['Overfull','Missing character','undefined references','undefined on input','Float too large']:
    assert bad not in log,bad
checks['layout_log']='no overflow, missing glyphs or undefined references'
pdf=P/'output/pdf/main.pdf';checks['pages']=len(PdfReader(pdf).pages);checks['pdf_sha256']=sha(pdf)
alltext='\n'.join(x.read_text(encoding='utf-8') for x in [P/'main.tex',*sorted((P/'sections').glob('*.tex'))])
assert not any(ord(c)<32 and c not in '\n\r\t' for c in alltext)
assert '\toprule' not in alltext # Python tab+oprule escape must not appear.
for number in ['17609791.6865','17020306.6465','17923538.0937','17244554.4259']:
    assert number in alltext
checks['main_numbers']='passed'
original=read(P/'review/source_hashes.json');changed=[s for s,h in original.items() if sha(Path(s))!=h]
assert not changed;checks['preserved_original_files']=len(original)
(P/'review/publication_verification.json').write_text(json.dumps(checks,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(checks,ensure_ascii=False,indent=2))
