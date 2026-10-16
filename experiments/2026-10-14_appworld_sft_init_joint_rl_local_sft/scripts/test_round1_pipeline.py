"""CPU tests for newly added diagnostics, gating, schedule and supervisor failure/restart behavior."""
import importlib.util,json,math,os,subprocess,sys,tempfile,time,types
from pathlib import Path
import numpy as np
import torch
from common import ROOT,read,dump,require,now
from round_data import schedule
from run_checks import alignment_report,check_drift,branch_diagnostics
from evaluate import evaluation_config
from owned_process import record,cleanup,birth
import run_round1 as runner

def main():
    torch.set_num_threads(2);cfg=read(ROOT/'config/round1_trial_15.json');results={}
    for tag,n in [('15',15),('05',5)]:
        c=read(ROOT/f'config/round1_trial_{tag}.json');allrows=[]
        for r in range(1,6):
            rows=schedule(c,(ROOT/'config/train90.txt').read_text().split(),2623,r)
            require(len(rows)==n,'Schedule count');require(sorted(i for x in rows for i in x['sft_indices'])==list(range(2623)),'SFT lost/repeated')
            require(len({t for x in rows for t in x['tasks']})==90,'RL task coverage');allrows+=rows
        require(len(allrows)==n*5,'Global update count')
        results['schedule_'+tag]={'updates':n*5,'sft_consumptions':sum(len(x['sft_indices']) for x in allrows)}
    pool={'tasks':['task']};groups={'task':[{'sample':0,'steps':[{'old_logprobs':[-1.,-2.]}]}]};refs={'task__00':[np.array([-1.001,-1.99])]}
    require(alignment_report(pool,groups,refs,cfg)['passed'],'Expected backend agreement')
    bad={'task__00':[np.array([-.5,-1.])]} ;require(not alignment_report(pool,groups,bad,cfg)['passed'],'Mismatch was accepted')
    require(not check_drift({'ratio_outside_clip_interval':.01,'kl_sampled_k3':.001,'old_new_abs_logp':.02},cfg),'Good drift rejected')
    require(len(check_drift({'ratio_outside_clip_interval':.4,'kl_sampled_k3':float('nan'),'old_new_abs_logp':.3},cfg))==3,'Bad drift accepted')
    results['whole_run_gates']=True
    spec=importlib.util.spec_from_file_location('math_checks',ROOT/'scripts/04_check_joint_math.py');tests=importlib.util.module_from_spec(spec);spec.loader.exec_module(tests)
    m=tests.tiny();prompt=[1,2,3];target=[4,5]
    from joint_core import action_logprobs
    with torch.no_grad():ref=action_logprobs(m,prompt,target).numpy()
    episodes=[{'task_id':'task','sample':0,'advantage':1.,'steps':[{'prompt_ids':prompt,'response_ids':target,'old_logprobs':(ref+.02).tolist()}]}]
    class Data:
        rows=[{'target_start':3,'target_tokens':2}]
        def __getitem__(self,i):return {'input_ids':torch.tensor(prompt+target),'labels':torch.tensor([-100]*3+target)}
    before=[p.clone() for p in m.parameters()];rng=torch.get_rng_state().clone()
    d=branch_diagnostics(m,episodes,{'task__00':[ref]},Data(),[0],cfg)
    require(d['grad_norm_rl_unscaled']>0 and d['grad_norm_sft_unscaled']>0,'Diagnostic branch missing')
    require(0<d['categorical_entropy_mean_at_audited_states']<=math.log(97),'Entropy invalid')
    require(torch.equal(rng,torch.get_rng_state()),'Diagnostics changed RNG')
    require(all(torch.equal(a,b) and b.grad is None for a,b in zip(before,m.parameters())),'Diagnostics mutated parameters/left gradients')
    results['diagnostics']=d
    ec=evaluation_config(cfg,cfg['model']['adapter_weights_sha256'],'initial')
    require(ec['evaluation']['temperature']==0 and ec['agent']['max_steps']==50 and ec['server']['gpu']==cfg['resource_constraints']['physical_gpu_uuid'],'Evaluation protocol mismatch')
    with tempfile.TemporaryDirectory(dir=ROOT/'checks',prefix='pipeline_test_') as temp:
        root=Path(temp);(root/'scripts').mkdir();(root/'runtime').mkdir();dump(root/'STATUS.json',{})
        # The test launcher is CPU-only; production uses the separately verified GPU1 launcher.
        (root/'scripts/gpu1_run.py').write_text('import os,sys\na=sys.argv[2:]\nos.execvpe(a[0],a,os.environ)\n')
        runner.ROOT=root;runner.RUN=root/'runtime/run';runner.time=types.SimpleNamespace(time=time.time,time_ns=time.time_ns,sleep=lambda t:time.sleep(.01))
        lock=runner.locked_run()
        try:runner.locked_run()
        except RuntimeError:results['duplicate_supervisor_rejected']=True
        else:raise AssertionError('Duplicate supervisor accepted')
        progress=root/'progress.json'
        runner.run_stage('test_success',[sys.executable,'-c',f'import pathlib;pathlib.Path({str(progress)!r}).write_text("{{}}")'],[progress])
        out=root/'output';dump(out/'drift_rejected.json',{'failure':'synthetic'})
        try:runner.run_stage('test_reject',[sys.executable,'-c','raise SystemExit(2)'],[progress],out)
        except runner.DriftRejected:results['supervisor_drift_stops_before_formal']=True
        else:raise AssertionError('Drift failure ignored')
        # Crash/retry retains output slots, succeeds on the second attempt.
        marker=root/'retry_marker';code=f'import pathlib,sys\np=pathlib.Path({str(marker)!r})\nold=p.exists()\np.write_text("1")\nsys.exit(0 if old else 7)'
        runner.run_stage('test_retry',[sys.executable,'-c',code],[progress],attempts=2)
        require(marker.exists(),'Retry marker missing');results['infrastructure_retry']=True
        child=subprocess.Popen([sys.executable,'-c','import time;time.sleep(60)'],start_new_session=True)
        path=root/'owned.json';record(path,child.pid,child.args);d=read(path);d['start_ticks']='not-the-process';dump(path,d)
        cleanup(path);require(child.poll() is None,'Stale PID record killed a process')
        record(path,child.pid,child.args);cleanup(path);child.wait(timeout=5)
        results['owned_process_cleanup_and_stale_pid_protection']=True
        lock.close()
    # Compile without writing pycache; do not import optional worker environments.
    for path in (ROOT/'scripts').rglob('*.py'):compile(path.read_text(),str(path),'exec')
    results.update(at=now(),passed=True,cuda_initialized=torch.cuda.is_initialized())
    require(not results['cuda_initialized'],'CPU test allocated CUDA')
    dump(ROOT/'checks/pipeline_tests.json',results);print(json.dumps(results,indent=2))
if __name__=='__main__':main()
