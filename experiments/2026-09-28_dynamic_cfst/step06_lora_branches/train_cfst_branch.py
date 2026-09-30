#!/usr/bin/env python3
"""Two-GPU DDP trainer for one frozen Dynamic-CFST Step 6 branch."""

from __future__ import annotations

import argparse
import hashlib
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
from peft import PeftModel
from torch.nn.parallel import DistributedDataParallel
from torch.utils.data import DataLoader, Dataset, DistributedSampler
from transformers import AutoModelForCausalLM, AutoTokenizer


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not rows:
        raise ValueError(f"empty JSONL: {path}")
    return rows


def render_record(tokenizer: Any, row: dict[str, Any], max_length: int) -> dict[str, Any]:
    prompt_ids = tokenizer.apply_chat_template(
        row["prompt"], tools=None, tokenize=True,
        add_generation_prompt=True, enable_thinking=False,
    )
    full_ids = tokenizer.apply_chat_template(
        row["prompt"] + row["completion"], tools=None, tokenize=True,
        add_generation_prompt=False, enable_thinking=False,
    )
    if full_ids[: len(prompt_ids)] != prompt_ids:
        raise ValueError(f"chat-template prefix mismatch: {row['id']}")
    completion_ids = full_ids[len(prompt_ids):]
    if not completion_ids or len(full_ids) > max_length:
        raise ValueError(f"invalid length for {row['id']}: {len(full_ids)}")
    labels = [-100] * len(prompt_ids) + completion_ids
    schedule_meta = row["metadata"].get("step06_schedule", {})
    return {
        "id": row["id"],
        "source_training_id": schedule_meta.get("source_training_id", row["id"]),
        "task_id": row["metadata"]["task_id"],
        "schedule_index": int(schedule_meta.get("schedule_index_1based", 0)),
        "input_ids": torch.tensor(full_ids, dtype=torch.long),
        "labels": torch.tensor(labels, dtype=torch.long),
        "tokens": len(full_ids),
        "prompt_tokens": len(prompt_ids),
        "completion_tokens": len(completion_ids),
    }


class CompletionDataset(Dataset):
    def __init__(self, path: Path, tokenizer: Any, max_length: int):
        self.items = [render_record(tokenizer, row, max_length) for row in read_jsonl(path)]

    def __len__(self) -> int:
        return len(self.items)

    def __getitem__(self, index: int) -> dict[str, Any]:
        return self.items[index]


@dataclass
class CompletionCollator:
    pad_token_id: int
    pad_to_multiple_of: int = 8

    def __call__(self, features: list[dict[str, Any]]) -> dict[str, Any]:
        max_length = max(item["input_ids"].numel() for item in features)
        max_length = int(math.ceil(max_length / self.pad_to_multiple_of) * self.pad_to_multiple_of)
        input_ids = torch.full((len(features), max_length), self.pad_token_id, dtype=torch.long)
        attention_mask = torch.zeros((len(features), max_length), dtype=torch.long)
        labels = torch.full((len(features), max_length), -100, dtype=torch.long)
        metadata: list[dict[str, Any]] = []
        for index, item in enumerate(features):
            length = item["input_ids"].numel()
            input_ids[index, :length] = item["input_ids"]
            attention_mask[index, :length] = 1
            labels[index, :length] = item["labels"]
            metadata.append({key: item[key] for key in ("id", "source_training_id", "task_id", "schedule_index", "tokens", "prompt_tokens", "completion_tokens")})
        return {"input_ids": input_ids, "attention_mask": attention_mask, "labels": labels, "metadata": metadata}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    return parser.parse_args()


def weighted_forward(model: Any, batch: dict[str, torch.Tensor], world_size: int) -> tuple[torch.Tensor, float, int]:
    outputs = model(**batch)
    local_count = (batch["labels"][:, 1:] != -100).sum().to(dtype=torch.float64)
    if local_count.item() <= 0:
        raise RuntimeError("batch has no supervised causal target tokens")
    global_count = local_count.detach().clone()
    dist.all_reduce(global_count, op=dist.ReduceOp.SUM)
    local_loss_sum = outputs.loss.detach().double() * local_count
    global_loss_sum = local_loss_sum.clone()
    dist.all_reduce(global_loss_sum, op=dist.ReduceOp.SUM)
    global_mean = (global_loss_sum / global_count).item()
    backward_loss = outputs.loss * (local_count.float() * world_size / global_count.float())
    return backward_loss, global_mean, int(global_count.item())


def evaluate(model: Any, loader: DataLoader, device: torch.device) -> tuple[float, int]:
    model.eval()
    local_loss_sum = torch.zeros(1, dtype=torch.float64, device=device)
    local_count = torch.zeros(1, dtype=torch.float64, device=device)
    with torch.no_grad():
        for raw in loader:
            batch = {key: value.to(device, non_blocking=True) for key, value in raw.items() if key != "metadata"}
            with torch.autocast(device_type="cuda", dtype=torch.bfloat16):
                outputs = model(**batch)
            count = (batch["labels"][:, 1:] != -100).sum().double()
            local_loss_sum += outputs.loss.double() * count
            local_count += count
    dist.all_reduce(local_loss_sum, op=dist.ReduceOp.SUM)
    dist.all_reduce(local_count, op=dist.ReduceOp.SUM)
    return (local_loss_sum / local_count).item(), int(local_count.item())


def main() -> None:
    args = parse_args()
    config_path = args.config.resolve()
    config = json.loads(config_path.read_text(encoding="utf-8"))
    rank = int(os.environ.get("RANK", "0"))
    local_rank = int(os.environ.get("LOCAL_RANK", "0"))
    world_size = int(os.environ.get("WORLD_SIZE", "1"))
    if world_size != int(config["world_size"]) or world_size != 2:
        raise RuntimeError(f"expected two DDP ranks, got {world_size}")

    torch.cuda.set_device(local_rank)
    dist.init_process_group("nccl", device_id=torch.device("cuda", local_rank))
    device = torch.device("cuda", local_rank)
    seed = int(config["seed"])
    random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)
    torch.backends.cuda.matmul.allow_tf32 = True

    base_path = Path(config["base_model"]).resolve()
    source_adapter = Path(config["source_adapter"]).resolve()
    schedule_path = Path(config["schedule_json"]).resolve()
    unique_path = Path(config["unique_train_json"]).resolve()
    branch_dir = Path(config["branch_dir"]).resolve()
    branch_dir.mkdir(parents=True, exist_ok=True)
    if (branch_dir / "adapter").exists():
        raise FileExistsError(f"refusing to overwrite {branch_dir / 'adapter'}")
    if sha256_file(source_adapter / "adapter_model.safetensors") != config["source_adapter_model_sha256"]:
        raise ValueError("source adapter hash changed")
    if sha256_file(schedule_path) != config["schedule_sha256"]:
        raise ValueError("training schedule hash changed")
    if sha256_file(unique_path) != config["unique_train_sha256"]:
        raise ValueError("unique package hash changed")

    tokenizer = AutoTokenizer.from_pretrained(
        source_adapter, local_files_only=True, use_fast=True, padding_side="right"
    )
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token = tokenizer.eos_token
    train_dataset = CompletionDataset(schedule_path, tokenizer, int(config["max_length"]))
    diagnostic_dataset = CompletionDataset(unique_path, tokenizer, int(config["max_length"]))
    if len(train_dataset) != int(config["scheduled_examples"]) or len(train_dataset) % 2:
        raise ValueError("schedule length does not match frozen even count")
    collator = CompletionCollator(tokenizer.pad_token_id)
    train_sampler = DistributedSampler(
        train_dataset, num_replicas=world_size, rank=rank,
        shuffle=True, seed=seed, drop_last=False,
    )
    diagnostic_sampler = DistributedSampler(
        diagnostic_dataset, num_replicas=world_size, rank=rank,
        shuffle=False, drop_last=False,
    )
    train_sampler.set_epoch(0)
    train_loader = DataLoader(
        train_dataset, batch_size=1, sampler=train_sampler, collate_fn=collator,
        num_workers=0, pin_memory=True,
    )
    diagnostic_loader = DataLoader(
        diagnostic_dataset, batch_size=1, sampler=diagnostic_sampler, collate_fn=collator,
        num_workers=0, pin_memory=True,
    )

    base = AutoModelForCausalLM.from_pretrained(
        base_path, local_files_only=True, dtype=torch.bfloat16,
        low_cpu_mem_usage=True, attn_implementation="sdpa",
    )
    base.config.use_cache = False
    base.gradient_checkpointing_enable(gradient_checkpointing_kwargs={"use_reentrant": False})
    base.enable_input_require_grads()
    model = PeftModel.from_pretrained(base, source_adapter, is_trainable=True)
    model.to(device)
    trainable_parameters = sum(parameter.numel() for parameter in model.parameters() if parameter.requires_grad)
    total_parameters = sum(parameter.numel() for parameter in model.parameters())
    if trainable_parameters != int(config["expected_trainable_parameters"]):
        raise RuntimeError(f"unexpected trainable parameter count: {trainable_parameters}")
    ddp_model = DistributedDataParallel(
        model, device_ids=[local_rank], output_device=local_rank,
        broadcast_buffers=False, find_unused_parameters=False,
    )
    optimizer = torch.optim.AdamW(
        (parameter for parameter in ddp_model.parameters() if parameter.requires_grad),
        lr=float(config["learning_rate"]), weight_decay=float(config["weight_decay"]),
    )

    if rank == 0:
        print(json.dumps({
            "event": "initialized", "branch": config["branch"],
            "source_adapter_sha256": config["source_adapter_model_sha256"],
            "scheduled_examples": len(train_dataset),
            "expected_optimizer_steps": len(train_loader),
            "expected_supervised_tokens": config["scheduled_supervised_tokens"],
            "trainable_parameters": trainable_parameters,
        }), flush=True)

    torch.cuda.reset_peak_memory_stats(device)
    started = time.time()
    history: list[dict[str, Any]] = []
    cumulative_tokens = 0
    ddp_model.train()
    for step, raw in enumerate(train_loader, 1):
        metadata = raw.pop("metadata")
        batch = {key: value.to(device, non_blocking=True) for key, value in raw.items()}
        optimizer.zero_grad(set_to_none=True)
        with torch.autocast(device_type="cuda", dtype=torch.bfloat16):
            backward_loss, global_loss, step_tokens = weighted_forward(ddp_model, batch, world_size)
        if not math.isfinite(global_loss):
            raise RuntimeError(f"non-finite loss at step {step}: {global_loss}")
        backward_loss.backward()
        optimizer.step()
        cumulative_tokens += step_tokens
        local_meta = metadata[0]
        all_meta: list[Any] = [None] * world_size
        dist.all_gather_object(all_meta, local_meta)
        event = {
            "step": step,
            "loss": global_loss,
            "supervised_tokens": step_tokens,
            "cumulative_supervised_tokens": cumulative_tokens,
            "samples": all_meta,
            "elapsed_seconds": time.time() - started,
        }
        if rank == 0:
            history.append(event)
            print(json.dumps({"event": "train_step", **event}), flush=True)

    if cumulative_tokens != int(config["scheduled_supervised_tokens"]):
        raise RuntimeError(f"actual supervised tokens {cumulative_tokens} != frozen {config['scheduled_supervised_tokens']}")
    actual_steps = len(history) if rank == 0 else len(train_loader)
    if actual_steps != int(config["optimizer_steps"]):
        raise RuntimeError("optimizer step count differs from frozen plan")

    diagnostic_loss, diagnostic_tokens = evaluate(ddp_model, diagnostic_loader, device)
    local_gpu = {
        "rank": rank,
        "name": torch.cuda.get_device_name(local_rank),
        "capability": list(torch.cuda.get_device_capability(local_rank)),
        "peak_allocated_gib": torch.cuda.max_memory_allocated(device) / (1024 ** 3),
        "peak_reserved_gib": torch.cuda.max_memory_reserved(device) / (1024 ** 3),
    }
    gpu_rows: list[Any] = [None] * world_size
    dist.all_gather_object(gpu_rows, local_gpu)
    dist.barrier()

    if rank == 0:
        adapter_dir = branch_dir / "adapter"
        ddp_model.module.save_pretrained(adapter_dir, safe_serialization=True)
        tokenizer.save_pretrained(adapter_dir)
        adapter_hash = sha256_file(adapter_dir / "adapter_model.safetensors")
        metrics = {
            "schema_version": "dynamic-cfst-step06-branch-metrics-v1",
            "status": "SUCCESS",
            "branch": config["branch"],
            "started_at_utc": datetime.fromtimestamp(started, tz=timezone.utc).isoformat(),
            "finished_at_utc": datetime.now(timezone.utc).isoformat(),
            "hostname": socket.gethostname(),
            "source": {
                "base_model": str(base_path),
                "adapter": str(source_adapter),
                "adapter_model_sha256": config["source_adapter_model_sha256"],
                "optimizer_state_reused": False,
                "model_weights_reused": True,
            },
            "data": {
                "unique_train_json": str(unique_path),
                "unique_train_sha256": config["unique_train_sha256"],
                "unique_samples": config["unique_sample_count"],
                "schedule_json": str(schedule_path),
                "schedule_sha256": config["schedule_sha256"],
                "scheduled_examples": len(train_dataset),
                "scheduled_supervised_tokens": cumulative_tokens,
            },
            "training": {
                "optimizer": "AdamW",
                "learning_rate": float(config["learning_rate"]),
                "weight_decay": float(config["weight_decay"]),
                "scheduler": "none_constant",
                "warmup_steps": 0,
                "seed": seed,
                "world_size": world_size,
                "global_batch_size": 2,
                "optimizer_steps": len(history),
                "loss_reduction": "global supervised-token mean across two DDP ranks",
                "loss_first": history[0]["loss"],
                "loss_last": history[-1]["loss"],
                "loss_mean": sum(row["loss"] for row in history) / len(history),
                "duration_seconds": time.time() - started,
                "history": history,
            },
            "diagnostic": {
                "scope": config["diagnostic_scope"],
                "loss": diagnostic_loss,
                "perplexity": math.exp(min(diagnostic_loss, 20.0)),
                "completion_target_tokens": diagnostic_tokens,
            },
            "model": {
                "dtype": "bfloat16",
                "attention": "sdpa",
                "max_length": int(config["max_length"]),
                "trainable_parameters": trainable_parameters,
                "total_parameters": total_parameters,
                "trainable_percent": 100.0 * trainable_parameters / total_parameters,
            },
            "distributed": {"backend": "nccl", "world_size": world_size, "gpus": gpu_rows},
            "artifacts": {
                "adapter_dir": str(adapter_dir),
                "adapter_model_sha256": adapter_hash,
                "adapter_differs_from_source": adapter_hash != config["source_adapter_model_sha256"],
            },
            "software": {
                "torch": torch.__version__, "cuda_runtime": torch.version.cuda,
            },
        }
        (branch_dir / "metrics.json").write_text(
            json.dumps(metrics, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        (branch_dir / "loss_history.jsonl").write_text(
            "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in history), encoding="utf-8"
        )
        print(json.dumps({
            "event": "completed", "branch": config["branch"],
            "optimizer_steps": len(history), "supervised_tokens": cumulative_tokens,
            "diagnostic_loss": diagnostic_loss, "adapter_sha256": adapter_hash,
        }), flush=True)
    dist.barrier()
    dist.destroy_process_group()


if __name__ == "__main__":
    main()
