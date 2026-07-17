"""Adapters that convert external dataset formats into :class:`Example`.

Public QA benchmarks and in-house datasets rarely match this kit's golden
schema. Rather than couple the kit to any one benchmark, these adapters map
arbitrary records (dicts or CSV rows) onto :class:`Example` by letting the caller
name which fields carry the question, reference, required terms, and contexts.

No network and no third-party dependencies: the caller brings the records (from
a file, a `datasets` load, an API — whatever), and the adapter only reshapes
them. That keeps benchmark support flexible without bloating the core.
"""

from __future__ import annotations

import csv
from collections.abc import Iterable
from typing import Any

from agent_eval.datasets import Example


def from_records(
    records: Iterable[dict[str, Any]],
    *,
    question_key: str = "question",
    reference_key: str = "reference",
    must_include_key: str | None = None,
    contexts_key: str | None = None,
) -> list[Example]:
    """Map an iterable of dict records onto :class:`Example`.

    Args:
        records: The source rows (e.g. parsed JSON, a benchmark's items).
        question_key: Field holding the question text.
        reference_key: Field holding the reference answer.
        must_include_key: Optional field holding required terms (a list of
            strings, or a single string treated as one term).
        contexts_key: Optional field holding ground-truth contexts (a list of
            strings, or a single string).

    Returns:
        The converted examples, in input order.

    Raises:
        ValueError: If a record lacks a non-empty question or reference.
    """
    examples: list[Example] = []
    for idx, record in enumerate(records):
        question = _require_text(record, question_key, idx)
        reference = _require_text(record, reference_key, idx)
        examples.append(
            Example(
                question=question,
                reference=reference,
                must_include=_as_str_list(record.get(must_include_key)) if must_include_key else [],
                contexts=_as_str_list(record.get(contexts_key)) if contexts_key else [],
            )
        )
    return examples


def from_csv(
    path: str,
    *,
    question_key: str = "question",
    reference_key: str = "reference",
    must_include_key: str | None = None,
    contexts_key: str | None = None,
    delimiter: str = ",",
) -> list[Example]:
    """Load a CSV with a header row and convert it via :func:`from_records`.

    List-valued columns (``must_include``, ``contexts``) are split on ``;``.
    """
    with open(path, newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle, delimiter=delimiter))

    def split_lists(row: dict[str, Any]) -> dict[str, Any]:
        out = dict(row)
        for key in (must_include_key, contexts_key):
            if key and isinstance(out.get(key), str):
                out[key] = [part.strip() for part in out[key].split(";") if part.strip()]
        return out

    return from_records(
        (split_lists(r) for r in rows),
        question_key=question_key,
        reference_key=reference_key,
        must_include_key=must_include_key,
        contexts_key=contexts_key,
    )


def _require_text(record: dict[str, Any], key: str, idx: int) -> str:
    value = record.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"record {idx}: field {key!r} must be a non-empty string")
    return value


def _as_str_list(value: object) -> list[str]:
    """Coerce a value into a list of strings (single string -> one-item list)."""
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, Iterable):
        return [str(item) for item in value]
    return [str(value)]
