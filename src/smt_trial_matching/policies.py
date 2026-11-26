"""Our question-asking policy: ask the question most likely to be answered AND to settle something.

Each turn, every open question gets a score:

    score = P(answered) x value

- P(answered): the chance the patient can answer it (predicted from the variable's name, answerability.py).
- value: how much the answer would settle. Ruling a trial out counts most; ruling out one of its cohorts
  counts in proportion; confirming a trial eligible counts a little.

The policy asks the highest-scoring question, and stops when no question has any value left.
It never reads the answer key. The baseline it is compared with, greedy_smt, is in baselines/policies.py.

A policy is a function ``policy(states, asked, rng) -> (trial, variable) | None`` (None = stop), where
``states`` maps each candidate trial to its solver state (smtstate/state.py).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


def _undetermined(states: dict) -> list[str]:
    return [n for n, s in states.items() if s.status() == "undetermined"]


# --------------------------------------------------------------------------------------------------
# The value of an answer


@dataclass(frozen=True)
class AnswerableConfig:
    """Weights for the value of a possible answer (chosen on dev, then frozen), and two ablation switches."""

    w_ineligible: float = 1.0  # the answer would make the trial ineligible (the only verdict flip)
    # Per share of the trial's open cohorts the answer would rule out. At 1.0, ruling out every open
    # cohort is worth as much as making the trial ineligible, which is the same thing.
    w_cohort: float = 1.0
    w_eligible: float = 0.2  # the answer would make the trial certainly eligible (ends its questions)
    w_numeric: float = 0.3  # fallback for a number with no value distribution (see _numeric_value)
    # Ablation switches (defaults = the policy as tuned):
    use_answerability: bool = True  # False: P(answered) = 1 for every variable (informativeness x value)
    use_value: bool = True  # False: value = 1 if some answer could decide something, else 0 (answerability only)


def _answer_value(state: Any, var: str, val: bool | float, open_cohorts: list[str],
                  cfg: AnswerableConfig) -> float:
    """Value of learning ``var = val`` (a Bool or a number) for one trial, from its cohort
    statuses after the answer."""
    after = state.cohort_status({**state.answers, var: val})
    if all(s == "ineligible" for s in after.values()):
        return cfg.w_ineligible
    if any(s == "eligible" for s in after.values()):
        return cfg.w_eligible
    knocked = sum(after[c] == "ineligible" for c in open_cohorts)
    return cfg.w_cohort * knocked / len(open_cohorts)


def _numeric_value(state: Any, var: str, open_cohorts: list[str], model: Any,
                   cfg: AnswerableConfig) -> float:
    """Expected value of asking a number, e.g. age.

    A number used to get the flat ``w_numeric``, so age (almost always
    answerable) outranked every Bool question even when no plausible age could change the trial
    (e.g. 18-65 for a typical adult). Now, when the model has a value distribution for the name
    (values from at least MIN_VALUE_PATIENTS training patients; cross-fitted like P(answered), so a
    dev patient's own age is never in it), we run each observed value through the solver exactly as
    a Bool answer and average: an 18-65 range scores only the share of patients outside it.
    Numbers without a distribution (everything but age today) keep the flat ``w_numeric``.
    """
    dist = model.value_distribution(var)
    if dist is None:
        return cfg.w_numeric
    return sum(p * _answer_value(state, var, v, open_cohorts, cfg) for v, p in dist)


def candidate_questions(state: Any) -> list[str]:
    """Unanswered variables of the trial's open cohorts (wider than informative(): it keeps
    questions that rule out one cohort of a multi-cohort trial without changing the trial status)."""
    open_c = [c for c, s in state.cohort_status().items() if s == "open"]
    names = {v for c in open_c for prog in state.cohorts[c] for v in prog.types}
    return sorted(v for v in names if state.answers.get(v) is None)


def _could_decide(state: Any, var: str, open_cohorts: list[str], model: Any,
                  cfg: AnswerableConfig) -> float:
    """1.0 if some possible answer has value (rules out a cohort, the trial, or makes it eligible),
    else 0.0. The ``use_value=False`` ablation. Numbers without a value distribution count as 1."""
    if state.types[var] == "Bool":
        answers: list = [True, False]
    else:
        dist = model.value_distribution(var)
        if dist is None:
            return 1.0
        answers = [v for v, _ in dist]
    return float(any(_answer_value(state, var, a, open_cohorts, cfg) > 0 for a in answers))


def score_question(state: Any, var: str, model: Any, cfg: AnswerableConfig,
                   p_ans: float | None = None) -> float:
    """P(answered) x expected value of the answer, for one (trial, variable).

    ``p_ans`` overrides the model's P(answered) (the no-answerability ablation passes 1)."""
    open_c = [c for c, s in state.cohort_status().items() if s == "open"]
    if not open_c:
        return 0.0
    vtype = state.types[var]
    p_pred, p_true = model.predict(var, vtype)
    if p_ans is None:
        p_ans = p_pred if cfg.use_answerability else 1.0
    if p_ans == 0:
        return 0.0
    if not cfg.use_value:
        return p_ans * _could_decide(state, var, open_c, model, cfg)
    if vtype != "Bool":
        # Age scoring: expected value over observed values, not a flat weight (see _numeric_value).
        return p_ans * _numeric_value(state, var, open_c, model, cfg)
    value = (p_true * _answer_value(state, var, True, open_c, cfg)
             + (1 - p_true) * _answer_value(state, var, False, open_c, cfg))
    return p_ans * value


# --------------------------------------------------------------------------------------------------
# The policy


class AnswerableInformative:
    """Ask the question with the highest P(answered) x value across all undetermined trials.

    Signature as the CA's policies: ``policy(states, asked, rng) -> (nct, var) | None``. It never
    reads the answer key; P(answered) comes from ``answerability.model_for`` (dev-fit, cross-fitted
    for dev patients). It stops only when no question has any value (as greedy_smt does); otherwise
    it uses the whole budget. Ties go to the higher P(answered), then trial and variable name.
    """

    def __init__(self, cfg: AnswerableConfig | None = None) -> None:
        self.cfg = cfg or AnswerableConfig()

    def _p_answered(self, model: Any, var: str, vtype: str) -> float:
        return model.p_answered(var, vtype) if self.cfg.use_answerability else 1.0

    def __call__(self, states: dict, asked: set, rng: Any) -> tuple[str, str] | None:
        from smt_trial_matching.answerability import model_for

        model = model_for(states)
        best, best_key = None, (0.0, 0.0, "", "")
        for n in _undetermined(states):
            for v in candidate_questions(states[n]):
                if (n, v) in asked:
                    continue
                # The tie-break uses the same P(answered) as the score, so the no-answerability
                # ablation cannot get answerability back through ties.
                p = self._p_answered(model, v, states[n].types[v])
                score = score_question(states[n], v, model, self.cfg, p_ans=p)
                key = (score, p, _neg(n), _neg(v))
                if score > 0 and (best is None or key > best_key):
                    best, best_key = (n, v), key
        return best


def _neg(s: str) -> str:
    """Sort key that makes smaller strings win a max() tie-break."""
    return "".join(chr(0x10FFFF - ord(ch)) for ch in s)


answerable_informative = AnswerableInformative()


# Ablations: the same policy with one factor switched off.
answerable_informative_no_answerability = AnswerableInformative(AnswerableConfig(use_answerability=False))
answerable_informative_no_value = AnswerableInformative(AnswerableConfig(use_value=False))
