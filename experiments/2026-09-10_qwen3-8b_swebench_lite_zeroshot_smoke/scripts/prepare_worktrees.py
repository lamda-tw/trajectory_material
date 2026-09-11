#!/usr/bin/env python3
"""Select the fixed dev tasks and prepare isolated base-commit checkouts."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path


EXPERIMENT = Path(__file__).resolve().parents[1]
CONFIG = json.loads((EXPERIMENT / "config.json").read_text(encoding="utf-8"))


def run(command: list[str], *, cwd: Path | None = None) -> str:
    result = subprocess.run(
        command,
        cwd=cwd,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    return result.stdout


def safe_component(value: str) -> str:
    return value.replace("/", "__")


def main() -> None:
    wanted = set(CONFIG["instance_ids"])
    rows: dict[str, dict] = {}
    with Path(CONFIG["task_view"]).open(encoding="utf-8") as handle:
        for line in handle:
            row = json.loads(line)
            if row["instance_id"] in wanted:
                rows[row["instance_id"]] = row
    missing = wanted.difference(rows)
    if missing:
        raise SystemExit(f"Missing task IDs: {sorted(missing)}")

    data_dir = EXPERIMENT / "data"
    repos_dir = EXPERIMENT / "repos"
    worktrees_dir = EXPERIMENT / "worktrees"
    logs_dir = EXPERIMENT / "logs"
    for directory in (data_dir, repos_dir, worktrees_dir, logs_dir):
        directory.mkdir(parents=True, exist_ok=True)

    ordered = [rows[instance_id] for instance_id in CONFIG["instance_ids"]]
    with (data_dir / "selected_tasks.jsonl").open("w", encoding="utf-8") as handle:
        for row in ordered:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    log_lines: list[str] = []
    unique_repos = {row["repo"] for row in ordered}
    for repo in sorted(unique_repos):
        destination = repos_dir / safe_component(repo)
        if destination.exists():
            log_lines.append(f"reuse source clone: {destination}")
            continue
        url = f"https://github.com/{repo}.git"
        log_lines.append(f"clone {url} -> {destination}")
        log_lines.append(run(["git", "clone", "--filter=blob:none", url, str(destination)]))

    for row in ordered:
        instance_id = row["instance_id"]
        source = repos_dir / safe_component(row["repo"])
        destination = worktrees_dir / instance_id
        if destination.exists():
            head = run(["git", "rev-parse", "HEAD"], cwd=destination).strip()
            if head != row["base_commit"]:
                raise SystemExit(
                    f"Existing worktree {destination} is at {head}, expected {row['base_commit']}"
                )
            if run(["git", "status", "--porcelain"], cwd=destination).strip():
                raise SystemExit(f"Existing worktree is not clean: {destination}")
            log_lines.append(f"reuse clean worktree: {destination}")
            continue
        # The source repositories are partial clones. A second local clone can
        # copy commit/tree objects without the historical blobs needed by an
        # old SWE-bench base commit. Creating a worktree from the source clone
        # lets its promisor remote fetch exactly those missing blobs.
        log_lines.append(f"git worktree {source} -> {destination}")
        log_lines.append(
            run(
                [
                    "git",
                    "-C",
                    str(source),
                    "worktree",
                    "add",
                    "--detach",
                    str(destination),
                    row["base_commit"],
                ]
            )
        )
        head = run(["git", "rev-parse", "HEAD"], cwd=destination).strip()
        if head != row["base_commit"]:
            raise SystemExit(f"Checkout verification failed for {instance_id}: {head}")

    (logs_dir / "prepare.log").write_text("\n".join(log_lines) + "\n", encoding="utf-8")
    print(f"Prepared {len(ordered)} tasks under {EXPERIMENT}")


if __name__ == "__main__":
    main()
