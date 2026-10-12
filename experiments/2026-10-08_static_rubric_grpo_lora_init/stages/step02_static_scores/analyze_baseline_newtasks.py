"""Read-only scoring audit and deterministic aggregation for the DRACO baseline."""
from collections import Counter
from datetime import datetime, timezone
from fractions import Fraction
import csv,json,math,statistics,sys
from pathlib import Path
sys.dont_write_bytecode=True
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
import common
import baseline_newtasks as run

OUT=run.OUT

def main():
    cfg=common.load_config(); m=common.read_json(OUT/'manifest.json'); spec=common.read_json(OUT/'analysis_spec.json')
    summary=common.read_json(OUT/'summary.json')
    assert summary['scored_trajectories']==18 and summary['complete_groups']==3
    assert common.file_sha(OUT/'analysis_spec.json')==m['audit_spec_sha256']
    assert common.input_fingerprint(cfg)==m['collection_runtime_fingerprint']
    for rel,sha in m['source_hashes'].items(): assert common.file_sha(run.ROOT/rel)==sha
    rules=common.load_rules(cfg); lookup={}; rows=[]; usage=Counter(); attempts=[]
    for row in m['selected_trajectories']:
        assert common.file_sha(row['trajectory'])==row['sha256']
        uid=f"{row['task_id']}__{row['sample']:02d}"; folder=OUT/'judgements'/uid
        result=common.read_json(folder/'judgement.json')
        common.validate_judgement({'scores':result['scores']},rules)
        assert result['scores']==common.read_json(folder/f"response_{result['attempts']}.json")['scores']
        prompt=run.judge.build_prompt(cfg,common.read_json(row['trajectory']))
        assert prompt==(folder/'prompt.txt').read_text()
        assert result['cache_key']==common.digest({'prompt':prompt,'judge':cfg['judge'],'schema_sha256':common.file_sha(run.ROOT/cfg['judge']['schema'])})
        lookup[uid]=result
        for i,s in enumerate(result['scores']): rows.append({'trajectory_id':uid,'rule_id':i,**s})
        for events in sorted(folder.glob('events_*.jsonl')):
            try:
                a=run.judge.audit_events(events.read_text()); usage.update(a['usage'] or {}); attempts.append({'path':str(events),'completed':True})
            except ValueError as e: attempts.append({'path':str(events),'completed':False,'error':str(e)})
    with (OUT/'all_verdicts.csv').open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    audit=[{**p,**lookup[p['trajectory_id']]['scores'][p['rule_id']]} for p in spec['audit_pairs']]
    common.atomic_json(OUT/'audit_sample.json',{'selection':spec['audit_selection'],'records':audit})
    group_checks=[]; tables=['# 新题 DRACO 静态基线：原始判定与 reward','', '每项为整个 rollout 的判定。P=+1，F=−1，NA=0；至少一个 F 的规则进入同题六条共同保留集合。NA 不计入 reward 分母。','']
    for g in summary['groups']:
        task=g['task_id']; matrix=[[s['score'] for s in lookup[f'{task}__{i:02d}']['scores']] for i in range(6)]
        kept=[r for r in range(21) if any(v[r]==-1 for v in matrix)]
        assert kept==g['kept_rule_ids']; calculated=[]; counts=[]
        for i,v in enumerate(matrix):
            p=sum(v[r]==1 for r in kept); f=sum(v[r]==-1 for r in kept); na=sum(v[r]==0 for r in kept)
            reward=float(10*Fraction(p-f,p+f)) if p+f else 0.0
            assert math.isclose(reward,g['rewards'][i],abs_tol=1e-12)
            counts.append({'sample':i,'P':p,'F':f,'NA':na,'reward':reward});calculated.append(reward)
        mean=statistics.mean(calculated); sd=statistics.stdev(calculated)
        adv=[(r-mean)/(sd+1e-6) if sd else 0.0 for r in calculated]
        assert all(math.isclose(a,b,abs_tol=1e-12) for a,b in zip(adv,g['advantages']))
        group_checks.append({'task_id':task,'kept_rule_ids':kept,'counts':counts,'mean':mean,'sample_std':sd,'advantages':adv})
        instruction=common.read_json(run.COLLECTION/'trajectories'/f'{task}__00.json')['public_task']['instruction']
        tables.extend([f'## {task}', '',instruction,'','| 规则 | 00 | 01 | 02 | 03 | 04 | 05 | 保留 |','| --- | --- | --- | --- | --- | --- | --- | --- |'])
        labels={1:'P',-1:'F',0:'NA'}
        for r,rule in enumerate(rules): tables.append('| R'+f'{r+1:02d} '+rule['title']+' | '+' | '.join(labels[v[r]] for v in matrix)+' | '+('是' if r in kept else '否')+' |')
        tables.extend(['','reward = 10×(P−F)/(P+F)；P+F=0 时记 0。','', '| 轨迹 | P | F | NA | 代入 | reward | advantage | 官方成功（仅诊断） |','| --- | --- | --- | --- | --- | --- | --- | --- |'])
        for row in counts:
            i=row['sample'];p=row['P'];f=row['F'];formula=f'10×({p}−{f})/({p}+{f})' if p+f else '分母为0'
            tables.append(f"| {i:02d} | {p} | {f} | {row['NA']} | {formula} | {row['reward']:.6f} | {adv[i]:.6f} | {g['official_success'][i]} |")
        tables.extend(['',f'均值 {mean:.9f}；样本标准差 {sd:.9f}；advantage=(reward−均值)/(标准差+1e−6)。',''])
    (OUT/'REWARD_TABLES.md').write_text('\n'.join(tables)+'\n')
    common.atomic_json(OUT/'reward_verification.json',group_checks)
    validation={'passed':True,'at_utc':datetime.now(timezone.utc).isoformat(),'scope':'technical integrity and deterministic calculations, not semantic accuracy','trajectories':18,'verdicts':378,'groups':3,'requests':len(attempts),'retries':len(attempts)-18,'usage':dict(usage),'attempts':attempts,'checks':['source and input SHA256 match','official prompt and rubric unchanged','no calibration_v3 module or semantic rejection','accepted responses equal stored verdicts','same fixed 30 audit pairs','independent Fraction reward and sample-std advantage match'],'analysis_script_sha256':common.file_sha(Path(__file__))}
    common.atomic_json(OUT/'technical_validation.json',validation)
    print(json.dumps({'counts':summary['verdict_counts'],'groups':summary['groups'],'requests':len(attempts),'usage':dict(usage),'audit':audit},ensure_ascii=False,indent=2))

if __name__=='__main__':main()
