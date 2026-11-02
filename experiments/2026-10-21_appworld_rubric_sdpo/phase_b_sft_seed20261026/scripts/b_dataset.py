"""Whole-trajectory scoring inputs and exact response-only training examples."""
from b_common import B, R, read, write_json, frozen_json, digest, file_sha, config
from prepare_sources import sanitize, strings
from prepare_input_v3 import prepare
from analyze_sources import render_message
from validate_v7_feedback import validate, feedback_text
import collections
import jsonschema


def validate_result(payload, result):
    jsonschema.Draft202012Validator(read(R / 'config/output_schema_v7_feedback.json')).validate(result)
    validate(payload, result)


def public_payload(trajectory, trajectory_id):
    clean, audit, secrets = sanitize(trajectory, trajectory['job']['task_id'])
    payload = prepare(clean, trajectory_id)
    # Omit feedback_step_ids: the unchanged v7-feedback template requests ALL F steps.
    assert 'feedback_step_ids' not in payload
    assert not any(secret in text for text in strings(payload) for secret in secrets)
    return payload, audit


def route(labels, feedback, feedback_tokens, student_length, teacher_length, cfg, arm):
    if student_length > cfg['agent']['max_model_len']:
        return 'mask', 'student_context_overflow'
    if 'F' not in labels:
        if arm == 'sdpo':
            return 'mask', 'zero_FAIL_excluded_from_SDPO_control'
        return ('sft', '') if labels.count('P') >= 3 else ('mask', 'zero_fail_P_below_3')
    if arm == 'sft':
        return 'mask', 'FAIL_excluded_from_SFT_control'
    if not feedback or not feedback['usable']:
        return 'mask', 'feedback_unusable'
    if feedback_tokens > cfg['training']['feedback_max_tokens']:
        return 'mask', 'feedback_too_long'
    if teacher_length > cfg['training']['teacher_max_length']:
        return 'mask', 'teacher_context_overflow'
    return 'sdpo', ''


def compile_trajectory(trajectory, payload, judged, tokenizer, cfg, arm):
    validate_result(payload, judged)
    labels = {i: value for i, value, _ in judged['steps']}
    feedbacks = {f['step_id']: f for f in judged['feedback']}
    messages = [dict(m) for m in trajectory['initial_messages']]
    examples = []
    for step in trajectory['steps']:
        sid = step['step']
        prompt = tokenizer.apply_chat_template(messages, tools=None, tokenize=True, add_generation_prompt=True, enable_thinking=False)
        assert prompt == step['prompt_ids'], f'Historical prompt mismatch at step {sid}'
        response = step['response_ids']
        assert response and len(response) == len(step['old_logprobs'])
        f = feedbacks.get(sid)
        text = feedback_text(f) if f and f['usable'] else ''
        feedback_tokens = len(tokenizer.encode(text, add_special_tokens=False))
        teacher = None
        if f and f['usable']:
            message = render_message('C2_feedback', f['failed_rules'], text, '')
            assert '<original_attempt_json_string>' not in message
            teacher = tokenizer.apply_chat_template(messages + [{'role': 'user', 'content': message}], tools=None,
                tokenize=True, add_generation_prompt=True, enable_thinking=False)
        branch, why = route(labels[sid], f, feedback_tokens, len(prompt) + len(response),
                            len(teacher or []) + len(response), cfg, arm)
        examples.append({'trajectory_id': payload['trajectory_id'], 'task_id': trajectory['job']['task_id'],
                         'step': sid, 'labels': labels[sid], 'branch': branch, 'mask_reason': why,
                         'prompt_ids': prompt, 'response_ids': response, 'teacher_prompt_ids': teacher if branch == 'sdpo' else None,
                         'feedback_tokens': feedback_tokens, 'uses_later_evidence': bool(f and f['uses_later_evidence']),
                         'response_finish_reason': step['finish_reason']})
        messages.append({'role': 'assistant', 'content': step['history_assistant_text'] + '\n\n'})
        if step['code']:
            messages.append({'role': 'user', 'content': 'Output:\n```\n' + step['observation'].rstrip() + '\n```\n\n'})
    return examples


def compile_batch(folder, arm):
    from transformers import AutoTokenizer
    cfg = config()
    tokenizer = AutoTokenizer.from_pretrained(cfg['paths']['base_model'], local_files_only=True)
    manifest = read(folder / 'collection.json')
    assert len(manifest['trajectories']) == cfg['training']['tasks_per_batch']
    rows = []
    inputs = []
    for item in manifest['trajectories']:
        source = folder / item['path']; assert file_sha(source) == item['sha256']
        trajectory = read(source); assert trajectory['job']['policy_identity'] == manifest['policy_identity']
        public = folder / 'judge_inputs' / (item['id'] + '.json')
        judgment = folder / 'judging' / item['id'] / 'judgement.json'
        rows.extend(compile_trajectory(trajectory, read(public), read(judgment), tokenizer, cfg, arm))
        inputs.append({'source': item['path'], 'source_sha256': item['sha256'], 'public_sha256': file_sha(public), 'judgment_sha256': file_sha(judgment)})
    counts = collections.Counter(r['branch'] for r in rows)
    result = {'arm': arm, 'batch': manifest['batch'], 'policy_identity': manifest['policy_identity'], 'sources': inputs,
              'examples': rows, 'counts': dict(counts), 'mask_reasons': dict(collections.Counter(r['mask_reason'] for r in rows if r['branch'] == 'mask')),
              'teacher_condition': 'C2_feedback', 'loss_on_history_or_feedback': False}
    frozen_json(folder / 'dataset.json', result)
    return result
