import copy,json,sys,tempfile,unittest,hashlib
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import b_common as c
import b_retention as retention
from b_loss import learning_rate
from b_dataset import route


class ContinuationTests(unittest.TestCase):
    def test_original_protocol_preserved(self):
        old=c.read(c.SOURCE/'config/run.json');new=c.config()
        ot=copy.deepcopy(old['training']);nt=copy.deepcopy(new['training'])
        for key in ['epochs','update_opportunities']:ot.pop(key);nt.pop(key)
        self.assertEqual(ot,nt)
        for key in ['agent','sampling','paths','server']:self.assertEqual(old[key],new[key])
        for key in ['collection','evaluation']:
            a=copy.deepcopy(old[key]);b=copy.deepcopy(new[key]);a.pop('tasks');b.pop('tasks');self.assertEqual(a,b)
        for name in ['b_loss.py','b_dataset.py','b_judge.py','b_rollout_worker.py']:
            self.assertEqual(c.file_sha(c.S/name),c.file_sha(c.SOURCE/'scripts'/name))
        for name in ['judge.json','train90.txt','dev57.txt']:
            self.assertEqual(c.file_sha(c.B/'config'/name),c.file_sha(c.SOURCE/'config'/name))

    def test_schedule_and_no_rewarmup(self):
        schedule=c.read(c.B/'config/schedule.json')['batches'];old=c.read(c.SOURCE/'config/schedule.json')['batches']
        self.assertEqual(schedule[:36],old);self.assertEqual(len(schedule),90)
        expected=set((c.B/'config/train90.txt').read_text().split());seen=set()
        for e in range(1,6):
            rows=[x for x in schedule if x['epoch']==e];self.assertEqual(len(rows),18)
            tasks=[t['task_id'] for b in rows for t in b['tasks']];self.assertEqual(len(tasks),90);self.assertEqual(set(tasks),expected)
            for row in rows:
                self.assertEqual(len(row['tasks']),5)
                for t in row['tasks']:self.assertNotIn(t['seed'],seen);seen.add(t['seed'])
        self.assertEqual(learning_rate(37,c.config()['training']),5e-5)
        self.assertEqual(learning_rate(90,c.config()['training']),5e-5)
        self.assertEqual(c.previous_checkpoint('sft',37),c.SOURCE/'runs/sft/batch_036/checkpoint')
        with self.assertRaises(AssertionError):c.previous_checkpoint('sft',36)

    def test_sft_routing_unchanged(self):
        cfg=c.config()
        for label in ['PPPNNNNN','PPPNNNNU','PPPPPPPP']:self.assertEqual(route(label,None,0,100,100,cfg,'sft')[0],'sft')
        for label in ['PPNNNNNN','PPPFNNNN','FNNNNNNN','NNNNNNNN']:self.assertEqual(route(label,{'usable':True},10,100,100,cfg,'sft')[0],'mask')

    def test_model_pruning_preserves_evidence_and_protected_epochs(self):
        with tempfile.TemporaryDirectory() as temp:
            base=Path(temp);B=base/'continuation';source=base/'source';(B/'config').mkdir(parents=True)
            policy={'user_authorized_model_retention':True,'source_keep_full_batches':[1,18,36],'continuation_keep_full_batches':[54,72,90],'eligible_model_files':['state.pt','adapters/student/adapter_model.safetensors']}
            (B/'config/retention.json').write_text(json.dumps(policy))
            def checkpoint(n):
                cp=source/'runs/sft'/f'batch_{n:03d}/checkpoint';(cp/'adapters/student').mkdir(parents=True)
                payloads={'state.pt':b'optimizer','adapters/student/adapter_model.safetensors':b'weights','metrics.json':b'{}','step_metrics.json':b'[]','adapters/student/adapter_config.json':b'{}'}
                for name,data in payloads.items():(cp/name).write_bytes(data)
                done={'batch':n,'arm':'sft','files':{name:hashlib.sha256(v).hexdigest() for name,v in payloads.items()}}
                (cp/'COMPLETE.json').write_text(json.dumps(done));return cp
            cp=checkpoint(2);protected=checkpoint(36)
            with patch.object(retention,'B',B),patch.object(retention,'SOURCE',source),patch.object(retention,'run_dir',return_value=B/'runs/sft'):
                before=(cp/'COMPLETE.json').read_bytes();self.assertEqual(retention.prune_checkpoint(cp),16)
                self.assertFalse((cp/'state.pt').exists());self.assertTrue((cp/'metrics.json').exists());self.assertEqual(before,(cp/'COMPLETE.json').read_bytes())
                retention.validate_committed(cp,allow_pruned=True)
                with self.assertRaises(AssertionError):retention.validate_committed(cp,allow_pruned=False)
                self.assertEqual(retention.prune_checkpoint(cp),0)
                with self.assertRaises(AssertionError):retention.prune_checkpoint(protected)
                self.assertTrue((protected/'state.pt').exists())
                (cp/'metrics.json').write_text('{"changed":1}')
                with self.assertRaises(AssertionError):retention.validate_committed(cp,allow_pruned=True)


if __name__=='__main__':unittest.main()
