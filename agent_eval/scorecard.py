"""The Scorecard — aggregated results, a pass/fail verdict, and reporting.

The scorecard is what turns evaluation from a report into a *test*: it compares
each aggregated metric against a threshold and fails the run when quality drops
below the bar. That verdict, surfaced as a process exit code, is what lets the
kit sit in CI and block bad output.
"""

from __future__ import annotations

import html
import json
from dataclasses import dataclass, field
from typing import Any

# One per-item result row: heterogeneous by nature (scores are floats,
# `question`/`rationale` are strings), so values are typed as Any.
Row = dict[str, Any]

# Keys used in each per-item row that are not 0..1 scores.
LATENCY_KEY = "latency_ms"
_NON_SCORE_KEYS = frozenset({"question", "rationale", LATENCY_KEY})


@dataclass
class Scorecard:
    """Aggregated evaluation results and the pass/fail verdict.

    Attributes:
        per_item: One dict per example with every metric, plus ``question``,
            ``rationale``, and ``latency_ms``.
        aggregate: Mean of each 0..1 metric across all items.
        thresholds: Minimum acceptable mean per metric. Metrics absent here are
            reported but do not affect the verdict.
        passed: True when every thresholded metric meets or exceeds its bar.
    """

    per_item: list[Row] = field(default_factory=list)
    aggregate: dict[str, float] = field(default_factory=dict)
    thresholds: dict[str, float] = field(default_factory=dict)
    passed: bool = False

    # -- Verdict ---------------------------------------------------------------

    def failures(self) -> dict[str, tuple[float, float]]:
        """Metrics that fell short, mapped to ``(actual, threshold)``."""
        shortfalls: dict[str, tuple[float, float]] = {}
        for metric, minimum in self.thresholds.items():
            actual = self.aggregate.get(metric, 0.0)
            if actual < minimum:
                shortfalls[metric] = (actual, minimum)
        return shortfalls

    # -- Reporting -------------------------------------------------------------

    def to_json(self) -> str:
        """Serialize the full scorecard to indented JSON."""
        payload = {
            "passed": self.passed,
            "aggregate": self.aggregate,
            "thresholds": self.thresholds,
            "failures": {
                metric: {"actual": actual, "threshold": threshold}
                for metric, (actual, threshold) in self.failures().items()
            },
            "per_item": self.per_item,
        }
        return json.dumps(payload, indent=2, ensure_ascii=False)

    def to_markdown(self) -> str:
        """Render a human-readable Markdown report."""
        verdict = "✅ PASS" if self.passed else "❌ FAIL"
        lines = [
            "# Evaluation Scorecard",
            "",
            f"**Verdict: {verdict}** — {len(self.per_item)} example(s) evaluated.",
            "",
            "## Aggregate",
            "",
            "| Metric | Score | Threshold | Status |",
            "| --- | ---: | ---: | :---: |",
        ]
        for metric in self._metric_order():
            score = self.aggregate[metric]
            threshold = self.thresholds.get(metric)
            if threshold is None:
                lines.append(f"| {metric} | {score:.3f} | — | — |")
            else:
                mark = "✅" if score >= threshold else "❌"
                lines.append(f"| {metric} | {score:.3f} | {threshold:.3f} | {mark} |")

        lines += ["", "## Per-item", ""]
        lines += self._per_item_markdown()
        lines.append("")
        return "\n".join(lines)

    def to_html(self) -> str:
        """Render a self-contained HTML report (inline CSS, no external assets).

        The smallest useful "UI": a single file that opens in any browser and
        renders the verdict, the aggregate table, and the per-item breakdown. No
        server, no dependencies — the report reads the same data as ``to_json``.
        """
        passed = self.passed
        verdict_text = "PASS" if passed else "FAIL"
        verdict_class = "pass" if passed else "fail"

        agg_rows = []
        for metric in self._metric_order():
            score = self.aggregate[metric]
            threshold = self.thresholds.get(metric)
            if threshold is None:
                status = '<td class="muted">—</td>'
                thr = '<td class="muted">—</td>'
            else:
                ok = score >= threshold
                thr = f"<td>{threshold:.3f}</td>"
                status = f'<td class="{"ok" if ok else "low"}">{"✓" if ok else "✗"}</td>'
            agg_rows.append(f"<tr><td>{_esc(metric)}</td><td>{score:.3f}</td>{thr}{status}</tr>")

        return _HTML_TEMPLATE.format(
            verdict_class=verdict_class,
            verdict_text=verdict_text,
            count=len(self.per_item),
            aggregate_rows="\n".join(agg_rows),
            per_item_table=self._per_item_html(),
        )

    def print_table(self) -> None:
        """Print a compact aggregate table and the verdict to stdout."""
        verdict = "PASS" if self.passed else "FAIL"
        print(f"\nScorecard - {verdict} ({len(self.per_item)} example(s))")
        print("-" * 48)
        for metric in self._metric_order():
            score = self.aggregate[metric]
            threshold = self.thresholds.get(metric)
            if threshold is None:
                print(f"  {metric:<22} {score:6.3f}   (no threshold)")
            else:
                mark = "ok " if score >= threshold else "LOW"
                print(f"  {metric:<22} {score:6.3f}   >= {threshold:.3f}  [{mark}]")
        print("-" * 48)

    # -- Internals -------------------------------------------------------------

    def _metric_order(self) -> list[str]:
        """Aggregate metrics with thresholded ones first, then alphabetical."""
        thresholded = [m for m in self.aggregate if m in self.thresholds]
        rest = [m for m in self.aggregate if m not in self.thresholds]
        return sorted(thresholded) + sorted(rest)

    def _per_item_markdown(self) -> list[str]:
        if not self.per_item:
            return ["_No items._"]

        score_keys = [key for key in self.per_item[0] if key not in _NON_SCORE_KEYS]
        header = ["#", "question", *score_keys, LATENCY_KEY]
        rows = ["| " + " | ".join(header) + " |", "| " + " | ".join(["---"] * len(header)) + " |"]

        for idx, item in enumerate(self.per_item, start=1):
            question = _truncate(str(item.get("question", "")), 60)
            cells = [str(idx), question]
            cells += [f"{item.get(key, 0.0):.3f}" for key in score_keys]
            cells.append(f"{item.get(LATENCY_KEY, 0.0):.1f}")
            rows.append("| " + " | ".join(cells) + " |")
        return rows

    def _per_item_html(self) -> str:
        if not self.per_item:
            return "<p><em>No items.</em></p>"

        score_keys = [key for key in self.per_item[0] if key not in _NON_SCORE_KEYS]
        headers = ["#", "question", *score_keys, LATENCY_KEY]
        head = "".join(f"<th>{_esc(h)}</th>" for h in headers)

        body_rows = []
        for idx, item in enumerate(self.per_item, start=1):
            question = _truncate(str(item.get("question", "")), 80)
            cells = [str(idx), _esc(question)]
            cells += [f"{item.get(key, 0.0):.3f}" for key in score_keys]
            cells.append(f"{item.get(LATENCY_KEY, 0.0):.1f}")
            body_rows.append("<tr>" + "".join(f"<td>{c}</td>" for c in cells) + "</tr>")

        return (
            "<table><thead><tr>"
            + head
            + "</tr></thead><tbody>\n"
            + "\n".join(body_rows)
            + "\n</tbody></table>"
        )


def _esc(text: str) -> str:
    """HTML-escape a value for safe insertion into the report."""
    return html.escape(str(text), quote=True)


def _truncate(text: str, limit: int) -> str:
    """Collapse whitespace and cut ``text`` to ``limit`` chars for table cells."""
    collapsed = " ".join(text.split())
    if len(collapsed) <= limit:
        return collapsed
    return collapsed[: limit - 1] + "…"


_HTML_TEMPLATE = """\
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Evaluation Scorecard</title>
<style>
  :root {{ color-scheme: light dark; }}
  body {{ font-family: system-ui, -apple-system, Segoe UI, Roboto, sans-serif;
         margin: 2rem auto; max-width: 960px; padding: 0 1rem; line-height: 1.5; }}
  h1 {{ font-size: 1.5rem; margin-bottom: 0.25rem; }}
  .verdict {{ display: inline-block; padding: 0.25rem 0.75rem; border-radius: 999px;
             font-weight: 700; color: #fff; }}
  .verdict.pass {{ background: #1a7f37; }}
  .verdict.fail {{ background: #cf222e; }}
  .sub {{ color: #6e7781; margin: 0.5rem 0 1.5rem; }}
  table {{ border-collapse: collapse; width: 100%; margin: 0.5rem 0 2rem;
          font-variant-numeric: tabular-nums; }}
  th, td {{ text-align: right; padding: 0.4rem 0.6rem; border-bottom: 1px solid #d0d7de; }}
  th:first-child, td:first-child,
  th:nth-child(2), td:nth-child(2) {{ text-align: left; }}
  thead th {{ border-bottom: 2px solid #57606a; }}
  td.ok {{ color: #1a7f37; font-weight: 700; }}
  td.low {{ color: #cf222e; font-weight: 700; }}
  td.muted {{ color: #8c959f; }}
  .wrap {{ overflow-x: auto; }}
</style>
</head>
<body>
<h1>Evaluation Scorecard</h1>
<p><span class="verdict {verdict_class}">{verdict_text}</span></p>
<p class="sub">{count} example(s) evaluated.</p>
<h2>Aggregate</h2>
<div class="wrap">
<table>
<thead><tr><th>Metric</th><th>Score</th><th>Threshold</th><th>Status</th></tr></thead>
<tbody>
{aggregate_rows}
</tbody>
</table>
</div>
<h2>Per-item</h2>
<div class="wrap">
{per_item_table}
</div>
</body>
</html>
"""
