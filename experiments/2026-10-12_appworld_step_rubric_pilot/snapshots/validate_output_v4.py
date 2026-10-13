"""Validate a saved v4 response locally; never call the judge."""
import argparse
import json
from pathlib import Path

import jsonschema


def validate(payload: dict, result: dict) -> None:
    schema = json.loads(Path(__file__).with_name("output_schema_v4.json").read_text())
    jsonschema.Draft202012Validator(schema).validate(result)
    if result["trajectory_id"] != payload["trajectory_id"]:
        raise ValueError("Trajectory ID does not match the input")
    if [row[0] for row in result["steps"]] != [step["id"] for step in payload["steps"]]:
        raise ValueError("Step IDs must match the input exactly once and in order")
    for step, labels, reason in result["steps"]:
        if any(label in "FU" for label in labels):
            if not reason.strip():
                raise ValueError(f"Step {step}: F/U requires a short reason")
        elif reason != "":
            raise ValueError(f"Step {step}: P/N-only rows require an empty reason")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("response", type=Path)
    args = parser.parse_args()
    validate(json.loads(args.input.read_text()), json.loads(args.response.read_text()))
    print("Valid v4 response structure and step coverage; semantic correctness is not verified.")


if __name__ == "__main__":
    main()
