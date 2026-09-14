#!/usr/bin/env python3
"""Prepare and hydrate shared bare mirrors for a frozen SWE-bench selection."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import tempfile
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path


def atomic_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def run(command: list[str], *, env: dict[str, str] | None = None, capture: bool = False) -> subprocess.CompletedProcess[str]:
    print("+", " ".join(command), flush=True)
    return subprocess.run(
        command,
        check=True,
        text=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.PIPE if capture else None,
        env=env,
    )


def object_exists(mirror: Path, commit: str) -> bool:
    return subprocess.run(
        ["git", f"--git-dir={mirror}", "cat-file", "-e", f"{commit}^{{commit}}"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    ).returncode == 0


def hydrate_tree(mirror: Path, commit: str) -> None:
    archive = subprocess.Popen(
        ["git", f"--git-dir={mirror}", "archive", "--format=tar", commit],
        stdout=subprocess.PIPE,
    )
    assert archive.stdout is not None
    listing = subprocess.run(["tar", "-tf", "-"], stdin=archive.stdout, stdout=subprocess.DEVNULL)
    archive.stdout.close()
    archive_status = archive.wait()
    if archive_status != 0 or listing.returncode != 0:
        raise subprocess.CalledProcessError(archive_status or listing.returncode, "git archive | tar -tf -")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--selected", type=Path, required=True)
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--metadata", type=Path, required=True)
    args = parser.parse_args()

    selected = args.selected.resolve(strict=True)
    cache = args.cache.resolve()
    cache.mkdir(parents=True, exist_ok=True)
    tasks = [json.loads(line) for line in selected.read_text(encoding="utf-8").splitlines() if line.strip()]
    by_repo: dict[str, list[dict]] = defaultdict(list)
    for task in tasks:
        by_repo[task["repo"]].append(task)

    started = datetime.now(timezone.utc)
    records = []
    for repository in sorted(by_repo):
        mirror = cache / f"{repository.replace('/', '__')}.git"
        url = f"https://github.com/{repository}.git"
        record = {
            "repo": repository,
            "url": url,
            "mirror": str(mirror),
            "created": False,
            "fetched": False,
            "commits": [],
        }
        repo_start = time.monotonic()
        if not mirror.exists():
            run(["git", "clone", "--mirror", "--filter=blob:none", url, str(mirror)])
            record["created"] = True
        elif not (mirror / "HEAD").exists():
            raise RuntimeError(f"Cache path exists but is not a bare Git repository: {mirror}")

        missing = sorted({task["base_commit"] for task in by_repo[repository] if not object_exists(mirror, task["base_commit"])})
        if missing:
            run(
                [
                    "git",
                    f"--git-dir={mirror}",
                    "fetch",
                    "--prune",
                    "--filter=blob:none",
                    "origin",
                    "+refs/heads/*:refs/heads/*",
                    "+refs/tags/*:refs/tags/*",
                ]
            )
            record["fetched"] = True

        for task in by_repo[repository]:
            commit = task["base_commit"]
            if not object_exists(mirror, commit):
                raise RuntimeError(f"Required commit {commit} is absent from {mirror}")
            print(f"Hydrating {task['instance_id']} at {commit}", flush=True)
            hydrate_tree(mirror, commit)
            record["commits"].append({"instance_id": task["instance_id"], "base_commit": commit, "hydrated": True})

        record["elapsed_seconds"] = round(time.monotonic() - repo_start, 3)
        record["disk_bytes"] = int(
            run(["du", "-sb", str(mirror)], capture=True).stdout.split()[0]
        )
        records.append(record)
        atomic_json(
            args.metadata,
            {
                "schema_version": 1,
                "started_at_utc": started.isoformat(),
                "updated_at_utc": datetime.now(timezone.utc).isoformat(),
                "complete": False,
                "repositories": records,
            },
        )

    atomic_json(
        args.metadata,
        {
            "schema_version": 1,
            "started_at_utc": started.isoformat(),
            "finished_at_utc": datetime.now(timezone.utc).isoformat(),
            "complete": True,
            "repositories": records,
        },
    )
    print(f"Prepared {len(records)} repositories for {len(tasks)} tasks", flush=True)


if __name__ == "__main__":
    main()
