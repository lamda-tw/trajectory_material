"""Technical acceptance must reject finite-looking but ineffective updates."""
import copy
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
import b_supervise as supervisor


class AcceptanceTests(unittest.TestCase):
    def metrics(self):
        return dict(physical_gpu_uuid=supervisor.GPU,teacher_received_gradient=False,
            sft_loss=1.,sdpo_loss=.2,total_loss=1.2,sft_grad_norm=1.,weighted_sdpo_grad_norm=.5,
            grad_norm_before_clip=1.2,grad_norm_after_clip=1.,student_parameter_delta_norm=.001,
            peak_allocated_gib=50.,peak_reserved_gib=60.,counts={'sft':3,'sdpo':2},optimizer_step_performed=True)

    def validate(self,metrics):
        def read(path):
            if path.name=='COMPLETE.json':return {'files':{}}
            return metrics
        with patch.object(supervisor,'read',side_effect=read),patch.object(supervisor,'file_sha',return_value='sha'),\
             patch.object(supervisor,'write_json'),patch.object(supervisor,'config',return_value={'training':{'grad_clip_norm':1.}}):
            return supervisor.validate_checkpoint(1)

    def test_valid_first_batch(self):
        self.assertEqual(self.validate(self.metrics())['sdpo_loss'],.2)

    def test_rejects_numerical_and_effectiveness_failures(self):
        for change in [dict(sdpo_loss=float('nan')),dict(grad_norm_after_clip=1.1),
                       dict(student_parameter_delta_norm=0.),dict(counts={'sft':3}),
                       dict(weighted_sdpo_grad_norm=0.),dict(teacher_received_gradient=True),
                       dict(physical_gpu_uuid='GPU0')]:
            with self.subTest(change=change),self.assertRaises(AssertionError):
                m=copy.deepcopy(self.metrics());m.update(change);self.validate(m)


if __name__=='__main__':unittest.main()
