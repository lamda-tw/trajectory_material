#!/usr/bin/env python3
"""Persist progress and finalize this one local run after the evaluator exits."""
from pathlib import Path
import collections, datetime, fcntl, json, os, subprocess, sys, time
stage = Path(__file__).resolve().parent
lock = open(stage/'logs/finalizer.lock','w')
fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
(stage/'logs/finalizer.pid').write_text(str(os.getpid())+'\n')
while True:
    try:
        manifest = json.loads((stage/'manifest.json').read_text())
        path = stage/'task_status.jsonl'
        rows = [json.loads(x) for x in path.read_text().splitlines() if x.strip()] if path.exists() else []
    except json.JSONDecodeError:
        time.sleep(1)
        continue
    counts = collections.Counter(row['status'] for row in rows)
    progress = {'updated_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'status':manifest['status'],'completed':len(rows),'expected':90,
        'success':counts['success'],'failed':counts['failed'],'evaluation_errors':counts['evaluation_error'],
        'latest_task':rows[-1]['task_id'] if rows else None}
    temp=stage/'progress.json.tmp'
    temp.write_text(json.dumps(progress,ensure_ascii=False,indent=2)+'\n')
    temp.replace(stage/'progress.json')
    if manifest['status'] == 'awaiting_validation':
        with open(stage/'logs/report.log','a',buffering=1) as log:
            result=subprocess.run([sys.executable,str(stage/'build_report.py')],stdout=log,stderr=subprocess.STDOUT)
        progress['status']='completed' if result.returncode==0 else 'validation_failed'
        (stage/'progress.json').write_text(json.dumps(progress,ensure_ascii=False,indent=2)+'\n')
        raise SystemExit(result.returncode)
    if manifest['status'] in ('completed','validation_failed','run_error'):
        break
    try:
        os.kill(manifest['supervisor_pid'],0)
    except ProcessLookupError:
        progress['status']='supervisor_missing'
        (stage/'progress.json').write_text(json.dumps(progress,ensure_ascii=False,indent=2)+'\n')
        raise SystemExit('Supervisor disappeared before recording its exit status.')
    time.sleep(15)
