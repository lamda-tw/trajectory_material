"""SFT-only routing, unchanged protocol, and first-update acceptance guards."""
import copy
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import b_common as c
import b_supervise as supervisor
from b_dataset import route


class ControlTests(unittest.TestCase):
    def test_training_protocol_and_loss_unchanged(self):
        old=c.read(c.R/'phase_b/config/run.json');new=c.config()
        for key in ['training','agent','sampling','paths']:
            self.assertEqual(old[key],new[key])
        for name in ['schedule.json','train90.txt','dev57.txt','judge.json']:
            self.assertEqual(c.file_sha(c.R/'phase_b/config'/name),c.file_sha(c.B/'config'/name))
        self.assertEqual(c.file_sha(c.S/'b_loss.py'),c.file_sha(c.R/'scripts/b_loss.py'))
        self.assertEqual(new['available_arms'],['sft'])
        self.assertNotEqual(c.run_dir('sft'),c.R/'phase_b/runs/mixed')
        self.assertNotEqual(c.run_dir('sft'),c.R/'phase_b_sdpo_only/runs/sdpo')

    def test_sft_selection_unchanged_and_all_FAIL_masked(self):
        cfg=c.config()
        for labels in ['PPPNNNNU','PPPPPPPP','PPNNNNNN','NNNNNNNN','PNNNNNNN']:
            self.assertEqual(route(labels,None,0,100,0,cfg,'sft'),route(labels,None,0,100,0,cfg,'mixed'))
        for labels in ['PPPFNNNN','FNNNNNNN','FFFFPPPP']:
            for usable in [True,False]:
                self.assertEqual(route(labels,{'usable':usable},80,100,200,cfg,'sft')[0],'mask')
        self.assertEqual(route('PPPNNNNN',None,0,32001,0,cfg,'sft')[0],'mask')

    def test_first_batch_reuses_exact_initial_trajectories(self):
        old=c.read(c.R/'phase_b/runs/mixed/batch_001/collection.json')
        new=c.read(c.batch_dir('sft',1)/'collection.json')
        self.assertEqual(old['trajectories'],new['trajectories'])
        self.assertEqual(old['schedule'],new['schedule'])
        self.assertEqual(new['policy_identity'],c.policy_identity(None))
        reuse=c.read(c.B/'config/first_batch_reuse.json')
        self.assertEqual(reuse['source_collection_sha256'],c.file_sha(c.R/'phase_b/runs/mixed/batch_001/collection.json'))

    def test_acceptance_rejects_distillation_and_changed_SFT(self):
        original=c.read(c.R/'phase_b/runs/mixed/batch_001/checkpoint/metrics.json')
        good=copy.deepcopy(original)
        good.update(sdpo_loss=0.,weighted_sdpo_grad_norm=0.,counts={'sft':20,'mask':48},
            total_loss=original['sft_loss'],grad_norm_before_clip=original['sft_grad_norm'],
            grad_norm_after_clip=original['sft_grad_norm'])
        def validate(m):
            def read(path):
                if path.name=='COMPLETE.json':return {'files':{}}
                if 'runs/mixed' in str(path):return original
                return m
            with patch.object(supervisor,'read',side_effect=read),patch.object(supervisor,'file_sha',return_value='test'),patch.object(supervisor,'write_json'):
                return supervisor.validate_checkpoint(1)
        self.assertGreater(validate(good)['sft_loss'],0)
        for change in [{'sdpo_loss':.1},{'weighted_sdpo_grad_norm':.1},{'counts':{'sft':20,'sdpo':1}},
            {'sft_loss':good['sft_loss']+.01},{'sft_grad_norm':0.},{'counts':{'sft':19}},
            {'teacher_received_gradient':True},{'student_parameter_delta_norm':0.}]:
            with self.subTest(change=change),self.assertRaises(AssertionError):validate(dict(good,**change))


if __name__=='__main__':unittest.main()
