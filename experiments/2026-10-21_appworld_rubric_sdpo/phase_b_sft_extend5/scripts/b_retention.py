"""Prune only explicitly authorized intermediate model blobs, after verified commits."""
from b_common import *


def validate_committed(checkpoint, allow_pruned=False):
    checkpoint=Path(checkpoint);done=read(checkpoint/'COMPLETE.json')
    receipt=read(checkpoint/'RETENTION.json') if (checkpoint/'RETENTION.json').exists() else None
    if receipt:
        assert receipt['complete_sha256']==file_sha(checkpoint/'COMPLETE.json')
    for name,expected in done['files'].items():
        path=checkpoint/name
        if path.exists():
            assert file_sha(path)==expected,(path,'checksum mismatch')
        else:
            assert allow_pruned and receipt and name in receipt['removed_files'],path
            assert receipt['removed_files'][name]['sha256']==expected,path
    return done


def prune_checkpoint(checkpoint):
    checkpoint=Path(checkpoint);policy=read(B/'config/retention.json')
    assert policy['user_authorized_model_retention']
    allowed_roots=[SOURCE/'runs/sft',run_dir('sft')]
    assert checkpoint.parent.parent in allowed_roots and checkpoint.name=='checkpoint'
    assert not checkpoint.is_symlink()
    done=validate_committed(checkpoint,allow_pruned=True);number=done['batch']
    protected=policy['source_keep_full_batches'] if checkpoint.parent.parent==allowed_roots[0] else policy['continuation_keep_full_batches']
    assert number not in protected,'Attempt to remove a protected epoch/source model'
    receipt_path=checkpoint/'RETENTION.json'
    receipt=read(receipt_path) if receipt_path.exists() else {'created_at':now(),'complete_sha256':file_sha(checkpoint/'COMPLETE.json'),
        'reason':'User requested necessary models only; preserve all trajectories, judgments and metrics.','removed_files':{},'status':'planned'}
    reclaimed=0
    for name in policy['eligible_model_files']:
        path=checkpoint/name
        if not path.exists():continue
        assert not path.is_symlink() and path.resolve().is_relative_to(checkpoint.resolve())
        assert name in done['files'] and file_sha(path)==done['files'][name]
        size=path.stat().st_size
        receipt['removed_files'][name]={'sha256':done['files'][name],'bytes':size}
        receipt['status']='planned';write_json(receipt_path,receipt)
        path.unlink();reclaimed+=size
    receipt.update(status='complete',completed_at=now());write_json(receipt_path,receipt)
    validate_committed(checkpoint,allow_pruned=True)
    return reclaimed


def apply_retention(latest):
    authorize('training_allowed')
    assert latest>=FIRST_BATCH
    # Never prune anything unless a complete, accepted continuation checkpoint exists.
    validate_committed(batch_dir('sft',latest)/'checkpoint',allow_pruned=False)
    assert read(batch_dir('sft',latest)/'acceptance.json')['passed']
    policy=read(B/'config/retention.json');saved=0;pruned=[]
    marker=B/'analysis/source_retention_complete.json'
    if not marker.exists():
        for number in range(1,37):
            if number in policy['source_keep_full_batches']:continue
            p=SOURCE/'runs/sft'/f'batch_{number:03d}/checkpoint'
            saved+=prune_checkpoint(p);pruned.append(str(p))
        write_json(marker,{'completed_at':now(),'source_keep_full_batches':policy['source_keep_full_batches'],'bytes_freed_this_pass':saved})
    protected=set(policy['continuation_keep_full_batches'])|set(range(max(FIRST_BATCH,latest-policy['keep_latest_batches']+1),latest+1))
    for number in range(FIRST_BATCH,latest+1):
        if number in protected:continue
        p=batch_dir('sft',number)/'checkpoint'
        if (p/'RETENTION.json').exists() and read(p/'RETENTION.json')['status']=='complete':continue
        saved+=prune_checkpoint(p);pruned.append(str(p))
    event={'at':now(),'latest_accepted_batch':latest,'bytes_freed':saved,'checkpoints_pruned':pruned,'kept_continuation_batches':sorted(protected)}
    with (B/'analysis/retention_events.jsonl').open('a') as f:f.write(__import__('json').dumps(event)+'\n')
    return event
