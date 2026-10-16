"""CPU checks: final adapter export, partial-run rejection, and parent-only handoff preserving child work."""
import copy,json,os,signal,subprocess,sys,tempfile,time
from pathlib import Path
import torch
from safetensors.torch import save_file
from common import ROOT,read,dump,sha,require,now
from owned_process import birth
from round_data import schedule
import finish_current_pool as f

def main():
    results={};cfg0=read(ROOT/'config/round1_trial_15.json')
    with tempfile.TemporaryDirectory(dir=ROOT/'checks',prefix='finish_test_') as temp:
        root=Path(temp);f.ROOT=root;f.P=root/'plan';f.P.mkdir();f.LORA_PARAMETERS=2
        original=root/'A0';original.mkdir();save_file({'test.lora_A':torch.tensor([0.,1.])},str(original/'adapter_model.safetensors'))
        cfg=copy.deepcopy(cfg0);cfg['model']['initial_adapter']=str(original);cfg['model']['adapter_weights_sha256']=sha(original/'adapter_model.safetensors')
        cfgpath=root/'config.json';dump(cfgpath,cfg);source=root/'trajectory.json';dump(source,{'test':'source'});encoded=root/'encoded.bin';encoded.write_bytes(b'fixture')
        tasks=[f't{i}' for i in range(90)]
        episodes=[{'task_id':t,'sample':i,'trajectory':str(source),'sha256':sha(source),'tokens':2} for t in tasks for i in range(6)]
        poolpath=root/'pool.json';dump(poolpath,{'tasks':tasks,'episodes':episodes})
        data={'samples':[{'encoded_file':'encoded.bin','encoded_sha256':sha(encoded)} for i in range(2623)]};dump(root/'data/data_manifest.json',data)
        out=root/'pool';out.mkdir();rows=schedule(cfg,tasks,2623,1)
        identity=f.hashlib.sha256(json.dumps({'config':sha(cfgpath),'data':sha(root/'data/data_manifest.json'),'mode':'smoke'},sort_keys=True,separators=(',',':')).encode()).hexdigest()
        for row in rows:
            cp=out/f"step_{row['batch']:05d}";cp.mkdir();save_file({'test.lora_A':torch.tensor([.01*row['batch'],1.])},str(cp/'adapter_model.safetensors'));dump(cp/'adapter_config.json',{'r':8})
            metrics={'optimizer_steps_this_batch':1,'sft_tokens':205238 if row['batch']==1 else 0,'rl_tokens':72}
            state={'identity':identity,'mode':'smoke','round':1,'batch':row['batch'],'global_update':row['global_update'],'pool_sha256':sha(poolpath),
                   'sft_indices':row['sft_indices'],'task_ids':row['tasks'],'trajectory_ids':[f'{t}__{i:02d}' for t in row['tasks'] for i in range(6)],'metrics':metrics}
            dump(cp/'manifest.json',{'state':state,'adapter_sha256':sha(cp/'adapter_model.safetensors'),'files':{p.name:sha(p) for p in cp.iterdir()}})
        dump(out/'alignment.json',{'passed':True});dump(out/'final_policy_probe.json',{'passed':True})
        control={'config':str(cfgpath),'config_sha256':sha(cfgpath),'pool':str(poolpath),'pool_sha256':sha(poolpath),'training_code_sha256':{},'output':str(out),'final_adapter':str(root/'final_adapter')}
        report=f.audit_and_export(control)
        require(report['optimizer_updates']==15 and report['DEV57_performed'] is False and not report['repeated_training'],'Wrong completion semantics')
        require(sha(root/'final_adapter/adapter_model.safetensors')==sha(out/'step_00015/adapter_model.safetensors'),'Export changed weights')
        f.audit_and_export(control);results['atomic_export_and_idempotence']=True
        cp=out/'step_00015';cp.rename(out/'step_00015.hidden')
        try:f.audit_and_export(control)
        except ValueError:results['incomplete_pool_rejected']=True
        else:raise AssertionError('Partial run exported as final')
        cp.with_name('step_00015.hidden').rename(cp)
        # Final non-mutating probe failure is explicitly reported, not hidden, and never reruns training.
        dump(out/'final_policy_probe.json',{'passed':False});control['final_adapter']=str(root/'flagged_adapter')
        flagged=f.audit_and_export(control);require(flagged['final_policy_probe_passed'] is False,'Failed final probe hidden');results['probe_failure_retains_completed_model_with_flag']=True
        # Check real parent-only process termination leaves its separate-session worker alive.
        marker=root/'child.json';tick=root/'tick'
        code=f'import time,pathlib\np=pathlib.Path({str(tick)!r})\nwhile True:\n p.write_text(str(time.time()))\n time.sleep(.05)'
        parentcode=f'import subprocess,sys,time,json,pathlib,os\np=subprocess.Popen([sys.executable,"-c",{code!r}],start_new_session=True,env={{**os.environ,"CUDA_VISIBLE_DEVICES":"test-gpu"}})\npathlib.Path({str(marker)!r}).write_text(json.dumps({{"pid":p.pid,"argv":p.args}}))\ntime.sleep(60)'
        parent=subprocess.Popen([sys.executable,'-c',parentcode],start_new_session=True)
        try:
            deadline=time.time()+5
            while not marker.exists() and time.time()<deadline:time.sleep(.02)
            d=read(marker);pid=d['pid'];start=birth(pid)
            f.check_owned(pid,start,['launcher','--',*d['argv']],'test-gpu')
            deadline=time.time()+5
            while not tick.exists() and time.time()<deadline:time.sleep(.02)
            require(tick.exists(),'Test worker did not start')
            os.kill(parent.pid,signal.SIGKILL);parent.wait(timeout=5)
            before=tick.stat().st_mtime;time.sleep(.2)
            require(f.is_alive(pid,start) and tick.stat().st_mtime>before,'Worker lost during parent-only handoff')
            results['parent_only_handoff_preserves_worker_progress']=True
        finally:
            if parent.poll() is None:parent.kill();parent.wait()
            if 'pid' in locals() and f.is_alive(pid,start):os.kill(pid,signal.SIGTERM)
    require(not torch.cuda.is_initialized(),'CPU checks touched CUDA')
    results.update(at=now(),passed=True,cuda_initialized=False)
    dump(ROOT/'checks/finish_current_pool_tests.json',results);print(json.dumps(results,indent=2))
if __name__=='__main__':main()
