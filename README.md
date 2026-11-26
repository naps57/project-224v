# Conversational clinical-trial matching

An agent asks a patient questions, one fact at a time, to decide which clinical trials the patient is
eligible for. The goal is to get the verdicts right with as few questions as possible.

Each trial's eligibility rules have been turned into logic formulas ahead of time. After every answer, a
logic solver (Z3) says exactly whether each trial is ruled out, confirmed, or still open. The baseline
agent asks any question that could settle a trial. The problem is that most of those facts are not in the
patient's record, so many questions come back "not sure" and are wasted. Our agent scores each question by
**the chance the patient can answer it, times how much the answer would settle**, and asks the top one.

## How one conversation works

1. The patient has a set of candidate trials. All start as "undetermined".
2. The agent picks one fact to ask about, for example "Are you currently receiving light therapy?"
3. The simulated patient answers yes, no, a number, or "not sure".
4. The answer is given to Z3. Z3 rechecks every trial: ineligible (a rule is now broken), eligible (the
   rules hold whatever else is unknown), or still undetermined.
5. Repeat until no question could change anything, or 30 questions have been asked.
6. Score: each trial's verdict is compared with the true label from the dataset. A trial that is still
   undetermined counts as eligible.

## The two agents

| | How it picks the next question | Where |
|---|---|---|
| `greedy_smt` (baseline) | Any question whose answer could decide a trial. Ignores whether the patient can answer. | `baselines/policies.py` |
| `ours` | Highest score, where score = P(answered) x value. | `src/smt_trial_matching/policies.py` |

- **P(answered)** is predicted by a logistic regression from the words in the variable's name
  (`src/smt_trial_matching/answerability.py`). It never sees the patient.
- **Value** is how much an answer would settle: ruling a trial out counts most, ruling out part of a trial
  counts in proportion, confirming a trial counts a little.

## Results

Accuracy over (patient, trial) pairs after k questions. AUC is the area under the accuracy curve from 0
to 30 questions, on a 0 to 1 scale.

**Test split** (29 patients, 175 pairs; run once, details in `docs/results/policy_v1_test.md`)

| | k=10 | k=30 | AUC |
|---|---|---|---|
| no questions | 0.514 | 0.514 | 0.514 |
| greedy_smt | 0.594 | 0.646 | 0.599 |
| ours | 0.640 | 0.760 | 0.663 |

At 30 questions ours beats greedy by +0.114 (95% CI +0.01 to +0.22, p = .034). The differences at 10
questions and on AUC are positive but not statistically significant.

**Dev split** (28 patients, 188 pairs; printed by `run.py --ablations`)

| | k=10 | k=30 | AUC |
|---|---|---|---|
| greedy_smt | 0.564 | 0.691 | 0.599 |
| ours | 0.670 | 0.793 | 0.700 |
| ours without P(answered) | 0.670 | 0.793 | 0.695 |
| ours without value | 0.633 | 0.718 | 0.649 |

**What the ablation says:** removing value costs about 5 points of AUC. Removing P(answered) costs almost
nothing. So most of the gain over greedy comes from value weighting, not from predicting answerability.

## What is in this repo

Our code:

| File | What it does |
|---|---|
| `src/smt_trial_matching/policies.py` | Our agent: the score, and the rule for picking a question |
| `src/smt_trial_matching/answerability.py` | The logistic regression that predicts P(answered) |
| `src/smt_trial_matching/data.py` | Small helpers that read the dataset |
| `run.py` | Runs the agents on a split and prints the tables above |
| `tests/` | Checks for the solver library, our agent and the scoring |

Provided by the course staff, used as provided:

| Folder | What it is |
|---|---|
| `smtstate/` | The solver state for a trial, the patient simulator, and the loop that runs a conversation |
| `baselines/` | The baseline agents, including `greedy_smt` |
| `eval/` | The staff's evaluation script |
| `data/` | 57 patients and 263 trials from TREC 2021 Clinical Trials (363 patient and trial pairs), the trial rules as Z3 programs, the answer keys, and the dev/test split |
| `docs/*.md` | Prompts for two extensions the course package describes (not built yet) |

`docs/results/` holds our two results write-ups.

## How the patient is simulated

The patient is a lookup table, not a language model. Before any experiment, GPT-5 read each patient's
note and recorded the value of every variable in that patient's trials, or "unknown" if the note does not
say. That file is the answer key (`data/answer_keys/gpt5_oracle.jsonl`). When the agent asks about a
variable, the simulator returns the stored value. About 57% of the stored values are unknown.
