# Conversational clinical-trial matching

An agent interviews a patient to decide which clinical trials they are eligible for, asking as few
questions as possible. Following the approach of Lam's lab (Genie, VERDICT), **language models handle the
conversation and a logic solver handles the reasoning**: an LLM asks the questions and reads the answers,
while Z3 holds every trial's eligibility rules and makes every verdict. Each verdict can be traced to the
written criterion it breaks and the patient's answer that broke it.

## How one conversation works

The patient has a set of candidate trials (6 on average, up to 23). All start as "undetermined". Each turn:

1. **Pick what to ask.** Z3 lists every unanswered fact that could still change a trial's verdict. Our
   scoring picks the best one (see "The agents" below).
2. **Write the question.** A Gemini "doctor" turns the fact into a plain-English question. Open facts on the
   same topic (e.g. asthma ever, asthma now, asthma uncontrolled) are asked together in one natural question.
3. **The patient answers.** A second Gemini plays the patient, using the course's simulator prompt
   (`docs/nl_simulator_prompt.md`) as given. It sees only the patient's medical note and the question, and
   says "I'm not sure" when the note does not say.
4. **Read the answer.** A third Gemini call turns the free-text reply into yes / no / a number for **every**
   open fact the reply settles, across all of the patient's trials, not only the one asked about (Genie's
   contextual parser does the same). Facts the reply doesn't settle stay unknown.
5. **Z3 updates every trial:** ineligible (a rule is broken), eligible (the rules hold whatever else is
   unknown), or still undetermined. A topic the patient said they don't know about is not asked again.

The first four turns are a fixed intake, the same for every patient, in the standard order of a clinical
history: background and language; main conditions; medications and allergies; surgeries, smoking, alcohol
and pregnancy. Turns 5 to 10 are chosen as above. The conversation stops after 10 questions or when nothing
could change a verdict. A trial still undetermined at the end counts as eligible (the course's rule: unknown
facts do not disqualify).

## How the solver works

Each trial's inclusion and exclusion criteria were compiled ahead of time into Z3 programs
(`data/programs/`), one per cohort and side. Each rule is named after the criterion it encodes (`REQ8_...`
is the 9th written criterion). Given the answers so far, Z3 checks each program:

- **violated:** the answers plus the rules are unsatisfiable, so some criterion already fails → ineligible;
- **satisfied:** no way of filling in the unknown facts could break the rules → eligible;
- **open:** otherwise.

To explain a verdict, `explain.py` checks each rule on its own and uses Z3's unsat core to find the answers
that break it:

```
$ uv run python -m smt_trial_matching.explain results/dev/ours.jsonl trec-202123
...
NCT00287378: ineligible
  ...
  exclusion criterion: Use of systemic steroid therapy within the preceding 12 months.
    broken by: patient_has_undergone_administration_of_steroid_inthepast12months = True
```

## The agents

| Agent | Picks questions by | Decides verdicts with | Where |
|---|---|---|---|
| **ours** | The fact whose answer could settle the most, added up over every open trial that asks about it | Z3 | `src/smt_trial_matching/policies.py` |
| `greedy_smt` (course baseline) | Any fact whose answer could decide a trial | Z3 | `baselines/policies.py` |
| `llm_only` (course baseline) | Gemini, from the trials' criteria text and the conversation so far | Gemini | `src/smt_trial_matching/llm_only.py` |

- **Value** is how much an answer would settle: ruling a trial out counts most, ruling out one of its cohorts
  counts in proportion, confirming a trial counts a little. A fact that several trials ask about counts for all
  of them, since one answer is read into every trial.
- **Nothing is learned from patients' answers in advance.** A "no" is weighted more than a "yes" on one fixed
  assumption, set once and not tuned: most patients don't have most of the conditions a trial asks about (20%
  chance of yes). An earlier version learned these chances, and how likely a patient could answer at all, from
  the GPT-5 answer key, which the lookup patient also answers from. That made the lookup results circular, so it
  was removed (dev: 0.782 before, 0.750 after; test: 0.760 before, 0.771 after).
- `ours` and `greedy_smt` share the same question writer, patient and reader, so comparing them isolates the
  question choice. `llm_only` talks to the same patient with the same 10-question budget, using the course's
  prompt (`docs/llm_only_baseline_prompt.md`). As the course allows, its final verdicts are recorded at every
  turn, so it is compared at the final budget.

## Results

Final system, frozen on dev: 4-question intake, then our question choice,
10 questions in total. Accuracy over (patient, trial) pairs after 10 questions. Significance is a two-sided
paired bootstrap over patients (2,000 re-draws), as printed by `run.py`. Logs of these runs are in `results/`.

| Agent | Dev (28 patients, 188 pairs) | Test (29 patients, 175 pairs) | Dev + test (57 patients) |
|---|---|---|---|
| no questions | 0.532 | 0.514 | 0.523 |
| llm_only | 0.697 | 0.669 | 0.683 |
| greedy_smt | 0.734 | 0.737 | 0.736 |
| **ours** | **0.750** | **0.771** | **0.760** |

| Comparison | Dev | Test | Dev + test |
|---|---|---|---|
| ours − llm_only | +0.053 [−0.009, +0.128], p = 0.148 | +0.103 [+0.000, +0.219], p = 0.061 | +0.077 [+0.014, +0.144], **p = 0.013** |
| ours − greedy_smt | +0.016 [−0.040, +0.069], p = 0.659 | +0.034 [−0.036, +0.103], p = 0.383 | +0.025 [−0.017, +0.069], p = 0.279 |

- **What the architecture gives.** Every verdict of ours is decided by Z3 and can be explained with the criterion
  and the answer behind it (`explain.py`); the LLM-only baseline's verdicts cannot. When Z3 decides a trial it is
  right 80% of the time on dev (60 of 75) and 90% on test (57 of 63). Asking nothing scores 0.532 on dev; with
  perfect answers and no question limit ours reaches 0.947 (lookup patient, dev). Ten questions with the LLM
  patient close about half of that gap.
- **Against LLM-only.** Ours is ahead on both splits (+0.053 dev, +0.103 test). On test it does better on 9
  patients, ties on 17 and does worse on 3; the two largest gains are +7 correct verdicts each, and the other 27
  patients are net +4. Neither split alone is significant (test p = 0.061); pooled over all 57 patients it is
  (+0.077, p = 0.013). Dev was used for design choices, including the 10-question budget.
- **Against greedy_smt (our question choice).** Both share the intake, the question writer and the answer reader,
  so this row measures only which fact is asked about. Ours is ahead (+0.016 dev, +0.034 test) but not
  significantly: at this sample size our question choice does not beat greedy with the LLM patient. Most of the
  conversation's gains (reading every fact a reply settles, asking related facts together) help greedy_smt just
  as much.
- **Where the errors are.** Most trials are still undecided after 10 questions (113 of 188 on dev, 112 of 175 on
  test) and count as eligible. Ineligible trials that were never ruled out are 32 of ours' 47 errors on dev and
  34 of 40 on test.
- **Eligible patients wrongly ruled out:** ours 15 vs LLM-only 14 on dev, 6 vs 7 on test, about the same.

**What each change added** (ours, dev):

| Step | ours | llm_only |
|---|---|---|
| First LLM conversation: one fact per question, reader keeps only the asked fact (15 questions) | 0.633 | 0.697 |
| Reader fills every fact a reply settles | 0.713 | 0.697 |
| Related facts asked together in one question | 0.739 | 0.697 |
| + 4-question intake and topic skipping, 10 questions | 0.782 | 0.697 |
| Nothing learned from the answer key: fixed "most answers are no", facts summed across trials | 0.750 | 0.697 |

The budget is 10 questions because on dev accuracy peaked there: later answers were mostly "not sure" and
occasionally pushed a correct verdict the wrong way.

**Reference: lookup patient (perfect communication).** Before the LLM conversation, the patient was a lookup
table of GPT-5's reading of each note (`smtstate/sim.py`, `data/answer_keys/gpt5_oracle.jsonl`). On test at
30 questions: ours 0.720, greedy_smt 0.646 (+0.074, p = 0.120).

**Which parts of the score matter** (dev, lookup patient, 30 questions, `run.py --ablations --budget 30`):

| Agent | 10 questions | 30 questions | AUC |
|---|---|---|---|
| ours | 0.654 | 0.750 | 0.666 |
| ours without value (any fact that could decide a trial) | 0.580 | 0.681 | 0.607 |
| greedy_smt | 0.564 | 0.691 | 0.599 |

Value carries the gain over greedy_smt (AUC +0.066, p = 0.006; without value +0.008, p = 0.768).

**Answer reader check.** On 103 facts from 2 dev patients, the reader agreed with the GPT-5 answer key on
89%, missed 7% (said unknown), gave a value where the key said unknown on 4%, and gave a wrong value on 0%.

## What could come next

- **Sort the misses by cause.** For each ineligible trial never ruled out: was the deciding fact never asked,
  asked with "not sure" as the answer, or not in the patient's note at all? The last is a limit no question
  choice can fix.
- **Ask fewer questions patients can't answer.** About two thirds of the questions after the intake get
  "not sure". The policy has no estimate of what a patient can answer; one learned from conversations (not
  from an answer key) could skip more dead ends.

## Run it

Needs Python 3.11+ and [uv](https://docs.astral.sh/uv/). The LLM runs need a Gemini API key.

```bash
uv sync
export GEMINI_API_KEY=...
uv run python run.py                                  # dev, LLM patient: ours, greedy_smt, llm_only
uv run python run.py --patient lookup                 # dev, answer-key lookup patient (no API key)
uv run python -m smt_trial_matching.interview trec-202140 trec-202135   # reader check vs the answer key
uv run python -m smt_trial_matching.explain results/dev/ours.jsonl trec-202123   # why trials were ruled out
uv run pytest                                         # tests; tests/test_live.py runs only with a key
```

The test split needs `--split test --confirmed`. Every Gemini reply is
cached in `cache/llm/` (temperature 0), so reruns are free and give the same results. Conversation logs,
with full transcripts, are written to `runs/<split>_<patient>/` in the staff's log format, so
`eval/evaluate.py` can score them too. The logs of the final runs reported above are in `results/dev/` and
`results/test/`.

## What is in this repo

Our code:

| File | What it does |
|---|---|
| `src/smt_trial_matching/policies.py` | Our agent: the value of each question and the rule for picking one |
| `src/smt_trial_matching/interview.py` | The conversation: intake, question writer, answer reader, `LLMPatient`, the reader check |
| `src/smt_trial_matching/patient.py` | The LLM patient (the course's simulator prompt) |
| `src/smt_trial_matching/llm_only.py` | The LLM-only baseline (the course's questioner prompt) |
| `src/smt_trial_matching/explain.py` | Explains each ruled-out trial with Z3's unsat core |
| `src/smt_trial_matching/llm.py` | Gemini calls, cached on disk |
| `src/smt_trial_matching/data.py` | Reads the dataset |
| `run.py` | Runs the agents and prints accuracy and the bootstrap tests |
| `tests/` | Free checks with scripted model replies, plus real-Gemini checks in `test_live.py` |
| `results/` | Logs (with full transcripts) of the final dev and test runs reported above |

Provided by the course staff, used as provided:

| Folder | What it is |
|---|---|
| `smtstate/` | The solver state for a trial, the lookup patient, and the loop that runs a conversation |
| `baselines/` | The baseline agents, including `greedy_smt` |
| `eval/` | The staff's evaluation script |
| `data/` | 57 patients and 263 trials from TREC 2021 Clinical Trials (363 patient and trial pairs), the trial rules as Z3 programs, the answer keys, and the dev/test split |
| `docs/` | The course's prompts for the LLM patient and the LLM-only baseline |
| `logs/reference/` | The staff's log of `greedy_smt` with the lookup patient; the tests check against it |
