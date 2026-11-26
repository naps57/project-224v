"""Real-Gemini checks on real dev patients. Skipped unless GEMINI_API_KEY is set; replies are cached, so reruns
are free.  Run with:  GEMINI_API_KEY=... uv run pytest tests/test_live.py"""

import os

import pytest

from smt_trial_matching import llm_only
from smt_trial_matching.data import patients
from smt_trial_matching.interview import LLMPatient
from smt_trial_matching.patient import ask_patient

pytestmark = pytest.mark.skipif(not os.environ.get("GEMINI_API_KEY"), reason="needs GEMINI_API_KEY")


def test_patient_answers_from_the_note():
    assert "yes" in ask_patient("trec-202112", "Do you have Marfan syndrome?").lower()
    assert "sure" in ask_patient("trec-202112", "Do you smoke?").lower()  # not in the note


@pytest.mark.parametrize("qid, nct, var", [
    ("trec-202123", "NCT00000577", "patient_has_diagnosis_of_asthma_now"),
    ("trec-202112", "NCT02719912", "patient_has_finding_of_mitral_valve_regurgitation_now"),
])
def test_question_patient_reader_chain(qid, nct, var):
    assert LLMPatient().answer(qid, nct, var) is True  # the answer key says True for both


def test_llm_only_gives_a_verdict_for_every_trial():
    trials = dict(patients("dev"))["trec-202112"]
    log = llm_only.interview("trec-202112", trials, budget=3)
    assert len(log["turns"]) <= 3 and set(log["final_verdicts"]) == set(trials)
