from pathlib import Path
import ast,hashlib,json,math,sys
exp=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(exp/'scripts_snapshot'))
from full_sft_train_fsdp_scheduled import build_lr_factor
cfg=json.loads((exp/'config/training_config.json').read_text())
old=Path(cfg['reference_training_experiment'])
new_source=(exp/'scripts_snapshot/full_sft_train_fsdp_scheduled.py').read_text()
old_source=(old/'scripts_snapshot/full_sft_train_fsdp_scheduled.py').read_text()
def function_ast(source,name):
 return ast.dump(next(n for n in ast.parse(source).body if isinstance(n,ast.FunctionDef) and n.name==name),include_attributes=False)
for name in ['render_record','save_full_hf_model','build_lr_factor']:
 assert function_ast(new_source,name)==function_ast(old_source,name),name
assert (exp/'scripts_snapshot/full_sft_runtime.py').read_bytes()==(old/'scripts_snapshot/full_sft_runtime.py').read_bytes()
start='    for epoch_index in range(start_epoch, args.epochs):'
assert new_source[new_source.index(start):new_source.index('    local_gpu =')]==old_source[old_source.index(start):old_source.index('    local_gpu =')]
history=[json.loads(line) for line in (old/'metrics/training_history.jsonl').read_text().splitlines()][:1170]
factor=build_lr_factor(2925,88,.1)
expected=[1e-5*factor(i) for i in range(1170)]
max_delta=max(abs(row['learning_rate']-lr) for row,lr in zip(history,expected))
assert len(history)==1170 and max_delta<1e-18
assert math.ceil(2925*.03)==88 and expected[-1]>1e-6
result={'status':'PASS','schedule_steps':2925,'actual_training_steps':1170,'warmup_steps':88,
 'lr_at_first_update':expected[0],'lr_at_update_1170':expected[-1],'maximum_lr_difference_from_original_prefix':max_delta,
 'supervision_rendering_and_runtime_unchanged':True,'training_update_loop_unchanged':True,'hf_export_function_unchanged':True,
 'train_sha256':hashlib.sha256(Path(cfg['train_json']).read_bytes()).hexdigest()}
assert result['train_sha256']==cfg['train_sha256']
(exp/'config/prefix_preflight.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
