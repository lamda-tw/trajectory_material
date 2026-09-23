#!/usr/bin/env python3
"""Finalize only after complete official scores, reviewed cases and model integrity."""
import csv,hashlib,json,re,subprocess,sys
from datetime import datetime,timezone
from pathlib import Path
E=Path(__file__).resolve().parent.parent;W=E.parent.parent
sys.path.insert(0,str(E/'scripts_snapshot'))
from build_appworld_full_sft_aligned_dev_report import sha256
from analyze_appworld_matched_rollouts import OUTPUT

def load(p):return json.loads(p.read_text())
def write(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def main():
    manifest=load(E/'manifest.json');T=Path(manifest['training_experiment']);s=load(E/'summary.json')
    review=load(E/'metrics/case_review.json');assert review['status']=='COMPLETE' and len(review['cases'])>=4
    assert (E/'CASE_STUDIES.md').is_file() and len((E/'CASE_STUDIES.md').read_text())>1500
    for report_path in [T/'REPORT.md',E/'REPORT.md',E/'CASE_STUDIES.md']:
        report=report_path.read_text();assert len(report)>500
        assert 'OUTPUT_PLACEHOLDER' not in report and 'TODO' not in report
        for target in re.findall(r'\]\((/root/autodl-tmp/workspace-tw/[^)]+)\)',report):
            path=re.sub(r':\d+$','',target);assert Path(path).exists(),path
    tm=load(T/'metrics/metrics.json');assert tm['status']=='SUCCESS'
    assert tm['training']['epochs_completed']==2 and tm['training']['global_steps']==1170
    assert tm['training']['schedule_steps']==2925 and tm['training']['warmup_steps']==88
    assert load(T/'metrics/prefix_replay_audit.json')['status']=='PASS'
    assert load(T/'metrics/generation_smoke.json')['status']=='PASS'
    inventory=load(T/'metrics/model_inventory.json');checked=[]
    for relative,model in inventory.items():
        directory=T/relative
        assert set(model['files'])=={x.name for x in directory.iterdir() if x.is_file()}
        for name,expected in model['files'].items():
            file=directory/name;assert file.stat().st_size==expected['bytes'];assert sha256(file)==expected['sha256'],file
            checked.append(str(file))
    assert not list((T/'artifacts').rglob('rank_*.pt'))
    for name,digest in load(T/'config/source_hashes.json').items():assert sha256(T/name)==digest,name
    assert (E/'logs/run_exit_code.txt').read_text().strip()=='0'
    assert not s['run_audit']['anomalies'] and s['task_status_audit']['strictly_one_row_per_task']
    ids=(E/'data/datasets/test_normal.txt').read_text().split();assert len(ids)==168 and len(set(ids))==168
    scores=load(Path(s['models']['epoch2']['evaluation_path']))
    assert set(scores['individual'])==set(ids)
    assert sum(bool(x['success']) for x in scores['individual'].values())==s['models']['epoch2']['success_count']
    old_scores=load(Path(s['models']['epoch5']['evaluation_path']))['individual']
    for case in review['cases']:
        task=case['task_id'];assert len(scores['individual'][task]['passes'])==case['epoch2_passed_tests']
        assert len(old_scores[task]['passes'])==case['epoch5_passed_tests']
    for key in ['epoch2','epoch5','lora']:
        model=s['models'][key];assert sha256(Path(model['evaluation_path']))==model['evaluation_sha256']
    for row in load(E/'config/reference_evidence.json').values():assert sha256(Path(row['path']))==row['sha256']
    with (E/'task_comparison.csv').open(encoding='utf-8-sig') as f:rows=list(csv.DictReader(f))
    assert len(rows)==168 and {x['task_id'] for x in rows}==set(ids)
    assert sum(x['epoch2_success']=='True' for x in rows)==s['models']['epoch2']['success_count']
    with (E/'scenario_comparison.csv').open(encoding='utf-8-sig') as f:scenario_rows=list(csv.DictReader(f))
    assert len(scenario_rows)==56
    assert sum(int(x['epoch2_minus_epoch5']) for x in rows)==s['models']['epoch2']['success_count']-28
    evidence={}
    for task in ids:
        root=E/'experiments/outputs'/OUTPUT/'tasks'/task
        evidence[task]={name:sha256(root/name) for name in ['logs/lm_calls.jsonl','logs/api_calls.jsonl','logs/environment_io.md','misc/usage.json','misc/finished','evaluation/report.md']}
    write(E/'metrics/task_evidence_sha256.json',evidence)
    from PIL import Image
    for file in [T/'metrics/loss_comparison.png',E/'metrics/performance_comparison.png']:
        with Image.open(file) as im:im.verify()
    for file in [T/'metrics/loss_comparison.pdf',E/'metrics/performance_comparison.pdf']:assert file.read_bytes().startswith(b'%PDF')
    active=subprocess.check_output(['nvidia-smi','--query-compute-apps=pid','--format=csv,noheader,nounits'],text=True).strip()
    owned=[]
    logged_server_pids=set(re.findall(r'(?:APIServer|EngineCore_DP\d+) pid=(\d+)',(E/'logs/run.log').read_text(errors='replace')))
    for pid in active.splitlines():
        cmd=Path('/proc')/pid.strip()/'cmdline'
        if pid.strip() in logged_server_pids or (cmd.exists() and str(T/'artifacts/model').encode() in cmd.read_bytes()):owned.append(pid)
    assert not owned,owned
    validation={'status':'PASS','validated_at_utc':datetime.now(timezone.utc).isoformat(),'training_epochs':2,'training_steps':1170,
        'evaluated_tasks':168,'scenarios':56,'task_evidence_files':sum(map(len,evidence.values())),
        'model_files_hash_checked':len(checked),'optimizer_restart_files':0,'training_snapshot_hashes_match':True,
        'official_scores_match_status_and_csv':True,'reference_reports_and_scores_unchanged':True,'owned_gpu_processes_remaining':owned,
        'report_case_review':'Manually inspected original interaction and official evaluator evidence before finalization.'}
    write(E/'metrics/final_validation.json',validation)
    write(T/'metrics/final_validation.json',validation)
    for root in [T,E]:
        m=load(root/'manifest.json');m.update(status='SUCCESS',updated_at_utc=validation['validated_at_utc'],finished_at_utc=validation['validated_at_utc'],exit_code=0,training_finished_at_utc=tm['finished_at_utc'],evaluation_finished_at_utc=datetime.fromisoformat(s['run_audit']['run_finished_at']).astimezone(timezone.utc).isoformat())
        if root==E:m.update(official_scores=s['models']['epoch2']['aggregate'],success_count=s['models']['epoch2']['success_count'],official_evaluation_sha256=s['models']['epoch2']['evaluation_sha256'])
        write(root/'manifest.json',m)
        (root/'STATUS.txt').write_text('SUCCESS epochs=2 steps=1170 test_normal_success='+str(s['models']['epoch2']['success_count'])+'/168\n')
        paths=[x for x in root.iterdir() if x.is_file() and x.name!='artifacts.sha256']
        for folder in ['config','metrics','scripts','scripts_snapshot']:
            for x in (root/folder).rglob('*'):
                if x.is_file() and not x.is_symlink() and '__pycache__' not in x.parts:paths.append(x)
        paths += [x for x in (root/'logs').glob('*.log') if x.name not in ('final_hash_verification.log','finalization.log')]
        if root==E:paths.append(Path(s['models']['epoch2']['evaluation_path']))
        paths=sorted(set(paths))
        (root/'artifacts.sha256').write_text(''.join(sha256(x)+'  '+str(x.relative_to(root))+'\n' for x in paths))
        with (root/'logs/final_hash_verification.log').open('w') as f:
            subprocess.run(['sha256sum','-c','artifacts.sha256'],cwd=root,stdout=f,stderr=subprocess.STDOUT,check=True)
    print(json.dumps(validation,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
