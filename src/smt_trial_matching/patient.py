"""The simulated patient: a language model answers in plain language, from the patient's note.

The prompt is the course's, read from docs/nl_simulator_prompt.md. Each question is answered on its own.

  uv run python -m smt_trial_matching.patient trec-202112 "Do you have high blood pressure?"
"""

from __future__ import annotations

import sys
from functools import cache

from smt_trial_matching.data import ROOT, patient_note
from smt_trial_matching.llm import ask_llm


@cache
def patient_prompt() -> str:
    """The prompt template: the first code block of the course's simulator doc."""
    text = (ROOT / "docs" / "nl_simulator_prompt.md").read_text()
    return text.split("```")[1].strip()


def ask_patient(qid: str, question: str) -> str:
    """What patient `qid` says when asked `question`."""
    prompt = patient_prompt().format(patient_note=patient_note(qid), question=question)
    return ask_llm(prompt)


if __name__ == "__main__":
    print(ask_patient(sys.argv[1], sys.argv[2]))
