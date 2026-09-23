"""Read-only resource monitor; write metrics only into the requested experiment."""
import argparse
import json
import shutil
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument('--experiment', type=Path, required=True)
args = parser.parse_args()
exp = args.experiment.resolve()
with (exp/'logs/resource_usage.jsonl').open('a', buffering=1) as out:
    while True:
        event = {'time_utc': datetime.now(timezone.utc).isoformat(),
                 'disk_free_bytes': shutil.disk_usage(exp).free}
        for key in ['memory.current', 'memory.peak', 'memory.max', 'memory.events']:
            p = Path('/sys/fs/cgroup')/key
            if p.exists(): event[key] = p.read_text().strip()
        try:
            event['gpu_csv'] = subprocess.check_output(
                ['nvidia-smi','--query-gpu=index,memory.used,memory.total,utilization.gpu',
                 '--format=csv,noheader,nounits'], text=True, timeout=10).strip()
        except (subprocess.SubprocessError, OSError) as error:
            event['gpu_query_error'] = type(error).__name__
        processes=[]
        for proc in Path('/proc').glob('[0-9]*'):
            try:
                command = (proc/'cmdline').read_bytes()
                if b'full_sft_train_fsdp_scheduled.py' in command:
                    rss = next(line for line in (proc/'status').read_text().splitlines()
                               if line.startswith('VmRSS:'))
                    processes.append({'pid':int(proc.name),'rss_kib':int(rss.split()[1])})
            except (OSError, StopIteration): pass
        event['training_processes']=processes
        out.write(json.dumps(event)+'\n')
        time.sleep(5)
