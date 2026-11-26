"""Run the question-asking agents on the patients and print how accurate each one is.

  uv run python run.py                           # dev patients: no_questions, greedy_smt, ours
  uv run python run.py --ablations               # also two cut-down versions of ours
  uv run python run.py --split test --confirmed  # test patients: run once, on the final agent
  uv run python run.py --patient llm --budget 15 # talk to the LLM patient instead of the answer key

What it does:
  1. Each agent interviews each patient, up to 30 questions (--budget), using the course staff's
     conversation loop (smtstate/runner.py). The patient is the staff's answer-key lookup
     (smtstate/sim.py) or, with --patient llm, our LLM patient (src/smt_trial_matching/interview.py).
     Logs, with transcripts for the LLM patient, are saved to runs/<split>_<patient>/.
  2. After every question, count how many trial verdicts are right. A trial that is still
     undecided counts as "eligible".
  3. Print accuracy after 0, 5, 10, ... questions, and the AUC: the area under the accuracy curve
     from 0 to the budget, on a 0-1 scale.
  4. Check whether each agent's gap to greedy_smt (and, with --patient llm, to the LLM-only
     baseline in src/smt_trial_matching/llm_only.py) is real or luck (a bootstrap: re-draw the
     patients at random 2,000 times and see how much the gap moves).

With --patient lookup (the default) no language model runs and no API key is needed.
--patient llm calls Gemini and needs GEMINI_API_KEY.
"""

import argparse
import json
import os
import sys
from multiprocessing import Pool
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

from baselines.policies import greedy_smt, no_questions  # noqa: E402
from smt_trial_matching import llm_only  # noqa: E402
from smt_trial_matching import policies as ours  # noqa: E402
from smt_trial_matching.data import load_gold, patients  # noqa: E402
from smt_trial_matching.interview import LLMPatient  # noqa: E402
from smtstate.runner import run_patient  # noqa: E402
from smtstate.sim import AnswerKeySimulator  # noqa: E402

AGENTS = {
    "no_questions": no_questions,  # asks nothing: the starting point
    "llm_only": None,  # Gemini interviews and decides alone, no solver (needs --patient llm)
    "greedy_smt": greedy_smt,  # the course staff's baseline, the one to beat
    "ours": ours.answerable_informative,  # our agent: P(answered) x value
    "ours_no_answerability": ours.answerable_informative_no_answerability,  # ours without P(answered)
    "ours_no_value": ours.answerable_informative_no_value,  # ours without value
}
REFERENCES = ("greedy_smt", "llm_only")  # every agent is compared with these
BOOTSTRAP_DRAWS = 2000
SEED = 0


def interview(job):
    """One agent interviews one patient. Returns the log of the conversation.
    The patient is the answer-key lookup (perfect communication) or the LLM patient (a real conversation)."""
    patient, trials, agent, who, budget = job
    if agent == "llm_only":
        return llm_only.interview(patient, trials, budget)
    sim = LLMPatient() if who == "llm" else AnswerKeySimulator("gpt5_oracle")
    log = run_patient(patient, trials, AGENTS[agent], sim, budget=budget)
    if who == "llm":
        log["transcript"] = sim.transcript
    return log


def show_after(budget):
    """Question counts shown in the table: 0, 5, 10, 20, 30 up to the budget, and the budget itself."""
    return sorted({k for k in (0, 5, 10, 20, 30) if k < budget} | {budget})


def verdicts_at(log, k):
    """The agent's verdicts after k questions. If it stopped early, its last verdicts stand."""
    turns = log["turns"]
    if k == 0 or not turns:
        return log["initial_verdicts"]
    return turns[min(k, len(turns)) - 1]["verdicts"]


def correct_counts(logs, gold, budget):
    """For each patient, how many verdicts are right after 0, 1, ..., budget questions.
    Also returns how many trials each patient has."""
    correct = []
    for log in logs:
        row = []
        for k in range(budget + 1):
            verdicts = verdicts_at(log, k)
            row.append(sum((verdicts[t] == "eligible") == gold[(log["qid"], t)] for t in log["trials"]))
        correct.append(row)
    trials = [len(log["trials"]) for log in logs]
    return np.array(correct), np.array(trials)


def auc(accuracy, budget):
    """Area under the accuracy curve from 0 to `budget` questions, on a 0-1 scale."""
    return np.trapezoid(accuracy, dx=1.0, axis=-1) / budget


def describe_gap(gap, redrawn_gaps):
    """Format a gap as: gap [95% range over the re-draws], p-value."""
    low, high = np.percentile(redrawn_gaps, [2.5, 97.5])
    p = min(1.0, 2 * min(np.mean(redrawn_gaps <= 0), np.mean(redrawn_gaps >= 0)))
    p_text = "p < 0.001" if p < 0.001 else f"p = {p:.3f}"
    return f"{gap:+.3f} [{low:+.3f}, {high:+.3f}], {p_text}"


def main(argv=None):
    parser = argparse.ArgumentParser(description="Run the agents and print their accuracy.")
    parser.add_argument("--split", choices=["dev", "test"], default="dev")
    parser.add_argument("--ablations", action="store_true", help="also run the two cut-down versions of ours")
    parser.add_argument("--confirmed", action="store_true", help="required for --split test")
    parser.add_argument("--patient", choices=["lookup", "llm"], default="lookup",
                        help="lookup = answer key (perfect communication), llm = LLM patient")
    parser.add_argument("--budget", type=int, default=30, help="most questions per patient")
    args = parser.parse_args(argv)
    if args.split == "test" and not args.confirmed:
        raise SystemExit("test is run once per final system: add --confirmed if that is what you mean")

    agents = ["no_questions", "llm_only", "greedy_smt", "ours"] if args.patient == "llm" else \
        ["no_questions", "greedy_smt", "ours"]
    if args.ablations:
        agents += ["ours_no_answerability", "ours_no_value"]
    patient_list = patients(args.split)  # [(patient, [its candidate trials]), ...]
    gold = load_gold()  # (patient, trial) -> True if truly eligible
    budget, shown = args.budget, show_after(args.budget)
    out = ROOT / "runs" / f"{args.split}_{args.patient}"  # logs in the staff format, for eval/evaluate.py
    out.mkdir(parents=True, exist_ok=True)

    # The bootstrap's re-draws: each row is the patient list drawn again at random, with repeats.
    # Every agent uses the same re-draws, so every comparison is like for like.
    redraws = np.random.default_rng(SEED).integers(0, len(patient_list), size=(BOOTSTRAP_DRAWS, len(patient_list)))

    n_pairs = sum(len(trials) for _, trials in patient_list)
    print(f"split {args.split} ({len(patient_list)} patients, {n_pairs} pairs), "
          f"patient {args.patient}, budget {budget}\n")
    print(f"{'policy':<24}" + "".join(f"{'k=' + str(k):>8}" for k in shown)
          + f"{'AUC':>8}{'questions':>11}{'unanswered':>12}")

    accuracy = {}  # agent -> accuracy after 0..30 questions
    redrawn_accuracy = {}  # agent -> the same, for each bootstrap re-draw
    with Pool(os.cpu_count() or 1) as pool:  # interview several patients at once
        for agent in agents:
            jobs = [(patient, trials, agent, args.patient, budget) for patient, trials in patient_list]
            logs = pool.map(interview, jobs)
            (out / f"{agent}.jsonl").write_text("".join(json.dumps(log) + "\n" for log in logs))
            correct, trials = correct_counts(logs, gold, budget)
            accuracy[agent] = correct.sum(0) / trials.sum()
            redrawn_accuracy[agent] = correct[redraws].sum(1) / trials[redraws].sum(1)[:, None]

            turns = [turn for log in logs for turn in log["turns"]]
            questions_per_patient = len(turns) / len(patient_list)
            not_sure = sum(turn["answer"] is None for turn in turns) / len(turns) if turns else 0.0
            print(f"{agent:<24}" + "".join(f"{accuracy[agent][k]:>8.3f}" for k in shown)
                  + f"{auc(accuracy[agent], budget):>8.3f}{questions_per_patient:>11.1f}{not_sure:>12.1%}",
                  flush=True)

    for ref in (r for r in REFERENCES if r in agents):
        print(f"\ndifference from {ref} [95% CI] (paired bootstrap over patients)")
        for agent in agents:
            if agent in (ref, "no_questions") or (ref == "llm_only" and agent == "greedy_smt"):
                continue
            gap_at_end = describe_gap(
                accuracy[agent][budget] - accuracy[ref][budget],
                redrawn_accuracy[agent][:, budget] - redrawn_accuracy[ref][:, budget])
            gap_in_auc = describe_gap(
                float(auc(accuracy[agent], budget) - auc(accuracy[ref], budget)),
                auc(redrawn_accuracy[agent], budget) - auc(redrawn_accuracy[ref], budget))
            print(f"{agent:<24} k={budget}: {gap_at_end}   AUC: {gap_in_auc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
