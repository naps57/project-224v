"""One question to the simulated patient: write the question, ask it, and read the reply back into values.

`LLMPatient.answer(qid, nct, var)` has the same signature as the staff's `AnswerKeySimulator.answer`, so it can
replace it in smtstate/runner.py. Run this file to check it against the answer key on dev patients:

  uv run python -m smt_trial_matching.interview trec-202140 trec-202135
"""

from __future__ import annotations

import json
import re
import sys

from smt_trial_matching.data import load_split, patients, variable
from smt_trial_matching.llm import ask_llm
from smt_trial_matching.patient import ask_patient
from smt_trial_matching.policies import candidate_questions

WRITER_PROMPT = """You are a research coordinator screening a patient for a clinical trial.
Write ONE short question, in plain everyday language, that asks the patient about this fact:
{meaning}
Reply with the question only."""

GROUP_PROMPT = """You are a research coordinator screening a patient for clinical trials.
Write ONE short, natural question, in plain everyday language, that covers all of these related facts:
{meanings}
Reply with the question only."""

# The first turns of every conversation: a fixed intake in the standard order of a clinical history
# (background, conditions, medications and allergies, surgeries and social history), the same for every patient.
INTAKE = (
    "Could you tell me your age, sex, and roughly your height and weight? And what language are you most "
    "comfortable speaking and reading?",
    "What are your main health conditions, and roughly when was each one diagnosed?",
    "What medications are you taking now, or have taken in the last month, including inhalers, injections and "
    "supplements? And do you have any drug allergies?",
    "Have you had any surgeries, procedures or hospital stays? Do you smoke or drink alcohol? And, if it applies "
    "to you, are you pregnant, breastfeeding, or using birth control?",
)

TIMEFRAME = re.compile(r"_(now|inthehistory|inthepast\w*|prior_to\w*|within\w*|during\w*)$")
GROUP_SIZE = 4  # most facts asked about in one question
GENERIC_WORDS = frozenset({"patient", "has", "is", "of", "finding", "diagnosis", "undergone", "taking", "exposed",
                           "to", "value", "recorded", "the", "a", "an", "and", "or", "in", "with"})

READER_PROMPT = """A research coordinator asked a patient a question. Find every fact below that the patient's
reply clearly settles.

Question: {question}
Patient's reply: {reply}

Facts (id. type: description):
{facts}

Rules:
- Fact 1 is what the coordinator asked about: give it a value whenever the reply settles it.
- Use only what the reply says. Do not infer that something is false just because it was not mentioned.
- yes/no facts take true or false; number facts take a number.
- Examples: "Not that I know of, no" -> false. "Nobody has ever told me I have that" -> false.
  "I'm not sure" or "I think so, maybe?" -> leave it out. "I'm 34" -> 34 for age.

Reply with JSON only, mapping fact id to value, e.g. {{"3": true, "7": 34}}. Reply {{}} if the reply settles nothing."""


def describe(v: dict) -> str:
    """The fact in words: its written meaning, or (for the quarter of variables without one) its name."""
    return v["meaning"] or v["name"].replace("@@", ", specifically: ").replace("_", " ")


def topic(name: str) -> frozenset[str]:
    """What a fact is about, without its timeframe or detail: "asthma" for has_finding_of_asthma_now,
    has_finding_of_asthma_inthehistory and has_diagnosis_of_asthma_now alike."""
    stem = TIMEFRAME.sub("", name.partition("@@")[0])
    return frozenset(w for w in re.split(r"[^a-z0-9]+", stem) if w and w not in GENERIC_WORDS)


def write_question(facts: list[tuple[str, str]]) -> str:
    """One question about a fact, or about a group of related facts at once."""
    meanings = list(dict.fromkeys(describe(variable(n, v)) for n, v in facts))
    if len(meanings) == 1:
        return ask_llm(WRITER_PROMPT.format(meaning=meanings[0]))
    return ask_llm(GROUP_PROMPT.format(meanings="\n".join(f"- {m}" for m in meanings)))


def read_reply(question: str, reply: str, facts: list[tuple[str, str]]) -> dict:
    """Every (trial, variable) in `facts` that the reply settles -> its value. One model call for all of them."""
    listed = "\n".join(f"{i}. {'yes/no' if variable(n, v)['type'] == 'Bool' else 'number'}: "
                        f"{describe(variable(n, v))}" for i, (n, v) in enumerate(facts, 1))
    found = parse_json(ask_llm(READER_PROMPT.format(question=question, reply=reply, facts=listed)))
    values = {}
    for i, (n, v) in enumerate(facts, 1):
        x = found.get(str(i))
        is_bool = variable(n, v)["type"] == "Bool"
        if is_bool and isinstance(x, bool) or not is_bool and isinstance(x, (int, float)) and not isinstance(x, bool):
            values[(n, v)] = x  # anything else (missing, wrong type) stays unknown, which never changes a verdict
    return values


def parse_json(text: str) -> dict:
    """The JSON object in a model reply, or {} if there is none."""
    try:
        found = json.loads(text[text.index("{"):text.rindex("}") + 1])
    except ValueError:
        return {}
    return found if isinstance(found, dict) else {}


class LLMPatient:
    """The patient as a conversation: same `answer` method as the staff's AnswerKeySimulator.

    Each reply is read for every still-open fact of the patient's trials, not only the one asked about (as Genie's
    parser fills every field an utterance settles). `attach` wraps a policy so the patient can see the trial states
    and write those extra answers into them; the asked fact's value is returned to the runner as usual."""

    def __init__(self):
        self.transcript = []
        self.states = None
        self.unknown_topics = set()  # topics the patient already said they don't know about

    def attach(self, policy):
        """Wrap a policy so the patient can see the trial states, and so a topic the patient already said they
        don't know about is not asked again (in other words, or for another trial)."""
        def wrapped(states, asked, rng):
            self.states = states
            pick = policy(states, asked, rng)
            while pick and topic(pick[1]) in self.unknown_topics:
                asked.add(pick)  # skipped, not asked: it does not use up a question
                pick = policy(states, asked, rng)
            return pick
        return wrapped

    def open_facts(self, nct: str, var: str) -> list[tuple[str, str]]:
        """The asked fact first, then every fact of the undecided trials that could still change a verdict."""
        facts = [(nct, var)]
        for n, s in (self.states or {}).items():
            if s.status() == "undetermined":
                facts += [(n, v) for v in candidate_questions(s) if (n, v) != (nct, var) and variable(n, v)]
        return facts

    def answer(self, qid: str, nct: str, var: str) -> bool | float | None:
        facts = self.open_facts(nct, var)
        turn = len(self.transcript)
        if self.states is not None and turn < len(INTAKE):
            question = INTAKE[turn]
        else:
            # The chosen fact together with up to 3 open facts on the same topic (e.g. asthma ever + now).
            group = [(nct, var)] + [(n, v) for n, v in facts[1:] if topic(v) == topic(var)][:GROUP_SIZE - 1]
            question = write_question(group)
        reply = ask_patient(qid, question)
        values = read_reply(question, reply, facts)
        if question not in INTAKE and not any(topic(v) == topic(var) for _, v in values):
            self.unknown_topics.add(topic(var))
        for (n, v), x in values.items():
            if (n, v) != (nct, var):
                self.states[n].answers[v] = x
        value = values.get((nct, var))
        self.transcript.append(dict(qid=qid, nct=nct, var=var, question=question, reply=reply, value=value,
                                    also=[[n, v, x] for (n, v), x in values.items() if (n, v) != (nct, var)]))
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
