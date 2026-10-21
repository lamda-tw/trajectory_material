"""Supervisor safety checks without GPU, network, real signals, or experiment mutations."""
import json,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import watchdog as w

class SupervisorChecks(unittest.TestCase):
 def test_only_descendants_are_owned_and_pid_reuse_is_discarded(self):
  state={'owned_processes':{'70':'old','71':'alive'}}
  table={10:{'ppid':1,'birth':'p'},11:{'ppid':10,'birth':'c'},12:{'ppid':11,'birth':'g'},20:{'ppid':1,'birth':'foreign_gpu0'},70:{'ppid':1,'birth':'reused'},71:{'ppid':1,'birth':'alive'}}
  w.track_children(state,table,[10]);self.assertEqual(state['owned_processes'],{'71':'alive','10':'p','11':'c','12':'g'})
 def test_cleanup_does_not_signal_reused_or_foreign_process(self):
  state={'owned_processes':{'10':'old','11':'owned'}}
  table={10:{'birth':'reused'},11:{'birth':'owned'},20:{'birth':'foreign'}}
  with patch.object(w,'process_table',return_value=table),patch.object(w.os,'kill') as kill,patch.object(w.time,'sleep'),patch.object(w,'event'):
   w.stop_owned(state);self.assertEqual({x.args[0] for x in kill.call_args_list},{11})
 def fixture(self,status,state=None,free=100,integrity=False,complete=False):
  temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup);root=Path(temp.name);(root/'runtime').mkdir();(root/'STATUS.json').write_text(json.dumps(status))
  if complete:(root/'REPORT.md').write_text('done')
  c={'generated':1,'paired':0,'paired_valid':0,'scored':0,'reviewed':0,'reference_evaluators':299}
  patches=[patch.object(w,'R',root),patch.object(w,'STATE',root/'runtime/state.json'),patch.object(w,'counts',return_value=(c,[],[])),patch.object(w,'process_table',return_value={}),patch.object(w,'frozen_ok',return_value=not integrity),patch.object(w.shutil,'disk_usage',return_value=SimpleNamespace(free=free*2**30)),patch.object(w.subprocess,'run',return_value=SimpleNamespace(stdout='GPU1')),patch.object(w,'refresh'),patch.object(w,'event')]
  for p in patches:p.start();self.addCleanup(p.stop)
  state=state or {};state['last_counts']=json.dumps(c,sort_keys=True)
  return root,state
 def test_transient_exit_resumes_without_touching_results(self):
  root,state=self.fixture({'status':'error','current_detail':'worker timeout'})
  with patch.object(w,'stop_owned'),patch.object(w,'launch',return_value=99) as launch:
   w.tick(state);launch.assert_called_once();self.assertEqual(state['total_restarts'],1)
  self.assertEqual(json.loads((root/'HEALTH.json').read_text())['monitor_status'],'recovering')
 def test_frozen_change_blocks_restart(self):
  root,state=self.fixture({'status':'running'},integrity=True)
  with patch.object(w,'stop_owned'),patch.object(w,'launch') as launch:
   w.tick(state);launch.assert_not_called()
  self.assertIn('哈希异常',state['blocked'])
 def test_total_retry_budget_is_bounded(self):
  root,state=self.fixture({'status':'error','current_detail':'worker timeout'},state={'total_restarts':8})
  with patch.object(w,'stop_owned'),patch.object(w,'launch') as launch:
   w.tick(state);launch.assert_not_called()
  self.assertIn('累计8次',state['blocked'])
 def test_low_disk_pauses_without_deleting_evidence(self):
  root,state=self.fixture({'status':'running'},free=9)
  with patch.object(w,'stop_owned'),patch.object(w,'launch') as launch:
   w.tick(state);launch.assert_not_called()
  self.assertEqual(json.loads((root/'HEALTH.json').read_text())['monitor_status'],'waiting_disk')
 def test_success_exits_supervision(self):
  root,state=self.fixture({'status':'complete','current_node':'evaluator与报告'},complete=True)
  with patch.object(w,'launch') as launch:
   self.assertTrue(w.tick(state));launch.assert_not_called()

if __name__=='__main__':unittest.main()
