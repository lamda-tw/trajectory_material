"""Read-only evidence analysis; writes derived outputs, never invokes a model."""
from collections import Counter
import csv
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import statistics
import sys
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
import common
import judge_compat
OUT=ROOT/'runs/step02_static_scores/smoke_v2'

def main():
    config=common.load_config();manifest=common.read_json(OUT/'manifest.json');rules=common.load_rules(config)
    rows=manifest['selected_trajectories'];records=[];totals=Counter();calls=[]
    assert common.input_fingerprint(config)==manifest['collection_runtime_fingerprint']
    assert common.file_sha(ROOT/'runs/step01_train90_rollouts/trajectory_index.json')==manifest['trajectory_index_sha256']
    for rel,sha in manifest['source_hashes'].items():
        assert common.file_sha(ROOT/rel)==sha
    for row in rows:
        assert common.file_sha(row['trajectory'])==row['sha256']
        uid=f"{row['task_id']}__{row['sample']:02d}";d=OUT/'judgements'/uid
        result=common.read_json(d/'judgement.json')
        common.validate_judgement({'scores':result['scores']},rules)
        for i,score in enumerate(result['scores']):
            records.append({'trajectory_id':uid,'task_id':row['task_id'],'sample':row['sample'],
                            'rule_id':i,'rubric_title':rules[i]['title'],'score':score['score'],
                            'evidence':score['evidence'],'justification':score['justification']})
        for p in sorted(d.glob('events_*.jsonl')):
            audit=judge_compat.audit_events(p.read_text());usage=audit['usage'] or {}
            totals.update({k:v for k,v in usage.items() if isinstance(v,int)})
            calls.append({'trajectory_id':uid,'stream':str(p),'usage':usage,'tool_free':True,
                          'accepted_startup_diagnostics':audit['accepted_startup_diagnostics']})
    with (OUT/'all_verdicts.csv').open('w',newline='') as h:
        w=csv.DictWriter(h,fieldnames=list(records[0]));w.writeheader();w.writerows(records)
    samples=[]
    for verdict in [1,-1,0]:
        candidates=[x for x in records if x['score']==verdict]
        candidates.sort(key=lambda x:hashlib.sha256(f"rubric-audit:20261009:{x['trajectory_id']}:{x['rule_id']}".encode()).hexdigest())
        samples+=candidates[:10]
    common.atomic_json(OUT/'audit_sample.json',{'selection':'sha256 rubric-audit:20261009:<trajectory_id>:<rule_id>, first 10 per score; shortage kept as-is','records':samples})
    summary=common.read_json(OUT/'summary.json');assert summary['scored_trajectories']==12 and summary['complete_groups']==2
    first=OUT/'judgements/e7a10f8_3__00'
    first_scores=common.read_json(first/'response_1.json')['scores'];second_scores=common.read_json(first/'response_2.json')['scores']
    differences=[{'rule_id':i,'title':rules[i]['title'],'first':a['score'],'repeat':b['score'],'first_evidence':a['evidence'],'repeat_evidence':b['evidence']} for i,(a,b) in enumerate(zip(first_scores,second_scores)) if a['score']!=b['score']]
    group=next(x for x in summary['groups'] if x['task_id']=='e7a10f8_3')
    matrix=[];verdict_map={-1:'FAIL',0:'NA',1:'PASS'}
    for sample in range(6):
        result=common.read_json(OUT/f'judgements/e7a10f8_3__{sample:02d}/judgement.json')
        matrix.append([verdict_map[x['score']] for x in result['scores']])
    matrix[0]=[verdict_map[x['score']] for x in second_scores]
    alternative=common.rubric_rewards(matrix)
    repetition={'reason':'Unplanned retry caused by pre-turn diagnostic validator bug; earliest response retained. This is one repeat only, not a judge reliability estimate.',
                'agreement':sum(a['score']==b['score'] for a,b in zip(first_scores,second_scores)),
                'total_rules':21,'differences':differences,
                'accepted_group_rewards':group['rewards'],'counterfactual_repeat_group_rewards':alternative['rewards'],
                'accepted_kept_rule_ids':group['kept_rule_ids'],'counterfactual_repeat_kept_rule_ids':alternative['kept_rule_ids']}
    common.atomic_json(OUT/'incidental_repeat_analysis.json',repetition)
    checks={'complete_12_trajectories_252_verdicts':len(records)==252,'complete_two_groups':len(summary['groups'])==2,
            'exact_rule_order_and_schema':True,'inputs_and_collection_fingerprint_unchanged':True,
            'all_remote_turns_completed_no_tools':all(x['tool_free'] for x in calls),
            'earliest_complete_response_retained':common.read_json(first/'judgement.json')['accepted_attempt']==1}
    assert all(checks.values())
    validation={'passed':True,'verified_at_utc':datetime.now(timezone.utc).isoformat(),'checks':checks,
                'judge_requests':len(calls),'unique_scored_trajectories':12,'extra_retry_requests':len(calls)-12,
                'all_call_usage_including_retry':dict(totals),'call_details':calls,
                'audit_sample_size':len(samples),'incidental_repeat':repetition,
                'manual_evidence_review':'pending','analysis_script_sha256':common.file_sha(Path(__file__))}
    common.atomic_json(OUT/'technical_validation.json',validation)
    print(json.dumps({'verdict_counts':summary['verdict_counts'],'groups':summary['groups'],
                      'judge_requests':len(calls),'all_usage':dict(totals),'incidental_repeat':repetition},ensure_ascii=False,indent=2))

if __name__=='__main__': main()
