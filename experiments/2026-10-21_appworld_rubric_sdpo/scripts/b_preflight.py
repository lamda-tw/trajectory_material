"""CPU-only preparation audit against cached A artifacts; never calls a model or judge."""
from b_common import *
from b_dataset import compile_trajectory,validate_result
from analyze_sources import render_message
from validate_v7_feedback import feedback_text
import collections,copy,json,subprocess,sys,ast


def main():
    check_preparation();cfg=config();gate=read(B/'config/execution_gate.json')
    assert not any(gate.get(k,False) for k in ['rollout_allowed','external_judging','training_allowed','evaluation_allowed'])
    from transformers import AutoTokenizer
    tokenizer=AutoTokenizer.from_pretrained(cfg['paths']['base_model'],local_files_only=True)
    matches=[]
    for item in read(R/'phase_a/ready/manifest.json')['states']:
        p=read(R/item['path']);f=p['feedback']
        if not f:continue
        original=read(R/p['state']['policy_input'])
        text=render_message('C2_feedback',f['failed_rules'],feedback_text(f),'')
        ids=tokenizer.apply_chat_template(original['messages']+[{'role':'user','content':text}],tools=None,
            tokenize=True,add_generation_prompt=True,enable_thinking=False)
        assert ids==p['prompts']['C2_feedback']['prompt_ids']
        matches.append(item['state_id'])
    # Existing whole-trajectory labels are real A judgments. Missing non-target
    # feedback is marked unusable in this CPU fixture only, never invented or trained.
    fixture_states=['state_9ac003937b88afdd','state_74151614143520ad','state_126d6a707faa9c5f']
    fixtures=[]
    for sid in fixture_states:
        p=read(R/'phase_a/ready'/f'{sid}.json');source=read(p['state']['source']);payload=read(R/p['state']['input'])
        payload.pop('feedback_step_ids',None)
        actual=read(R/'phase_a/judging/formal'/sid/'feedback/judgement.json')
        result=copy.deepcopy(actual);old={f['step_id']:f for f in actual['feedback']}
        result['feedback']=[]
        for i,labels,_ in result['steps']:
            if 'F' not in labels:continue
            result['feedback'].append(old.get(i,{'step_id':i,'failed_rules':[f'R{n+1}' for n,c in enumerate(labels) if c=='F'],
                'diagnosis':'CPU fixture: no actual feedback exists for this step.','correction':'','evidence_steps':[i],
                'uses_later_evidence':False,'usable':False,'unusable_reason':'CPU fixture only; never a training sample.'}))
        examples=compile_trajectory(source,payload,result,tokenizer,cfg,'mixed')
        assert len(examples)==len(source['steps'])
        target=examples[p['state']['target_step']-1]
        assert target['branch']=='sdpo'
        assert target['teacher_prompt_ids']==p['prompts']['C2_feedback']['prompt_ids']
        # The SAME result must exclude all FAIL steps in the online SFT control.
        baseline=compile_trajectory(source,payload,result,tokenizer,cfg,'sft')
        assert not any(x['branch']=='sdpo' for x in baseline)
        assert all(a['branch']==b['branch']=='sft' for a,b in zip(examples,baseline) if 'F' not in a['labels'] and a['labels'].count('P')>=3)
        fixtures.append({'state_id':sid,'all_step_prompts_exact':True,'steps':len(examples),'mixed_counts':dict(collections.Counter(x['branch'] for x in examples)),
                         'fixture_only':True,'no_training_dataset_written':True})
        if len(result['feedback'])>1:
            incomplete=copy.deepcopy(result);incomplete['feedback']=incomplete['feedback'][:1]
            try:validate_result(payload,incomplete)
            except (ValueError,AssertionError):pass
            else:raise AssertionError('Missing all-step feedback was accepted')
    for path in (R/'scripts').glob('b_*.py'):ast.parse(path.read_text(),filename=str(path))
    denied=[]
    for capability in ['training_allowed','rollout_allowed','external_judging','evaluation_allowed']:
        try:authorize(capability)
        except PermissionError:denied.append(capability)
        else:raise AssertionError('Execution gate unexpectedly open')
    versions={}
    for python in [cfg['paths']['training_python'],cfg['paths']['vllm_python'],cfg['paths']['appworld_python']]:
        assert Path(python).exists()
        out=subprocess.check_output([python,'-c','import importlib.metadata as m,json; out={};\nfor p in ["torch","transformers","peft","vllm","appworld"]:\n try: out[p]=m.version(p)\n except m.PackageNotFoundError: pass\nprint(json.dumps(out))'],env=CPU,text=True)
        versions[python]=json.loads(out)
    report={'checked_at':now(),'cached_A_C2_prompts_exact':len(matches),'whole_trajectory_CPU_fixtures':fixtures,
        'gate_denials_verified':denied,'runtime_versions':versions,'phase_b_config_sha256':file_sha(B/'config/run.json'),
        'model_weights_loaded':False,'gpu_used':False,'remote_judge_calls':0,'new_rollouts':0,'training_updates':0,
        'remaining_runtime_checks':['Real Qwen3-8B GPU memory/throughput and first gradient diagnostics','One new complete trajectory scored with all FAIL feedback; structural CPU fixtures do not verify Codex semantic quality']}
    write_json(B/'analysis/preflight.json',report);print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
