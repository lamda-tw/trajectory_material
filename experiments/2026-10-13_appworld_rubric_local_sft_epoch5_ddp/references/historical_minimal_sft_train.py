#!/usr/bin/env python3
"""Minimal completion-only LoRA SFT for Qwen3 using two-process DDP."""

from __future__ import annotations

import argparse
import json
import math
import os
import random
import socket
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import torch
import torch.distributed as dist
from peft import LoraConfig, get_peft_model
from torch.nn.parallel import DistributedDataParallel
from torch.utils.data import DataLoader, Dataset, DistributedSampler
from transformers import AutoModelForCausalLM, AutoTokenizer


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
        input_ids = torch.full(
            (batch_size, max_length), self.pad_token_id, dtype=torch.long
        )
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
    if world_size > 1:
        dist.all_reduce(reduced, op=dist.ReduceOp.SUM)
        reduced /= world_size
    return reduced.item()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--train-json", type=Path, required=True)
    parser.add_argument("--validation-json", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--max-length", type=int, default=4096)
    parser.add_argument("--epochs", type=int, default=1)
    parser.add_argument("--learning-rate", type=float, default=2e-4)
    parser.add_argument("--weight-decay", type=float, default=0.0)
    parser.add_argument("--lora-r", type=int, default=8)
    parser.add_argument("--lora-alpha", type=int, default=16)
    parser.add_argument("--seed", type=int, default=20260909)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    rank = int(os.environ.get("RANK", "0"))
    local_rank = int(os.environ.get("LOCAL_RANK", "0"))
    world_size = int(os.environ.get("WORLD_SIZE", "1"))
    if world_size != 2:
        raise RuntimeError(f"this smoke run requires two DDP processes; got {world_size}")
    torch.cuda.set_device(local_rank)
    dist.init_process_group("nccl")
    device = torch.device("cuda", local_rank)
    random.seed(args.seed)
    torch.manual_seed(args.seed)
    torch.cuda.manual_seed_all(args.seed)
    torch.backends.cuda.matmul.allow_tf32 = True

    model_path = args.model.resolve()
    output_dir = args.output_dir.resolve()
    if rank == 0:
        output_dir.mkdir(parents=True, exist_ok=True)
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

    model = AutoModelForCausalLM.from_pretrained(
        model_path,
        local_files_only=True,
        dtype=torch.bfloat16,
        low_cpu_mem_usage=True,
        attn_implementation="sdpa",
    )
    model.config.use_cache = False
    model.gradient_checkpointing_enable(gradient_checkpointing_kwargs={"use_reentrant": False})
    model.enable_input_require_grads()
    lora_config = LoraConfig(
        r=args.lora_r,
        lora_alpha=args.lora_alpha,
        lora_dropout=0.0,
        bias="none",
        task_type="CAUSAL_LM",
        target_modules=[
            "q_proj",
            "k_proj",
            "v_proj",
            "o_proj",
            "gate_proj",
            "up_proj",
            "down_proj",
        ],
    )
    model = get_peft_model(model, lora_config)
    model.to(device)
    trainable_parameters = sum(parameter.numel() for parameter in model.parameters() if parameter.requires_grad)
    total_parameters = sum(parameter.numel() for parameter in model.parameters())
    ddp_model = DistributedDataParallel(
        model,
        device_ids=[local_rank],
        output_device=local_rank,
        broadcast_buffers=False,
        find_unused_parameters=False,
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
        (parameter for parameter in ddp_model.parameters() if parameter.requires_grad),
        lr=args.learning_rate,
        weight_decay=args.weight_decay,
    )

    if rank == 0:
        print(
            json.dumps(
                {
                    "event": "initialized",
                    "world_size": world_size,
                    "train_samples": len(train_dataset),
                    "validation_samples": len(validation_dataset),
                    "trainable_parameters": trainable_parameters,
                    "total_parameters": total_parameters,
                    "trainable_percent": 100.0 * trainable_parameters / total_parameters,
                },
                ensure_ascii=False,
            ),
            flush=True,
        )

    torch.cuda.reset_peak_memory_stats(device)
    started = time.time()
    history: list[dict[str, Any]] = []
    global_step = 0
    ddp_model.train()
    for epoch in range(args.epochs):
        train_sampler.set_epoch(epoch)
        for batch in train_loader:
            batch = {key: value.to(device, non_blocking=True) for key, value in batch.items()}
            optimizer.zero_grad(set_to_none=True)
            with torch.autocast(device_type="cuda", dtype=torch.bfloat16):
                loss = ddp_model(**batch).loss
            loss.backward()
            optimizer.step()
            global_step += 1
            mean_loss = reduce_mean(loss, world_size)
            event = {
                "epoch": epoch + 1,
                "step": global_step,
                "train_loss": mean_loss,
                "elapsed_seconds": time.time() - started,
            }
            if rank == 0:
                history.append(event)
                print(json.dumps({"event": "train_step", **event}), flush=True)

    ddp_model.eval()
    local_loss_sum = torch.zeros(1, dtype=torch.float64, device=device)
    local_token_count = torch.zeros(1, dtype=torch.float64, device=device)
    with torch.no_grad():
        for batch in validation_loader:
            batch = {key: value.to(device, non_blocking=True) for key, value in batch.items()}
            with torch.autocast(device_type="cuda", dtype=torch.bfloat16):
                loss = ddp_model(**batch).loss
            target_count = (batch["labels"][:, 1:] != -100).sum().double()
            local_loss_sum += loss.double() * target_count
            local_token_count += target_count
    dist.all_reduce(local_loss_sum, op=dist.ReduceOp.SUM)
    dist.all_reduce(local_token_count, op=dist.ReduceOp.SUM)
    validation_loss = (local_loss_sum / local_token_count).item()
    validation_perplexity = math.exp(min(validation_loss, 20.0))

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
    dist.barrier()
    if rank == 0:
        adapter_dir = output_dir / "adapter"
        ddp_model.module.save_pretrained(adapter_dir, safe_serialization=True)
        tokenizer.save_pretrained(adapter_dir)
        metrics = {
            "status": "SUCCESS",
            "finished_at_utc": datetime.now(timezone.utc).isoformat(),
            "hostname": socket.gethostname(),
            "arguments": {
                key: str(value) if isinstance(value, Path) else value
                for key, value in vars(args).items()
            },
            "distributed": {"backend": "nccl", "world_size": world_size, "ranks": gpu_ranks},
            "model": {
                "base_model": str(model_path),
                "dtype": "bfloat16",
                "attention": "sdpa",
                "method": "LoRA",
                "trainable_parameters": trainable_parameters,
                "total_parameters": total_parameters,
                "trainable_percent": 100.0 * trainable_parameters / total_parameters,
            },
            "data": {
                "train": summarize_token_stats(train_dataset.stats),
                "validation": summarize_token_stats(validation_dataset.stats),
            },
            "training": {
                "optimizer": "AdamW",
                "global_steps": global_step,
                "duration_seconds": time.time() - started,
                "history": history,
            },
            "validation": {
                "loss": validation_loss,
                "perplexity": validation_perplexity,
                "completion_target_tokens": int(local_token_count.item()),
            },
            "artifacts": {"adapter_dir": str(adapter_dir)},
            "software": {
                "torch": torch.__version__,
                "cuda_runtime": torch.version.cuda,
            },
        }
        (output_dir / "metrics.json").write_text(
            json.dumps(metrics, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(json.dumps({"event": "completed", "validation": metrics["validation"]}), flush=True)
    dist.barrier()
    dist.destroy_process_group()


if __name__ == "__main__":
    main()
