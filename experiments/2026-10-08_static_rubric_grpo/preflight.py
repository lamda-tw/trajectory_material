"""Offline preparation checks. No generation, judge request, task execution, or GPU training."""
from __future__ import annotations
import importlib.metadata
import json
import os
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from common import ROOT, atomic_json, file_sha, ids, input_fingerprint, load_rules, read_json
from judge import make_schema
from run import prepare_runtime

def probe(python, code):
    result = subprocess.run([python, '-c', code], capture_output=True, text=True, timeout=180,
                            env=dict(os.environ, HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1', CUDA_VISIBLE_DEVICES=''))
    if result.returncode:
        raise RuntimeError((result.stderr or result.stdout)[-6000:])
    return {'stdout': result.stdout.strip(), 'stderr': result.stderr.strip()[-2500:]}

def run(config):
    checks = []
    def check(name, function):
        try:
            value = function()
            checks.append({'name': name, 'status': 'PASS', 'detail': value})
        except Exception as error:
            checks.append({'name': name, 'status': 'FAIL', 'detail': f'{type(error).__name__}: {error}'})
        print(f"{checks[-1]['status']}: {name}", flush=True)
    def paths():
        for key, path in config['paths'].items():
            if not Path(path).exists():
                raise FileNotFoundError(f'{key}: {path}')
        base = Path(config['paths']['base_model'])
        if (base / 'adapter_config.json').exists() or read_json(base / 'config.json')['model_type'] != 'qwen3':
            raise ValueError('Base path must contain raw Qwen3, not an old adapter.')
        index = read_json(base / 'model.safetensors.index.json')
        shards = sorted(set(index['weight_map'].values()))
        for shard in shards:
            if (base / shard).stat().st_size == 0:
                raise ValueError('Empty model shard.')
        return {'model_shards_present': shards, 'base_model': str(base)}
    def assets():
        provenance = read_json(ROOT / 'assets/draco/provenance.json')
        for name, entry in provenance['files'].items():
            if file_sha(ROOT / 'assets/draco' / name) != entry['sha256']:
                raise ValueError('DRACO source changed: ' + name)
        frozen = read_json(ROOT / 'assets/inputs.json')
        for name, expected in frozen['sha256'].items():
            if file_sha(ROOT / name) != expected:
                raise ValueError('Frozen input changed: ' + name)
        train, dev = ids(ROOT / 'assets/splits/train_all.txt'), ids(ROOT / config['evaluation']['tasks'])
        pilot = ids(ROOT / 'assets/splits/train_pilot_8.txt')
        if len(pilot) != 8 or not set(pilot) <= set(train) or set(train) & set(dev):
            raise ValueError('Invalid train/dev boundaries.')
        for split, values in [('train', train), ('dev', dev)]:
            if values != ids(Path(config['paths']['appworld_data']) / 'datasets' / (split + '.txt')):
                raise ValueError('Frozen split differs from official full split.')
        if len(load_rules(config)) != 21:
            raise ValueError('Expected 21 rules.')
        if read_json(ROOT / config['judge']['schema']) != make_schema(load_rules(config)):
            raise ValueError('Judge schema differs from frozen rules.')
        return {'draco_commit': provenance['commit'], 'rules': 21, 'train': len(train), 'pilot': len(pilot), 'dev': len(dev)}
    def runtime():
        path = prepare_runtime(config)
        original = Path(config['paths']['appworld_test_cache'])
        files = list(original.rglob('*.py'))
        if not files:
            raise ValueError('No evaluator tests in source cache.')
        for source in files:
            if file_sha(source) != file_sha(path / 'cache/tests' / source.relative_to(original)):
                raise ValueError('Evaluator test cache copy differs from source.')
        return {'runtime': str(path), 'test_files': len(files), 'task_executions': 0}
    def appworld():
        code = """import importlib.metadata as m, inspect, json
from appworld import AppWorld, update_root
from appworld.task import Task
from appworld.apps.lib.models.db import CachedDBHandler
from jinja2 import StrictUndefined, Template
print(json.dumps({'appworld':m.version('appworld'),'AppWorld_signature':str(inspect.signature(AppWorld)), 'Task_load_signature':str(inspect.signature(Task.load))}))
"""
        return probe(config['paths']['appworld_python'], code)
    def training():
        code = """import importlib.metadata as m, json
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer
from peft import PeftModel, LoraConfig, get_peft_model
print(json.dumps({k:m.version(k) for k in ['torch','transformers','peft','accelerate','safetensors']}))
"""
        return probe(config['paths']['training_python'], code)
    def vllm():
        code = """import importlib.metadata as m, json
from vllm.entrypoints.openai.protocol import CompletionRequest, CompletionResponseChoice, TokenizeChatRequest
assert {'return_token_ids','return_tokens_as_token_ids','logprobs','prompt'} <= set(CompletionRequest.model_fields)
assert 'token_ids' in CompletionResponseChoice.model_fields
assert 'chat_template_kwargs' in TokenizeChatRequest.model_fields
print(json.dumps({'vllm':m.version('vllm'),'exact_token_protocol':True}))
"""
        return probe(config['paths']['vllm_python'], code)
    def codex():
        cli = config['paths']['codex']
        help_result = subprocess.run([cli, 'exec', '--help'], text=True, capture_output=True, timeout=30, check=True)
        for flag in ('--ephemeral', '--ignore-user-config', '--ignore-rules', '--output-schema', '--output-last-message', '--disable'):
            if flag not in help_result.stdout:
                raise ValueError('Codex CLI missing ' + flag)
        features = subprocess.run([cli, 'features', 'list'], text=True, capture_output=True, timeout=30, check=True)
        if 'shell_tool' not in features.stdout:
            raise ValueError('Cannot disable the shell_tool feature on this Codex build.')
        login = subprocess.run([cli, 'login', 'status'], text=True, capture_output=True, timeout=30)
        if login.returncode:
            raise RuntimeError('Codex CLI is not authenticated. No credentials were printed or changed.')
        version = subprocess.run([cli, '--version'], text=True, capture_output=True, timeout=30, check=True)
        return {'version': version.stdout.strip(), 'authenticated': True, 'shell_tool_disable_supported': True,
                'model': config['judge']['model'], 'model_availability': 'not called; live availability remains unverified'}
    def public_prompts():
        # Public metadata read only: no AppWorld instance, API action, solution or evaluator.
        code = """
import json, os, sys
from pathlib import Path
sys.path.insert(0, %r)
from common import ROOT, ids, load_config, text_to_messages
from appworld import update_root
from appworld.task import Task
from appworld.apps.lib.models.db import CachedDBHandler
from jinja2 import Template, StrictUndefined
config=load_config()
update_root(str(ROOT/'runtime/appworld'))
tasks=ids(ROOT/config['training']['train_tasks'])+ids(ROOT/config['evaluation']['tasks'])
counts=[]
previews=[]
for task_id in tasks:
 task=Task.load(task_id=task_id,load_ground_truth=False)
 try:
  prompt=Template((ROOT/config['agent']['prompt']).read_text().lstrip(),undefined=StrictUndefined).render(instruction=task.instruction,main_user=task.supervisor,app_descriptions=json.dumps([{'name':k,'description':v} for k,v in task.app_descriptions.items()],indent=1))
  messages=text_to_messages(prompt)
  assert messages[-1]['role']=='user' and task.instruction in messages[-1]['content']
  counts.append(len(messages))
  previews.append({'task_id':task_id,'messages':messages})
 finally:
  task.close()
  CachedDBHandler.reset()
(ROOT/'cache').mkdir(exist_ok=True)
(ROOT/'cache/public_prompt_preview.json').write_text(json.dumps(previews))
print(json.dumps({'public_tasks_rendered':len(tasks),'message_counts':sorted(set(counts)),'task_executions':0,'ground_truth_loaded':False}))
""" % str(ROOT)
        return probe(config['paths']['appworld_python'], code)
    def tokenizer():
        code = """import json
from pathlib import Path
from transformers import AutoTokenizer
t=AutoTokenizer.from_pretrained(%r,local_files_only=True)
previews=json.loads(Path(%r).read_text())
lengths=[len(t.apply_chat_template(p['messages'],add_generation_prompt=True,enable_thinking=False,tokenize=True)) for p in previews]
assert lengths and max(lengths) < %r - %r, 'Initial public prompt leaves insufficient response budget'
print(json.dumps({'tokenizer_class':type(t).__name__,'public_prompts_checked':len(lengths),'min_prompt_tokens':min(lengths),'max_prompt_tokens':max(lengths),'vocab_size':len(t),'enable_thinking':False,'model_weights_loaded':False}))
""" % (config['paths']['base_model'], str(ROOT / 'cache/public_prompt_preview.json'), config['agent']['max_model_len'], config['agent']['max_new_tokens'])
        return probe(config['paths']['training_python'], code)
    check('paths and raw model files', paths)
    check('frozen rules, prompt, official splits and schema', assets)
    check('isolated AppWorld runtime and copied evaluator cache', runtime)
    check('AppWorld imports', appworld)
    check('PyTorch / Transformers / PEFT imports', training)
    check('vLLM exact-token API protocol', vllm)
    check('Codex CLI flags and existing login (no request)', codex)
    check('public task prompt rendering, configured train + complete dev', public_prompts)
    check('local Qwen tokenizer only', tokenizer)
    free = shutil.disk_usage(ROOT).free
    checks.append({'name': 'disk space', 'status': 'PASS' if free >= 20 * 1024**3 else 'FAIL', 'detail': {'free_GiB': round(free / 1024**3, 2), 'minimum_GiB': 20}})
    gpu = subprocess.run(['nvidia-smi', '--query-gpu=index,name,memory.total,memory.free', '--format=csv,noheader'], text=True, capture_output=True)
    checks.append({'name': 'GPU inventory only', 'status': 'PASS' if gpu.returncode == 0 else 'FAIL', 'detail': gpu.stdout.strip() or gpu.stderr.strip()})
    from resources import inventory
    gpu_rows = inventory()
    resources_available = all(any(row['index'] == config[role]['gpu'] and row['free_mib'] >= config[role]['minimum_free_gpu_gib'] * 1024 for row in gpu_rows) for role in ('server', 'training'))
    failed = [c['name'] for c in checks if c['status'] == 'FAIL']
    report = {'time_utc': datetime.now(timezone.utc).isoformat(), 'status': 'OFFLINE_READY' if not failed else 'NEEDS_FIX',
              'fingerprint': input_fingerprint(config), 'checks': checks, 'failed': failed,
              'gpu_resources_available_now': resources_available, 'gpu_inventory': gpu_rows,
              'not_executed': ['Qwen model load / generation', 'Codex model request', 'AppWorld task execution / official dev evaluation', 'GRPO update'],
              'live_checks_after_start': ['GPU memory and first generation', 'first structured judge response', 'HF/vLLM sampled logprob consistency', 'first optimizer update and adapter reload']}
    atomic_json(ROOT / 'readiness.json', report)
    if failed:
        raise SystemExit('Preflight failed: ' + ', '.join(failed))
    print('OFFLINE_READY; no experiment was started.')

if __name__ == '__main__':
    from common import load_config
    run(load_config())
