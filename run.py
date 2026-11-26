"""Run the question-asking agents on the patients and print how accurate each one is.

  uv run python run.py                           # dev patients: no_questions, greedy_smt, ours
  uv run python run.py --ablations               # also two cut-down versions of ours
  uv run python run.py --split test --confirmed  # test patients: run once, on the final agent

What it does:
  1. Each agent interviews each patient, up to 30 questions, using the course staff's conversation
     loop (smtstate/runner.py) and answer-key patient (smtstate/sim.py).
  2. After every question, count how many trial verdicts are right. A trial that is still
     undecided counts as "eligible".
  3. Print accuracy after 0, 5, 10, 20 and 30 questions, and the AUC: the area under the accuracy
     curve from 0 to 30 questions, on a 0-1 scale.
  4. Check whether each agent's gap to greedy_smt is real or luck (a bootstrap: re-draw the
     patients at random 2,000 times and see how much the gap moves).

No language model and no API key.
"""

import argparse
import os
import sys
from multiprocessing import Pool
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

from baselines.policies import greedy_smt, no_questions  # noqa: E402
from smt_trial_matching import policies as ours  # noqa: E402
from smt_trial_matching.data import load_gold, patients  # noqa: E402
from smtstate.runner import run_patient  # noqa: E402
from smtstate.sim import AnswerKeySimulator  # noqa: E402

AGENTS = {
    "no_questions": no_questions,  # asks nothing: the starting point
    "greedy_smt": greedy_smt,  # the course staff's baseline, the one to beat
    "ours": ours.answerable_informative,  # our agent: P(answered) x value
    "ours_no_answerability": ours.answerable_informative_no_answerability,  # ours without P(answered)
    "ours_no_value": ours.answerable_informative_no_value,  # ours without value
}
BASELINE = "greedy_smt"
BUDGET = 30  # most questions per patient
SHOW_AFTER = (0, 5, 10, 20, 30)  # question counts shown in the table
BOOTSTRAP_DRAWS = 2000
SEED = 0


def interview(job):
    """One agent interviews one patient. Returns the log of the conversation."""
    patient, trials, agent = job
    return run_patient(patient, trials, AGENTS[agent], AnswerKeySimulator("gpt5_oracle"), budget=BUDGET)


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
    args = parser.parse_args(argv)
    if args.split == "test" and not args.confirmed:
        raise SystemExit("test is run once per final system: add --confirmed if that is what you mean")

    agents = ["no_questions", "greedy_smt", "ours"]
    if args.ablations:
        agents += ["ours_no_answerability", "ours_no_value"]
    patient_list = patients(args.split)  # [(patient, [its candidate trials]), ...]
    gold = load_gold()  # (patient, trial) -> True if truly eligible

    # The bootstrap's re-draws: each row is the patient list drawn again at random, with repeats.
    # Every agent uses the same re-draws, so the comparison with greedy_smt is like for like.
    redraws = np.random.default_rng(SEED).integers(0, len(patient_list), size=(BOOTSTRAP_DRAWS, len(patient_list)))

    n_pairs = sum(len(trials) for _, trials in patient_list)
    print(f"split {args.split} ({len(patient_list)} patients, {n_pairs} pairs), "
          f"answer key gpt5_oracle, budget {BUDGET}\n")
    print(f"{'policy':<24}" + "".join(f"{'k=' + str(k):>8}" for k in SHOW_AFTER)
          + f"{'AUC':>8}{'questions':>11}{'unanswered':>12}")

    accuracy = {}  # agent -> accuracy after 0..30 questions
    redrawn_accuracy = {}  # agent -> the same, for each bootstrap re-draw
    with Pool(os.cpu_count() or 1) as pool:  # interview several patients at once
        for agent in agents:
            logs = pool.map(interview, [(patient, trials, agent) for patient, trials in patient_list])
            correct, trials = correct_counts(logs, gold, BUDGET)
            accuracy[agent] = correct.sum(0) / trials.sum()
            redrawn_accuracy[agent] = correct[redraws].sum(1) / trials[redraws].sum(1)[:, None]

            turns = [turn for log in logs for turn in log["turns"]]
            questions_per_patient = len(turns) / len(patient_list)
            not_sure = sum(turn["answer"] is None for turn in turns) / len(turns) if turns else 0.0
            print(f"{agent:<24}" + "".join(f"{accuracy[agent][k]:>8.3f}" for k in SHOW_AFTER)
                  + f"{auc(accuracy[agent], BUDGET):>8.3f}{questions_per_patient:>11.1f}{not_sure:>12.1%}",
                  flush=True)

    print(f"\ndifference from {BASELINE} [95% CI] (paired bootstrap over patients)")
    for agent in agents:
        if agent in (BASELINE, "no_questions"):
            continue
        gap_at_30 = describe_gap(
            accuracy[agent][BUDGET] - accuracy[BASELINE][BUDGET],
            redrawn_accuracy[agent][:, BUDGET] - redrawn_accuracy[BASELINE][:, BUDGET])
        gap_in_auc = describe_gap(
            float(auc(accuracy[agent], BUDGET) - auc(accuracy[BASELINE], BUDGET)),
            auc(redrawn_accuracy[agent], BUDGET) - auc(redrawn_accuracy[BASELINE], BUDGET))
        print(f"{agent:<24} k={BUDGET}: {gap_at_30}   AUC: {gap_in_auc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
