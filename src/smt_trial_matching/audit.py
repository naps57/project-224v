"""How accountable each agent's verdicts are, from saved dev logs.

1. Backed rejections: of the trials an agent ruled out, how many can Z3 justify from what the patient actually
   said? Our agent's rejections come from Z3, so each one is backed by construction. For the LLM-only agents, the
   answer reader turns their own conversation into facts and Z3 checks the trial against them.
2. Order: re-run an agent with each patient's trials in reverse order and count verdicts that change.

  uv run python -m smt_trial_matching.audit
"""

from __future__ import annotations

import json
import sys

from smt_trial_matching.data import ROOT, variable
from smt_trial_matching.interview import read_reply
from smtstate import TrialState

BUDGET = 10  # questions per patient in the final setup


def backed_rejections(log: dict) -> tuple[int, int]:
    """(trials ruled out, of which Z3 can justify from the conversation) for one LLM-only log."""
    out = [n for n in log["trials"] if log["final_verdicts"][n] == "ineligible"]
    if not out:
        return 0, 0
    facts = [(n, v) for n in out for v in TrialState(n).variables if variable(n, v)]
    answers = {n: {} for n in out}
    for turn in log["turns"]:
        for (n, v), x in read_reply(turn["question"], turn["answer"], facts).items():
            answers[n][v] = x
    return len(out), sum(TrialState(n, answers[n]).status() == "ineligible" for n in out)


def verdict_changes(agent: str, logs: list[dict]) -> tuple[int, int]:
    """(verdicts, of which changed) when the agent is re-run on each patient with the trials in reverse order."""
    from run import interview

    changed = total = 0
    for log in logs:
        again = interview((log["qid"], list(reversed(log["trials"])), agent, "llm", BUDGET))
        total += len(log["trials"])
        changed += sum(again["final_verdicts"][n] != log["final_verdicts"][n] for n in log["trials"])
    return total, changed


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT))
    runs = ROOT / "runs" / "dev_llm"
    for agent in sys.argv[1:] or ["llm_only", "llm_only_intake", "ours"]:
        logs = [json.loads(line) for line in (runs / f"{agent}.jsonl").open()]
        if agent.startswith("llm_only"):
            out, backed = map(sum, zip(*(backed_rejections(log) for log in logs)))
            print(f"{agent}: {backed} of {out} rejections backed by Z3 from the conversation")
        total, changed = verdict_changes(agent, logs)
        print(f"{agent}: {changed} of {total} verdicts change when the trial order is reversed")
