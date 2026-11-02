"""One synchronous optimizer opportunity over one frozen five-trajectory batch."""
from b_common import B, R, read, write_json, file_sha, digest, config, authorize, batch_dir, previous_checkpoint, policy_identity, gpu_lock, now
import argparse
import os
import time


def main(arm, number):
    authorize('training_allowed')
    cfg = config(); train = cfg['training']; folder = batch_dir(arm, number)
    data = read(folder / 'dataset.json'); parent = previous_checkpoint(arm, number)
    assert data['arm'] == arm and data['batch'] == number
    assert data['policy_identity'] == policy_identity(parent), 'Batch is not from this student checkpoint'
    output = folder / 'checkpoint'; complete = output / 'COMPLETE.json'
    identity = {'arm':arm,'batch':number,'dataset_sha256':file_sha(folder/'dataset.json'),
                'config_sha256':file_sha(B/'config/run.json'),'parent_policy':data['policy_identity']}
    if complete.exists():
        saved=read(complete);assert saved['identity']==identity
        for name,h in saved['files'].items():assert file_sha(output/name)==h
        return
    output.mkdir(parents=True,exist_ok=True)
    with gpu_lock('training_allowed'):
        os.environ.update(USE_TORCH='1',USE_TF='0',TOKENIZERS_PARALLELISM='false')
        import torch
        from transformers import AutoModelForCausalLM
        from peft import LoraConfig,get_peft_model,get_peft_model_state_dict,set_peft_model_state_dict
        from b_loss import step_loss,select_adapter,learning_rate,ema_state
        assert torch.cuda.device_count()==1
        torch.set_num_threads(4);torch.manual_seed(train['seed']);torch.cuda.manual_seed_all(train['seed'])
        started=time.monotonic()
        base=AutoModelForCausalLM.from_pretrained(cfg['paths']['base_model'],local_files_only=True,
            torch_dtype=torch.bfloat16,attn_implementation='sdpa')
        base.config.use_cache=False
        assert train['teacher_max_length']<=base.config.max_position_embeddings
        torch.manual_seed(train['seed']);torch.cuda.manual_seed_all(train['seed'])
        model=get_peft_model(base,LoraConfig(**train['lora']),adapter_name='student')
        model.add_adapter('teacher',LoraConfig(**train['lora']))
        def state(name):
            return {k:v.detach().cpu().float().clone() for k,v in get_peft_model_state_dict(model,adapter_name=name).items()}
        teacher=state('student')
        set_peft_model_state_dict(model,teacher,adapter_name='teacher')
        model.to('cuda:0');select_adapter(model,'student')
        model.gradient_checkpointing_enable(gradient_checkpointing_kwargs={'use_reentrant':False});model.enable_input_require_grads()
        parameters=[p for p in model.parameters() if p.requires_grad]
        assert parameters and all('lora_' in n and '.student.' in n for n,p in model.named_parameters() if p.requires_grad)
        optimizer=torch.optim.AdamW(parameters,lr=train['learning_rate'],betas=tuple(train['betas']),eps=train['eps'],weight_decay=0)
        actual_updates=0
        if parent:
            saved=torch.load(parent/'state.pt',map_location='cpu',weights_only=False)
            set_peft_model_state_dict(model,saved['student'],adapter_name='student')
            teacher=saved['teacher'];set_peft_model_state_dict(model,teacher,adapter_name='teacher')
            optimizer.load_state_dict(saved['optimizer']);actual_updates=saved['optimizer_updates']
            torch.set_rng_state(saved['torch_rng']);torch.cuda.set_rng_state(saved['cuda_rng'])
            del saved
        select_adapter(model,'student');optimizer.zero_grad(set_to_none=True)
        student_before=state('student')
        chosen={branch:[x for x in data['examples'] if x['branch']==branch] for branch in ['sft','sdpo']}
        assert arm=='mixed' or not chosen['sdpo']
        # This exact initialization invariant matters more than a particular KL threshold.
        if number==1:
            assert all(torch.equal(v,teacher[k]) for k,v in state('student').items())
        rate=learning_rate(actual_updates+1,train)
        for group in optimizer.param_groups:group['lr']=rate
        metrics={'batch':number,'arm':arm,'created_at':now(),'counts':data['counts'],'mask_reasons':data['mask_reasons'],
                 'lr':rate,'lambda_sdpo':train['lambda_sdpo'],'sft_loss':0.,'sdpo_loss':0.,'supervised_tokens':0}
        g_grad=None;step_metrics=[]
        for branch in ['sft','sdpo']:
            examples=chosen[branch]
            scale=1.0 if branch=='sft' else train['lambda_sdpo']
            for i,example in enumerate(examples):
                with torch.autocast('cuda',dtype=torch.bfloat16):loss=step_loss(model,example,train)
                assert torch.isfinite(loss).item() and (branch!='sdpo' or loss.item()>=-1e-4)
                value=loss.item();(loss*scale/len(examples)).backward()
                assert all(p.grad is None for n,p in model.named_parameters() if '.teacher.' in n), 'Teacher received a gradient'
                metrics[branch+'_loss']+=value/len(examples)
                metrics['supervised_tokens']+=len(example['response_ids'])
                step_metrics.append({'trajectory_id':example['trajectory_id'],'step':example['step'],'branch':branch,'loss':value,
                                     'response_tokens':len(example['response_ids']),'labels':example['labels']})
                write_json(folder/'training_progress.json',{'batch':number,'branch':branch,'done':i+1,'total':len(examples),'optimizer_updates_before_batch':actual_updates})
                del loss
            if branch=='sft':
                g_grad=[p.grad.detach().float().clone() if p.grad is not None else torch.zeros_like(p,dtype=torch.float32) for p in parameters]
        total=[p.grad.detach().float() if p.grad is not None else torch.zeros_like(p,dtype=torch.float32) for p in parameters]
        def norm2(values):return sum((v*v).sum() for v in values)
        s2=norm2(g_grad);b_grad=[v-g for v,g in zip(total,g_grad)];b2=norm2(b_grad)
        dot=sum((g*b).sum() for g,b in zip(g_grad,b_grad))
        metrics.update(sft_grad_norm=float(s2.sqrt()),weighted_sdpo_grad_norm=float(b2.sqrt()),
                       branch_grad_cosine=float(dot/(s2*b2).sqrt()) if s2>0 and b2>0 else None)
        del g_grad,b_grad,total
        nonempty=bool(chosen['sft'] or chosen['sdpo'])
        if nonempty:
            authorize('training_allowed')
            before=torch.nn.utils.clip_grad_norm_(parameters,train['grad_clip_norm'],error_if_nonfinite=True)
            after_clip=sum(p.grad.detach().float().square().sum() for p in parameters if p.grad is not None).sqrt()
            optimizer.step();actual_updates+=1
            teacher=ema_state(teacher,state('student'),train['ema_decay'])
            metrics.update(grad_norm_before_clip=float(before),grad_norm_after_clip=float(after_clip),clipped=bool(before>train['grad_clip_norm']))
        else:
            # AdamW, EMA and warmup counter must all stay unchanged on empty batches.
            metrics.update(grad_norm_before_clip=0.,grad_norm_after_clip=0.,clipped=False)
        metrics.update(optimizer_updates=actual_updates,optimizer_step_performed=nonempty,
                       total_loss=metrics['sft_loss']+train['lambda_sdpo']*metrics['sdpo_loss'],
                       seconds=time.monotonic()-started,peak_allocated_gib=torch.cuda.max_memory_allocated()/2**30,
                       peak_reserved_gib=torch.cuda.max_memory_reserved()/2**30,
                       physical_gpu_uuid=os.environ['CUDA_VISIBLE_DEVICES'],teacher_received_gradient=False)
        student=state('student');assert all(torch.isfinite(v).all() for v in student.values())
        metrics['student_parameter_delta_norm']=float(sum((student[k]-v).square().sum() for k,v in student_before.items()).sqrt())
        select_adapter(model,'student')
        model.save_pretrained(output/'adapters',selected_adapters=['student'],safe_serialization=True)
        adapter=output/'adapters/student';assert (adapter/'adapter_config.json').exists()
        snapshot={'identity':identity,'student':student,'teacher':teacher,'optimizer':optimizer.state_dict(),
                  'optimizer_updates':actual_updates,'torch_rng':torch.get_rng_state(),'cuda_rng':torch.cuda.get_rng_state()}
        torch.save(snapshot,output/'state.tmp.pt');(output/'state.tmp.pt').replace(output/'state.pt')
        write_json(output/'metrics.json',metrics);write_json(output/'step_metrics.json',step_metrics)
        files={str(p.relative_to(output)):file_sha(p) for p in output.rglob('*') if p.is_file() and p.name!='COMPLETE.json'}
        write_json(complete,{'identity':identity,'arm':arm,'batch':number,'optimizer_updates':actual_updates,
                            'student_adapter':'adapters/student','files':files,'completed_at':now()})
        print(__import__('json').dumps(metrics),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--arm',choices=['mixed','sft'],required=True);parser.add_argument('--batch',type=int,required=True)
    args=parser.parse_args();main(args.arm,args.batch)
