"""Read the dataset: gold labels, splits and each patient's candidate trials."""

from __future__ import annotations

import collections
import json
from functools import cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"


@cache
def _pairs() -> list[dict]:
    return [json.loads(line) for line in (DATA / "pairs.jsonl").open()]


def load_gold() -> dict[tuple[str, str], bool]:
    """(patient, trial) -> True if the gold label is eligible."""
    return {(p["qid"], p["nct"]): p["gold"] == "eligible" for p in _pairs()}


def load_split(split: str) -> list[str]:
    """Patient ids of the "dev" or "test" split."""
    return list(json.loads((DATA / "splits.json").read_text())[split])


def patients(split: str) -> list[tuple[str, list[str]]]:
    """(patient, candidate trials) for the split, in patient-id order."""
    by: dict[str, list[str]] = collections.defaultdict(list)
    for p in _pairs():
        by[p["qid"]].append(p["nct"])
    keep = set(load_split(split))
    return [(q, n) for q, n in sorted(by.items()) if q in keep]
