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


@cache
def _notes() -> dict[str, str]:
    return {p["qid"]: p["text"] for p in map(json.loads, (DATA / "patients.jsonl").open())}


def patient_note(qid: str) -> str:
    """The patient's medical note."""
    return _notes()[qid]


@cache
def _variables(nct: str) -> dict[str, dict]:
    return {v["name"]: v for v in json.loads((DATA / "variables" / f"{nct}.json").read_text())}


def variable(nct: str, name: str) -> dict | None:
    """A trial variable's definition: type, meaning, and when it is true, false, unknown or a value."""
    return _variables(nct).get(name)


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
