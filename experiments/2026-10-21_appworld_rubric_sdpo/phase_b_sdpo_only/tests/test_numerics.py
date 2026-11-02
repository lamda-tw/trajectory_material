"""CPU synthetic tests only: no pretrained model, environment execution or optimizer steps."""
from pathlib import Path
import sys
import unittest
import tempfile
import os
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import torch
from b_loss import bucket_reverse_kl,step_loss,select_adapter,learning_rate,ema_state
from b_dataset import route,validate_result
from b_judge import preserve_labels


class KLTests(unittest.TestCase):
    def test_bucket_formula_and_gradient(self):
        torch.manual_seed(9)
        p=torch.randn(3,11,requires_grad=True);q=torch.randn(3,11,requires_grad=True)
        actual=bucket_reverse_kl(p,q,4)
        indices=p.detach().topk(4).indices
        pp=p.softmax(-1);qq=q.detach().softmax(-1)
        ps=pp.gather(-1,indices);qs=qq.gather(-1,indices)
        pb=torch.cat([ps,1-ps.sum(-1,keepdim=True)],-1)
        qb=torch.cat([qs,1-qs.sum(-1,keepdim=True)],-1)
        expected=(pb*(pb.log()-qb.log())).sum(-1)
        torch.testing.assert_close(actual,expected,atol=2e-6,rtol=2e-5)
        g=torch.autograd.grad(actual.sum(),p,retain_graph=True)[0]
        expected_g=torch.autograd.grad(expected.sum(),p,retain_graph=True)[0]
        torch.testing.assert_close(g,expected_g,atol=2e-6,rtol=2e-5)
        actual.sum().backward();self.assertIsNone(q.grad)

    def test_full_vocab_and_zero_self_KL(self):
        p=torch.tensor([[0.,1.,-3.]],requires_grad=True);q=torch.tensor([[1.,-1.,2.]])
        expected=(p.softmax(-1)*(p.log_softmax(-1)-q.log_softmax(-1))).sum(-1)
        torch.testing.assert_close(bucket_reverse_kl(p,q,3),expected)
        same=bucket_reverse_kl(p,p.detach(),1);same.sum().backward()
        torch.testing.assert_close(same,torch.zeros_like(same),atol=1e-7,rtol=0)
        torch.testing.assert_close(p.grad,torch.zeros_like(p),atol=1e-7,rtol=0)

    def test_small_tail_remains_finite(self):
        p=torch.tensor([[30.,0.,-1.,-2.]],requires_grad=True)
        q=torch.tensor([[30.,-2.,-3.,-4.]],requires_grad=True)
        loss=bucket_reverse_kl(p,q,1).sum();loss.backward()
        self.assertTrue(torch.isfinite(loss));self.assertGreater(loss.item(),0)
        self.assertTrue(torch.isfinite(p.grad).all());self.assertIsNone(q.grad)

    def test_bucket_KL_bounded_by_full_KL(self):
        torch.manual_seed(8);p=torch.randn(7,19);q=torch.randn(7,19)
        self.assertTrue((bucket_reverse_kl(p,q,5)<=bucket_reverse_kl(p,q,19)+1e-6).all())

    def test_branch_normalization_and_accumulation(self):
        x=torch.tensor([0.2,-0.1],requires_grad=True)
        g=[(x-1).square().mean(),(x+2).square().mean()]
        b=[bucket_reverse_kl(x[None],torch.tensor([[2.,-1.]]),1).mean() for _ in range(3)]
        direct=torch.autograd.grad(sum(g)/2+0.3*sum(b)/3,x,retain_graph=True)[0]
        for loss in g:(loss/2).backward(retain_graph=True)
        for loss in b:(loss*0.3/3).backward(retain_graph=True)
        torch.testing.assert_close(x.grad,direct)


class RoutingTests(unittest.TestCase):
    def setUp(self):
        self.cfg={'agent':{'max_model_len':32000},'training':{'feedback_max_tokens':256,'teacher_max_length':32768}}
    def test_zero_fail_minimum_PASS_and_U(self):
        self.assertEqual(route('PPPNNNNU',None,0,100,0,self.cfg,'mixed')[0],'sft')
        self.assertEqual(route('PPNNNNNN',None,0,100,0,self.cfg,'mixed'),('mask','zero_fail_P_below_3'))
        self.assertEqual(route('NNNNNNNN',None,0,100,0,self.cfg,'mixed')[0],'mask')
    def test_FAIL_feedback_and_control(self):
        self.assertEqual(route('PPPFNNNN',{'usable':True},80,100,200,self.cfg,'mixed')[0],'sdpo')
        self.assertEqual(route('PPPFNNNN',{'usable':True},80,100,200,self.cfg,'sft')[0],'mask')
        self.assertEqual(route('PPPFNNNN',{'usable':False},0,100,200,self.cfg,'mixed')[0],'mask')
        self.assertEqual(route('PPPFNNNN',{'usable':True},257,100,200,self.cfg,'mixed')[0],'mask')
        self.assertEqual(route('PPPFNNNN',{'usable':True},80,100,32769,self.cfg,'mixed')[0],'mask')
    def test_warmup_and_ema(self):
        cfg={'learning_rate':5e-5,'warmup_nonempty_updates':5}
        self.assertAlmostEqual(learning_rate(1,cfg),1e-5);self.assertEqual(learning_rate(6,cfg),5e-5)
        t={'v':torch.tensor([1.])};s={'v':torch.tensor([3.],requires_grad=True)}
        result=ema_state(t,s,.95);self.assertAlmostEqual(result['v'].item(),1.1,places=6);self.assertFalse(result['v'].requires_grad)
    def test_format_repair_cannot_change_labels(self):
        preserve_labels({'steps':[[1,'F N P N N N N P','reason']]},{'steps':[[1,'FNPNNNNP','reason']]})
        with self.assertRaises(AssertionError):preserve_labels({'steps':[[1,'FNPNNNNP','reason']]},{'steps':[[1,'PPPNNNNP','']]})
    def test_gpu_context_restores_environment_without_real_gpu(self):
        import b_common
        with tempfile.TemporaryDirectory() as tmp, patch.object(b_common,'W',Path(tmp)), patch.object(b_common,'authorize'), patch.object(b_common,'require_free_gpu'), patch.object(b_common,'config',return_value={'server':{'minimum_free_gpu_gib':80}}), patch.dict(os.environ,{'CUDA_VISIBLE_DEVICES':'test_previous','USE_TORCH':'0'}):
            with b_common.gpu_lock('training_allowed'):
                self.assertEqual(os.environ['CUDA_VISIBLE_DEVICES'],b_common.GPU)
                self.assertEqual(os.environ['USE_TORCH'],'1')
            self.assertEqual(os.environ['CUDA_VISIBLE_DEVICES'],'test_previous')
            self.assertEqual(os.environ['USE_TORCH'],'0')


class TinyModelTests(unittest.TestCase):
    def setUp(self):
        from transformers import Qwen3Config,Qwen3ForCausalLM
        from peft import LoraConfig,get_peft_model,get_peft_model_state_dict,set_peft_model_state_dict
        torch.manual_seed(7)
        cfg=Qwen3Config(vocab_size=97,hidden_size=32,intermediate_size=64,num_hidden_layers=2,num_attention_heads=4,
                        num_key_value_heads=2,head_dim=8,max_position_embeddings=128,attention_dropout=0.)
        model=Qwen3ForCausalLM(cfg)
        lora=LoraConfig(r=2,lora_alpha=4,lora_dropout=0.,target_modules=['q_proj','v_proj'],task_type='CAUSAL_LM')
        self.model=get_peft_model(model,lora,adapter_name='student');self.model.add_adapter('teacher',lora)
        set_peft_model_state_dict(self.model,get_peft_model_state_dict(self.model,adapter_name='student'),adapter_name='teacher')
        self.model.gradient_checkpointing_enable(gradient_checkpointing_kwargs={'use_reentrant':False});self.model.enable_input_require_grads()
        self.cfg={'top_k':8,'head_chunk_size':2}
        self.example={'prompt_ids':[1,2,3,4],'response_ids':[5,6,7],'teacher_prompt_ids':[1,2,3,4],'branch':'sft'}
    def test_response_alignment_and_CE(self):
        select_adapter(self.model,'student');self.model.eval()
        tokens=torch.tensor([[1,2,3,4,5,6,7]])
        with torch.no_grad():
            logits=self.model(input_ids=tokens[:,:-1],use_cache=False).logits[0,3:]
            expected=torch.nn.functional.cross_entropy(logits,torch.tensor([5,6,7]))
        actual=step_loss(self.model,self.example,self.cfg)
        torch.testing.assert_close(actual,expected,atol=2e-6,rtol=2e-5)
        actual.backward()
        self.assertTrue(any(p.grad is not None and p.grad.abs().sum()>0 for n,p in self.model.named_parameters() if '.student.' in n))
        self.assertTrue(all(p.grad is None for n,p in self.model.named_parameters() if '.teacher.' in n))
    def test_equal_teacher_zero_KL_and_detachment(self):
        self.example['branch']='sdpo'
        value=step_loss(self.model,self.example,self.cfg);value.backward()
        self.assertAlmostEqual(value.item(),0.,places=6)
        self.assertTrue(all(p.grad is None for n,p in self.model.named_parameters() if '.teacher.' in n))
    def test_conditioned_teacher_backward_stays_on_student(self):
        self.example.update(branch='sdpo',teacher_prompt_ids=[1,8,9,10,3,4])
        value=step_loss(self.model,self.example,self.cfg);value.backward()
        self.assertTrue(torch.isfinite(value));self.assertGreater(value.item(),0.)
        self.assertTrue(any(p.grad is not None and p.grad.abs().sum()>0 for n,p in self.model.named_parameters() if '.student.' in n))
        self.assertTrue(all(p.grad is None for n,p in self.model.named_parameters() if '.teacher.' in n))
    def test_student_export_does_not_include_teacher(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.model.save_pretrained(tmp,selected_adapters=['student'],safe_serialization=True)
            self.assertTrue((Path(tmp)/'student/adapter_config.json').exists())
            self.assertTrue((Path(tmp)/'student/adapter_model.safetensors').exists())
            self.assertFalse((Path(tmp)/'teacher').exists())


if __name__=='__main__':
    torch.set_num_threads(2)
    unittest.main(verbosity=2)
