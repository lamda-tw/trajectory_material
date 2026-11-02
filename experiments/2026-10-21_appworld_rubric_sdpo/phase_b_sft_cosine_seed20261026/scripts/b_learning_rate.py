"""Stateless schedule indexed by the persisted count of nonempty Adam updates."""
import math


def learning_rate(update, cfg):
    assert isinstance(update, int) and update >= 1
    peak = cfg['learning_rate']
    warmup = cfg['warmup_nonempty_updates']
    assert peak > 0 and warmup >= 1
    schedule = cfg.get('lr_schedule')
    if schedule is None:
        # Preserve the original function for baseline numerical regression checks.
        return peak * min(1.0, update / warmup)
    assert schedule['type'] == 'cosine_with_min_lr'
    assert schedule['advance_on'] == 'nonempty_optimizer_update' and not schedule['warm_restarts']
    total = schedule['total_nonempty_updates']
    floor = schedule['min_learning_rate']
    assert total > warmup and 0 < floor < peak
    if update <= warmup:
        return peak * min(1.0, update / warmup)
    fraction = min(1.0, (update - warmup) / (total - warmup))
    return floor + (peak - floor) * (1.0 + math.cos(math.pi * fraction)) / 2.0
