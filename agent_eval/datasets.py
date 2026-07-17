"""Golden dataset loading.

A golden dataset is a JSONL file, one example per line, pairing a question with
its ground-truth reference answer. It is the yardstick the system under test is
measured against.
"""

from __future__ import annotations

import json
import random
from collections.abc import Iterator
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


def iter_golden(path: str) -> Iterator[Example]:
    """Yield examples from a JSONL dataset one at a time (streaming).

    Reads and parses line by line without holding the whole file in memory, so a
    large dataset can be consumed incrementally. Blank lines are skipped; each
    non-blank line must be a JSON object with non-empty ``question`` and
    ``reference``.

    Raises:
        DatasetError: If any line is not valid JSON, is not an object, or is
            missing required fields.
        FileNotFoundError: If ``path`` does not exist.
    """
    with open(path, encoding="utf-8") as handle:
        for lineno, raw in enumerate(handle, start=1):
            line = raw.strip()
            if not line:
                continue

            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise DatasetError(f"{path}:{lineno}: invalid JSON: {exc.msg}") from exc

            yield _parse_record(record, path, lineno)


def load_golden(path: str, limit: int | None = None) -> list[Example]:
    """Load a golden dataset from a JSONL file into a list.

    Args:
        path: Filesystem path to the ``.jsonl`` dataset.
        limit: If set, stop after reading this many examples. Useful to smoke-test
            a huge dataset without parsing all of it.

    Returns:
        The parsed examples, in file order.

    Raises:
        DatasetError: If the file has no examples, or any line is malformed.
        FileNotFoundError: If ``path`` does not exist.
        ValueError: If ``limit`` is not positive.
    """
    if limit is not None and limit <= 0:
        raise ValueError("limit must be a positive integer")

    examples: list[Example] = []
    for example in iter_golden(path):
        examples.append(example)
        if limit is not None and len(examples) >= limit:
            break

    if not examples:
        raise DatasetError(f"{path}: no examples found (file is empty or all blank)")

    return examples


def sample_dataset(examples: list[Example], n: int, seed: int = 0) -> list[Example]:
    """Return a deterministic random sample of ``n`` examples.

    Sampling is seeded so the same ``(dataset, n, seed)`` always yields the same
    subset — reproducibility is a project invariant. Returns the dataset
    unchanged (order preserved) when ``n`` is at least its size.

    Raises:
        ValueError: If ``n`` is not positive.
    """
    if n <= 0:
        raise ValueError("sample size must be a positive integer")
    if n >= len(examples):
        return list(examples)
    rng = random.Random(seed)
    return rng.sample(examples, n)


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
