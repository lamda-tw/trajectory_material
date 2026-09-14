#!/usr/bin/env python3
"""Build and verify one causal ReAct SFT trajectory for AppWorld task 229360a_3."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from jinja2 import Template


TASK_ID = "229360a_3"
TASK_FAMILY = TASK_ID.rsplit("_", 1)[0]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--work-root", type=Path, required=True)
    parser.add_argument("--prompt-file", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser.parse_args()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def text_to_messages(text: str) -> list[dict[str, str]]:
    messages: list[dict[str, str | None]] = []
    last_start = 0
    for match in re.finditer(r"(USER|ASSISTANT|SYSTEM):\n", text, flags=re.IGNORECASE):
        last_end = match.start()
        if not messages and last_end != 0:
            raise ValueError("prompt starts before the first role marker")
        if messages:
            messages[-1]["content"] = text[last_start:last_end]
        messages.append({"role": match.group(1).lower(), "content": None})
        last_start = match.end()
    if not messages:
        raise ValueError("prompt contains no role markers")
    messages[-1]["content"] = text[last_start:]
    return [{"role": str(m["role"]), "content": str(m["content"])} for m in messages]


def assistant_message(reasoning: str, code: str) -> dict[str, str]:
    return {
        "role": "assistant",
        "content": f"{reasoning.strip()}\n\n```python\n{code.strip()}\n```\n\n",
    }


def observation_message(output: str) -> dict[str, str]:
    suffix = "" if output.endswith("\n") else "\n"
    return {"role": "user", "content": f"Output:\n```\n{output}{suffix}```\n\n"}


def dump_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    args = parse_args()
    source_root = args.source_root.resolve()
    work_root = args.work_root.resolve()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    work_root.mkdir(parents=True, exist_ok=True)

    source_data = source_root / "data"
    work_data = work_root / "data"
    if not source_data.is_dir():
        raise FileNotFoundError(source_data)
    if not work_data.exists():
        work_data.symlink_to(source_data, target_is_directory=True)

    os.environ["APPWORLD_ROOT"] = str(work_root)
    from appworld import AppWorld, update_root

    update_root(str(work_root))
    specs_path = source_data / "tasks" / TASK_ID / "specs.json"
    specs = json.loads(specs_path.read_text(encoding="utf-8"))
    prompt_template = args.prompt_file.read_text(encoding="utf-8").lstrip()

    actions = [
        (
            "I need to preserve every liked or downloaded song, preserve every liked album or album "
            "whose songs are all downloaded, and leave playlists untouched. Before calling the task "
            "APIs, I will inspect their parameters and success schemas.",
            '''api_plan = {
    "supervisor": ["show_profile", "show_account_passwords", "complete_task"],
    "spotify": [
        "login",
        "show_song_library",
        "show_album_library",
        "show_downloaded_songs",
        "show_liked_songs",
        "show_liked_albums",
        "remove_song_from_library",
        "remove_album_from_library",
    ],
}
for app_name, api_names in api_plan.items():
    for api_name in api_names:
        doc = apis.api_docs.show_api_doc(app_name=app_name, api_name=api_name)
        params = [
            {
                "name": item["name"],
                "type": item["type"],
                "required": item["required"],
                "default": item["default"],
            }
            for item in doc["parameters"]
        ]
        print({
            "app": app_name,
            "api": api_name,
            "parameters": params,
            "success_schema": doc["response_schemas"]["success"],
        })''',
        ),
        (
            "The API specifications confirm that I should obtain the supervisor's current Spotify "
            "credentials and use the returned access token in later calls. I will keep the password "
            "and token in REPL variables and avoid printing their concrete values.",
            '''profile = apis.supervisor.show_profile()
passwords = apis.supervisor.show_account_passwords()
spotify_password = next(
    item["password"] for item in passwords if item["account_name"] == "spotify"
)
login_result = apis.spotify.login(
    username=profile["email"],
    password=spotify_password,
)
spotify_access_token = login_result["access_token"]
print({"profile_email": profile["email"], "spotify_login": "successful"})''',
        ),
        (
            "I am authenticated. I will now read every page of the song library, album library, "
            "downloaded songs, liked songs, and liked albums. These are read-only calls. I will print "
            "counts and representative records so that the next decision is grounded in observations.",
            '''def collect_all(api_function):
    rows = []
    for page_index in range(100):
        page = api_function(
            access_token=spotify_access_token,
            page_index=page_index,
            page_limit=20,
        )
        if not page:
            break
        rows.extend(page)
        if len(page) < 20:
            break
    return rows

library_songs = collect_all(apis.spotify.show_song_library)
library_albums = collect_all(apis.spotify.show_album_library)
downloaded_songs = collect_all(apis.spotify.show_downloaded_songs)
liked_songs = collect_all(apis.spotify.show_liked_songs)
liked_albums = collect_all(apis.spotify.show_liked_albums)
collections = {
    "library_songs": library_songs,
    "library_albums": library_albums,
    "downloaded_songs": downloaded_songs,
    "liked_songs": liked_songs,
    "liked_albums": liked_albums,
}
print({
    name: {"count": len(rows), "sample": rows[0] if rows else None}
    for name, rows in collections.items()
})''',
        ),
        (
            "The observations expose the relevant IDs and album song membership. I will compute the "
            "exact deletion candidates without changing state: a song is removed only if it is neither "
            "liked nor downloaded; an album is removed only if it is neither liked nor fully downloaded.",
            '''downloaded_song_ids = {item["song_id"] for item in downloaded_songs}
liked_song_ids = {item["song_id"] for item in liked_songs}
liked_album_ids = {item["album_id"] for item in liked_albums}

song_ids_to_remove = sorted(
    item["song_id"]
    for item in library_songs
    if item["song_id"] not in downloaded_song_ids
    and item["song_id"] not in liked_song_ids
)
album_ids_to_remove = sorted(
    item["album_id"]
    for item in library_albums
    if item["album_id"] not in liked_album_ids
    and not all(song_id in downloaded_song_ids for song_id in item["song_ids"])
)
print({
    "song_ids_to_remove": song_ids_to_remove,
    "album_ids_to_remove": album_ids_to_remove,
})''',
        ),
        (
            "The candidates were derived only from observed library, like, and download data. I will "
            "remove exactly those songs and albums and make no playlist calls.",
            '''for song_id in song_ids_to_remove:
    apis.spotify.remove_song_from_library(
        access_token=spotify_access_token,
        song_id=song_id,
    )
for album_id in album_ids_to_remove:
    apis.spotify.remove_album_from_library(
        access_token=spotify_access_token,
        album_id=album_id,
    )
print({
    "removed_song_ids": song_ids_to_remove,
    "removed_album_ids": album_ids_to_remove,
})''',
        ),
        (
            "The requested deletions completed. Before marking the task complete, I will re-read both "
            "libraries and verify that every remaining song and album satisfies the requested keep rule "
            "and that every computed deletion candidate is absent.",
            '''remaining_songs = collect_all(apis.spotify.show_song_library)
remaining_albums = collect_all(apis.spotify.show_album_library)
remaining_song_ids = {item["song_id"] for item in remaining_songs}
remaining_album_ids = {item["album_id"] for item in remaining_albums}

songs_valid = all(
    song_id in downloaded_song_ids or song_id in liked_song_ids
    for song_id in remaining_song_ids
)
albums_valid = all(
    item["album_id"] in liked_album_ids
    or all(song_id in downloaded_song_ids for song_id in item["song_ids"])
    for item in remaining_albums
)
deleted_songs_absent = not (set(song_ids_to_remove) & remaining_song_ids)
deleted_albums_absent = not (set(album_ids_to_remove) & remaining_album_ids)
assert songs_valid and albums_valid
assert deleted_songs_absent and deleted_albums_absent
print({
    "remaining_song_count": len(remaining_songs),
    "remaining_album_count": len(remaining_albums),
    "songs_valid": songs_valid,
    "albums_valid": albums_valid,
    "deleted_songs_absent": deleted_songs_absent,
    "deleted_albums_absent": deleted_albums_absent,
    "playlist_library_modified": False,
})''',
        ),
        (
            "All postcondition checks passed and the playlist library was never modified. I can now "
            "mark the task complete without an answer value because this is an action task.",
            '''apis.supervisor.complete_task(status="success")''',
        ),
    ]

    records: list[dict[str, Any]] = []
    trajectory_steps: list[dict[str, Any]] = []
    experiment_name = "codex_ground_truth_guided_react_229360a_3"

    with AppWorld(task_id=TASK_ID, experiment_name=experiment_name) as world:
        app_descriptions = json.dumps(
            [
                {"name": name, "description": description}
                for name, description in world.task.app_descriptions.items()
            ],
            ensure_ascii=False,
            indent=1,
        )
        rendered_prompt = Template(prompt_template).render(
            instruction=world.task.instruction,
            main_user=world.task.supervisor,
            app_descriptions=app_descriptions,
        )
        initial_messages = text_to_messages(rendered_prompt + "\n\n")
        history = copy.deepcopy(initial_messages)
        for step_index, (reasoning, code) in enumerate(actions, start=1):
            completion = assistant_message(reasoning, code)
            output = world.execute(code)
            observation = observation_message(output)
            record = {
                "id": f"{TASK_ID}::step_{step_index:02d}",
                "prompt": copy.deepcopy(history),
                "completion": [copy.deepcopy(completion)],
                "metadata": {
                    "trajectory_id": TASK_ID,
                    "task_id": TASK_ID,
                    "task_family": TASK_FAMILY,
                    "step_index": step_index,
                    "source": "ground_truth_api_calls_guided_codex_reconstruction",
                    "loss_scope": "assistant_completion_only",
                    "privileged_context_in_prompt": False,
                },
            }
            records.append(record)
            trajectory_steps.append(
                {
                    "step_index": step_index,
                    "assistant": completion,
                    "environment": observation,
                    "raw_environment_output": output,
                }
            )
            history.extend([completion, observation])

        evaluation = world.evaluate().to_dict()

    success = bool(evaluation.get("success"))
    if not success:
        raise RuntimeError(f"official evaluator rejected generated trajectory: {evaluation}")
    model_visible_text = json.dumps(
        [
            {
                "prompt": record["prompt"],
                "completion": record["completion"],
            }
            for record in records
        ],
        ensure_ascii=False,
    )
    forbidden_model_visible_terms = [
        "private_data",
        "evaluation_code",
        "compiled_solution",
        "ground_truth.api_calls",
    ]
    found_terms = [term for term in forbidden_model_visible_terms if term in model_visible_text]
    if found_terms:
        raise RuntimeError(f"privileged terms leaked into model-visible messages: {found_terms}")
    for record in records:
        record["metadata"]["verified_success"] = True

    train_path = output_dir / "train.jsonl"
    with train_path.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")

    trajectory_path = output_dir / "trajectory.json"
    dump_json(
        trajectory_path,
        {
            "task_id": TASK_ID,
            "task_family": TASK_FAMILY,
            "initial_messages": initial_messages,
            "steps": trajectory_steps,
            "final_messages": history,
            "evaluation": evaluation,
        },
    )
    evaluation_path = output_dir / "evaluation.json"
    dump_json(evaluation_path, evaluation)
    manifest_path = output_dir / "manifest.json"
    dump_json(
        manifest_path,
        {
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "task_id": TASK_ID,
            "task_family": TASK_FAMILY,
            "num_steps": len(actions),
            "num_sft_records": len(records),
            "official_evaluator_success": success,
            "source_specs_sha256": sha256(specs_path),
            "prompt_template_sha256": sha256(args.prompt_file),
            "outputs": {
                "train.jsonl": sha256(train_path),
                "trajectory.json": sha256(trajectory_path),
                "evaluation.json": sha256(evaluation_path),
            },
            "construction_notes": [
                "Ground-truth API calls were used only as an action-plan reference.",
                "All observations were captured from a fresh AppWorld execution.",
                "No ground-truth solution, evaluation code, private_data, or test_data appears in prompts.",
                "Credentials and access tokens stay in REPL variables and are not printed into SFT observations.",
                "Each JSONL row trains one assistant turn with the exact preceding observable history.",
            ],
        },
    )
    print(json.dumps({
        "status": "ok",
        "task_id": TASK_ID,
        "num_steps": len(actions),
        "success": success,
        "output_dir": str(output_dir),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
