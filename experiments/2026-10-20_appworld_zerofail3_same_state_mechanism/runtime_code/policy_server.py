"""Owned vLLM process and exact-token sampling. Nothing starts on import."""
from __future__ import annotations
import contextlib
import json
import os
import signal
import socket
import subprocess
import time
import urllib.request
from pathlib import Path
from common import ROOT, validate_tokens

def request(config, route, payload=None):
    url = f"http://{config['server']['host']}:{config['server']['port']}{route}"
    body = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=body, headers={'Content-Type': 'application/json'})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(req, timeout=config['server']['request_timeout_seconds']) as response:
        return json.load(response)

def model_name(config, checkpoint):
    return config['server']['adapter_name' if checkpoint else 'model_name']

def server_command(config, checkpoint=None):
    c = config['server']
    assert c['gpu'] == 'GPU-35170b76-56ce-240a-19c0-0c092a3e8501'
    assert os.environ.get('CUDA_VISIBLE_DEVICES') == c['gpu']
    command = [config['paths']['vllm_python'], '-m', 'vllm.entrypoints.openai.api_server',
               '--model', config['paths']['base_model'], '--served-model-name', c['model_name'],
               '--host', c['host'], '--port', str(c['port']), '--dtype', 'bfloat16',
               '--max-model-len', str(config['agent']['max_model_len']),
               '--max-num-seqs', str(c['max_num_seqs']), '--gpu-memory-utilization', str(c['gpu_memory_utilization']),
               '--generation-config', 'vllm', '--disable-log-requests', '--enforce-eager']
    if checkpoint:
        command += ['--enable-lora', '--max-lora-rank', str(config['training']['lora']['r']),
                    '--lora-modules', f"{c['adapter_name']}={Path(checkpoint).resolve()}"]
    return command

@contextlib.contextmanager
def owned_server(config, log_dir, checkpoint=None):
    from resources import require_free_gpu
    require_free_gpu(config['server']['gpu'], config['server']['minimum_free_gpu_gib'])
    with socket.socket() as sock:
        if sock.connect_ex((config['server']['host'], config['server']['port'])) == 0:
            raise RuntimeError('Experiment port is occupied; refusing an unverified policy.')
    log_dir = Path(log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, CUDA_VISIBLE_DEVICES=config['server']['gpu'], HF_HUB_OFFLINE='1',
               TRANSFORMERS_OFFLINE='1', VLLM_NO_USAGE_STATS='1', DO_NOT_TRACK='1')
    env['JOINT_VLLM_GPU1_COMPAT']='1'
    env['PYTHONPATH']=str(ROOT/'runtime_code/vllm_uuid_compat')+os.pathsep+env.get('PYTHONPATH','')
    process = None
    with (log_dir / 'vllm.log').open('a') as log:
        try:
            process = subprocess.Popen(server_command(config, checkpoint), env=env, stdout=log,
                                       stderr=subprocess.STDOUT, start_new_session=True, cwd=ROOT)
            deadline = time.monotonic() + config['server']['startup_timeout_seconds']
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    raise RuntimeError(f'vLLM exited with {process.returncode}; see {log_dir / "vllm.log"}')
                try:
                    available = request(config, '/v1/models')
                    if model_name(config, checkpoint) in {item['id'] for item in available['data']}:
                        break
                except (OSError, ValueError):
                    pass
                time.sleep(2)
            else:
                raise TimeoutError('vLLM startup timed out; check its log.')
            yield model_name(config, checkpoint)
        finally:
            if process is not None and process.poll() is None:
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.wait(timeout=30)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait(timeout=30)

def sample_step(config, model, messages, seed, evaluation=False):
    started = time.monotonic()
    tokenized = request(config, '/tokenize', {
        'model': model, 'messages': messages, 'add_generation_prompt': True,
        'add_special_tokens': False, 'chat_template_kwargs': {'enable_thinking': False}})
    prompt_ids = tokenized['tokens']
    remaining = config['agent']['max_model_len'] - len(prompt_ids)
    if remaining <= 0:
        return None
    response = request(config, '/v1/completions', {
        'model': model, 'prompt': prompt_ids, 'max_tokens': min(config['agent']['max_new_tokens'], remaining),
        'temperature': config['evaluation']['temperature'] if evaluation else config['sampling']['temperature'],
        'top_p': 1.0, 'top_k': -1, 'repetition_penalty': 1.0, 'seed': seed,
        'logprobs': 1, 'return_token_ids': True, 'return_tokens_as_token_ids': True,
        'add_special_tokens': False, 'skip_special_tokens': True, 'ignore_eos': False})
    choice = response['choices'][0]
    if choice.get('prompt_token_ids') is not None and choice['prompt_token_ids'] != prompt_ids:
        raise ValueError('Server changed the supplied prompt tokens.')
    response_ids = choice['token_ids']
    logprobs = choice['logprobs']['token_logprobs']
    validate_tokens(prompt_ids, response_ids, logprobs)
    if choice['logprobs']['tokens'] != [f'token_id:{t}' for t in response_ids]:
        raise ValueError('vLLM token IDs and logprob tokens disagree.')
    return {'text': choice['text'], 'prompt_ids': prompt_ids, 'response_ids': response_ids,
            'old_logprobs': logprobs, 'finish_reason': choice['finish_reason'],
            'stop_reason': choice.get('stop_reason'), 'usage': response.get('usage', {}),
            'elapsed_seconds': time.monotonic() - started}
