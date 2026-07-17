"""Command-line entry point.

Wires the pieces together: load the dataset, import the SUT dynamically, build
the judge, run the evaluation, write reports, print the scorecard, and exit with
a status code CI can act on (0 = passed, 1 = failed quality).
"""

from __future__ import annotations

import argparse
import importlib
import os
import sys
from collections.abc import Sequence
from pathlib import Path

from agent_eval.datasets import DatasetError, load_golden
from agent_eval.judges import JUDGE_METRICS, make_judge
from agent_eval.metrics import DETERMINISTIC_METRICS
from agent_eval.runner import evaluate
from agent_eval.scorecard import Scorecard
from agent_eval.sut import SUT

# Default pass bar per metric. Deliberately modest: the point of v0 is to show
# the mechanism, and to let a deliberately-mediocre example SUT still pass while
# a broken one fails. Override per metric with --threshold name=value.
_DEFAULT_THRESHOLDS: dict[str, float] = {
    "relevance": 0.25,
    "faithfulness": 0.25,
    "not_hallucinated": 0.25,
    "keyword_recall": 0.40,
}

_ALL_METRIC_NAMES = (*DETERMINISTIC_METRICS, *JUDGE_METRICS)

# Exit codes, named for clarity at the call sites.
_EXIT_PASSED = 0
_EXIT_FAILED = 1
_EXIT_USAGE = 2


def build_parser() -> argparse.ArgumentParser:
    """Construct the argument parser."""
    parser = argparse.ArgumentParser(
        prog="agent_eval",
        description=(
            "Evaluate an LLM system against a golden dataset and emit a "
            "pass/fail quality scorecard."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "example:\n"
            "  python -m agent_eval \\\n"
            "    --dataset examples/golden.jsonl \\\n"
            "    --sut examples.tiny_rag:answer \\\n"
            "    --judge mock \\\n"
            "    --report out/\n"
        ),
    )
    parser.add_argument(
        "--dataset",
        required=True,
        help="path to the golden dataset (JSONL).",
    )
    parser.add_argument(
        "--sut",
        required=True,
        metavar="MODULE:FUNCTION",
        help="system under test as 'module.path:callable', imported dynamically.",
    )
    parser.add_argument(
        "--judge",
        default="mock",
        choices=("mock", "anthropic"),
        help="judge to use (default: mock; 'anthropic' needs ANTHROPIC_API_KEY).",
    )
    parser.add_argument(
        "--report",
        metavar="DIR",
        help="directory to write report.md and report.json into.",
    )
    parser.add_argument(
        "--threshold",
        action="append",
        default=[],
        metavar="METRIC=VALUE",
        help=(
            "override a pass threshold, e.g. --threshold relevance=0.5. "
            "Repeatable. Known metrics: " + ", ".join(_ALL_METRIC_NAMES) + "."
        ),
    )
    parser.add_argument(
        "--no-default-thresholds",
        action="store_true",
        help="start from an empty threshold set (report-only unless --threshold given).",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point. Returns the process exit code."""
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        dataset = load_golden(args.dataset)
    except FileNotFoundError:
        print(f"error: dataset not found: {args.dataset}", file=sys.stderr)
        return _EXIT_USAGE
    except DatasetError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return _EXIT_USAGE

    try:
        sut = _import_sut(args.sut)
    except (ImportError, AttributeError, ValueError) as exc:
        print(f"error: could not load --sut {args.sut!r}: {exc}", file=sys.stderr)
        return _EXIT_USAGE

    try:
        thresholds = _resolve_thresholds(args.threshold, args.no_default_thresholds)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return _EXIT_USAGE

    try:
        judge = make_judge(args.judge)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return _EXIT_USAGE

    scorecard = evaluate(sut, dataset, judge, thresholds)
    scorecard.print_table()

    if args.report:
        _write_reports(scorecard, args.report)

    _print_failures(scorecard)
    return _EXIT_PASSED if scorecard.passed else _EXIT_FAILED


def _import_sut(spec: str) -> SUT:
    """Import a SUT callable from a ``'module:function'`` specification."""
    if ":" not in spec:
        raise ValueError("expected format 'module.path:callable'")

    module_name, _, attr = spec.partition(":")
    if not module_name or not attr:
        raise ValueError("expected format 'module.path:callable'")

    # Make the current working directory importable so example SUTs resolve
    # without installation (e.g. examples.tiny_rag from the repo root).
    cwd = os.getcwd()
    if cwd not in sys.path:
        sys.path.insert(0, cwd)

    module = importlib.import_module(module_name)
    candidate = getattr(module, attr)
    if not callable(candidate):
        raise ValueError(f"{spec!r} is not callable")
    return candidate


def _resolve_thresholds(overrides: list[str], no_defaults: bool) -> dict[str, float]:
    """Merge CLI ``--threshold`` overrides onto the defaults."""
    thresholds: dict[str, float] = {} if no_defaults else dict(_DEFAULT_THRESHOLDS)

    for raw in overrides:
        if "=" not in raw:
            raise ValueError(f"invalid --threshold {raw!r}; expected METRIC=VALUE")
        name, _, value = raw.partition("=")
        name = name.strip()
        try:
            thresholds[name] = float(value)
        except ValueError as exc:
            raise ValueError(f"invalid threshold value in {raw!r}: {exc}") from exc

    return thresholds


def _write_reports(scorecard: Scorecard, report_dir: str) -> None:
    """Write ``report.md`` and ``report.json`` into ``report_dir``."""
    directory = Path(report_dir)
    directory.mkdir(parents=True, exist_ok=True)

    md_path = directory / "report.md"
    json_path = directory / "report.json"
    md_path.write_text(scorecard.to_markdown(), encoding="utf-8")
    json_path.write_text(scorecard.to_json(), encoding="utf-8")

    print(f"\nwrote {md_path}")
    print(f"wrote {json_path}")


def _print_failures(scorecard: Scorecard) -> None:
    """Explain, on stderr, which metrics fell short (if any)."""
    failures = scorecard.failures()
    if not failures:
        return
    print("\nfailing metrics:", file=sys.stderr)
    for metric, (actual, threshold) in sorted(failures.items()):
        print(f"  {metric}: {actual:.3f} < {threshold:.3f}", file=sys.stderr)
