#!/usr/bin/env python3
"""Completion-only full-parameter SFT for Qwen3-8B with two-GPU FSDP."""

from __future__ import annotations

import argparse
import gc
import json
import math
import os
import random
import shutil
import socket
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import partial
from pathlib import Path
from typing import Any

import torch
import torch.distributed as dist
from torch.distributed.fsdp import (
    BackwardPrefetch,
    FullStateDictConfig,
    FullyShardedDataParallel as FSDP,
    MixedPrecision,
    ShardingStrategy,
    StateDictType,
)
from torch.distributed.fsdp.wrap import transformer_auto_wrap_policy
from torch.utils.data import DataLoader, Dataset, DistributedSampler
from transformers import AutoModelForCausalLM, AutoTokenizer
from transformers.models.qwen3.modeling_qwen3 import Qwen3DecoderLayer


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))
    if not rows:
        raise ValueError(f"empty dataset: {path}")
    return rows


def render_record(
    tokenizer: Any, row: dict[str, Any], max_length: int
) -> tuple[list[int], list[int], dict[str, Any]]:
    tools = row.get("tools") or None
    prompt_ids = tokenizer.apply_chat_template(
        row["prompt"],
        tools=tools,
        tokenize=True,
        add_generation_prompt=True,
        enable_thinking=False,
    )
    full_ids = tokenizer.apply_chat_template(
        row["prompt"] + row["completion"],
        tools=tools,
        tokenize=True,
        add_generation_prompt=False,
        enable_thinking=False,
    )
    if full_ids[: len(prompt_ids)] != prompt_ids:
        raise ValueError(f"chat-template prefix mismatch for {row['id']}")
    completion_ids = full_ids[len(prompt_ids) :]
    if not completion_ids:
        raise ValueError(f"empty rendered completion for {row['id']}")
    if len(completion_ids) >= max_length:
        raise ValueError(
            f"completion alone is too long for {row['id']}: {len(completion_ids)} >= {max_length}"
        )
    original_length = len(full_ids)
    truncated_prompt_tokens = max(0, original_length - max_length)
    if truncated_prompt_tokens:
        keep_prompt = max_length - len(completion_ids)
        prompt_ids = prompt_ids[-keep_prompt:]
        full_ids = prompt_ids + completion_ids
    labels = [-100] * len(prompt_ids) + completion_ids
    if len(full_ids) != len(labels) or len(full_ids) > max_length:
        raise AssertionError("token/label length invariant failed")
    stats = {
        "id": row["id"],
        "tokens": len(full_ids),
        "prompt_tokens": len(prompt_ids),
        "completion_tokens": len(completion_ids),
        "original_tokens": original_length,
        "truncated_prompt_tokens": truncated_prompt_tokens,
    }
    return full_ids, labels, stats


class CompletionOnlyDataset(Dataset):
    def __init__(self, path: Path, tokenizer: Any, max_length: int):
        self.items: list[dict[str, torch.Tensor]] = []
        self.stats: list[dict[str, Any]] = []
        for row in load_jsonl(path):
            input_ids, labels, stats = render_record(tokenizer, row, max_length)
            self.items.append(
                {
                    "input_ids": torch.tensor(input_ids, dtype=torch.long),
                    "labels": torch.tensor(labels, dtype=torch.long),
                }
            )
            self.stats.append(stats)

    def __len__(self) -> int:
        return len(self.items)

    def __getitem__(self, index: int) -> dict[str, torch.Tensor]:
        return self.items[index]


@dataclass
class CompletionCollator:
    pad_token_id: int
    pad_to_multiple_of: int = 8

    def __call__(self, features: list[dict[str, torch.Tensor]]) -> dict[str, torch.Tensor]:
        max_length = max(feature["input_ids"].numel() for feature in features)
        max_length = int(math.ceil(max_length / self.pad_to_multiple_of) * self.pad_to_multiple_of)
        batch_size = len(features)
        input_ids = torch.full((batch_size, max_length), self.pad_token_id, dtype=torch.long)
        attention_mask = torch.zeros((batch_size, max_length), dtype=torch.long)
        labels = torch.full((batch_size, max_length), -100, dtype=torch.long)
        for index, feature in enumerate(features):
            length = feature["input_ids"].numel()
            input_ids[index, :length] = feature["input_ids"]
            attention_mask[index, :length] = 1
            labels[index, :length] = feature["labels"]
        return {"input_ids": input_ids, "attention_mask": attention_mask, "labels": labels}


def summarize_token_stats(stats: list[dict[str, Any]]) -> dict[str, Any]:
    keys = ("tokens", "prompt_tokens", "completion_tokens", "original_tokens")
    summary: dict[str, Any] = {"count": len(stats), "samples": stats}
    for key in keys:
        values = [int(row[key]) for row in stats]
        summary[key] = {"min": min(values), "max": max(values), "mean": sum(values) / len(values)}
    summary["truncated_samples"] = sum(
        int(row["truncated_prompt_tokens"] > 0) for row in stats
    )
    summary["truncated_prompt_tokens_total"] = sum(
        int(row["truncated_prompt_tokens"]) for row in stats
    )
    return summary


def reduce_mean(value: torch.Tensor, world_size: int) -> float:
    reduced = value.detach().float().clone()
    dist.all_reduce(reduced, op=dist.ReduceOp.SUM)
    reduced /= world_size
    return reduced.item()


def atomic_json(path: Path, payload: Any) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def epoch_summary(history: list[dict[str, Any]], epoch: int) -> dict[str, Any]:
    losses = [float(row["train_loss"]) for row in history if int(row["epoch"]) == epoch]
    if not losses:
        return {"epoch": epoch, "steps": 0}
    window = min(20, len(losses))
    return {
        "epoch": epoch,
        "steps": len(losses),
        "mean_loss": sum(losses) / len(losses),
        "first_20_mean_loss": sum(losses[:window]) / window,
        "last_20_mean_loss": sum(losses[-window:]) / window,
        "min_loss": min(losses),
        "max_loss": max(losses),
    }


def save_full_hf_model(
    fsdp_model: FSDP,
    tokenizer: Any,
    destination: Path,
    rank: int,
) -> None:
    dist.barrier()
    torch.cuda.empty_cache()
    state_config = FullStateDictConfig(offload_to_cpu=True, rank0_only=True)
    with FSDP.state_dict_type(fsdp_model, StateDictType.FULL_STATE_DICT, state_config):
        full_state = fsdp_model.state_dict()
    if rank == 0:
        temporary = destination.with_name(destination.name + ".tmp")
        if temporary.exists():
            shutil.rmtree(temporary)
        temporary.mkdir(parents=True)
        old_use_cache = fsdp_model.module.config.use_cache
        fsdp_model.module.config.use_cache = True
        fsdp_model.module.save_pretrained(
            temporary,
            state_dict=full_state,
            safe_serialization=True,
            max_shard_size="4GB",
        )
        fsdp_model.module.config.use_cache = old_use_cache
        tokenizer.save_pretrained(temporary)
        if destination.exists():
            raise FileExistsError(f"refusing to replace existing model directory: {destination}")
        temporary.replace(destination)
        print(
            json.dumps(
                {"event": "full_model_checkpoint_saved", "path": str(destination)},
                ensure_ascii=False,
            ),
            flush=True,
        )
    del full_state
    gc.collect()
    torch.cuda.empty_cache()
    dist.barrier()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--train-json", type=Path, required=True)
    parser.add_argument("--validation-json", type=Path, required=True)
    parser.add_argument("--experiment-dir", type=Path, required=True)
    parser.add_argument("--max-length", type=int, default=32768)
    parser.add_argument("--epochs", type=int, default=5)
    parser.add_argument("--learning-rate", type=float, default=2e-4)
    parser.add_argument("--weight-decay", type=float, default=0.0)
    parser.add_argument("--seed", type=int, default=20260915)
    parser.add_argument("--max-steps", type=int, default=0)
    parser.add_argument("--skip-validation", action="store_true")
    parser.add_argument("--skip-model-save", action="store_true")
    parser.add_argument("--save-every-epoch", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    rank = int(os.environ.get("RANK", "0"))
    local_rank = int(os.environ.get("LOCAL_RANK", "0"))
    world_size = int(os.environ.get("WORLD_SIZE", "1"))
    if world_size != 2:
        raise RuntimeError(f"full SFT requires exactly two FSDP processes; got {world_size}")
    torch.cuda.set_device(local_rank)
    device = torch.device("cuda", local_rank)
    dist.init_process_group("nccl", device_id=device)
    random.seed(args.seed)
    torch.manual_seed(args.seed)
    torch.cuda.manual_seed_all(args.seed)
    torch.backends.cuda.matmul.allow_tf32 = True

    model_path = args.model.resolve()
    experiment_dir = args.experiment_dir.resolve()
    metrics_dir = experiment_dir / "metrics"
    artifacts_dir = experiment_dir / "artifacts"
    if rank == 0:
        metrics_dir.mkdir(parents=True, exist_ok=True)
        artifacts_dir.mkdir(parents=True, exist_ok=True)
    dist.barrier()

    tokenizer = AutoTokenizer.from_pretrained(
        model_path, local_files_only=True, use_fast=True, padding_side="right"
    )
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token = tokenizer.eos_token
    train_dataset = CompletionOnlyDataset(args.train_json.resolve(), tokenizer, args.max_length)
    validation_dataset = CompletionOnlyDataset(
        args.validation_json.resolve(), tokenizer, args.max_length
    )
    collator = CompletionCollator(tokenizer.pad_token_id)

    base_model = AutoModelForCausalLM.from_pretrained(
        model_path,
        local_files_only=True,
        dtype=torch.bfloat16,
        low_cpu_mem_usage=True,
        attn_implementation="sdpa",
    )
    base_model.config.use_cache = False
    base_model.gradient_checkpointing_enable(
        gradient_checkpointing_kwargs={"use_reentrant": False}
    )
    base_model.enable_input_require_grads()
    total_parameters = sum(parameter.numel() for parameter in base_model.parameters())
    trainable_parameters = sum(
        parameter.numel() for parameter in base_model.parameters() if parameter.requires_grad
    )
    if trainable_parameters != total_parameters:
        raise RuntimeError(
            f"full SFT invariant failed: trainable={trainable_parameters}, total={total_parameters}"
        )

    auto_wrap = partial(
        transformer_auto_wrap_policy, transformer_layer_cls={Qwen3DecoderLayer}
    )
    mixed_precision = MixedPrecision(
        param_dtype=torch.bfloat16,
        reduce_dtype=torch.bfloat16,
        buffer_dtype=torch.bfloat16,
        cast_forward_inputs=True,
    )
    model = FSDP(
        base_model,
        auto_wrap_policy=auto_wrap,
        sharding_strategy=ShardingStrategy.FULL_SHARD,
        mixed_precision=mixed_precision,
        backward_prefetch=BackwardPrefetch.BACKWARD_PRE,
        device_id=device,
        sync_module_states=True,
        use_orig_params=True,
        limit_all_gathers=True,
    )

    train_sampler = DistributedSampler(
        train_dataset, num_replicas=world_size, rank=rank, shuffle=True, seed=args.seed
    )
    validation_sampler = DistributedSampler(
        validation_dataset, num_replicas=world_size, rank=rank, shuffle=False
    )
    train_loader = DataLoader(
        train_dataset,
        batch_size=1,
        sampler=train_sampler,
        collate_fn=collator,
        num_workers=0,
        pin_memory=True,
    )
    validation_loader = DataLoader(
        validation_dataset,
        batch_size=1,
        sampler=validation_sampler,
        collate_fn=collator,
        num_workers=0,
        pin_memory=True,
    )
    optimizer = torch.optim.AdamW(
        model.parameters(),
        lr=args.learning_rate,
        weight_decay=args.weight_decay,
        fused=True,
    )

    if rank == 0:
        print(
            json.dumps(
                {
                    "event": "initialized_full_sft",
                    "world_size": world_size,
                    "train_samples": len(train_dataset),
                    "validation_samples": len(validation_dataset),
                    "trainable_parameters": trainable_parameters,
                    "total_parameters": total_parameters,
                    "fsdp": "FULL_SHARD",
                    "optimizer": "fused AdamW",
                },
                ensure_ascii=False,
            ),
            flush=True,
        )

    torch.cuda.reset_peak_memory_stats(device)
    started = time.time()
    history: list[dict[str, Any]] = []
    history_path = metrics_dir / "training_history.jsonl"
    history_handle = history_path.open("w", encoding="utf-8") if rank == 0 else None
    global_step = 0
    epochs_completed = 0
    stop_training = False
    model.train()
    for epoch_index in range(args.epochs):
        epoch = epoch_index + 1
        train_sampler.set_epoch(epoch_index)
        for batch in train_loader:
            batch = {key: value.to(device, non_blocking=True) for key, value in batch.items()}
            optimizer.zero_grad(set_to_none=True)
            with torch.autocast(device_type="cuda", dtype=torch.bfloat16):
                loss = model(**batch).loss
            if not torch.isfinite(loss):
                raise FloatingPointError(f"non-finite loss at epoch={epoch}, step={global_step + 1}")
            loss.backward()
            optimizer.step()
            global_step += 1
            mean_loss = reduce_mean(loss, world_size)
            event = {
                "epoch": epoch,
                "step": global_step,
                "train_loss": mean_loss,
                "elapsed_seconds": time.time() - started,
            }
            if rank == 0:
                history.append(event)
                assert history_handle is not None
                history_handle.write(json.dumps(event, ensure_ascii=False) + "\n")
                history_handle.flush()
                print(json.dumps({"event": "train_step", **event}), flush=True)
            if args.max_steps and global_step >= args.max_steps:
                stop_training = True
                break
        if stop_training:
            break
        epochs_completed = epoch
        if rank == 0:
            progress = {
                "status": "RUNNING",
                "epochs_completed": epochs_completed,
                "global_step": global_step,
                "epoch_summaries": [epoch_summary(history, e) for e in range(1, epoch + 1)],
            }
            atomic_json(metrics_dir / "progress.json", progress)
        if args.save_every_epoch and not args.skip_model_save:
            destination = (
                artifacts_dir / "model"
                if epoch == args.epochs
                else artifacts_dir / "checkpoints" / f"epoch_{epoch}_model"
            )
            save_full_hf_model(model, tokenizer, destination, rank)
        model.train()

    if history_handle is not None:
        history_handle.close()

    validation: dict[str, Any] | None = None
    if not args.skip_validation and not stop_training:
        model.eval()
        local_loss_sum = torch.zeros(1, dtype=torch.float64, device=device)
        local_token_count = torch.zeros(1, dtype=torch.float64, device=device)
        with torch.no_grad():
            for batch in validation_loader:
                batch = {key: value.to(device, non_blocking=True) for key, value in batch.items()}
                with torch.autocast(device_type="cuda", dtype=torch.bfloat16):
                    loss = model(**batch).loss
                target_count = (batch["labels"][:, 1:] != -100).sum().double()
                local_loss_sum += loss.double() * target_count
                local_token_count += target_count
        dist.all_reduce(local_loss_sum, op=dist.ReduceOp.SUM)
        dist.all_reduce(local_token_count, op=dist.ReduceOp.SUM)
        validation_loss = (local_loss_sum / local_token_count).item()
        validation = {
            "scope": "diagnostic subset overlapping all-data training",
            "loss": validation_loss,
            "perplexity": math.exp(min(validation_loss, 20.0)),
            "completion_target_tokens": int(local_token_count.item()),
        }

    if not args.skip_model_save and not args.save_every_epoch and not stop_training:
        save_full_hf_model(model, tokenizer, artifacts_dir / "model", rank)

    local_gpu = {
        "rank": rank,
        "local_rank": local_rank,
        "device_name": torch.cuda.get_device_name(local_rank),
        "device_capability": list(torch.cuda.get_device_capability(local_rank)),
        "peak_allocated_gib": torch.cuda.max_memory_allocated(device) / (1024**3),
        "peak_reserved_gib": torch.cuda.max_memory_reserved(device) / (1024**3),
    }
    gpu_ranks: list[object] = [None] * world_size
    dist.all_gather_object(gpu_ranks, local_gpu)

    if rank == 0:
        status = "PROBE_SUCCESS" if args.max_steps else "SUCCESS"
        epoch_summaries = [epoch_summary(history, epoch) for epoch in range(1, args.epochs + 1)]
        epoch_summaries = [row for row in epoch_summaries if int(row["steps"]) > 0]
        metrics = {
            "status": status,
            "finished_at_utc": datetime.now(timezone.utc).isoformat(),
            "hostname": socket.gethostname(),
            "arguments": {
                key: str(value) if isinstance(value, Path) else value
                for key, value in vars(args).items()
            },
            "distributed": {
                "backend": "nccl",
                "world_size": world_size,
                "sharding": "FSDP FULL_SHARD",
                "ranks": gpu_ranks,
            },
            "model": {
                "source_base_model": str(model_path),
                "method": "full_parameter_sft",
                "dtype": "bfloat16",
                "attention": "sdpa",
                "trainable_parameters": trainable_parameters,
                "total_parameters": total_parameters,
                "trainable_percent": 100.0 * trainable_parameters / total_parameters,
                "final_model": None
                if args.skip_model_save or stop_training
                else str((artifacts_dir / "model").resolve()),
            },
            "data": {
                "train": summarize_token_stats(train_dataset.stats),
                "validation": summarize_token_stats(validation_dataset.stats),
            },
            "training": {
                "epochs_requested": args.epochs,
                "epochs_completed": epochs_completed,
                "global_steps": global_step,
                "per_gpu_batch_size": 1,
                "global_batch_size": world_size,
                "gradient_accumulation_steps": 1,
                "learning_rate": args.learning_rate,
                "weight_decay": args.weight_decay,
                "optimizer": "fused AdamW",
                "loss_policy": "assistant_completion_only",
                "enable_thinking": False,
                "gradient_checkpointing": True,
                "max_length": args.max_length,
                "elapsed_seconds": time.time() - started,
                "epoch_summaries": epoch_summaries,
                "history": history,
            },
            "validation": validation,
        }
        atomic_json(metrics_dir / "metrics.json", metrics)
        atomic_json(
            metrics_dir / "progress.json",
            {
                "status": status,
                "epochs_completed": epochs_completed,
                "global_step": global_step,
                "epoch_summaries": epoch_summaries,
            },
        )
        print(
            json.dumps(
                {
                    "event": "completed_full_sft",
                    "status": status,
                    "global_step": global_step,
                    "validation": validation,
                    "final_model": metrics["model"]["final_model"],
                },
                ensure_ascii=False,
            ),
            flush=True,
        )

    dist.barrier()
    dist.destroy_process_group()


if __name__ == "__main__":
    main()
