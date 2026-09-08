from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from .catalog import INDICATORS
from .evaluator import TrajectoryEvaluator
from .reporting import write_report_bundle


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="eval4trajectory",
        description="Score exported user-agent HTML trajectories with deterministic checks.",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list", help="List the 12 implemented trajectory indicators.")
    evaluate = sub.add_parser("evaluate", help="Evaluate one exported trajectory HTML.")
    evaluate.add_argument("--trajectory", type=Path, required=True)
    evaluate.add_argument("--output", type=Path, required=True)
    evaluate.add_argument("--json", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "list":
        for item in INDICATORS:
            print(f"{item.check_id}\t{item.max_score:g}\t{item.title}")
        print("I3\t4\t负反馈修复闭环")
        return 0
    report = TrajectoryEvaluator().evaluate(args.trajectory)
    write_report_bundle(report, args.output)
    if args.json:
        print(json.dumps(report.as_dict(), ensure_ascii=False, indent=2))
    else:
        normalized = (
            f"{report.normalized_score:.2f}"
            if report.normalized_score is not None
            else "N/A"
        )
        print(
            f"raw={report.raw_score:.2f}/{report.max_score:.0f} "
            f"normalized={normalized}/100 coverage={report.coverage:.2%} "
            f"passed={str(report.passed).lower()} output={args.output}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

