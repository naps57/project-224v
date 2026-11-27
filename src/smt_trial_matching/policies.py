"""Our question-asking policy: ask the question whose answer could settle the most.

Each turn, every open question gets a value: how much its answer would settle, averaged over a yes and a no
(numbers get a flat weight). A no counts more than a yes, on one fixed assumption: most patients do not have
most of the conditions a trial asks about. Ruling a trial out counts most; ruling out one of its cohorts counts in proportion;
confirming a trial eligible counts a little. The policy asks the highest-value question and stops when no
question has any value left.

Nothing is learned in advance: the policy uses only the trials' rules, that one stated assumption and what the
patient has said so far, never an answer key or any patient's answers. The baseline it is compared with, greedy_smt (any question that could decide a trial), is in
baselines/policies.py.

A policy is a function ``policy(states, asked, rng) -> (trial, variable) | None`` (None = stop), where
``states`` maps each candidate trial to its solver state (smtstate/state.py).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ValueConfig:
    """Weights for the value of a possible answer, and one ablation switch."""

    w_ineligible: float = 1.0  # the answer would make the trial ineligible (the only verdict flip)
    # Per share of the trial's open cohorts the answer would rule out. At 1.0, ruling out every open
    # cohort is worth as much as making the trial ineligible, which is the same thing.
    w_cohort: float = 1.0
    w_eligible: float = 0.2  # the answer would make the trial certainly eligible (ends its questions)
    w_numeric: float = 0.3  # a number (e.g. age): no answer to try, so a flat weight
    p_yes: float = 0.2  # assumed chance a yes/no answer is yes (set once, not learned or tuned)
    use_value: bool = True  # False: value = 1 if some yes/no answer could decide something, else 0 (ablation)


def _answer_value(state: Any, var: str, val: bool, open_cohorts: list[str], cfg: ValueConfig) -> float:
    """Value of learning ``var = val`` for one trial, from its cohort statuses after the answer."""
    after = state.cohort_status({**state.answers, var: val})
    if all(s == "ineligible" for s in after.values()):
        return cfg.w_ineligible
    if any(s == "eligible" for s in after.values()):
        return cfg.w_eligible
    knocked = sum(after[c] == "ineligible" for c in open_cohorts)
    return cfg.w_cohort * knocked / len(open_cohorts)


def candidate_questions(state: Any) -> list[str]:
    """Unanswered variables of the trial's open cohorts (wider than informative(): it keeps
    questions that rule out one cohort of a multi-cohort trial without changing the trial status)."""
    open_c = [c for c, s in state.cohort_status().items() if s == "open"]
    names = {v for c in open_c for prog in state.cohorts[c] for v in prog.types}
    return sorted(v for v in names if state.answers.get(v) is None)


def score_question(state: Any, var: str, cfg: ValueConfig) -> float:
    """How much the answer to ``var`` would settle for one trial: its value if yes and if no, weighted by p_yes."""
    open_c = [c for c, s in state.cohort_status().items() if s == "open"]
    if not open_c:
        return 0.0
    if state.types[var] != "Bool":
        return cfg.w_numeric
    values = [_answer_value(state, var, x, open_c, cfg) for x in (True, False)]
    if not cfg.use_value:
        return float(any(values))
    return cfg.p_yes * values[0] + (1 - cfg.p_yes) * values[1]


class ValuePolicy:
    """Ask about the fact whose answer could settle the most, added up over every undetermined trial that asks
    about it: a fact that 3 trials depend on counts for all 3, since one answer is read into all of them.

    Signature as the course's policies: ``policy(states, asked, rng) -> (nct, var) | None``; the trial returned is
    the one that fact matters most to. It stops only when no question has any value (as greedy_smt does). Ties go
    to the variable and trial name."""

    def __init__(self, cfg: ValueConfig | None = None) -> None:
        self.cfg = cfg or ValueConfig()

    def __call__(self, states: dict, asked: set, rng: Any) -> tuple[str, str] | None:
        total, where = {}, {}  # fact -> value summed over trials; fact -> (its best value, trial)
        for n, s in states.items():
            if s.status() != "undetermined":
                continue
            for v in candidate_questions(s):
                if (n, v) in asked:
                    continue
                score = score_question(s, v, self.cfg)
                if score > 0:
                    total[v] = total.get(v, 0.0) + score
                    where[v] = max(where.get(v, (0.0, "")), (score, _neg(n)))
        if not total:
            return None
        v = max(total, key=lambda v: (total[v], _neg(v)))
        return _neg(where[v][1]), v  # _neg is its own inverse


def _neg(s: str) -> str:
    """Sort key that makes smaller strings win a max() tie-break."""
    return "".join(chr(0x10FFFF - ord(ch)) for ch in s)


value_policy = ValuePolicy()
value_policy_no_value = ValuePolicy(ValueConfig(use_value=False))  # ablation: any question that could decide
