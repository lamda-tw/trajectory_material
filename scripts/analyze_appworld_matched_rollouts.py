#!/usr/bin/env python3
"""Read-only, matched-protocol rollout diagnostics for AppWorld evaluation."""
from __future__ import annotations
import ast
import collections
import hashlib
import json
import re
import warnings
from pathlib import Path

OUTPUT = 'simplified_react_code_agent/alibaba/qwen3-8b-with-reasoning/test_normal'


def read_json(path):
    return json.loads(Path(path).read_text())


def json_hash(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def failure_category(requirement):
    text = ' '.join(requirement.lower().split())
    if 'answers match' in text or ('answer' in text and 'match' in text): return '最终答案不匹配'
    if any(w in text for w in ('file_system','file path','file_paths','directory')): return '文件系统路径、目录或内容错误'
    if 'simple_note' in text or 'note' in text: return '笔记状态或内容错误'
    if 'venmo' in text or 'friend' in text: return 'Venmo 好友、交易或付款状态错误'
    if any(w in text for w in ('spotify','musicplayer','music player','song')): return 'Spotify 播放、队列或收藏状态错误'
    if any(w in text for w in ('gmail','email','mail')): return '邮件状态或内容错误'
    if 'todoist' in text or any(w in text for w in ('todo','project','task list','reminder')): return '待办或项目状态错误'
    if 'splitwise' in text or 'expense' in text: return 'Splitwise 或费用状态错误'
    if 'phone' in text or any(w in text for w in ('text message','voice message','alarm')): return '电话、消息或联系人状态错误'
    if any(w in text for w in ('transaction','payment','order','cart','shopping')): return '交易或购物状态错误'
    if any(w in text for w in ('model changes','changed_records','record')): return '数据库变更不符合要求'
    return '其他业务条件未满足'


def canonical_code(content):
    blocks = re.findall(r'```python\s+(.+?)(?:```|$)', content or '', re.S)
    if not blocks: return None
    code = '\n'.join(blocks).strip()
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('ignore', SyntaxWarning)
            return ast.dump(ast.parse(code), include_attributes=False)
    except (SyntaxError, ValueError): return code


def analyze(experiment, task_ids, individual, expected_model=None):
    experiment = Path(experiment)
    root = experiment / 'experiments/outputs' / OUTPUT / 'tasks'
    rows = {}
    totals = collections.Counter()
    category_tasks, error_type_tasks = collections.defaultdict(list), collections.defaultdict(list)
    api_endpoints = collections.Counter()
    parameter_mismatches = []
    for task_id in task_ids:
        task = root / task_id
        score = individual[task_id]
        counters = collections.Counter()
        code_counts = collections.Counter()
        errors, successful_prompt_tokens = [], []
        first_prompt_hash = None
        first_prompt_tokens = None
        fixed_request_hashes = set()
        with (task/'logs/lm_calls.jsonl').open() as handle:
            for line in handle:
                if not line.strip(): continue
                record = json.loads(line)
                request, response = record['input'], record['output']
                if first_prompt_hash is None:
                    first_prompt_hash = json_hash(request['messages'])
                    first_prompt_tokens = response.get('usage',{}).get('prompt_tokens')
                fixed_request_hashes.add(json_hash({k:v for k,v in request.items() if k not in ['messages','model','base_url','api_key']}))
                expected = {'temperature':0, 'seed':100, 'max_completion_tokens':3000,
                            'client_name':'openai', 'api_type':'chat_completions','tools':None}
                if expected_model is not None: expected['model'] = expected_model
                for key, value in expected.items():
                    if request.get(key) != value:
                        parameter_mismatches.append({'task_id':task_id,'field':key,'actual':request.get(key)})
                counters['lm_requests'] += 1
                choice = response['choices'][0]
                content = choice['message'].get('content')
                counters['content_null'] += content is None
                counters['content_empty'] += content == ''
                error = response.get('error')
                if error:
                    counters['error_responses'] += 1
                    match = re.search(r'request has (\d+) input tokens', str(error))
                    input_tokens = int(match.group(1)) if match else None
                    kind = ('input_exceeds_context' if input_tokens is not None and input_tokens > 32000
                            else 'input_plus_output_exceeds_context' if 'maximum context length' in str(error) else 'other')
                    counters[kind] += 1
                    errors.append({'kind':kind,'input_tokens':input_tokens,'empty_placeholder':content=='',
                                   'usage_tokens':response.get('usage',{}).get('total_tokens')})
                    continue
                counters['model_responses'] += 1
                counters['unexplained_empty_model_responses'] += not bool(content)
                counters['length_truncated_responses'] += choice.get('finish_reason') == 'length'
                normalized = canonical_code(content)
                counters['no_python_model_responses'] += normalized is None
                if normalized is not None: code_counts[normalized] += 1
                counters['completion_tokens'] += response.get('usage',{}).get('completion_tokens',0) or 0
                successful_prompt_tokens.append(response.get('usage',{}).get('prompt_tokens',0) or 0)
        assert first_prompt_hash is not None, task_id
        environment = (task/'logs/environment_io.md').read_text(errors='replace')
        exception_types = collections.Counter(re.findall(r'^\s*([\w.]*(?:Error|Exception)|StopIteration|StopAsyncIteration)(?::|$)', environment, re.M))
        for error_type in exception_types: error_type_tasks[error_type].append(task_id)
        app_names = set()
        with (task/'logs/api_calls.jsonl').open() as handle:
            for line in handle:
                if not line.strip(): continue
                record = json.loads(line)
                url = str(record.get('url',''))
                api_endpoints[url] += 1
                counters['api_calls'] += 1
                app = url.strip('/').split('/')[0]
                app_names.add(app)
                counters['api_docs_calls'] += app == 'api_docs'
                counters['completion_endpoint_calls'] += url.endswith(('/supervisor/complete_task','/supervisor/message'))
        usage = read_json(task/'misc/usage.json')['tokens']
        counters['input_tokens'] = sum(int(usage.get(k,0) or 0) for k in ['input_cache_miss','input_cache_hit'])
        counters['output_tokens'] = int(usage.get('output',0) or 0)
        counters['total_tokens'] = counters['input_tokens'] + counters['output_tokens']
        counters['repeated_identical_code_actions'] = sum(count-1 for count in code_counts.values())
        counters['max_same_code_occurrences'] = max(code_counts.values(),default=0)
        counters['complete_task_actions'] = environment.count('apis.supervisor.complete_task(')
        counters['no_code_observations'] = environment.count('No code available to execute')
        requirements = [item.get('requirement','') for item in score.get('failures',[])]
        categories = sorted({failure_category(requirement) for requirement in requirements})
        answer_failures = [item for item in score.get('failures',[]) if failure_category(item.get('requirement',''))=='最终答案不匹配']
        answer_failure_kind = ('not_given_marker' if any('<<not_given>>' in str(item.get('trace','')) for item in answer_failures)
                               else 'other_answer_mismatch' if answer_failures else None)
        for category in categories: category_tasks[category].append(task_id)
        context_error = any(e['kind']!='other' for e in errors)
        python_error = 'Execution failed. Traceback' in environment or 'Syntax error in line:' in environment
        signals = {'context_error':context_error,'python_error':python_error,
                   'max_50_requests':counters['lm_requests']>=50,
                   'no_complete_task_action':counters['complete_task_actions']==0,
                   'repeated_identical_code':counters['repeated_identical_code_actions']>0}
        if score['success']: terminal = '成功'
        elif context_error: terminal = '上下文请求被拒绝'
        elif counters['lm_requests']>=50: terminal = '达到50步上限'
        elif counters['complete_task_actions']>0: terminal = '出现提交动作但未满足官方条件'
        else: terminal = '无提交动作的其他终止'
        row={'task_id':task_id,'success':bool(score['success']),'difficulty':score['difficulty'],
             'passed_tests':len(score.get('passes',[])),'failed_tests':len(score.get('failures',[])),
             'num_tests':score['num_tests'],'answer_failure_kind':answer_failure_kind,'failure_categories':categories,'failure_requirements':requirements,
             'terminal_group':terminal,'signals':signals,'counts':dict(counters),'request_errors':errors,
             'python_exception_types':dict(exception_types),'apps_called':sorted(app_names),
             'max_successful_prompt_tokens':max(successful_prompt_tokens,default=0),
             'first_prompt_sha256':first_prompt_hash,'first_prompt_tokens':first_prompt_tokens,
             'fixed_request_parameter_hashes':sorted(fixed_request_hashes),
             'evidence_environment':str(task/'logs/environment_io.md'),
             'evidence_lm':str(task/'logs/lm_calls.jsonl')}
        rows[task_id]=row
        totals.update(counters)
    totals['max_same_code_occurrences'] = max((r['counts']['max_same_code_occurrences'] for r in rows.values()),default=0)
    def group(ids):
        selected=[rows[task_id] for task_id in ids]
        group_counts=sum((collections.Counter(r['counts']) for r in selected),collections.Counter())
        group_counts['max_same_code_occurrences']=max((r['counts']['max_same_code_occurrences'] for r in selected),default=0)
        return {'task_count':len(selected),'success_count':sum(r['success'] for r in selected),
                'signals':{k:sum(r['signals'][k] for r in selected) for k in ['context_error','python_error','max_50_requests','no_complete_task_action','repeated_identical_code']},
                'counts':dict(group_counts)}
    return {'experiment':str(experiment),'per_task':rows,'totals':dict(totals),
            'all_tasks':group(task_ids),'failed_tasks':group([t for t in task_ids if not rows[t]['success']]),
            'successful_tasks':group([t for t in task_ids if rows[t]['success']]),
            'terminal_groups':dict(collections.Counter(r['terminal_group'] for r in rows.values())),
            'answer_failure_kinds':dict(collections.Counter(r['answer_failure_kind'] for r in rows.values() if r['answer_failure_kind'])),
            'failure_categories':{k:{'task_count':len(v),'task_ids':sorted(v)} for k,v in sorted(category_tasks.items())},
            'exception_types':{k:{'task_count':len(v),'task_ids':sorted(v)} for k,v in sorted(error_type_tasks.items())},
            'api_endpoint_counts':dict(api_endpoints),'request_parameter_mismatches':parameter_mismatches,
            'notes':['Failure categories match the historical LoRA report rules.','Terminal groups use priority: context, 50-step limit, submission action, other.','An API log records an attempted call, not proof it succeeded.','Repeated identical code is an observable signal, not necessarily an unproductive loop.']}
