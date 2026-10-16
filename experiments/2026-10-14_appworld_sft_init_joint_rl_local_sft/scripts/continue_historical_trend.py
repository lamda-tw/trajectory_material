"""Honor user's acceptance of A0 output variance without changing the frozen evaluator.

The original coordinator intentionally stops after a historical outcome mismatch.
This continuation changes that outcome gate only; protocol/coverage checks stay intact.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from common import ROOT, dump, now, read, require, sha
import evaluate_historical_trend as historical

def alive(pid):
    try:return Path(f'/proc/{pid}/stat').read_text().rsplit(')',1)[1].split()[0]!='Z'
    except FileNotFoundError:return False

def execute():
    expected='A0 differs from historical baseline; inspect before continuing'
    require(read(historical.DEST/'ACCEPT_BASELINE_VARIANCE.json')['user_authorized'], 'Missing acceptance record')
    error_path=historical.DEST/'ERROR.json'
    if error_path.exists():
        error=read(error_path)
        require(error['step']==0 and error['error']==expected, 'Unexpected failure requires investigation')
        archive=historical.DEST/'events/baseline_outcome_gate.json'
        archive.parent.mkdir(exist_ok=True)
        require(not archive.exists(), 'Gate failure already archived')
        error_path.rename(archive)
    original=historical.summarize
    def summarize_accepting_outcome_variance(step):
        try:return original(step)
        except ValueError as exc:
            if step!=0 or str(exc)!=expected:raise
            audit=read(historical.DEST/'BASELINE_REPRODUCTION.json')
            require(audit['initial_messages_exact_match']==57, 'Protocol mismatch remains disallowed')
            dump(historical.DEST/'BASELINE_VARIANCE_REVIEW.json',dict(at=now(),accepted=True,
                reason='User accepts outcome variation after protocol checks. Use GPU1 step 0 as the paired baseline.',
                reproduction_audit=audit,source_manifest_sha256=sha(historical.DEST/'INPUT_MANIFEST.json'),
                continuation_script_sha256=sha(__file__)))
            return read(historical.stage_root(0)/'SUMMARY.json')
    historical.summarize=summarize_accepting_outcome_variance
    historical.execute()

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--wait-for-pid',type=int)
    parser.add_argument('--execute',action='store_true')
    args=parser.parse_args()
    if args.wait_for_pid:
        while alive(args.wait_for_pid):time.sleep(10)
        if (historical.DEST/'COMPLETE.json').exists():return
        # Let the original report watcher observe the outcome-gate event before replacing it.
        time.sleep(12)
        watcher=read(historical.DEST/'REPORT_LAUNCH.json')
        if alive(watcher['pid']):
            # A live watcher will continue once the gate event is archived below.
            pass
        else:
            pending=historical.DEST/'ERROR.json'
            require(pending.exists() and read(pending)['error']=='A0 differs from historical baseline; inspect before continuing',
                    'Unexpected stop; do not restart blindly')
        cmd=[sys.executable,str(ROOT/'scripts/gpu1_run.py'),'--',sys.executable,'-u',str(Path(__file__).resolve()),'--execute']
        with (ROOT/'logs/historical_dev57_trend_continuation.log').open('a') as log:
            child=subprocess.Popen(cmd,stdout=log,stderr=subprocess.STDOUT,start_new_session=True,stdin=subprocess.DEVNULL,cwd=ROOT)
        dump(historical.DEST/'CONTINUATION_LAUNCH.json',dict(at=now(),pid=child.pid,argv=cmd))
        # Wait for the continuation to archive the reviewed event, then keep report generation live.
        for _ in range(30):
            if not (historical.DEST/'ERROR.json').exists():break
            if child.poll() is not None:raise RuntimeError('Continuation failed; inspect log')
            time.sleep(1)
        require(not (historical.DEST/'ERROR.json').exists(), 'Continuation did not clear reviewed event')
        if not alive(watcher['pid']):
            with (ROOT/'logs/historical_dev57_report.log').open('a') as log:
                proc=subprocess.Popen(['python','-u',str(ROOT/'scripts/summarize_historical_trend.py'),'--watch'],
                    stdout=log,stderr=subprocess.STDOUT,start_new_session=True,stdin=subprocess.DEVNULL,cwd=ROOT)
            dump(historical.DEST/'REPORT_LAUNCH.json',dict(at=now(),pid=proc.pid))
        return
    require(args.execute,'Use --wait-for-pid or --execute')
    execute()

if __name__=='__main__':main()
