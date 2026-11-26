"""Scoring in run.py: verdicts after k questions, and the area under the accuracy curve."""

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from run import auc, correct_counts, verdicts_at

EP = {"qid": "p", "trials": ["A", "B"], "initial_verdicts": {"A": "eligible", "B": "eligible"},
      "turns": [{"verdicts": {"A": "eligible", "B": "eligible"}},
                {"verdicts": {"A": "ineligible", "B": "eligible"}}]}
GOLD = {("p", "A"): False, ("p", "B"): True}


def test_verdicts_hold_after_the_agent_stops():
    assert verdicts_at(EP, 0) == EP["initial_verdicts"]
    assert verdicts_at(EP, 2)["A"] == verdicts_at(EP, 30)["A"] == "ineligible"


def test_correct_counts_and_auc():
    correct, pairs = correct_counts([EP], GOLD, budget=4)
    assert correct.tolist() == [[1, 1, 2, 2, 2]] and pairs.tolist() == [2]
    assert auc(np.array([0.5, 0.5, 1.0, 1.0, 1.0]), 4) == (0.5 + 0.75 + 1.0 + 1.0) / 4
