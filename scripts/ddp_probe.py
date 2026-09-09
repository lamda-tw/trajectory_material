#!/usr/bin/env python3
"""Fail-fast two-GPU NCCL communication probe."""

from __future__ import annotations

import json
import os

import torch
import torch.distributed as dist


def main() -> None:
    rank = int(os.environ["RANK"])
    local_rank = int(os.environ["LOCAL_RANK"])
    world_size = int(os.environ["WORLD_SIZE"])
    if world_size != 2:
        raise RuntimeError(f"expected exactly two processes, got {world_size}")
    torch.cuda.set_device(local_rank)
    dist.init_process_group("nccl")
    value = torch.tensor(float(rank + 1), device=f"cuda:{local_rank}")
    dist.all_reduce(value, op=dist.ReduceOp.SUM)
    local = {
        "rank": rank,
        "local_rank": local_rank,
        "device": torch.cuda.get_device_name(local_rank),
        "capability": list(torch.cuda.get_device_capability(local_rank)),
        "all_reduce_sum": value.item(),
    }
    gathered: list[object] = [None] * world_size
    dist.all_gather_object(gathered, local)
    if rank == 0:
        expected = world_size * (world_size + 1) / 2
        if value.item() != expected:
            raise RuntimeError(f"all-reduce mismatch: {value.item()} != {expected}")
        print(json.dumps({"status": "PASS", "world_size": world_size, "ranks": gathered}, indent=2))
    dist.destroy_process_group()


if __name__ == "__main__":
    main()
