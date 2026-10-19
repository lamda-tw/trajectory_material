"""Load the disposable probe adapter on GPU1 and validate exact-token serving."""
import argparse
import os
import sys
from experiment_utils import R, read, dump, sha, jsonl, now
sys.path.insert(0, str(R / 'runtime_code'))
from policy_server import owned_server, sample_step


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    assert args.execute
    cfg = read(R / 'config/evaluation.json')
    assert os.environ.get('CUDA_VISIBLE_DEVICES') == cfg['server']['gpu']
    adapter = R / 'probe/drop_r1/seed_20261015/epoch_01_adapter'
    assert read(adapter.parent / 'COMPLETE.json')['probe']
    row = jsonl(R / 'data/drop_r1/seed_20261015/selection.jsonl')[0]
    trajectory = read(row['source'])
    with owned_server(cfg, R / 'checks/serving', adapter) as model:
        response = sample_step(cfg, model, trajectory['initial_messages'], 100, evaluation=True)
        assert response and response['prompt_ids'] == trajectory['steps'][0]['prompt_ids']
    dump(R / 'checks/serving_preflight.json', {'passed': True, 'at_beijing': now(),
         'gpu_uuid': cfg['server']['gpu'], 'adapter_sha256': sha(adapter / 'adapter_model.safetensors'),
         'evaluation_config_sha256': sha(R / 'config/evaluation.json'),
         'prompt_tokens': len(response['prompt_ids']), 'response_tokens': len(response['response_ids']),
         'exact_prompt_ids_verified': True, 'evaluation_temperature': 0.0,
         'scope': 'Disposable probe only; no DEV task executed; no sample filtering.'})
    print('PASS: GPU1 vLLM, LoRA loading and exact-token generation.', flush=True)


if __name__ == '__main__':
    main()
