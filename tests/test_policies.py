"""Our question-choice policy (no LLM calls; the policy never reads an answer key)."""

from __future__ import annotations

import json
from pathlib import Path

from smt_trial_matching.policies import ValueConfig, candidate_questions, score_question, value_policy
from smtstate import TrialState
from smtstate.runner import run_patient
from smtstate.sim import AnswerKeySimulator

ROOT = Path(__file__).resolve().parents[1]
DEMO_QID = "trec-202112"  # dev patient from the onboarding doc
SLEEP_TRIAL = "NCT01029561"  # gold ineligible; 3 cohorts


def _trials(qid: str) -> list[str]:
    return [p["nct"] for p in map(json.loads, (ROOT / "data/pairs.jsonl").open()) if p["qid"] == qid]


def test_candidates_include_cohort_knockouts_missed_by_informative() -> None:
    s = TrialState(SLEEP_TRIAL)
    informative = {v for v, _ in s.informative()}
    assert "patient_is_included_in_obesity_surgery_program_now" in set(candidate_questions(s)) - informative


def test_score_rewards_ruling_out_cohorts() -> None:
    s = TrialState(SLEEP_TRIAL)
    assert score_question(s, "patient_is_included_in_obesity_surgery_program_now", ValueConfig()) > 0
    s.answers["patient_is_included_in_obesity_surgery_program_now"] = False
    s.answers["patient_is_included_in_obesity_surgery_program"] = False
    s.answers["patient_has_diagnosis_of_sleep_apnea_now"] = False
    assert s.status() == "ineligible" and candidate_questions(s) == []


def test_policy_fixes_the_demo_patient_and_never_repeats() -> None:
    ep = run_patient(DEMO_QID, _trials(DEMO_QID), value_policy, AnswerKeySimulator(), budget=60)
    asked = [(t["nct"], t["var"]) for t in ep["turns"]]
    assert len(asked) == len(set(asked))
    assert ep["final_verdicts"][SLEEP_TRIAL] == "ineligible"
