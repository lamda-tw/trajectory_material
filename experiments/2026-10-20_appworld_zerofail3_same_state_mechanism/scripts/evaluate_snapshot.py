"""Evaluate only an isolated disk snapshot in a fresh process; never touch a live policy world."""
from pathlib import Path
import argparse,json,os,shutil,sys,types
R=Path(__file__).resolve().parents[1];sys.path.insert(0,str(R/'runtime_code'))
from common import atomic_json,digest,file_sha
from replay_worker import db_state

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--replay',type=Path,required=True);ap.add_argument('--phase',choices=['before','after','h1','h3','h4','h12'],required=True);ap.add_argument('--output',type=Path,required=True);a=ap.parse_args()
 d=json.loads(a.replay.read_text());cfg=json.loads((R/'config/runtime.json').read_text());src=Path(d['job']['runtime'])/'snapshots'/a.phase;task=d['task_id'];runtime=Path(d['job']['runtime'])/('eval_'+a.phase);runtime.mkdir(parents=True,exist_ok=True)
 before_files={p.name:file_sha(p) for p in src.iterdir() if p.is_file()}
 if not (runtime/'data').exists():(runtime/'data').symlink_to(cfg['paths']['appworld_data'],target_is_directory=True)
 cache=runtime/'cache';cache.mkdir(exist_ok=True)
 if not (cache/'tests').exists():(cache/'tests').symlink_to(cfg['paths']['appworld_test_cache'],target_is_directory=True)
 dest=runtime/'experiments/outputs/branch/tasks'/task/'dbs'
 # This is a disposable evaluator copy, never the retained source snapshot.
 if dest.exists():shutil.rmtree(dest)
 shutil.copytree(src,dest)
 os.environ['APPWORLD_ROOT']=str(runtime);os.environ['APPWORLD_CACHE']=str(cache);os.chdir(runtime)
 from appworld import update_root
 update_root(str(runtime))
 from appworld.task import Task
 from appworld.collections.models import ModelCollection
 from appworld.apps.lib.models.db import CachedDBHandler,get_db_home_path
 t=Task.load(task_id=task,load_ground_truth=False)
 models=ModelCollection.load(to_db_home_path=get_db_home_path(storage_type='memory',type='task_output',task_id=task),from_db_home_path=str(dest),load_apps=t.allowed_apps)
 loaded=db_state(types.SimpleNamespace(models=models))
 if loaded!=d[a.phase]['db_tables']:
  atomic_json(a.output.with_suffix('.mismatch.json'),{'state_id':d['state_id'],'phase':a.phase,'expected':d[a.phase]['db_tables'],'loaded':loaded})
  raise AssertionError('Evaluator disk snapshot != actual branch database')
 t.close();CachedDBHandler.reset()
 from appworld.evaluator import evaluate_task
 tracker=evaluate_task(task_id=task,experiment_name='branch',suppress_errors=True,save_report=True)
 assert tracker.num_tests>0 and tracker.total_count==tracker.num_tests
 report=runtime/'experiments/outputs/branch/tasks'/task/'evaluation/report.md'
 from evaluator_parse import parse_report
 checks=parse_report(report.read_text());assert len(checks)==tracker.num_tests and sum(checks.values())==tracker.pass_count
 assert before_files=={p.name:file_sha(p) for p in src.iterdir() if p.is_file()},'Source snapshot mutated'
 atomic_json(a.output,{'state_id':d['state_id'],'phase':a.phase,'source_replay':str(a.replay),'source_snapshot_sha256':digest(before_files),'loaded_db_matches_live_branch':True,'source_unmodified':True,'report':str(report),'checks':checks,'tracker':tracker.to_dict(),'num_tests':tracker.num_tests,'num_passes':tracker.pass_count,'success':tracker.success})
 # Retain the original snapshot and report; remove only this verified duplicate.
 shutil.rmtree(dest)
 print(json.dumps({'state':d['state_id'],'phase':a.phase,'passes':tracker.pass_count,'tests':tracker.num_tests,'loaded_db_matches':True}))
if __name__=='__main__':main()
