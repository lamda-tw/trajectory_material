"""CPU checks for run isolation, matched protocol, and protected checkpoint retention."""
import copy
import json
import random
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import b_common as c
import b_retention as retention
import b_evaluate
from b_report_helpers import behavior, parse_checks


class ReplicationTests(unittest.TestCase):
    def test_only_seed_and_duration_changed(self):
        old=c.read(c.R/'phase_b_sft_only/config/run.json');new=copy.deepcopy(c.config())
        new['experiment']=old['experiment']
        for key in ['seed','epochs','update_opportunities']:new['training'][key]=old['training'][key]
        new['collection']['tasks']=old['collection']['tasks'];new['evaluation']['tasks']=old['evaluation']['tasks']
        self.assertEqual(old,new)
        self.assertEqual(c.config()['training']['seed'],20261026)
        self.assertEqual(c.config()['evaluation']['seed'],100)
        self.assertIsNone(c.previous_checkpoint('sft',1))
        self.assertEqual(c.policy_identity(None)['initialization_seed'],20261026)
        self.assertFalse((c.B/'config/first_batch_reuse.json').exists())
        # The judge's infrastructure recovery was repaired; prompts/schema/config stay frozen.
        for name in ['b_loss.py','b_dataset.py','b_rollout_worker.py','b_train_batch.py']:
            self.assertEqual(c.file_sha(c.S/name),c.file_sha(c.R/'phase_b_sft_only/scripts'/name))

    def test_schedule_same_algorithm_new_seed(self):
        tasks=(c.B/'config/train90.txt').read_text().split();rng=random.Random(20261026);expected=[]
        for epoch in range(1,4):
            order=list(tasks);rng.shuffle(order)
            for i in range(0,90,5):
                expected.append({'batch':len(expected)+1,'epoch':epoch,'tasks':[
                    {'task_id':t,'seed':int(c.digest([20261026,epoch,t])[:12],16)%(2**31-51)} for t in order[i:i+5]]})
        self.assertEqual(c.read(c.B/'config/schedule.json')['batches'],expected)
        self.assertNotEqual(expected[:36],c.read(c.R/'phase_b_sft_only/config/schedule.json')['batches'])
        self.assertEqual(len(expected),54)
        for name in ['train90.txt','dev57.txt','judge.json']:
            self.assertEqual(c.file_sha(c.B/'config'/name),c.file_sha(c.R/'phase_b_sft_only/config'/name))

    def test_retention_keeps_protected_and_resume_models(self):
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp);root=base/'runs/sft'
            policy={'user_authorized_model_retention':True,'keep_full_batches':[1,18,36,54],
                'keep_latest_batches':2,'eligible_model_files':['state.pt','adapters/student/adapter_model.safetensors']}
            c.write_json(base/'config/retention.json',policy);(base/'analysis').mkdir()
            for n in range(1,6):
                cp=root/f'batch_{n:03d}/checkpoint';(cp/'adapters/student').mkdir(parents=True)
                (cp/'state.pt').write_bytes(f'state-{n}'.encode());(cp/'adapters/student/adapter_model.safetensors').write_bytes(f'adapter-{n}'.encode())
                c.write_json(cp/'metrics.json',{'batch':n})
                c.write_json(cp/'COMPLETE.json',{'batch':n,'files':{str(p.relative_to(cp)):c.file_sha(p) for p in cp.rglob('*') if p.is_file()}})
                c.write_json(cp.parent/'acceptance.json',{'passed':True})
            with patch.object(retention,'B',base),patch.object(retention,'authorize'),patch.object(retention,'run_dir',return_value=root),patch.object(retention,'batch_dir',side_effect=lambda arm,n:root/f'batch_{n:03d}'):
                result=retention.apply_retention(5)
                self.assertEqual(result['pruned_batches'],[2,3])
                for n in (1,4,5):self.assertTrue((root/f'batch_{n:03d}/checkpoint/state.pt').exists())
                for n in (2,3):
                    cp=root/f'batch_{n:03d}/checkpoint';self.assertFalse((cp/'state.pt').exists());retention.validate_committed(cp,True)
                    with self.assertRaises(AssertionError):retention.validate_committed(cp,False)
                self.assertEqual(retention.apply_retention(5)['bytes_freed'],0)

    def test_third_epoch_cached_evaluation_is_supported(self):
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp);root=base/'runs/sft';cp=root/'batch_054/checkpoint';cp.mkdir(parents=True)
            c.write_json(cp/'COMPLETE.json',{'batch':54,'files':{},'student_adapter':'adapters/student'})
            c.write_json(base/'config/run.json',{'fixture':True})
            c.write_json(base/'config/execution_gate.json',{'allowed_arms':['sft'],'evaluation_batches':[18,36,54]})
            tasks=[f'task_{i}' for i in range(57)];(base/'config/dev57.txt').write_text('\n'.join(tasks))
            folder=root/'epoch_03_dev57';rows=[]
            for task in tasks:
                p=folder/'trajectories'/f'{task}.json';c.write_json(p,{'fixture':True})
                rows.append({'task_id':task,'trajectory_sha256':c.file_sha(p)})
            c.write_json(folder/'summary.json',{'epoch':3,'results':rows})
            with patch.object(b_evaluate,'B',base),patch.object(b_evaluate,'run_dir',return_value=root),patch.object(b_evaluate,'batch_dir',return_value=cp.parent),patch.object(b_evaluate,'authorize'):
                self.assertEqual(b_evaluate.main('sft',54)['epoch'],3)

    def test_alternating_documents_are_counted(self):
        codes=["print(apis.api_docs.show_api_doc(app_name='spotify',api_name='search_songs'))", "print(apis.api_docs.show_api_doc(app_name='spotify',api_name='search_artists'))"]
        t={'steps':[{'code':codes[i%2],'response_ids':[1]} for i in range(8)]}
        v=behavior(t);self.assertEqual(v['repeated_docs_steps'],6);self.assertEqual(v['longest_docs_streak'],1)


if __name__=='__main__':unittest.main(verbosity=2)
