"""Keep epoch checkpoints and the latest two; operate only inside this run."""
from b_common import *


def validate_committed(checkpoint, allow_pruned=False):
    checkpoint = Path(checkpoint)
    done = read(checkpoint / 'COMPLETE.json')
    receipt_path = checkpoint / 'RETENTION.json'
    receipt = read(receipt_path) if receipt_path.exists() else None
    if receipt:
        assert receipt['complete_sha256'] == file_sha(checkpoint / 'COMPLETE.json')
    for name, expected in done['files'].items():
        path = checkpoint / name
        if path.exists():
            assert file_sha(path) == expected, path
        else:
            assert allow_pruned and receipt and name in receipt['removed_files'], path
            assert receipt['removed_files'][name]['sha256'] == expected, path
    return done


def apply_retention(latest):
    authorize('training_allowed')
    policy = read(B / 'config/retention.json')
    assert policy['user_authorized_model_retention']
    validate_committed(batch_dir('sft', latest) / 'checkpoint')
    assert read(batch_dir('sft', latest) / 'acceptance.json')['passed']
    keep = set(policy['keep_full_batches']) | set(range(max(1, latest - policy['keep_latest_batches'] + 1), latest + 1))
    removed = []; freed = 0
    for number in range(1, latest + 1):
        if number in keep:
            continue
        checkpoint = batch_dir('sft', number) / 'checkpoint'
        assert checkpoint.parent.parent == run_dir('sft') and not checkpoint.is_symlink()
        path = checkpoint / 'RETENTION.json'
        if path.exists() and read(path)['status'] == 'complete':
            continue
        done = validate_committed(checkpoint, allow_pruned=True)
        receipt = read(path) if path.exists() else {'created_at': now(), 'complete_sha256': file_sha(checkpoint / 'COMPLETE.json'),
            'reason': 'Keep necessary epoch models and the latest two; retain all data and metrics.', 'removed_files': {}}
        for name in policy['eligible_model_files']:
            target = checkpoint / name
            if not target.exists():
                continue
            assert not target.is_symlink() and target.resolve().is_relative_to(checkpoint.resolve())
            assert name in done['files'] and file_sha(target) == done['files'][name]
            size = target.stat().st_size
            receipt['removed_files'][name] = {'sha256': done['files'][name], 'bytes': size}
            receipt['status'] = 'planned'; write_json(path, receipt)
            target.unlink(); freed += size
        receipt.update(status='complete', completed_at=now()); write_json(path, receipt)
        validate_committed(checkpoint, allow_pruned=True); removed.append(number)
    event = {'at': now(), 'latest_accepted_batch': latest, 'pruned_batches': removed, 'bytes_freed': freed, 'protected_batches': sorted(keep)}
    with (B / 'analysis/retention_events.jsonl').open('a') as handle:
        handle.write(__import__('json').dumps(event) + '\n')
    return event
