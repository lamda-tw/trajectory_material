"""Unchanged action/parser protocol, experiment-local configuration and provenance."""
import os,re,math
from common import ROOT,read,sha,require
import hashlib,json

def load_config():return read(os.environ['JOINT_COLLECTION_CONFIG'])
def ids(path):return set(path.read_text().split())
def check_training_ids(task_ids,cfg):require(set(task_ids)<=ids(ROOT/'config/train90.txt'),'Non-training task')
def collection_fingerprint(cfg):return hashlib.sha256(json.dumps(cfg,sort_keys=True).encode()).hexdigest()
def execution_provenance(cfg):return {'config_sha256':collection_fingerprint(cfg),'worker_sha256':sha(ROOT/'scripts/rollout_worker.py'),'gpu_policy':read(ROOT/'config/resource_policy.json')}
def text_to_messages(text):
    parts=re.split(r'(?:^|\n)(USER|ASSISTANT|SYSTEM):\n',text.lstrip())
    require(not parts[0].strip() and len(parts)>=3,'Invalid prompt roles')
    return [{'role':parts[i].lower(),'content':parts[i+1].strip()} for i in range(1,len(parts),2)]
def parse_code(text):
    match=re.search(r'```python\n(.*?)```',text,flags=re.DOTALL)
    if match:return match.group(1).strip(),text
    match=re.search(r'```python\n(.*)',text,flags=re.DOTALL)
    if match:return match.group(1).strip(),text.rstrip()+'\n```'
    return '',text

def validate_tokens(prompt_ids,response_ids,old_logprobs):
    require(prompt_ids and response_ids and len(response_ids)==len(old_logprobs),'Missing sampled IDs/probabilities')
    require(all(type(x) is int and x>=0 for x in prompt_ids+response_ids),'Invalid token ID')
    require(all(isinstance(x,(int,float)) and math.isfinite(x) and x<=1e-5 for x in old_logprobs),'Invalid log-probability')
