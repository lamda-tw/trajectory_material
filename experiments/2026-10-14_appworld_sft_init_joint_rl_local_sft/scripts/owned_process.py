"""Track and clean only this experiment's explicitly spawned process groups."""
from pathlib import Path
import os,signal,time
from common import dump,read,now

def birth(pid):
    try:return Path(f'/proc/{pid}/stat').read_text().rsplit(')',1)[1].split()[19]
    except FileNotFoundError:return None

def record(path,pid,argv):
    dump(path,{'at':now(),'pid':pid,'start_ticks':birth(pid),'argv':list(map(str,argv)),'owner_pid':os.getpid()})

def cleanup(path):
    d=read(path);pid=d['pid']
    if not d.get('start_ticks') or birth(pid)!=d['start_ticks']:return
    # Each recorded process is launched in its own session; never target an unrelated group.
    try:
        if os.getpgid(pid)!=pid:return
        os.killpg(pid,signal.SIGTERM)
        deadline=time.monotonic()+10
        while birth(pid)==d['start_ticks'] and time.monotonic()<deadline:time.sleep(.2)
        if birth(pid)==d['start_ticks']:os.killpg(pid,signal.SIGKILL)
    except ProcessLookupError:pass
