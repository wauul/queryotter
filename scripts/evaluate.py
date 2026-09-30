"""Publish every fixed case, with a separately defined deterministic baseline."""
import json,time,sys
from pathlib import Path
from backend.cases import CASES
from backend.investigate import run
from backend.safety import Unsupported

def main():
    Path('public/reports').mkdir(parents=True,exist_ok=True)
    Path('public/examples.json').write_text(json.dumps([{k:v for k,v in c.items() if k!='baseline'} for c in CASES],indent=2),encoding='utf8')
    rows=[];start=time.monotonic()
    for case in CASES:
        print('Evaluating '+case['id'],flush=True)
        row={k:case[k] for k in ('id','title','category')};row.update(original_ms=None,best_ms=None,baseline_ms=None,correctness=None)
        try:
            r=run(case['sql']);best=r['best']
            row.update(outcome='verified improvement' if best else 'inconclusive' if r['candidates'] else 'no justified candidate',original_ms=r['original']['median_ms'],best_ms=best['optimized']['median_ms'] if best else None,correctness=all(c['correctness']['passed'] for c in r['candidates']) if r['candidates'] else None,agent_usage=r['usage'],candidate_outcomes=[c['status'] for c in r['candidates']],speedup=best['speedup'] if best else None,index_bytes=best['index_bytes'] if best else None,index_build_ms=best['index_build_ms'] if best else None)
            Path('public/reports/'+case['id']+'.json').write_text(json.dumps(r,indent=2,default=str),encoding='utf8')
            b=run(case['sql'],baseline=case['baseline'])
            row['baseline_ms']=b['best']['optimized']['median_ms'] if b['best'] else b['original']['median_ms']
            row['baseline_outcome']='verified improvement' if b['best'] else 'inconclusive or no gain'
        except Unsupported as e:row.update(outcome='rejected',reason=str(e))
        except Exception as e:row.update(outcome='error',reason=type(e).__name__)
        rows.append(row)
        print(json.dumps(row),flush=True)
        if case['id'] not in {'unsafe','volatile','ambiguous'}:time.sleep(10)
    candidates=[s for r in rows for s in r.get('candidate_outcomes',[])]
    eligible=[r for r in rows if r['outcome'] not in ('rejected','error')]
    checked=[r for r in rows if r['correctness'] is not None]
    summary={'cases':len(rows),'verified_optimizations':sum(r['outcome']=='verified improvement' for r in rows),'regressions':candidates.count('regression'),'inconclusive':sum(r['outcome']=='inconclusive' for r in rows),'rejected_inputs':sum(r['outcome']=='rejected' for r in rows),'errors':sum(r['outcome']=='error' for r in rows),'empirical_correctness_pass_rate':f'{sum(bool(r["correctness"]) for r in checked)}/{len(checked)} checked cases','verified_optimization_rate':f'{sum(r["outcome"]=="verified improvement" for r in eligible)}/{len(eligible)} supported cases'}
    data={'generated_at':'2026-09-30','summary':summary,'cases':rows,'runtime_seconds':round(time.monotonic()-start,2),'methodology':'Full fixed suite; no favorable-case selection. Original versus Groq-chosen candidates and independent fixed index baseline. PostgreSQL execution time, warm cache only. Seven repetitions after two warm-up rounds with alternating index states and equal warmups. A win must exceed 10% original median, 3× maximum MAD, and 0.05 ms. Empirical equality on empty, two edge fixtures and full synthetic data does not prove equivalence. Regressions count tested candidates; selected recommendations cannot be regressions. Pricing and database operation time unavailable in this run.'}
    Path('public/evaluation.json').write_text(json.dumps(data,indent=2),encoding='utf8')
    print(json.dumps(summary),flush=True)
if __name__=='__main__':main()
