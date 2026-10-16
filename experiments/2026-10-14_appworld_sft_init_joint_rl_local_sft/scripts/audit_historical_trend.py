"""CPU-only independent audit of the five historical-protocol DEV57 evaluations."""
import csv
import json
from pathlib import Path
from collections import defaultdict
from common import ROOT, now, read, dump, sha, require

D=ROOT/'evaluation/historical_protocol_trend'
manifest=read(D/'INPUT_MANIFEST.json')
baseline=Path(manifest['historical_baseline'])
rel=Path('simplified_react_code_agent/alibaba/qwen3-8b-with-reasoning/dev')
task_ids=set((baseline/'data/datasets/dev.txt').read_text().split())
require((D/'COMPLETE.json').exists() and (D/'REPORT_COMPLETE.json').exists(),'Evaluation/report not complete')
acceptance=read(D/'ACCEPT_BASELINE_VARIANCE.json')
require(acceptance['user_authorized'],'Historical outcome variance was not accepted')
require(sha(ROOT/'scripts/continue_historical_trend.py')==acceptance['continuation_script_sha256'],
        'Continuation script changed after acceptance')
if (D/'BASELINE_VARIANCE_REVIEW.json').exists():
    review=read(D/'BASELINE_VARIANCE_REVIEW.json')
    require(review['accepted'] and review['continuation_script_sha256']==acceptance['continuation_script_sha256'],
            'Baseline variance review differs')
for source in manifest['sources']:
    require(sha(source['path'])==source['sha256'],f'Frozen source changed: {source["path"]}')
points=[]
normalized_launches=[]
for entry in manifest['adapters']:
    step=entry['step'];stage=D/f'step_{step:05d}'
    argv=read(stage/'LAUNCH.json')['argv']
    normalized_launches.append([arg.replace(str(stage),'<STAGE>').replace(entry['adapter'],'<ADAPTER>') for arg in argv])
    require(normalized_launches[-1]==normalized_launches[0],'Launch settings vary across checkpoints')
    require(read(stage/'server_owned.json')['gpu_uuid']==manifest['gpu_uuid'],'Server GPU differs')
    require(sha(Path(entry['source'])/'adapter_model.safetensors')==entry['sha256'],'Checkpoint weight changed')
    require(sha(Path(entry['adapter'])/'adapter_model.safetensors')==entry['sha256'],'Served weight differs')
    require(sha(stage/'config/agent_configs'/Path(str(rel)+'.jsonnet'))==sha(D/'protocol_snapshot/dev.jsonnet'),'Config differs')
    official=read(stage/'experiments/outputs'/rel/'evaluations/dev.json')['individual']
    require(set(official)==task_ids,'Task set differs')
    summary=read(stage/'SUMMARY.json')
    calls_count=0
    for tid in sorted(task_ids):
        old_path=baseline/'experiments/outputs'/rel/'tasks'/tid/'logs/lm_calls.jsonl'
        with old_path.open() as handle:old=json.loads(handle.readline())
        path=stage/'experiments/outputs'/rel/'tasks'/tid/'logs/lm_calls.jsonl'
        with path.open() as handle:
            for index,line in enumerate(handle):
                call=json.loads(line);inp=call['input']
                if index==0:require(inp['messages']==old['input']['messages'],f'Prompt differs: {step}/{tid}')
                for key in ('model','tools','seed','temperature','max_completion_tokens','client_name','api_type'):
                    require(inp.get(key)==old['input'].get(key),f'Request parameter differs: {step}/{tid}/{key}')
                calls_count+=1
    groups=defaultdict(list)
    for tid,item in official.items():
        require(len(item['passes'])+len(item['failures'])==item['num_tests'],'Test count mismatch')
        groups[tid.rsplit('_',1)[0]].append(item['success'])
    require(sum(t['success'] for t in official.values())==summary['successes'],'TGC mismatch')
    require(sum(all(v) for v in groups.values())==summary['successful_scenarios'],'SGC mismatch')
    require(sum(len(t['passes']) for t in official.values())==summary['passed_tests'],'Evaluator totals mismatch')
    require(sum(t['num_tests'] for t in official.values())==291,'Unexpected evaluator denominator')
    points.append(dict(step=step,tasks=57,calls=calls_count,successes=summary['successes'],
                       successful_scenarios=summary['successful_scenarios'],evaluator_passed=summary['passed_tests']))
with (D/'evaluator_test_results.csv').open() as handle:conditions=list(csv.DictReader(handle))
require(len(conditions)==291*5,'Detailed evaluator report is incomplete')
for point in points:
    rows=[r for r in conditions if int(r['step'])==point['step']]
    require(sum(r['condition_passed']=='True' for r in rows)==point['evaluator_passed'],'Detailed evaluator CSV differs')
with (D/'paired_task_results.csv').open() as handle:require(len(list(csv.DictReader(handle)))==57,'Paired task CSV incomplete')
with (D/'scenario_results.csv').open() as handle:require(len(list(csv.DictReader(handle)))==19,'Scenario CSV incomplete')
dump(D/'FINAL_AUDIT.json',dict(at=now(),passed=True,points=points,
    total_task_evaluations=285,total_evaluator_conditions=1455,
    source_hashes_unchanged=True,all_initial_messages_match_historical=True,
    all_request_parameters_match_historical=True,all_adapters_match_source_checkpoints=True,
    all_launch_settings_equal_except_model_path_and_output_paths=True,all_owned_servers_pinned_to_gpu1=True))
print(json.dumps(read(D/'FINAL_AUDIT.json'),ensure_ascii=False,indent=2))
