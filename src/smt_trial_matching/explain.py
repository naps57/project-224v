"""Explain each verdict: for a trial Z3 ruled out, which written criterion failed and which answers broke it.

Each rule in a trial's Z3 program is named REQ<k>_..., where k numbers the paragraphs of the trial's written
inclusion or exclusion criteria. For every rule that fails on its own given the patient's answers, Z3's unsat core
names the answers responsible. Read only: it uses the staff's solver state without changing it.

  uv run python -m smt_trial_matching.explain results/dev/ours.jsonl trec-202123
"""

from __future__ import annotations

import json
import re
import sys
from functools import cache

import z3

from smt_trial_matching.data import DATA
from smtstate import TrialState
from smtstate.state import _top_level


@cache
def criteria(nct: str, side: str) -> list[str]:
    """The trial's written inclusion or exclusion criteria, one paragraph per criterion."""
    text = json.loads((DATA / "trials" / f"{nct}.json").read_text())[f"{side}_criteria"]
    return [p.strip() for p in text.split("\n\n") if p.strip().strip(":")]


def _rules(program) -> list[tuple[int, z3.BoolRef]]:
    """(criterion number, formula) for every rule of a program (definitional AUXILIARY links left out)."""
    exprs = _top_level(program.text)
    decls = "\n".join(e for e in exprs if e.lstrip("(").lstrip().startswith(("declare", "define")))
    out = []
    for e in exprs:
        name = re.search(r":named\s+REQ(\d+)_(\S+?)\)", e)
        if e.startswith("(assert") and name and "AUXILIARY" not in name.group(2):
            out.append((int(name.group(1)), z3.And(*z3.parse_smt2_string(decls + "\n" + e))))
    return out


def _criterion_text(nct: str, side: str, number: int, because: list) -> str:
    """The paragraph sharing the most topic words with the failing answers (nearest paragraph `number` on a tie);
    if none shares any, the rule number and facts."""
    from smt_trial_matching.interview import topic

    texts = criteria(nct, side)
    words = {w for v, _ in because for w in topic(v) if len(w) > 3}
    overlap = [sum(w[:5] in t.lower() for w in words) for t in texts]
    best = max(range(len(texts)), key=lambda i: (overlap[i], -abs(i - number)), default=None)
    if best is not None and overlap[best]:
        return texts[best]
    return f"{side} rule {number + 1} (on: " + ", ".join(v for v, _ in because) + ")"


def _equals(program, var: str, value):
    """The Z3 constraint "var has this value" in `program`, or None if the program has no such variable."""
    if value is None or var not in program.vars:
        return None
    if program.types[var] == "Bool":
        return program.vars[var] == z3.BoolVal(value) if isinstance(value, bool) else None
    return None if isinstance(value, bool) else program.vars[var] == value


def explain(nct: str, answers: dict) -> list[dict]:
    """Why trial `nct` is ruled out given `answers`: the failing criteria and the answers that break each one."""
    state = TrialState(nct, answers)
    reasons = []
    for side, k in (("inclusion", 0), ("exclusion", 1)):
        for program in {cohort[k] for cohort in state.cohorts.values()}:
            if program.status(answers) != "violated":
                continue
            marks = {z3.Bool(f"answer {v}"): (v, x) for v, x in answers.items() if _equals(program, v, x) is not None}
            for number, rule in _rules(program):
                solver = z3.Solver()
                solver.add(program.B, rule, *(z3.Implies(m, _equals(program, v, x)) for m, (v, x) in marks.items()))
                if solver.check(*marks) == z3.unsat:
                    because = [marks[m] for m in solver.unsat_core()]
                    reasons.append(dict(side=side, criterion=_criterion_text(nct, side, number, because),
                                        because=because))
    return reasons


def answers_from_log(log: dict) -> dict[str, dict]:
    """Each trial's answers at the end of a logged conversation (the asked facts and, for the LLM patient, the
    extra facts the reader filled)."""
    answers = {n: {} for n in log["trials"]}
    for turn in log["turns"]:
        if turn.get("nct") and turn.get("answer") is not None:
            answers[turn["nct"]][turn["var"]] = turn["answer"]
    for t in log.get("transcript", []):
        for n, v, x in t.get("also", []):
            answers[n][v] = x
    return answers


if __name__ == "__main__":
    path, qid = sys.argv[1], sys.argv[2]
    log = next(x for x in map(json.loads, open(path)) if x["qid"] == qid)
    answers = answers_from_log(log)
    for nct in log["trials"]:
        if log["final_verdicts"][nct] != "ineligible":
            continue
        print(f"{nct}: ineligible")
        for r in explain(nct, answers[nct]):
            said = ", ".join(f"{v} = {x}" for v, x in r["because"])
            print(f"  {r['side']} criterion: {r['criterion'][:160]}\n    broken by: {said}")
