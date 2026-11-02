"""Prepare the unified v3 trajectory input. No judge calls or trajectory execution."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path


def prepare(source: dict, trajectory_id: str) -> dict:
    messages = source["initial_messages"]
    task_messages = [
        m["content"] for m in messages
        if m["role"] == "user" and "solve the actual task:" in m["content"]
    ]
    instructions = [
        m["content"] for m in messages
        if m["role"] == "user" and m["content"].startswith("**Key instructions**")
    ]
    if len(task_messages) != 1 or len(instructions) != 1:
        raise ValueError("Expected exactly one actual task and one instruction block")
    reference_docs = [
        m["content"] for m in messages
        if m["role"] == "user"
        and all(key in m["content"] for key in ('"api_name"', '"parameters"', '"response_schemas"'))
    ]
    bootstrap = re.findall(r"```python\n(.*?)```", messages[0]["content"], flags=re.S)
    if len(bootstrap) != 3 or not all("apis.api_docs." in code for code in bootstrap):
        raise ValueError("Expected the three initially supplied API discovery entry points")
    reference_docs.insert(0, "Initially supplied API discovery entry points (reference only):\n" + "\n".join(bootstrap))
    steps = []
    for s in source["steps"]:
        text = s["text"]
        code = s["code"]
        # Remove only a fenced block whose body matches the actually submitted code.
        # Preserve other text/blocks as commentary, never as executed code.
        commentary = text
        format_flags = []
        if code.strip():
            # Match the actual collector: first closed Python fence, otherwise
            # the first open Python fence through EOF. Stray generic fences are
            # commentary and cannot swallow the submitted Python block.
            block = re.search(r"```python\n(.*?)```", text, flags=re.S)
            if block is None:
                block = re.search(r"```python\n(.*)\Z", text, flags=re.S)
                if block is not None:
                    format_flags.append("unclosed_code_block")
            if block is None or block.group(1).strip() != code.strip():
                raise ValueError(f"Cannot locate submitted code at step {s['step']}")
            commentary = text[:block.start()] + text[block.end():]
        steps.append({
            "id": s["step"],
            "commentary": commentary.strip(),
            "code": code,
            "observation": s["observation"],
        })
        if s.get("finish_reason") == "length":
            format_flags.append("generation_length_limit")
        if format_flags:
            steps[-1]["format_flags"] = format_flags
    ids = [s["id"] for s in steps]
    if ids != list(range(1, len(steps) + 1)):
        raise ValueError("Expected consecutive original step IDs starting at one")
    result = {
        "trajectory_id": trajectory_id,
        "task": task_messages[0],
        "agent_instructions": instructions[0],
        "reference_api_docs": reference_docs,
        "steps": steps,
        "termination": source["termination"],
    }
    # Redact recognizable credential values consistently across code and observations.
    # This preserves identity/equality relations; it does not replace arbitrary IDs.
    strings = [s["observation"] for s in steps]
    secret_pattern = re.compile(
        r'''["'](?:password|access_token|refresh_token)["']\s*:\s*["']([^"'\n]+)["']'''
    )
    secrets = sorted({
        match.group(1) for text in strings for match in secret_pattern.finditer(text)
        if match.group(1) not in {"string", "", "..."}
    })
    mapping = {value: f"<CREDENTIAL_{i + 1}>" for i, value in enumerate(secrets)}
    ordered = sorted(mapping, key=len, reverse=True)

    def redact(value):
        if isinstance(value, str):
            for secret in ordered:
                value = value.replace(secret, mapping[secret])
            return value
        if isinstance(value, list):
            return [redact(v) for v in value]
        if isinstance(value, dict):
            return {k: redact(v) for k, v in value.items()}
        return value

    return redact(result)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("trajectory", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--trajectory-id", help="Optional source-qualified ID to distinguish policy checkpoints")
    args = parser.parse_args()
    raw = args.trajectory.read_bytes()
    payload = prepare(json.loads(raw), args.trajectory_id or args.trajectory.stem)
    # Avoid silently replacing a previously reviewed input.
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(json.dumps({
        "output": str(args.output.resolve()),
        "steps": len(payload["steps"]),
        "source_sha256": hashlib.sha256(raw).hexdigest(),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
