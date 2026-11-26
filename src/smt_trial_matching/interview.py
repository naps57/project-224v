"""One question to the simulated patient: write the question, ask it, and read the reply back into a value.

`LLMPatient.answer(qid, nct, var)` has the same signature as the staff's `AnswerKeySimulator.answer`, so it can
replace it in smtstate/runner.py. Run this file to check it against the answer key on dev patients:

  uv run python -m smt_trial_matching.interview trec-202140 trec-202135
"""

from __future__ import annotations

import sys

from smt_trial_matching.data import load_split, patients, variable
from smt_trial_matching.llm import ask_llm
from smt_trial_matching.patient import ask_patient

WRITER_PROMPT = """You are a research coordinator screening a patient for a clinical trial.
Write ONE short question, in plain everyday language, that asks the patient about this fact:
{meaning}
Reply with the question only."""

READER_PROMPT = """A research coordinator asked a patient a question. Turn the patient's reply into a value.

Fact: {meaning}
{rules}

Question: {question}
Patient's reply: {reply}

Reply with ONE word only: {options}. Use unknown if the reply does not clearly settle the fact."""


def write_question(nct: str, var: str) -> str:
    return ask_llm(WRITER_PROMPT.format(meaning=variable(nct, var)["meaning"]))


def read_answer(nct: str, var: str, question: str, reply: str) -> bool | float | None:
    v = variable(nct, var)
    is_bool = v["type"] == "Bool"
    rules = "\n".join(f"- {v[k]}" for k in ("when_true", "when_false", "when_value", "when_unknown") if v[k])
    options = "true, false or unknown" if is_bool else "a number, or unknown"
    word = ask_llm(READER_PROMPT.format(meaning=v["meaning"], rules=rules, question=question,
                                        reply=reply, options=options)).strip().strip(".").lower()
    if is_bool:
        return {"true": True, "false": False}.get(word)
    try:
        return float(word)
    except ValueError:
        return None  # anything unreadable counts as unknown, which never changes a verdict


class LLMPatient:
    """The patient as a conversation: same `answer` method as the staff's AnswerKeySimulator."""

    def __init__(self):
        self.transcript = []

    def answer(self, qid: str, nct: str, var: str) -> bool | float | None:
        question = write_question(nct, var)
        reply = ask_patient(qid, question)
        value = read_answer(nct, var, question, reply)
        self.transcript.append(dict(qid=qid, nct=nct, var=var, question=question, reply=reply, value=value))
        return value


def bucket(ours, key) -> str:
    if ours is None:
        return "agree" if key is None else "missed"
    if key is None:
        return "made up"
    if isinstance(key, bool) or isinstance(ours, bool):
        return "agree" if ours == key else "wrong"
    return "agree" if abs(ours - key) <= 0.01 * max(abs(key), 1) else "wrong"


if __name__ == "__main__":
    from smtstate.sim import AnswerKeySimulator

    qids = sys.argv[1:]
    assert set(qids) <= set(load_split("dev")), "check on dev patients only"
    key, llm = AnswerKeySimulator("gpt5_oracle"), LLMPatient()
    rows = []
    for qid, ncts in patients("dev"):
        for nct in ncts if qid in qids else []:
            for var in key.keys.get(f"{qid}__{nct}", {}):
                if variable(nct, var):
                    truth = key.answer(qid, nct, var)
                    rows.append((bucket(llm.answer(qid, nct, var), truth), truth, llm.transcript[-1]))

    n = len(rows)
    counts = {b: sum(r[0] == b for r in rows) for b in ("agree", "missed", "made up", "wrong")}
    for b, c in counts.items():
        print(f"{b:8} {c:4}  {c / n:.0%}")
    passed = counts["agree"] / n >= 0.85 and (counts["made up"] + counts["wrong"]) / n <= 0.05
    print(f"\n{n} variables: {'PASS' if passed else 'FAIL'} (needs >=85% agree, <=5% made up + wrong)\n")
    for b, truth, t in rows:
        if b != "agree":
            print(f"[{b}] {t['nct']} {t['var']}\n  Q: {t['question']}\n  A: {t['reply']}\n"
                  f"  ours={t['value']}  key={truth}\n")
