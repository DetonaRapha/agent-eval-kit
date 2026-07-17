"""Golden dataset loading.

A golden dataset is a JSONL file, one example per line, pairing a question with
its ground-truth reference answer. It is the yardstick the system under test is
measured against.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Example:
    """One evaluation item: a question and its ground truth.

    Attributes:
        question: The prompt handed to the system under test.
        reference: The reference (ground-truth) answer to compare against.
        must_include: Terms the answer is expected to contain. Powers
            keyword-recall; empty means "no keyword requirement".
        contexts: Optional ground-truth contexts. Reserved for context-quality
            metrics; the deterministic groundedness proxy uses the SUT's own
            retrieved contexts, not these.
    """

    question: str
    reference: str
    must_include: list[str] = field(default_factory=list)
    contexts: list[str] = field(default_factory=list)


class DatasetError(ValueError):
    """Raised when a golden dataset is malformed."""


def load_golden(path: str) -> list[Example]:
    """Load a golden dataset from a JSONL file.

    Reads line by line, skipping blank lines. Each non-blank line must be a JSON
    object with non-empty ``question`` and ``reference`` fields. ``must_include``
    and ``contexts``, when present, must be lists of strings.

    Args:
        path: Filesystem path to the ``.jsonl`` dataset.

    Returns:
        The parsed examples, in file order.

    Raises:
        DatasetError: If the file is empty, or any line is not valid JSON, is not
            an object, or is missing required fields.
        FileNotFoundError: If ``path`` does not exist.
    """
    examples: list[Example] = []

    with open(path, encoding="utf-8") as handle:
        for lineno, raw in enumerate(handle, start=1):
            line = raw.strip()
            if not line:
                continue

            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise DatasetError(f"{path}:{lineno}: invalid JSON: {exc.msg}") from exc

            examples.append(_parse_record(record, path, lineno))

    if not examples:
        raise DatasetError(f"{path}: no examples found (file is empty or all blank)")

    return examples


def _parse_record(record: object, path: str, lineno: int) -> Example:
    """Validate one decoded JSON record and build an :class:`Example`."""
    where = f"{path}:{lineno}"

    if not isinstance(record, dict):
        raise DatasetError(f"{where}: each line must be a JSON object, got {type(record).__name__}")

    question = _require_nonempty_str(record, "question", where)
    reference = _require_nonempty_str(record, "reference", where)
    must_include = _optional_str_list(record, "must_include", where)
    contexts = _optional_str_list(record, "contexts", where)

    return Example(
        question=question,
        reference=reference,
        must_include=must_include,
        contexts=contexts,
    )


def _require_nonempty_str(record: dict[str, Any], key: str, where: str) -> str:
    value = record.get(key)
    if not isinstance(value, str) or not value.strip():
        raise DatasetError(f"{where}: field '{key}' is required and must be a non-empty string")
    return value


def _optional_str_list(record: dict[str, Any], key: str, where: str) -> list[str]:
    value = record.get(key, [])
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise DatasetError(f"{where}: field '{key}' must be a list of strings")
    return list(value)
