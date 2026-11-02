"""Create CPU-only Phase B configuration. Never enables execution or loads weights."""
from b_common import B,R,W,read,write_json,frozen_json,file_sha,digest,now,GPU
from pathlib import Path
import copy
import json
import random
import shutil


def main():
    folder=B/'config';folder.mkdir(parents=True,exist_ok=True)
    source=W/'experiments/2026-10-14_appworld_sft_init_joint_rl_local_sft'
    for name in ['train90.txt','dev57.txt']:
        path=folder/name
        if path.exists():assert path.read_bytes()==(source/'config'/name).read_bytes()
        else:shutil.copyfile(source/'config'/name,path)
    tasks=(folder/'train90.txt').read_text().split();dev=(folder/'dev57.txt').read_text().split()
    assert len(tasks)==len(set(tasks))==90 and len(dev)==len(set(dev))==57 and not set(tasks)&set(dev)
    expected={s['task_id'] for s in read(R/'phase_a/config/source_manifest.json')['samples']}
    assert set(tasks)==expected
    compat=R/'runtime_code/b_appworld_log_compat.py'
    if compat.exists():assert compat.read_bytes()==(source/'scripts/appworld_log_compat.py').read_bytes()
    else:shutil.copyfile(source/'scripts/appworld_log_compat.py',compat)
    cfg=copy.deepcopy(read(R/'config/phase_a_runtime.json'))
    cfg['experiment']='phase_b_online_C2_SDPO_v1'
    cfg['server'].update(port=8192,max_num_seqs=3,adapter_name='phase-b-student')
    cfg['sampling']={'temperature':1.0,'top_p':1.0,'top_k':-1,'repetition_penalty':1.0}
    cfg['collection']={'tasks':'phase_b/config/train90.txt','workers':3,'rollouts_per_task':1,'trajectory_timeout_seconds':5400,
                       'official_terminal_evaluation':False,'judge_calls_during_rollout':0}
    cfg['training']={'seed':20261022,'tasks_per_batch':5,'epochs':2,'update_opportunities':36,'teacher_condition':'C2_feedback',
        'original_answer_in_teacher_prompt':False,'teacher_uses_same_response_prefix':True,'lora':{
            'r':8,'lora_alpha':16,'lora_dropout':0.0,'target_modules':['q_proj','k_proj','v_proj','o_proj','gate_proj','up_proj','down_proj'],
            'bias':'none','task_type':'CAUSAL_LM'},
        'learning_rate':5e-5,'betas':[0.9,0.999],'eps':1e-8,'weight_decay':0.0,'warmup_nonempty_updates':5,
        'grad_clip_norm':1.0,'lambda_sdpo':1.0,'ema_decay':0.95,'top_k':100,'head_chunk_size':128,
        'teacher_max_length':32768,'feedback_max_tokens':256,'sft_min_PASS':3,'sft_exclude_U':False,
        'loss_normalization':'token mean within each step; independent step means for SFT/SDPO; one optimizer step per batch',
        'zero_branch_behavior':'zero loss; if both branches empty skip optimizer/EMA/warmup count',
        'teacher_gradient':False,'train_base_parameters':False,'precision':'bf16 base, fp32 probability arithmetic and EMA',
        'attention':'sdpa','gradient_checkpointing':True}
    cfg['evaluation']={'tasks':'phase_b/config/dev57.txt','temperature':0.0,'seed':100,'automatic_after_training':False,
                       'metric':'official task-goal completion on the final student, without feedback'}
    cfg['default_arm']='mixed';cfg['available_arms']=['mixed','sft'];cfg.pop('experiment_arm',None);cfg.pop('worker_count',None)
    assert cfg['training']['teacher_max_length']<=read(Path(cfg['paths']['base_model'])/'config.json')['max_position_embeddings']
    frozen_json(folder/'run.json',cfg)
    judge=read(R/'config/judge.json');judge.update(max_workers=5,timeout_seconds=1200)
    frozen_json(folder/'judge.json',judge)
    batches=[];rng=random.Random(cfg['training']['seed'])
    for epoch in range(1,3):
        order=list(tasks);rng.shuffle(order)
        for i in range(0,90,5):
            number=len(batches)+1
            batches.append({'batch':number,'epoch':epoch,'tasks':[
                {'task_id':task,'seed':int(digest([cfg['training']['seed'],epoch,task])[:12],16)%(2**31-51)} for task in order[i:i+5]]})
    frozen_json(folder/'schedule.json',{'seed':cfg['training']['seed'],'matched_between_arms':True,'batches':batches})
    gate=folder/'execution_gate.json'
    if not gate.exists():
        write_json(gate,{'updated_at':now(),'user_instruction':'Preparation only; do not train. C2 confirmed as default teacher input.',
            'physical_gpu':1,'gpu_uuid':GPU,'rollout_allowed':False,'external_judging':False,'training_allowed':False,'evaluation_allowed':False,
            'automatic_resume':False,'phase_c_allowed':False})
    else:
        assert not any(read(gate).get(k) for k in ['rollout_allowed','external_judging','training_allowed']), 'Do not re-prepare a running experiment'
    dependencies=[R/'config/agent_prompt.txt',R/'config/scoring_prompt_v7_en.txt',R/'config/scoring_prompt_v7_feedback_en.txt',
        R/'config/output_schema_v7_feedback.json',R/'plan_snapshot/prompts/teacher_reprompt_v2.txt',R/'phase_a/config/model_manifest.json']
    dependencies += [R/'scripts'/name for name in ['common.py','a_common.py','prepare_sources.py','analyze_sources.py','score_sources.py']]
    dependencies += [R/'runtime_code'/name for name in ['a_policy_server.py','a_judge_audit.py','judge_protocol.py','prepare_input_v3.py','validate_v7_feedback.py','b_appworld_log_compat.py']]
    dependencies += [p for p in (R/'runtime_code/vllm_uuid_compat').rglob('*.py')]
    dependencies += list((R/'scripts').glob('b_*.py'))+list((B/'tests').glob('*.py'))
    dependencies += [folder/name for name in ['run.json','judge.json','schedule.json','train90.txt','dev57.txt']]
    write_json(folder/'preparation_manifest.json',{'prepared_at':now(),'files':{str(p.relative_to(R)):file_sha(p) for p in sorted(set(dependencies))},
        'model_weights_loaded':False,'gpu_jobs_started':False,'training_started':False})
    print(json.dumps({'prepared':str(B),'default_teacher':'C2_feedback','batches_per_arm':36,'trajectories_per_arm':180,
                      'all_execution_gates_disabled':True,'training_started':False},ensure_ascii=False))


if __name__=='__main__':main()
