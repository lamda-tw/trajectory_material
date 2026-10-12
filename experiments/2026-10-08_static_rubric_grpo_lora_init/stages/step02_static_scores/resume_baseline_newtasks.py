"""Resume the unchanged baseline after authentication recovery; never tunes scores."""
import argparse
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from datetime import datetime, timezone
import fcntl,json,subprocess,sys
from pathlib import Path
sys.dont_write_bytecode=True
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
import common
import baseline_newtasks as base


def stamp(): return datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--execute',action='store_true');args=parser.parse_args()
    out=base.OUT; out.mkdir(parents=True,exist_ok=True)
    lock=(out/'run.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    cfg=common.load_config();manifest,rows,rules=base.prepare(cfg)
    pending=[r for r in rows if not (out/'judgements'/f"{r['task_id']}__{r['sample']:02d}"/'judgement.json').exists()]
    if not pending:
        print(json.dumps({'status':'already_scored','count':len(rows)}));return
    if not args.execute:
        print(json.dumps({'status':'ready_to_resume','pending':len(pending),'prompt_changed':False,'next':'restore Codex CLI login before --execute'}));return
    auth=subprocess.run([cfg['paths']['codex'],'login','status'],capture_output=True,text=True,timeout=30)
    if auth.returncode or 'not logged in' in (auth.stdout+auth.stderr).lower():
        raise SystemExit('Codex CLI is not authenticated; no scoring request or artifact move was made.')
    run_id=stamp();archive=out/'failed_launches'/run_id;archived=[]
    for row in pending:
        uid=f"{row['task_id']}__{row['sample']:02d}";folder=out/'judgements'/uid
        if folder.exists():
            destination=archive/'judgements'/uid;destination.parent.mkdir(parents=True,exist_ok=True);folder.rename(destination);archived.append(uid)
    record={'started_at_utc':datetime.now(timezone.utc).isoformat(),'parent_stage_fingerprint':manifest['fingerprint'],'resume_driver_sha256':common.file_sha(Path(__file__)),'archived_failed_jobs':archived,'archive':str(archive),'judge_config':cfg['judge'],'prompt_changed':False,'status':'running'}
    path=out/f'resume_{run_id}.json';common.atomic_json(path,record)
    def score(row):
        uid=f"{row['task_id']}__{row['sample']:02d}";print(json.dumps({'starting':uid}),flush=True)
        value=base.judge.score(cfg,common.read_json(row['trajectory']),out/'judgements'/uid,execute=True)
        print(json.dumps({'scored':uid,'attempts':value['attempts']}),flush=True)
    try:
        # Verify one complete request before submitting the remainder.
        score(pending[0]);base.summarize(cfg,manifest,rows,rules)
        iterator=iter(pending[1:]);executor=ThreadPoolExecutor(max_workers=2);futures=set()
        try:
            for _ in range(2):
                row=next(iterator,None)
                if row is not None:futures.add(executor.submit(score,row))
            while futures:
                done,futures=wait(futures,return_when=FIRST_COMPLETED)
                for future in done:future.result()
                base.summarize(cfg,manifest,rows,rules)
                for _ in done:
                    row=next(iterator,None)
                    if row is not None:futures.add(executor.submit(score,row))
        finally:
            executor.shutdown(wait=True,cancel_futures=True)
        record['status']='scored'
    except Exception as error:
        record.update(status='failed',error=f'{type(error).__name__}: {error}')
        raise
    finally:
        summary=base.summarize(cfg,manifest,rows,rules)
        record.update(finished_at_utc=datetime.now(timezone.utc).isoformat(),scored_trajectories=summary['scored_trajectories'])
        common.atomic_json(path,record)
        common.atomic_json(out/'status.json',{'status':record['status'],'scored_trajectories':summary['scored_trajectories'],'updated_at_utc':record['finished_at_utc']})

if __name__=='__main__':main()
