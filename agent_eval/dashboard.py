"""Static multi-run dashboard.

``Scorecard.to_html`` renders a single run. This renders *many*: point it at a
directory of saved run files (from ``--save-run``) and it produces one
self-contained HTML page comparing every run on every metric — a dashboard
without a server. It reads the same JSON the kit already writes; nothing to host.

Usage:

    python -m agent_eval.dashboard runs/ -o dashboard.html
"""

from __future__ import annotations

import argparse
import html
import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from agent_eval.scorecard import LATENCY_KEY


@dataclass(frozen=True)
class _Run:
    name: str
    passed: bool
    aggregate: dict[str, float]


def build_dashboard(runs_dir: str) -> str:
    """Render an HTML dashboard for every ``*.json`` run in ``runs_dir``.

    Runs are ordered by filename. Files without an ``aggregate`` section are
    skipped. Metric columns are the union across all runs, thresholded-style
    ordering is not applied here (runs may differ) — metrics are sorted by name.
    """
    runs = _load_runs(runs_dir)
    if not runs:
        body = "<p><em>No runs found in this directory.</em></p>"
        return _TEMPLATE.format(count=0, table=body)

    metrics = sorted({m for run in runs for m in run.aggregate if m != LATENCY_KEY})
    header = (
        "<tr><th>run</th><th>verdict</th>"
        + "".join(f"<th>{_esc(m)}</th>" for m in metrics)
        + "</tr>"
    )

    rows = []
    for run in runs:
        verdict = '<td class="pass">PASS</td>' if run.passed else '<td class="fail">FAIL</td>'
        cells = "".join(_metric_cell(run.aggregate.get(m)) for m in metrics)
        rows.append(f"<tr><td>{_esc(run.name)}</td>{verdict}{cells}</tr>")

    table = "<table><thead>" + header + "</thead><tbody>\n" + "\n".join(rows) + "\n</tbody></table>"
    return _TEMPLATE.format(count=len(runs), table=table)


def _load_runs(runs_dir: str) -> list[_Run]:
    directory = Path(runs_dir)
    runs: list[_Run] = []
    for path in sorted(directory.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        aggregate = payload.get("aggregate")
        if not isinstance(aggregate, dict):
            continue
        runs.append(
            _Run(
                name=path.stem,
                passed=bool(payload.get("passed", False)),
                aggregate={str(k): float(v) for k, v in aggregate.items()},
            )
        )
    return runs


def _metric_cell(value: float | None) -> str:
    if value is None:
        return '<td class="muted">—</td>'
    return f"<td>{value:.3f}</td>"


def _esc(text: str) -> str:
    return html.escape(str(text), quote=True)


def main(argv: Sequence[str] | None = None) -> int:
    """CLI: write an HTML dashboard for a directory of saved runs."""
    parser = argparse.ArgumentParser(
        prog="agent_eval.dashboard",
        description="Build a static HTML dashboard from a directory of saved runs.",
    )
    parser.add_argument("runs_dir", help="directory containing saved run *.json files.")
    parser.add_argument(
        "-o",
        "--output",
        default="dashboard.html",
        help="output HTML path (default: dashboard.html).",
    )
    args = parser.parse_args(argv)

    html_out = build_dashboard(args.runs_dir)
    Path(args.output).write_text(html_out, encoding="utf-8")
    print(f"wrote {args.output}")
    return 0


_TEMPLATE = """\
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>agent-eval-kit — Runs Dashboard</title>
<style>
  :root {{ color-scheme: light dark; }}
  body {{ font-family: system-ui, -apple-system, Segoe UI, Roboto, sans-serif;
         margin: 2rem auto; max-width: 1100px; padding: 0 1rem; line-height: 1.5; }}
  h1 {{ font-size: 1.5rem; margin-bottom: 0.25rem; }}
  .sub {{ color: #6e7781; margin: 0.25rem 0 1.5rem; }}
  table {{ border-collapse: collapse; width: 100%; font-variant-numeric: tabular-nums; }}
  th, td {{ text-align: right; padding: 0.4rem 0.6rem; border-bottom: 1px solid #d0d7de; }}
  th:first-child, td:first-child {{ text-align: left; }}
  thead th {{ border-bottom: 2px solid #57606a; }}
  td.pass {{ color: #1a7f37; font-weight: 700; }}
  td.fail {{ color: #cf222e; font-weight: 700; }}
  td.muted {{ color: #8c959f; }}
  .wrap {{ overflow-x: auto; }}
</style>
</head>
<body>
<h1>Runs Dashboard</h1>
<p class="sub">{count} run(s).</p>
<div class="wrap">
{table}
</div>
</body>
</html>
"""


if __name__ == "__main__":
    import sys

    sys.exit(main())
