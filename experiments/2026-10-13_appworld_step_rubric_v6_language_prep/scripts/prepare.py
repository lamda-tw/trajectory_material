"""Prepare frozen English-v6 pilot materials locally; no model calls or execution runner."""
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
import csv, hashlib, json, re, shutil
ROOT=Path(__file__).resolve().parents[1]
WS=ROOT.parents[1]
PLAN=WS/'plans/2026-10-12_appworld_step_rubric'
FULL=ROOT.parent/'2026-10-13_appworld_qwen3_8b_step_rubric_v5_full'
OLD=ROOT.parent/'2026-10-12_appworld_step_rubric_pilot'
DRACO=ROOT.parent/'2026-10-08_static_rubric_grpo/assets/draco'
SEED='v6-language-prep-20261013'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_text())
def dump(p,d):p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n')
for name in ['assets','manifests','review']:(ROOT/name).mkdir(exist_ok=True)
for src,dst in [('prompt_v6.txt','prompt_v6_zh.txt'),('prompt_v6_en.txt','prompt_v6_en.txt'),('output_schema_v6.json','output_schema_v6.json'),('validate_output_v6.py','validate_output_v6.py')]:shutil.copyfile(PLAN/src,ROOT/'assets'/dst)
assert sha(PLAN/'prompt_v6.txt')==read(PLAN/'v6_provenance.json')['prompt_sha256']
manifest=read(FULL/'manifest.json'); samples={s['id']:s for s in manifest['samples']}
metrics={r['id']:r for r in csv.DictReader((FULL/'analysis/trajectory_metrics.csv').open())}
reg=read(OLD/'manifest_v5_regression.json')['samples']
oldids={s['id'] for n in ['manifest_v5_regression.json','manifest_v5_fresh.json'] for s in read(OLD/n)['samples']}
dev=[s['id'] for s in reg]
devf={metrics[i]['task_family'] for i in dev}
def stable(i):return hashlib.sha256((SEED+i).encode()).hexdigest()
def features(i):
 r=metrics[i]; f={f'R{k}:{l}' for k in range(1,9) for l in 'PFUN' if int(r[f'R{k}_{l}'])>0}
 f|={f'termination:{r["termination"]}',f'length:{"short" if int(r["steps"])<=10 else "long" if int(r["steps"])>=30 else "medium"}'}
 if int(r['only_R8_F_steps']):f.add('only_R8_failure')
 return f
def choose(pool,n,chosen):
 added=[]
 for _ in range(n):
  covered=set().union(*(features(i) for i in chosen+added)) if chosen+added else set()
  tasks={metrics[i]['task_id'] for i in chosen+added}; families={metrics[i]['task_family'] for i in chosen+added}
  def key(i):
   new=features(i)-covered
   rare=sum(x.startswith(('R5:','R7:')) for x in new)
   return (metrics[i]['task_id'] not in tasks, rare, metrics[i]['task_family'] not in families,len(new),stable(i))
  pick=max((i for i in pool if i not in chosen+added),key=key);added.append(pick)
 return added
pool=[i for i,r in metrics.items() if r['task_family'] in devf and r['official_success']=='False' and i not in dev]
dev+=choose(pool,4,dev)
hold=[]
for outcome,n in [('True',8),('False',16)]:
 pool=[i for i,r in metrics.items() if r['task_family'] not in devf and r['official_success']==outcome and i not in oldids]
 hold+=choose(pool,n,hold)
repeat=[]
for split in [dev,hold]:
 for outcome in ['True','False']:
  pool=[i for i in split if metrics[i]['official_success']==outcome]
  repeat+=choose(pool,2,repeat)
assert len(dev)==12 and len(hold)==24 and len(repeat)==8
assert not set(dev)&set(hold)
assert not {metrics[i]['task_family'] for i in dev}&{metrics[i]['task_family'] for i in hold}
def entries(ids):
 out=[]
 for i in ids:
  s=dict(samples[i]);s['input']=str(FULL/s['input'])
  assert sha(Path(s['input']))==s['input_sha256']
  assert sha(Path(s['source']))==s['source_sha256']
  s['selection_metadata_not_for_judge']={'official_success':metrics[i]['official_success']=='True','task_family':metrics[i]['task_family'],'v5_applicable_labels':sorted(features(i))}
  out.append(s)
 return out
summaries={}
for name,ids in [('development',dev),('holdout',hold),('repeat',repeat)]:
 selected=entries(ids)
 summaries[name]={'trajectories':len(ids),'steps':sum(int(metrics[i]['steps']) for i in ids),'successes':sum(metrics[i]['official_success']=='True' for i in ids),'tasks':len({metrics[i]['task_id'] for i in ids}),'families':len({metrics[i]['task_family'] for i in ids}),'v5_label_counts':{f'R{k}':{l:sum(int(metrics[i][f'R{k}_{l}']) for i in ids) for l in 'PFUN'} for k in range(1,9)}}
 dump(ROOT/'manifests'/f'{name}.json',{'status':'prepared_not_scored','selection_seed':SEED,'purpose':name,'selection_uses_existing_v5_labels_only_as_sampling_proxies':True,'samples':selected})
source_zh=(PLAN/'prompt_v6.txt').read_text();source_en=(PLAN/'prompt_v6_en.txt').read_text()
zh_sections=source_zh.strip().split('\n\n');en_sections=source_en.strip().split('\n\n')
assert len(zh_sections)==len(en_sections)
alignment=[{'section':i+1,'zh':z,'en':e} for i,(z,e) in enumerate(zip(zh_sections,en_sections))]
dump(ROOT/'review/translation_alignment.json',alignment)
# Check structural compatibility, not scoring behavior.
import jsonschema
schema=read(ROOT/'assets/output_schema_v6.json');jsonschema.Draft202012Validator.check_schema(schema)
for text in [source_zh,source_en]:
 assert text.count('{{TRAJECTORY_JSON}}')==1
 assert re.findall(r'^R([1-8]) ',text,re.M)==list('12345678')
 example=json.loads(next(line for line in text.splitlines() if line.startswith('{"trajectory_id"')))
 jsonschema.Draft202012Validator(schema).validate(example)
 assert all(len(r[2])<=60 for r in example['steps'])
assert not re.search(r'[\u4e00-\u9fff]',source_en)
config={'status':'prepared_not_scored','execution_enabled':False,'purpose':'Quality-first validation of English v6; no mandatory Chinese/English A/B experiment.','model':'gpt-5.6-sol','reasoning_effort':'high','initial_workers':2,'max_workers':2,'rubric_version':'appworld-step-v6','prompt':'assets/prompt_v6_en.txt','prompt_sha256':sha(ROOT/'assets/prompt_v6_en.txt'),'chinese_reference_only':'assets/prompt_v6_zh.txt','output_schema':'assets/output_schema_v6.json','replication':'One first-valid result for 36 trajectories; one additional independent call for 8 selected trajectories.','planned_initial_calls_before_retries':44,'stage_calls':{'development_including_repeats':16,'holdout_including_repeats':28},'retry_rule':'Only transport/schema failures; never choose best-of valid labels; retain every attempt.','model_snapshot_policy':'Record resolved model/version if available; an alias may change over time.','source_payload_rule':'Pass only the pinned prepared input JSON; never include selection metadata, old judgments, official outcomes, or reference labels.','fallback_policy':'Review concrete English-v6 errors against Chinese v6 and v5; use English v5 only if evidence favors its rules. Do not infer a better prompt without pilot evidence.'}
dump(ROOT/'pilot_config.json',config)
provenance={'prepared_at':datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(),'status':'prepared_not_scored','new_judge_calls':0,'semantic_validation':'translation_review_only; neither language version has been validated in this preparation','source_zh':{'path':str(PLAN/'prompt_v6.txt'),'sha256':sha(PLAN/'prompt_v6.txt')},'english':{'path':str(PLAN/'prompt_v6_en.txt'),'sha256':sha(PLAN/'prompt_v6_en.txt')},'schema_sha256':sha(PLAN/'output_schema_v6.json'),'source_manifest':{'path':str(FULL/'manifest.json'),'sha256':sha(FULL/'manifest.json')},'references':{'CSO':{'url':'https://arxiv.org/html/2602.03412v1#A1','location':'Appendix A, Figure 5','use':'terminology and evaluator phrasing only; no scoring weights, thresholds, stylistic penalties, or GAIA-specific rules imported'},'DRACO':{'path':str(DRACO/'static_rubrics.json'),'sha256':sha(DRACO/'static_rubrics.json'),'repository_commit':read(DRACO/'provenance.json')['commit'],'use':'terminology only; v6 local-step applicability and evidence boundaries retained'}},'sampling_summary':summaries,'holdout_limitations':'Disjoint from this development set by task family, but all source trajectories were previously scored under v5. This is a reserved English-v6 validation set, not historically unseen data or an unbiased population sample. Old scores are sampling proxies, not gold.','artifacts_sha256':{str(p.relative_to(ROOT)):sha(p) for d in ['assets','manifests','review'] for p in sorted((ROOT/d).glob('*')) if p.is_file()}}
provenance['active_objective']='Quality-first English-v6 preparation; no mandatory Chinese-English A/B comparison.'
for path in [ROOT/'README.md', ROOT/'pilot_config.json', Path(__file__)]:
    if path.exists(): provenance['artifacts_sha256'][str(path.relative_to(ROOT))]=sha(path)
dump(ROOT/'PROVENANCE.json',provenance)
dump(ROOT/'VALIDATION.json',{'status':'passed_local_preparation_checks','new_judge_calls':0,'chinese_source_hash_matches_v6_provenance':True,'paired_sections':len(alignment),'eight_rubrics_in_order':True,'placeholder_once_per_language':True,'examples_match_unchanged_v6_schema':True,'english_example_reason_characters':len(example['steps'][1][2]),'selected_original_and_prepared_input_hashes_verified':True,'development_holdout_task_families_disjoint':True,'english_contains_no_chinese_characters':True,'does_not_establish_semantic_accuracy':True})
print(json.dumps({k:{a:b for a,b in v.items() if a!='v5_label_counts'} for k,v in summaries.items()},indent=2))
