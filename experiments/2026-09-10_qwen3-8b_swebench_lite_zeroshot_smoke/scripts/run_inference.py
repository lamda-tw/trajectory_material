#!/usr/bin/env python3
"""Run deterministic, single-turn zero-shot patch generation with local Qwen3-8B."""

from __future__ import annotations

import json
import os
import re
import subprocess
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer


EXPERIMENT = Path(__file__).resolve().parents[1]
CONFIG = json.loads((EXPERIMENT / "config.json").read_text(encoding="utf-8"))
SYSTEM_PROMPT = """You are a software engineer fixing a real bug in a checked-out Git repository.

You are given the issue and a deterministic selection of repository files. Diagnose the root cause and produce the smallest complete source-code patch that fixes the issue while preserving unrelated behavior.

Rules:
1. Do not modify tests, generated files, dependency locks, or documentation.
2. Do not invent files or APIs that are not supported by the supplied code.
3. Do not merely explain the solution: return a patch.
4. Return only a valid unified git diff beginning with `diff --git`.
5. Do not wrap the diff in Markdown fences and do not add prose before or after it.
"""

STOPWORDS = {
    "about", "after", "again", "also", "array", "because", "before", "being",
    "below", "between", "cannot", "class", "could", "data", "describe", "does",
    "error", "expected", "field", "fields", "from", "have", "however", "index",
    "instead", "issue", "like", "method", "model", "object", "only", "output",
    "problem", "return", "returns", "schema", "should", "test", "that", "their",
    "there", "these", "this", "throw", "using", "value", "version", "when", "where",
    "which", "with", "without", "works", "would",
}
EXCLUDED_PARTS = {
    ".git", ".tox", ".venv", "venv", "build", "dist", "docs", "doc", "site-packages",
    "node_modules", "vendor",
}


def run(command: list[str], *, cwd: Path, input_text: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
        input=input_text,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )


def issue_terms(issue: str) -> tuple[set[str], set[str]]:
    explicit_files = {
        Path(match).name.lower()
        for match in re.findall(r"[A-Za-z0-9_./-]+\.(?:py|pyx|c|h|cpp|js|ts)", issue)
    }
    identifiers = {
        token.lower()
        for token in re.findall(r"\b[A-Za-z_][A-Za-z0-9_]{3,}\b", issue)
        if token.lower() not in STOPWORDS
    }
    return explicit_files, identifiers


def readable_code_files(repo: Path) -> list[Path]:
    allowed = {".py", ".pyx", ".c", ".h", ".cpp", ".js", ".ts"}
    result: list[Path] = []
    for path in repo.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in allowed:
            continue
        relative = path.relative_to(repo)
        if any(part in EXCLUDED_PARTS for part in relative.parts):
            continue
        try:
            if path.stat().st_size <= 160_000:
                result.append(path)
        except OSError:
            continue
    return result


def select_context(repo: Path, issue: str) -> tuple[list[dict], str]:
    explicit_files, identifiers = issue_terms(issue)
    ranked: list[tuple[float, str, Path, str]] = []
    for path in readable_code_files(repo):
        relative = path.relative_to(repo).as_posix()
        relative_lower = relative.lower()
        try:
            content = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        lower = content.lower()
        score = 0.0
        if path.name.lower() in explicit_files:
            score += 120.0
        for filename in explicit_files:
            if filename in relative_lower:
                score += 35.0
        term_hits = Counter()
        for term in identifiers:
            if term in relative_lower:
                score += 14.0
            count = lower.count(term)
            if count:
                term_hits[term] = min(count, 5)
        score += min(sum(term_hits.values()), 45)
        if "/tests/" in f"/{relative_lower}" or relative_lower.startswith("tests/"):
            score += 2.0
        else:
            score += 6.0
        if score > 6.0:
            ranked.append((score, relative, path, content))

    ranked.sort(key=lambda item: (-item[0], item[1]))
    selected: list[dict] = []
    chunks: list[str] = []
    used_chars = 0
    for score, relative, _path, content in ranked:
        if len(selected) >= CONFIG["max_context_files"]:
            break
        chunk = f"<file path=\"{relative}\">\n{content}\n</file>\n"
        if used_chars + len(chunk) > CONFIG["max_context_chars"]:
            continue
        selected.append({"path": relative, "score": score, "chars": len(content)})
        chunks.append(chunk)
        used_chars += len(chunk)
    if not selected:
        raise RuntimeError(f"No source context selected in {repo}")
    return selected, "\n".join(chunks)


def extract_diff(text: str) -> str | None:
    cleaned = text.strip()
    fenced = re.search(r"```(?:diff)?\s*(diff --git[\s\S]*?)```", cleaned)
    if fenced:
        cleaned = fenced.group(1).strip()
    start = cleaned.find("diff --git ")
    if start < 0:
        return None
    return cleaned[start:].strip() + "\n"


def safe_patch_paths(patch: str) -> tuple[bool, str]:
    paths: list[str] = []
    for line in patch.splitlines():
        if line.startswith("+++ ") or line.startswith("--- "):
            value = line[4:].split("\t", 1)[0]
            if value == "/dev/null":
                continue
            if value.startswith(("a/", "b/")):
                value = value[2:]
            candidate = Path(value)
            if candidate.is_absolute() or ".." in candidate.parts:
                return False, f"unsafe patch path: {value}"
            paths.append(value)
    if not paths:
        return False, "patch contains no file paths"
    return True, "ok"


def main() -> None:
    torch.manual_seed(CONFIG["seed"])
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(CONFIG["seed"])

    for name in ("prompts", "outputs", "patches", "logs", "metadata"):
        (EXPERIMENT / name).mkdir(parents=True, exist_ok=True)

    task_rows = [
        json.loads(line)
        for line in (EXPERIMENT / "data" / "selected_tasks.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    model_path = Path(CONFIG["model_path"])
    tokenizer = AutoTokenizer.from_pretrained(model_path, local_files_only=True, use_fast=True)
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token = tokenizer.eos_token
    model = AutoModelForCausalLM.from_pretrained(
        model_path,
        local_files_only=True,
        dtype=torch.bfloat16,
        low_cpu_mem_usage=True,
        attn_implementation="sdpa",
    ).to("cuda:0").eval()

    predictions: list[dict] = []
    summary: list[dict] = []
    for index, row in enumerate(task_rows, start=1):
        instance_id = row["instance_id"]
        repo = EXPERIMENT / "worktrees" / instance_id
        status = run(["git", "status", "--porcelain"], cwd=repo)
        if status.stdout.strip():
            raise RuntimeError(f"Worktree must be clean before inference: {instance_id}")

        selected, context = select_context(repo, row["problem_statement"])
        user_prompt = f"""Resolve this repository issue.

Instance ID: {instance_id}
Repository: {row['repo']}
Base commit: {row['base_commit']}

<issue>
{row['problem_statement']}
</issue>

The following files were selected from the repository at the base commit:

{context}
Return only the unified git diff."""
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ]
        rendered = tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True,
            enable_thinking=CONFIG["enable_thinking"],
        )
        (EXPERIMENT / "prompts" / f"{instance_id}.txt").write_text(rendered, encoding="utf-8")
        (EXPERIMENT / "prompts" / f"{instance_id}.files.json").write_text(
            json.dumps(selected, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        encoded = tokenizer(
            rendered,
            return_tensors="pt",
            add_special_tokens=False,
            truncation=True,
            max_length=CONFIG["max_input_tokens"],
        ).to("cuda:0")

        started = time.monotonic()
        with torch.no_grad():
            generated = model.generate(
                **encoded,
                max_new_tokens=CONFIG["max_new_tokens"],
                do_sample=CONFIG["do_sample"],
                use_cache=True,
                pad_token_id=tokenizer.pad_token_id,
                eos_token_id=tokenizer.eos_token_id,
            )
        elapsed = time.monotonic() - started
        new_ids = generated[0, encoded["input_ids"].shape[1] :]
        response = tokenizer.decode(new_ids, skip_special_tokens=True)
        (EXPERIMENT / "outputs" / f"{instance_id}.txt").write_text(response + "\n", encoding="utf-8")

        patch = extract_diff(response)
        patch_status = "no_diff"
        patch_note = "model output did not contain `diff --git`"
        final_patch = ""
        if patch:
            safe, patch_note = safe_patch_paths(patch)
            if safe:
                check = run(["git", "apply", "--check", "--whitespace=nowarn", "-"], cwd=repo, input_text=patch)
                if check.returncode == 0:
                    applied = run(["git", "apply", "--whitespace=nowarn", "-"], cwd=repo, input_text=patch)
                    if applied.returncode == 0:
                        patch_status = "applied"
                        final_patch = run(["git", "diff", "--binary"], cwd=repo).stdout
                        if final_patch:
                            (EXPERIMENT / "patches" / f"{instance_id}.patch").write_text(
                                final_patch, encoding="utf-8"
                            )
                            patch_note = "parsed, safety-checked, and applied cleanly"
                        else:
                            patch_status = "no_effect"
                            patch_note = "patch applied but produced no repository change"
                    else:
                        patch_status = "apply_failed"
                        patch_note = applied.stdout
                else:
                    patch_status = "check_failed"
                    patch_note = check.stdout
            else:
                patch_status = "unsafe"

        prediction = {
            "instance_id": instance_id,
            "model_name_or_path": str(model_path),
            "model_patch": final_patch,
        }
        predictions.append(prediction)
        record = {
            "instance_id": instance_id,
            "finished_at_utc": datetime.now(timezone.utc).isoformat(),
            "input_tokens": int(encoded["input_ids"].shape[1]),
            "generated_tokens": int(new_ids.numel()),
            "generation_seconds": round(elapsed, 3),
            "selected_files": selected,
            "patch_status": patch_status,
            "patch_note": patch_note,
            "changed_files": run(["git", "diff", "--name-only"], cwd=repo).stdout.splitlines(),
        }
        summary.append(record)
        (EXPERIMENT / "metadata" / f"{instance_id}.json").write_text(
            json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(
            f"[{index}/{len(task_rows)}] {instance_id}: {patch_status}, "
            f"input={record['input_tokens']}, output={record['generated_tokens']}, {elapsed:.1f}s",
            flush=True,
        )

    with (EXPERIMENT / "predictions.jsonl").open("w", encoding="utf-8") as handle:
        for prediction in predictions:
            handle.write(json.dumps(prediction, ensure_ascii=False) + "\n")
    (EXPERIMENT / "metadata" / "inference_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Wrote {len(predictions)} predictions to {EXPERIMENT / 'predictions.jsonl'}")


if __name__ == "__main__":
    main()
