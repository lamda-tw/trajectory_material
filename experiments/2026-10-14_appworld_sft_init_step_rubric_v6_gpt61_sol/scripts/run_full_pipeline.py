"""Detached durable full scoring followed by deterministic exports."""
from pathlib import Path
import json, os, subprocess, sys, traceback
from datetime import datetime
from zoneinfo import ZoneInfo
ROOT=Path(__file__).resolve().parents[1]
def stamp(): return datetime.now(ZoneInfo('Asia/Shanghai')).isoformat()
def status(**kwargs): (ROOT/'PIPELINE_STATUS.json').write_text(json.dumps({'updated_at':stamp(),'pid':os.getpid(),**kwargs},indent=2)+'\n')
try:
    status(phase='full_scoring')
    subprocess.run([sys.executable,str(ROOT/'scripts/run_scoring.py'),'--execute'],check=True)
    status(phase='structural_validation_and_export')
    subprocess.run([sys.executable,str(ROOT/'scripts/analyze_results.py')],check=True)
    status(phase='scores_exported_pending_semantic_review')
except Exception:
    status(phase='needs_recovery',error=traceback.format_exc())
    raise
