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
and pregnancy. Turns 5 to 15 are chosen as above. The conversation stops after 15 questions or when nothing
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
$ uv run python -m smt_trial_matching.explain runs/dev_llm/ours.jsonl trec-202123
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

- **P(answered)** is a logistic regression on the words of a fact's name (`answerability.py`). It is fit on
  dev patients only, and each dev patient is scored by a model fit on the other dev patients.
- **Value** is how much an answer would settle: ruling a trial out counts most, ruling out one of its cohorts
  counts in proportion, confirming a trial counts a little.
- `ours` and `greedy_smt` share the same question writer, patient and reader, so comparing them isolates the
  question choice. `llm_only` talks to the same patient with the same 15-question budget, using the course's
  prompt (`docs/llm_only_baseline_prompt.md`). As the course allows, its final verdicts are recorded at every
  turn, so it is compared at the final budget.

## Results

Accuracy over (patient, trial) pairs. Significance is a paired bootstrap over patients (2,000 re-draws).
All numbers below are on the **dev** split (28 patients, 188 pairs). The test split is run once, on the
final system.

**Current system, real conversation, 15 questions** (before the 4-question intake; the intake run is in
progress):

| Agent | Accuracy at 15 | Questions per patient |
|---|---|---|
| no questions | 0.532 | 0 |
| greedy_smt | 0.628 | 14.4 |
| llm_only | 0.697 | 3.5 |
| **ours** | **0.739** | 13.7 |

| Comparison | Gap at 15 | 95% CI | p |
|---|---|---|---|
| ours − greedy_smt | +0.112 | +0.021 to +0.204 | **0.013** |
| ours − llm_only | +0.043 | −0.032 to +0.116 | 0.311 |
| llm_only − greedy_smt | +0.069 | −0.029 to +0.182 | 0.212 |

Ours beats greedy significantly. Ours is ahead of LLM-only but not significantly: with 28 patients a gap of
about 7.5 points is needed. At worst ours is about 3 points behind LLM-only, and every one of its verdicts is
checkable.

**What each change added** (ours, accuracy at 15):

| Step | ours | llm_only |
|---|---|---|
| First LLM conversation: one fact per question, reader keeps only the asked fact | 0.633 | 0.697 |
| Reader fills every fact a reply settles | 0.713 | 0.697 |
| Related facts asked together in one question | 0.739 | 0.697 |
| + 4-question intake, topic skipping, leaner reader | 0.761 | 0.697 |

**P(answered) matters in conversation.** Removing it costs 4.8 points (0.713 → 0.665, p = 0.12). With the
old lookup patient it changed almost nothing (AUC 0.700 vs 0.695).

**Reference: lookup patient (perfect communication).** Before the LLM conversation, the patient was a lookup
table of GPT-5's reading of each note (`smtstate/sim.py`, `data/answer_keys/gpt5_oracle.jsonl`). At 15
questions on dev: ours 0.713, greedy 0.596. On test at 30 questions: ours 0.760, greedy 0.646 (+0.114,
p = 0.034).

**Answer reader check.** On 103 facts from 2 dev patients, the reader agreed with the GPT-5 answer key on
89%, missed 7% (said unknown), gave a value where the key said unknown on 4%, and gave a wrong value on 0%.

## What we plan to change

- **Link the same fact across trials.** Each trial is its own Z3 program, so "has asthma now" in one trial and
  "diagnosis of asthma now" in another are separate variables. A fixed table of "same as" and "implies" links
  (e.g. on oral steroids now → steroids in the past month → steroids in the past year) would let one answer
  fill every linked fact by logic rather than by the reader. It would also stop reworded repeat questions.
- **Catch contradictions.** With facts linked across trials, Z3 can find answers that conflict and the agent
  can ask a clarifying question. Today no trial ends with conflicting answers, so this waits on the links.
- **Retrain P(answered) on the LLM patient.** It was fit on the GPT-5 answer key, which knows more than the
  patient says, so the agent still asks things patients can't know (device models, test scores).
- **Run the test split once** on the frozen system: ours, greedy_smt and llm_only.

## Run it

Needs Python 3.11+ and [uv](https://docs.astral.sh/uv/). The LLM runs need a Gemini API key.

```bash
uv sync
uv run python run.py                                  # dev, lookup patient (no API key)
export GEMINI_API_KEY=...
uv run python run.py --patient llm --budget 15        # dev, LLM patient: ours, greedy_smt, llm_only
uv run python -m smt_trial_matching.interview trec-202140 trec-202135   # reader check vs the answer key
uv run python -m smt_trial_matching.explain runs/dev_llm/ours.jsonl trec-202123   # why trials were ruled out
uv run pytest                                         # tests; tests/test_live.py runs only with a key
```

The test split needs `--split test --confirmed`; it is run once per final system. Every Gemini reply is
cached in `cache/llm/` (temperature 0), so reruns are free and give the same results. Conversation logs,
with full transcripts, are written to `runs/<split>_<patient>/` in the staff's log format, so
`eval/evaluate.py` can score them too.

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
| `src/smt_trial_matching/llm.py` | Gemini calls, cached on disk |
| `src/smt_trial_matching/data.py` | Reads the dataset |
| `run.py` | Runs the agents and prints accuracy and the bootstrap tests |
| `tests/` | Free checks with scripted model replies, plus real-Gemini checks in `test_live.py` |

Provided by the course staff, used as provided:

| Folder | What it is |
|---|---|
| `smtstate/` | The solver state for a trial, the lookup patient, and the loop that runs a conversation |
| `baselines/` | The baseline agents, including `greedy_smt` |
| `eval/` | The staff's evaluation script |
| `data/` | 57 patients and 263 trials from TREC 2021 Clinical Trials (363 patient and trial pairs), the trial rules as Z3 programs, the answer keys, and the dev/test split |
| `docs/` | The course's prompts for the LLM patient and the LLM-only baseline |
| `logs/reference/` | The staff's log of `greedy_smt` with the lookup patient; the tests check against it |
