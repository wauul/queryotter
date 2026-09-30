import time, statistics, math
from collections import Counter
from backend.db import sandbox, explain, result, compact, metadata, METRICS
from backend.safety import validate_query, validate_index
from backend.model import propose

class Cancelled(Exception): pass

def equivalent(conn, original, candidate):
    ot,orr=result(conn,original); ct,cr=result(conn,candidate)
    ordered='ORDER BY' in original.upper()
    return ot==ct and (orr==cr if ordered else Counter(orr)==Counter(cr))

def summary(values):
    med=statistics.median(values)
    return {'median_ms':round(med,3),'min_ms':round(min(values),3),'max_ms':round(max(values),3),'mad_ms':round(statistics.median(abs(x-med) for x in values),3),'samples_ms':[round(v,3) for v in values]}

def decide(a,b):
    # A conservative practical threshold plus robust within-run variability.
    margin=max(a['median_ms']*.1,3*max(a['mad_ms'],b['mad_ms']),.05)
    delta=a['median_ms']-b['median_ms']
    return 'verified improvement' if delta>margin else 'regression' if delta < -margin else 'inconclusive'

def run(query,event=lambda stage,message:None,check=lambda:None,baseline=None):
    start=time.monotonic(); db_seconds=0; tool_calls=0
    metrics={'calls':0,'seconds':0};METRICS.set(metrics)
    def checkpoint():
        check()
        if time.monotonic()-start>180: raise TimeoutError('Investigation exceeded the 180 second job budget.')
    query=validate_query(query)
    event('inspect','SQL parsed. One safe SELECT; disposable synthetic PostgreSQL only.')
    with sandbox() as (conn,schema):
        checkpoint(); info=metadata(conn); before=explain(conn,query,True); tool_calls+=2
        event('explain','Initial JSON execution plan collected; no records sent to model.')
        if baseline is None:
            proposal,usage=propose(query,info,compact(before))
            candidates=[c.model_dump() for c in proposal.candidates]; diagnosis=proposal.diagnosis
        else:
            candidates=[{'name':'Deterministic index baseline','hypothesis':'Index columns in the fixed evaluation manifest.','query':query,'indexes':baseline}] if baseline else []
            diagnosis='Deterministic evaluation baseline; no model call.'; usage={'provider':'deterministic baseline','calls':0,'input_tokens':0,'output_tokens':0,'estimated_cost_usd':0}
        checkpoint(); event('hypothesize',f'{len(candidates)} ranked candidates proposed. Measurements will decide.')
        results=[]
        for n,candidate in enumerate(candidates[:3]):
            checkpoint(); event('experiment',f'Testing candidate {n+1}: {candidate["name"]}')
            record={**candidate,'correctness':{'passed':False,'datasets':[]},'status':'rejected'}
            try:
                cq=validate_query(candidate['query']); indexes=[validate_index(s) for s in candidate['indexes']]
                # independent validation fixtures, including empty, NULLs, duplicates and skew.
                for size,seed,edge in [(0,17,False),(300,17,True),(900,31,True)]:
                    checkpoint()
                    with sandbox(size,seed,edge) as (small,_):
                        for index in indexes: small.execute(index)
                        passed=equivalent(small,query,cq); tool_calls+=2
                        record['correctness']['datasets'].append({'size':size,'seed':seed,'edges':edge,'passed':passed})
                        if not passed: raise ValueError('Candidate changed values, types, multiplicities or ordered output on an edge fixture.')
                # Freeze original result in the same synthetic dataset, before candidate indexes.
                ot,original_rows=result(conn,query); tool_calls+=1
                record['correctness']['passed']=True
                event('validate','Edge fixtures passed. Checking the 120,000-row dataset; empirical verification only.')
                with conn.transaction(force_rollback=True):
                    checkpoint()
                    # Warm both variants. Two index states are alternated in paired rounds.
                    index_seconds=0; index_bytes=0
                    a=[];b=[];after=None
                    for rep in range(9):
                        checkpoint(); forward=rep%2==0
                        for improved in ([False,True] if forward else [True,False]):
                            checkpoint()
                            if improved:
                                with conn.transaction(force_rollback=True):
                                    construction=time.monotonic()
                                    for index in indexes: conn.execute(index)
                                    elapsed=time.monotonic()-construction
                                    if rep==0:
                                        index_seconds=elapsed
                                        index_bytes=conn.execute("SELECT COALESCE(sum(pg_relation_size(indexrelid)),0) FROM pg_index i JOIN pg_class c ON c.oid=i.indexrelid WHERE c.relnamespace=current_schema()::regnamespace AND NOT i.indisprimary").fetchone()[0]
                                        ct,rows=result(conn,cq);tool_calls+=1
                                        if ot!=ct or (original_rows!=rows if 'ORDER BY' in query.upper() else Counter(original_rows)!=Counter(rows)):
                                            raise ValueError('Candidate changed output on benchmark dataset.')
                                        record['correctness']['datasets'].append({'size':120000,'seed':17,'edges':False,'passed':True})
                                    # Identical warmups for both states; exclude index build from latency.
                                    explain(conn,cq,True);tool_calls+=1
                                    plan=explain(conn,cq,True);tool_calls+=1
                                    if rep>=2: b.append(plan['Execution Time'])
                                    after=plan
                            else:
                                explain(conn,query,True);tool_calls+=1
                                plan=explain(conn,query,True);tool_calls+=1
                                if rep>=2:a.append(plan['Execution Time'])
                    aa,bb=summary(a),summary(b);state=decide(aa,bb)
                    record.update({'query':cq,'status':state,'original':aa,'optimized':bb,'speedup':round(aa['median_ms']/max(bb['median_ms'],.001),2),'saved_ms':round(aa['median_ms']-bb['median_ms'],3),'plan':compact(after),'index_build_ms':round(index_seconds*1000,2),'index_bytes':int(index_bytes),'tradeoff':'Index maintenance adds write work and storage; write overhead was not measured.' if indexes else 'No additional index storage.'})
                event('benchmark',f'{record["status"]}: {aa["median_ms"]} ms → {bb["median_ms"]} ms (warm cache).')
            except (ValueError, Exception) as exc:
                if isinstance(exc,(Cancelled,TimeoutError)): raise
                # SQL/provider errors may contain SQL but never DSN or raw values; only safe classification exported.
                record['reason']=str(exc) if isinstance(exc,ValueError) else f'Experiment rejected: {type(exc).__name__}. Statement budget or database restriction may apply.'
                record['correctness']['passed']=False
                event('validate',record['reason'])
            results.append(record)
        wins=[r for r in results if r['status']=='verified improvement' and r['correctness']['passed']]
        best=min(wins,key=lambda r:r['optimized']['median_ms']) if wins else None
        checkpoint(); event('recommend','Best measured candidate selected.' if best else 'No reliable improvement found. Retain the original query.')
        original=best['original'] if best else next((r['original'] for r in results if 'original' in r),None)
        if original is None:
            vals=[]
            for rep in range(9):
                checkpoint(); plan=explain(conn,query,True);tool_calls+=1
                if rep>=2: vals.append(plan['Execution Time'])
            original=summary(vals)
        return {'query':query,'diagnosis':diagnosis,'candidates':results,'best':best,'original':original,'plan_before':compact(before),'schema':info,'conditions':{'postgresql':info['version'],'rows':{'customers':10000,'orders':120000,'items':240000},'seed':17,'cache':'warm cache; no cold-cache control','repetitions':7,'warmup_rounds':2,'execution_order':'Alternating original/candidate index states; equal per-state warmups','parallel_workers':0,'statement_timeout_ms':3000,'lock_timeout_ms':500,'comparison_row_cap':20000,'equivalence':'Empirical result equality on four fixtures; not a mathematical proof. Types and duplicate counts preserved; sequence compared when ordered.','index_isolation':'Each candidate uses transaction rollback in a disposable schema.','database_time_definition':'Client time in SQL execute calls including seeding and metadata, excluding model; streaming fetch and connection setup excluded.'},'usage':usage|{'tool_calls':metrics['calls'],'runtime_seconds':round(time.monotonic()-start,2),'database_seconds':round(metrics['seconds'],3)},'migration':best['indexes'] if best else [],'limitations':['Synthetic workload; verify against representative sanitized data.','CPU/cache state and index construction can affect benchmark variability.','Write overhead and cold-cache latency not measured.','Sample equality does not prove equivalence on all possible databases.']}
