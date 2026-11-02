"""One tool-disabled Codex review per completed trajectory, all step labels/all F feedback."""
from b_common import R, B, read, write_json, frozen_json, file_sha, digest, now, CPU, authorize
from b_dataset import public_payload, validate_result
from a_judge_audit import audit_events
from judge_protocol import command
from score_sources import repair_prompt
from b_judge_recovery import JudgeTransportUnavailable, retryable_request, run_request
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import jsonschema
import subprocess
import time


def preserve_labels(before, after):
    valid = {}
    if isinstance(before, dict):
        for row in before.get('steps', []):
            if isinstance(row, list) and len(row) == 3 and isinstance(row[1], str):
                value = ''.join(row[1].split())
                if len(value) == 8 and set(value) <= set('PFUN'):
                    valid[row[0]] = value
    current = {row[0]: row[1] for row in after['steps']}
    assert all(current.get(i) == v for i, v in valid.items()), 'Format repair changed substantive labels'


def recover_saved_response(payload, dest, meta):
    # Recover only audited, valid prior responses; never re-score a completed judgment.
    for folder in sorted(dest.glob('attempt_*')):
        try:
            audit = audit_events(folder / 'events.jsonl')
            result = read(folder / 'response.json'); validate_result(payload, result)
            for earlier in sorted(dest.glob('attempt_*')):
                if earlier.name >= folder.name: break
                try: previous = read(earlier / 'response.json')
                except (OSError, ValueError): continue
                preserve_labels(previous, result)
        except (OSError, ValueError, AssertionError, KeyError, TypeError, jsonschema.ValidationError):
            continue
        frozen_json(dest / 'judgement.json', result)
        meta.update(status='valid', recovered_attempt=folder.name, audit=audit, completed_at=now(),
                    recovered_from_status=meta.get('status'), recovery_reason='audited_saved_response')
        write_json(dest / 'metadata.json', meta)
        return {'id': payload['trajectory_id'], 'recovered': True}
    return None


def score(payload_path, dest, source_sha):
    authorize('external_judging')
    cfg = read(B / 'config/judge.json')
    payload = read(payload_path)
    template = (R / 'config/scoring_prompt_v7_feedback_en.txt').read_text()
    prompt = template.replace('{{TRAJECTORY_JSON}}', json.dumps(payload, ensure_ascii=False, indent=2))
    identity = {'source_sha256': source_sha, 'payload_sha256': file_sha(payload_path), 'prompt_sha256': digest(prompt),
                'template_sha256': file_sha(R / 'config/scoring_prompt_v7_feedback_en.txt'), 'config_sha256': digest(cfg)}
    dest.mkdir(parents=True, exist_ok=True)
    frozen_json(dest / 'identity.json', identity)
    frozen_json(dest / 'input.json', payload)
    if (dest / 'judgement.json').exists():
        validate_result(payload, read(dest / 'judgement.json'))
        return {'id': payload['trajectory_id'], 'cached': True}
    meta_path = dest / 'metadata.json'
    meta = read(meta_path) if meta_path.exists() else {'identity': identity, 'attempts': [], 'started_at': now()}
    assert meta['identity'] == identity
    recovered = recover_saved_response(payload, dest, meta)
    if recovered: return recovered
    if meta.get('status') == 'failed':
        if not retryable_request(dest, meta):
            raise RuntimeError(f'Existing failed judge request needs diagnosis: {dest}')
        meta.setdefault('network_retry_rounds', []).append({'at': now(), 'prior_attempts': len(meta['attempts'])})
        meta.update(status='retry_pending', transport_round_start=len(meta['attempts']))
        write_json(meta_path, meta)
    cwd = dest / 'empty_cwd'; cwd.mkdir(exist_ok=True)
    text = prompt; kind = 'initial'; repair_count = 0; transport_count = 0; originals = []
    for index, attempt in enumerate(meta['attempts']):
        transport_count += index >= meta.get('transport_round_start', 0) and attempt.get('failure_type') == 'transport'
        repair_count += attempt['kind'] == 'format_repair'
    if meta['attempts']:
        last = meta['attempts'][-1]
        prior = dest / last['directory'] / 'response.json'
        text = (dest / last['directory'] / 'request.txt').read_text()
        for previous_attempt in meta['attempts']:
            if previous_attempt.get('failure_type') == 'format':
                try: originals.append(read(dest / previous_attempt['directory'] / 'response.json'))
                except (OSError, ValueError): pass
        if last.get('failure_type') == 'format':
            if repair_count >= cfg['max_format_repairs']: raise RuntimeError('Format repair exhausted')
            raw = prior.read_text() if prior.exists() else 'No final JSON returned.'
            text = repair_prompt(prompt, raw, last['error']); kind = 'format_repair'
            try: originals.append(json.loads(raw))
            except ValueError: pass
        else:
            kind = 'transport_retry'
    number = max([int(f.name.split('_')[-1]) for f in dest.glob('attempt_*')] + [0])
    while transport_count < cfg['max_transport_attempts']:
        authorize('external_judging')
        recovered = recover_saved_response(payload, dest, meta)
        if recovered: return recovered
        number += 1; folder = dest / f'attempt_{number:02d}'; folder.mkdir()
        (folder / 'request.txt').write_text(text)
        output = folder / 'response.json'; cmd = command(cfg, cwd, output)
        write_json(folder / 'command.json', cmd)
        item = {'directory': folder.name, 'kind': kind, 'started_at': now()}
        if kind == 'format_repair': repair_count += 1
        started = time.monotonic()
        try:
            with (folder / 'events.jsonl').open('w') as out, (folder / 'stderr.log').open('w') as err:
                result = run_request(cmd, input=text, stdout=out, stderr=err, env=CPU, cwd=cwd, timeout=cfg['timeout_seconds'])
            if result.returncode: raise RuntimeError(f'Codex exit {result.returncode}')
            item['audit'] = audit_events(folder / 'events.jsonl')
            try:
                result = read(output); validate_result(payload, result)
            except (OSError, ValueError, AssertionError, KeyError, TypeError, jsonschema.ValidationError) as error:
                item.update(status='invalid', failure_type='format', error=str(error)[:1800])
            else:
                for previous in originals: preserve_labels(previous, result)
                item.update(status='valid', seconds=time.monotonic()-started)
                meta['attempts'].append(item); meta.update(status='valid', completed_at=now())
                write_json(meta_path, meta); frozen_json(dest / 'judgement.json', result)
                return {'id': payload['trajectory_id'], 'attempts': len(meta['attempts'])}
        except AssertionError as error:
            item.update(status='invalid', failure_type='protocol', error=str(error))
        except (OSError, RuntimeError, subprocess.TimeoutExpired) as error:
            item.update(status='invalid', failure_type='transport', error=str(error))
        item['seconds'] = time.monotonic()-started
        meta['attempts'].append(item); meta['status'] = 'retry_pending'; write_json(meta_path, meta)
        if item['failure_type'] == 'protocol': break
        if item['failure_type'] == 'format':
            if repair_count >= cfg['max_format_repairs']: break
            raw = output.read_text() if output.exists() else 'No final JSON returned.'
            try: originals.append(json.loads(raw))
            except ValueError: pass
            text = repair_prompt(prompt, raw, item['error']); kind = 'format_repair'
        else:
            transport_count += 1
            if transport_count >= cfg['max_transport_attempts']: break
            time.sleep(cfg['transport_retry_delays_seconds'][min(transport_count-1, 1)])
            kind = 'transport_retry'
    recovered = recover_saved_response(payload, dest, meta)
    if recovered: return recovered
    meta.update(status='failed', completed_at=now(), retryable_network=retryable_request(dest, meta))
    write_json(meta_path, meta)
    if meta['retryable_network']:
        raise JudgeTransportUnavailable(f'Network unavailable; keep data and retry after cooldown: {dest}')
    raise RuntimeError(f'Judge failed; batch will not update: {dest}')


def judge_batch(folder):
    authorize('external_judging')
    manifest = read(folder / 'collection.json')
    jobs = []
    for item in manifest['trajectories']:
        path = folder / item['path']; assert file_sha(path) == item['sha256']
        payload, audit = public_payload(read(path), item['id'])
        dest = folder / 'judge_inputs' / (item['id'] + '.json')
        frozen_json(dest, payload); frozen_json(dest.with_suffix('.redaction.json'), audit)
        jobs.append((dest, folder / 'judging' / item['id'], item['sha256']))
    results = []
    with ThreadPoolExecutor(max_workers=read(B / 'config/judge.json')['max_workers']) as pool:
        for future in as_completed([pool.submit(score, *args) for args in jobs]):
            results.append(future.result())
            write_json(folder / 'judging_summary.json', {'requested': len(jobs), 'completed': len(results), 'results': results})
    return results
