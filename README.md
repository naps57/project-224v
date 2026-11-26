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
NCT00287378: ineligible
  exclusion criterion: Use of systemic steroid therapy within the preceding 12 months.
    broken by: patient_has_undergone_administration_of_steroid_inthepast12months = True
```

## The agents

| Agent | Picks questions by | Decides verdicts with | Where |
|---|---|---|---|
| **ours** | P(answered) × value, over the facts Z3 says could still matter | Z3 | `src/smt_trial_matching/policies.py` |
| `greedy_smt` (course baseline) | Any fact whose answer could decide a trial | Z3 | `baselines/policies.py` |
| `llm_only` (course baseline) | Gemini, from the trials' criteria text and the conversation so far | Gemini | `src/smt_trial_matching/llm_only.py` |
| `ours_hybrid` | As ours | Z3; Gemini only for the trials Z3 leaves undecided (logged as unverified) | `run.py`, `llm_only.judge` |

- **P(answered)** is a logistic regression on the words of a fact's name (`answerability.py`). It is fit on
  dev patients only, and each dev patient is scored by a model fit on the other dev patients.
- **Value** is how much an answer would settle: ruling a trial out counts most, ruling out one of its cohorts
  counts in proportion, confirming a trial counts a little.
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
| **ours** | **0.782** | **0.760** | **0.771** |
| ours_hybrid | 0.782 | 0.794 | 0.788 |

| Comparison | Dev | Test | Dev + test |
|---|---|---|---|
| ours − llm_only | +0.085 [+0.010, +0.176], **p = 0.023** | +0.091 [−0.066, +0.283], p = 0.353 | +0.088 [−0.003, +0.184], p = 0.063 |
| ours − greedy_smt | +0.048 [−0.005, +0.101], p = 0.094 | +0.023 [−0.043, +0.090], p = 0.599 | +0.036 [−0.008, +0.080], p = 0.111 |
| ours_hybrid − llm_only | +0.085 [−0.026, +0.225], p = 0.213 | +0.126 [−0.045, +0.310], p = 0.182 | +0.105 [−0.003, +0.218], p = 0.061 |

- **Ours beats the LLM-only baseline by about 9 points on both dev and the held-out test patients.** It is
  significant on dev; on test alone it is not, because the test gain is concentrated in a few patients with
  many trials (net +16 correct verdicts: +13 on trec-202159, which has 17 trials, +7 on one other patient, and
  −4 across the remaining 27 patients). Pooling dev and test (28 of the 57 patients were used during development) gives p = 0.063.
- **Ours is ahead of greedy_smt on dev and test, but not significantly.** Both share the intake, the question
  writer and the answer reader, so this row measures only the question choice, over the 6 questions after the
  intake. With more questions the gap is larger: on dev, at 15 questions without the intake, ours beat
  greedy_smt by +0.112 (p = 0.013).
- **The hybrid** changes only the trials Z3 leaves undecided. On dev Gemini's verdicts there fixed 14 and broke
  14 (no net change); on test they added 3.4 points. Its Gemini verdicts are not verifiable.
- **Fact linking** (`ours_linked`, dev only) lets one answer fill the same fact in every trial. Each trial is its
  own Z3 program, so "has asthma now" in one trial and "diagnosis of asthma now" in another are separate
  variables. A table of "same as" and "implies" links between them (`links.py`, built once with Gemini) fills
  every linked fact by logic. Links between two different time frames are left out: patients say "past" to mean
  before now, while the trials' "in the history" includes now, so "no past conditions" would rule out a
  condition the patient has now. On dev: 0.787 vs 0.782 for ours (+0.090 over llm_only, p = 0.022).
- **Every verdict of ours is decided by Z3** and can be explained with the criterion and the answer behind it
  (`explain.py`); the LLM-only baseline's verdicts cannot.

**What each change added** (ours, dev):

| Step | ours | llm_only |
|---|---|---|
| First LLM conversation: one fact per question, reader keeps only the asked fact (15 questions) | 0.633 | 0.697 |
| Reader fills every fact a reply settles | 0.713 | 0.697 |
| Related facts asked together in one question | 0.739 | 0.697 |
| + 4-question intake and topic skipping, 10 questions | 0.782 | 0.697 |

The budget is 10 questions because on dev accuracy peaked there: later answers were mostly "not sure" and
occasionally pushed a correct verdict the wrong way.

**Reference: lookup patient (perfect communication).** Before the LLM conversation, the patient was a lookup
table of GPT-5's reading of each note (`smtstate/sim.py`, `data/answer_keys/gpt5_oracle.jsonl`). On test at
30 questions: ours 0.760, greedy_smt 0.646 (+0.114, p = 0.034).

**Answer reader check.** On 103 facts from 2 dev patients, the reader agreed with the GPT-5 answer key on
89%, missed 7% (said unknown), gave a value where the key said unknown on 4%, and gave a wrong value on 0%.

## What could come next

- **Catch contradictions.** With facts linked across trials, Z3 can find answers that conflict and the agent
  can ask a clarifying question. The fact links make this possible now.
- **Ask fewer questions patients can't answer.** About two thirds of the questions after the intake get
  "not sure". P(answered) was fit on the GPT-5 answer key, which knows more than the patient says.

## Run it

Needs Python 3.11+ and [uv](https://docs.astral.sh/uv/). The LLM runs need a Gemini API key.

```bash
uv sync
uv run python run.py                                  # dev, lookup patient (no API key)
export GEMINI_API_KEY=...
uv run python run.py --patient llm --budget 10        # dev, LLM patient: ours, greedy_smt, llm_only
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
| `src/smt_trial_matching/policies.py` | Our agent: the score and the rule for picking a question |
| `src/smt_trial_matching/answerability.py` | The logistic regression that predicts P(answered) |
| `src/smt_trial_matching/interview.py` | The conversation: intake, question writer, answer reader, `LLMPatient`, the reader check |
| `src/smt_trial_matching/patient.py` | The LLM patient (the course's simulator prompt) |
| `src/smt_trial_matching/llm_only.py` | The LLM-only baseline (the course's questioner prompt) |
| `src/smt_trial_matching/explain.py` | Explains each ruled-out trial with Z3's unsat core |
| `src/smt_trial_matching/links.py`, `links.json` | Links the same fact across trials, and the link table |
| `src/smt_trial_matching/audit.py` | How many of the LLM-only agent's rejections Z3 can back, and whether trial order changes verdicts |
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
