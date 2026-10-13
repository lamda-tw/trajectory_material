"""Read-only evidence viewer; never execute trajectory code."""
from pathlib import Path
import argparse
import json
import re

ROOT = Path(__file__).resolve().parents[1]
p = argparse.ArgumentParser()
p.add_argument("id")
p.add_argument("--start", type=int, default=1)
p.add_argument("--end", type=int, default=999)
p.add_argument("--observation-limit", type=int, default=0)
p.add_argument("--instructions", action="store_true")
args = p.parse_args()
inp = json.loads((ROOT / "inputs" / f"{args.id}.json").read_text())
out = json.loads((ROOT / "runs/scoring" / args.id / "judgement.json").read_text())
labels = {s[0]: s[1:] for s in out["steps"]}


secrets = set()
for step in inp["steps"]:
    for m in re.finditer(r"password\s*=\s*([\"\'])(.*?)\1", step["code"]):
        if m[2] and not m[2].startswith("<"):
            secrets.add(m[2])
    scalar = step["observation"].strip()
    if re.search(r"print\([^)]*password[^)]*\)", step["code"]) and scalar and len(scalar) < 200 and not scalar.startswith(("Execution", "{", "[")):
        secrets.add(scalar)


def redact(text):
    for secret in sorted(secrets, key=len, reverse=True):
        text = text.replace(secret, "<REDACTED>")
    return re.sub(r'''((?:["']?(?:password|access_token|auth_token)["']?)\s*[:=]\s*)(["'])(.*?)\2''',
                  lambda m: m[1] + '"<REDACTED>"', text, flags=re.I)


print("TASK", inp["task"].split("Task:")[-1].strip(), "TERMINATION", inp["termination"])
if args.instructions:
    print("INSTRUCTIONS", inp["agent_instructions"])
    print("REFERENCE DOCS", redact(json.dumps(inp["reference_api_docs"], ensure_ascii=False)))
for s in inp["steps"]:
    if not args.start <= s["id"] <= args.end:
        continue
    print("\nSTEP", s["id"], *labels[s["id"]])
    print("COMMENTARY", redact(s["commentary"]))
    print("CODE", redact(s["code"]))
    obs = redact(s["observation"])
    if re.search(r"print\([^)]*(?:password|access_token)[^)]*\)", s["code"]) and len(obs) < 200 and not obs.startswith(("Execution failed.", "{", "[")):
        obs = "<credential-like scalar observation omitted>" if obs.strip() else obs
    if args.observation_limit and len(obs) > args.observation_limit:
        print("OBSERVATION", obs[:args.observation_limit], f"\n[TRUNCATED VIEW: {len(obs)} characters; input file unchanged]")
    else:
        print("OBSERVATION", obs)
