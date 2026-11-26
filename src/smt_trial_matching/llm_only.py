"""The LLM-only baseline: Gemini interviews the patient and decides eligibility on its own, with no solver.

It reads the trials' criteria as text and uses the course's questioner prompt (docs/llm_only_baseline_prompt.md).
It talks to the same LLM patient as our agent, with the same question budget. Each turn it asks one question or
stops with a verdict per trial. The log uses the staff runner's format; as the course allows, the final verdicts
are recorded at every turn.
"""

from __future__ import annotations

import json
from functools import cache

from smt_trial_matching.data import DATA, ROOT
from smt_trial_matching.interview import INTAKE, parse_json
from smt_trial_matching.llm import ask_llm
from smt_trial_matching.patient import ask_patient

STOP_NOW = "\nYou have no questions left: stop now and give your verdicts."


@cache
def questioner_prompt() -> str:
    """The prompt template: the first code block of the course's baseline doc."""
    return (ROOT / "docs" / "llm_only_baseline_prompt.md").read_text().split("```")[1].strip()


def trial_text(nct: str) -> str:
    t = json.loads((DATA / "trials" / f"{nct}.json").read_text())
    return f"## {nct}: {t['title']}\n{t['inclusion_criteria']}\n{t['exclusion_criteria']}"


def interview(qid: str, trials: list[str], budget: int, intake: bool = False) -> dict:
    """One LLM-only conversation with patient `qid`, in the staff runner's log format. With `intake`, it first
    asks the same 4 intake questions as our agent (they count toward the budget), then carries on as usual."""
    base = questioner_prompt().replace("{trials}", "\n\n".join(trial_text(n) for n in trials))
    transcript, verdicts = [(q, ask_patient(qid, q)) for q in INTAKE] if intake else [], None
    while verdicts is None:
        conversation = "\n".join(f"Coordinator: {q}\nPatient: {a}" for q, a in transcript) or "(none yet)"
        prompt = base.replace("{transcript}", conversation) + (STOP_NOW if len(transcript) >= budget else "")
        move = parse_json(ask_llm(prompt))
        if move.get("action") == "ask" and move.get("question") and len(transcript) < budget:
            transcript.append((move["question"], ask_patient(qid, move["question"])))
        else:
            said = move.get("verdicts") or {}
            # A missing or unreadable verdict counts as eligible, the course's rule for unknown facts.
            verdicts = {n: "ineligible" if said.get(n) == "ineligible" else "eligible" for n in trials}
    return dict(qid=qid, trials=list(trials), initial_verdicts={n: "eligible" for n in trials},
                turns=[dict(nct=None, var=None, question=q, answer=a, informative=False, verdicts=verdicts)
                       for q, a in transcript],
                final_verdicts=verdicts)


JUDGE_PROMPT = """You are screening a patient for this clinical trial.

# Trial
{trial}

# Screening conversation
{conversation}

Based on the conversation, is the patient eligible for this trial? Treat criteria the conversation does not address
as satisfied (unknown facts do not disqualify); answer ineligible only if the conversation shows a criterion fails.
Reply with one word: eligible or ineligible."""


def judge(nct: str, conversation: list[tuple[str, str]]) -> str:
    """Gemini's verdict on one trial from a finished conversation (used for trials the solver left undecided)."""
    said = "\n".join(f"Coordinator: {q}\nPatient: {a}" for q, a in conversation)
    reply = ask_llm(JUDGE_PROMPT.format(trial=trial_text(nct), conversation=said)).strip().lower()
    return "ineligible" if reply.startswith("ineligible") else "eligible"
