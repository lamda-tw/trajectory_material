"""CPU-only epoch/checkpoint isolation and paired evaluation aggregation."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
import b_evaluate
from b_common import write_json,file_sha
from b_report import paired_results


class EpochEvaluationTests(unittest.TestCase):
    def test_cached_epochs_keep_separate_checkpoint_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp);(base/'config').mkdir()
            write_json(base/'config/run.json',{'test_fixture':True})
            write_json(base/'config/execution_gate.json',{'allowed_arms':['mixed'],'evaluation_batches':[18,36]})
            tasks=[f'task_{i:02d}' for i in range(57)];(base/'config/dev57.txt').write_text('\n'.join(tasks))
            root=base/'runs/mixed'
            for number in (18,36):
                checkpoint=root/f'batch_{number:03d}/checkpoint'
                write_json(checkpoint/'COMPLETE.json',{'batch':number,'files':{},'student_adapter':'student'})
                folder=root/f'epoch_{number//18:02d}_dev57';rows=[]
                for task in tasks:
                    target=folder/'trajectories'/(task+'.json');write_json(target,{'test_fixture':number})
                    rows.append({'task_id':task,'trajectory_sha256':file_sha(target)})
                write_json(folder/'summary.json',{'results':rows,'epoch':number//18})
            with patch.object(b_evaluate,'B',base),patch.object(b_evaluate,'run_dir',return_value=root),\
                 patch.object(b_evaluate,'batch_dir',side_effect=lambda arm,n:root/f'batch_{n:03d}'),\
                 patch.object(b_evaluate,'config',return_value={'training':{'update_opportunities':36}}),\
                 patch.object(b_evaluate,'authorize'),patch.object(b_evaluate,'gpu_lock',side_effect=AssertionError('Cached evaluation must not use GPU')):
                self.assertEqual(b_evaluate.main('mixed',18)['epoch'],1)
                self.assertEqual(b_evaluate.main('mixed',36)['epoch'],2)
                one=json.loads((root/'epoch_01_dev57/identity.json').read_text())
                two=json.loads((root/'epoch_02_dev57/identity.json').read_text())
                self.assertNotEqual(one['policy_identity'],two['policy_identity'])

    def test_pair_by_task_id_not_completion_order(self):
        rows=[{'task_id':str(i),'success':i==1,'num_passes':int(i==1),'num_tests':1,'steps':3,'termination':'completion_api'} for i in range(57)]
        other=[dict(r,success=r['task_id']=='2') for r in reversed(rows)]
        result=paired_results({'results':rows},{'results':other})
        self.assertEqual(sum(not x['epoch_1_success'] and x['epoch_2_success'] for x in result),1)
        self.assertEqual(sum(x['epoch_1_success'] and not x['epoch_2_success'] for x in result),1)
        with self.assertRaises(AssertionError):paired_results({'results':rows},{'results':other[:-1]})


if __name__=='__main__':unittest.main()
