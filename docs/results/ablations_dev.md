> Note: this write-up was produced with the full experiment harness in the original repo
> (https://github.com/ardadastan04/ddx-genie). Commands and file paths below refer to that repo.
> In this repo, `run.py` reproduces the main numbers.

# Ablations of policy-v1 on dev (Nov 24, 2026)

**What this is for:** which part of `answerable_informative` (policy-v1, frozen at `ede13d9`) produces its gain over
`greedy_smt`. Each ablation switches off one factor of the score P(answered) × value (`AnswerableConfig`):

- `answerable_informative_no_answerability`: P(answered) = 1 for every question (informativeness × value only).
- `answerable_informative_no_value`: value = 1 if some answer could decide something, else 0 (answerability only).

- Split: **dev only** (28 patients, 188 pairs); budget 30; solver only, no LLM calls. Test has not been run for the
  ablations (needs Arda's OK; see `configs/ablations_test.yaml`).
- Keys: `gpt5_oracle` (primary) and `gpt5mini` (robustness). Dev patients use the cross-fitted answerability models.
- Command: `uv run python -m smt_trial_matching.experiment --config configs/ablations_dev.yaml --force`
  (main at `a65f35b`; the policy code is the frozen v1, so the numbers equal the Nov 19 pre-freeze run exactly).
- Reference for the paired tests: `answerable_informative`. Paired bootstrap over patients (95% CI) is primary.

## Headline

| Policy | Key | k=30 | AUC k=0..30 | Δ k=30 vs ours [95% CI], p | Δ AUC vs ours [95% CI], p |
|---|---|---|---|---|---|
| **answerable_informative (policy-v1)** | gpt5_oracle | **0.793** | **0.700** | – | – |
| no_answerability | gpt5_oracle | 0.793 | 0.695 | +0.000 [−0.09, +0.07], 1.00 | −0.005 [−0.05, +0.03], .78 |
| no_value | gpt5_oracle | 0.718 | 0.649 | **−0.074 [−0.14, −0.01], .029** | **−0.051 [−0.09, −0.01], .027** |
| greedy_smt | gpt5_oracle | 0.691 | 0.599 | **−0.101 [−0.19, −0.01], .026** | **−0.101 [−0.18, −0.03], <.001** |
| **answerable_informative (policy-v1)** | gpt5mini | **0.734** | **0.651** | – | – |
| no_answerability | gpt5mini | 0.718 | 0.644 | −0.016 [−0.08, +0.03], .68 | −0.008 [−0.05, +0.03], .65 |
| no_value | gpt5mini | 0.707 | 0.644 | −0.027 [−0.10, +0.05], .54 | −0.007 [−0.06, +0.04], .79 |
| greedy_smt | gpt5mini | 0.612 | 0.580 | **−0.122 [−0.23, −0.02], .023** | −0.072 [−0.16, +0.00], .068 |

**Does the Nov 19 finding hold?** Yes on the primary key: removing answerability changes nothing (AUC −0.005,
p = .78) and removing value weighting costs about 5 points of AUC (−0.051, p = .027). On `gpt5mini` neither
ablation is distinguishable from the full policy (both −0.01 AUC, n.s.), so the value-weighting effect is
key-dependent, and with 28 patients differences under ~0.05 should not be claimed.

Why answerability adds little despite changing most choices: see the answerability diagnostics in the README
(the policy's choice is answered 52% vs 26% for the P = 1 choice on the same state, but the ablation catches up
over its own 30-question conversation: 11.6 vs 13.9 answers per patient, realized value −7%).

---

The harness summary follows verbatim (`runs/ablations_dev/summary.md`; run outputs themselves are not committed).

# ablations_dev: accuracy vs question budget

Split `dev` (28 patients, 188 pairs), answer keys `gpt5_oracle`, `gpt5mini`, budget 30, commit `a65f35bf73b0`. 95% CIs bootstrap over patients (2,000 resamples, seed 0).

## Answer key `gpt5_oracle`

### Pair-level accuracy [95% CI]

AUC = area under accuracy vs k over k = 0..30, divided by the budget (average accuracy across budgets, 0–1).

| policy | k=0 | k=5 | k=10 | k=20 | k=30 | final | AUC | questions / patient |
|---|---|---|---|---|---|---|---|---|
| greedy_smt | 0.532 [0.39–0.66] | 0.564 [0.43–0.70] | 0.564 [0.42–0.70] | 0.612 [0.48–0.74] | 0.691 [0.57–0.82] | 0.691 [0.57–0.82] | 0.599 [0.47–0.73] | 28.0 |
| answerable_informative | 0.532 [0.39–0.66] | 0.622 [0.50–0.75] | 0.670 [0.55–0.79] | 0.745 [0.64–0.84] | 0.793 [0.69–0.88] | 0.793 [0.69–0.88] | 0.700 [0.60–0.80] | 26.4 |
| answerable_informative_no_answerability | 0.532 [0.39–0.66] | 0.628 [0.50–0.75] | 0.670 [0.55–0.79] | 0.723 [0.61–0.83] | 0.793 [0.70–0.88] | 0.793 [0.70–0.88] | 0.695 [0.59–0.80] | 27.4 |
| answerable_informative_no_value | 0.532 [0.39–0.66] | 0.612 [0.49–0.73] | 0.633 [0.51–0.74] | 0.665 [0.53–0.78] | 0.718 [0.59–0.84] | 0.718 [0.59–0.84] | 0.649 [0.53–0.76] | 26.1 |
| read_note `gpt5_oracle` (ceiling) | – | – | – | – | – | 0.957 | – | 0 |

### Where the questions go (all questions asked, final)

answered = the answer was not unknown; an unknown answer never changes a status. Two usefulness rules: **CA** = the answer could change the *trial's* status (the CA's `informative()`); **cohort** (ours, a superset) = it could change the status of any *open cohort* of an undetermined trial, so ruling out one cohort of a multi-cohort trial counts.

| policy | questions / patient | CA: useful, answered | CA: useful, unanswered | CA: not useful | cohort: useful, answered | cohort: useful, unanswered | cohort: not useful | F1 (eligible +) | patient set F1 |
|---|---|---|---|---|---|---|---|---|---|
| greedy_smt | 28.0 | 0.460 | 0.540 | 0.000 | 0.460 | 0.540 | 0.000 | 0.770 | 0.764 |
| answerable_informative | 26.4 | 0.511 | 0.455 | 0.034 | 0.524 | 0.476 | 0.000 | 0.833 | 0.837 |
| answerable_informative_no_answerability | 27.4 | 0.413 | 0.568 | 0.020 | 0.422 | 0.578 | 0.000 | 0.831 | 0.810 |
| answerable_informative_no_value | 26.1 | 0.593 | 0.325 | 0.082 | 0.641 | 0.359 | 0.000 | 0.787 | 0.834 |

### Paired tests vs `answerable_informative`

Differences are policy minus reference, with a paired bootstrap over patients (95% CI, two-sided p). **Pairs within a patient are not independent, so the patient bootstrap is the primary test; McNemar on pairs is secondary.**

| policy | k | Δ accuracy [95% CI], p | Δ set F1 [95% CI], p | McNemar (only policy – only ref), p |
|---|---|---|---|---|
| greedy_smt | 5 | -0.059 [-0.13, +0.01], .095 | -0.051 [-0.10, -0.01], .005 | 6–17, .035 |
| greedy_smt | 10 | -0.106 [-0.20, -0.02], .005 | -0.113 [-0.20, -0.04], <.001 | 7–27, <.001 |
| greedy_smt | 20 | -0.133 [-0.23, -0.04], .001 | -0.106 [-0.20, -0.03], .001 | 7–32, <.001 |
| greedy_smt | 30 | -0.101 [-0.19, -0.01], .026 | -0.072 [-0.14, -0.01], .017 | 8–27, .002 |
| greedy_smt | final | -0.101 [-0.19, -0.01], .026 | -0.072 [-0.14, -0.01], .017 | 8–27, .002 |
| greedy_smt | **AUC** | -0.101 [-0.18, -0.03], <.001 | | |
| answerable_informative_no_answerability | 5 | +0.005 [-0.02, +0.03], .818 | -0.006 [-0.03, +0.01], .670 | 5–4, 1.000 |
| answerable_informative_no_answerability | 10 | +0.000 [-0.05, +0.04], 1.000 | -0.039 [-0.12, +0.01], .267 | 8–8, 1.000 |
| answerable_informative_no_answerability | 20 | -0.021 [-0.07, +0.03], .457 | -0.038 [-0.12, +0.01], .255 | 8–12, .503 |
| answerable_informative_no_answerability | 30 | +0.000 [-0.09, +0.07], 1.000 | -0.026 [-0.09, +0.03], .405 | 10–10, 1.000 |
| answerable_informative_no_answerability | final | +0.000 [-0.09, +0.07], 1.000 | -0.026 [-0.09, +0.03], .405 | 10–10, 1.000 |
| answerable_informative_no_answerability | **AUC** | -0.005 [-0.05, +0.03], .783 | | |
| answerable_informative_no_value | 5 | -0.011 [-0.06, +0.04], .748 | +0.026 [-0.03, +0.11], .547 | 8–10, .815 |
| answerable_informative_no_value | 10 | -0.037 [-0.08, +0.01], .144 | -0.026 [-0.05, -0.00], .024 | 4–11, .118 |
| answerable_informative_no_value | 20 | -0.080 [-0.15, -0.02], .010 | -0.024 [-0.06, +0.01], .116 | 4–19, .003 |
| answerable_informative_no_value | 30 | -0.074 [-0.14, -0.01], .029 | -0.003 [-0.08, +0.09], .882 | 4–18, .004 |
| answerable_informative_no_value | final | -0.074 [-0.14, -0.01], .029 | -0.003 [-0.08, +0.09], .882 | 4–18, .004 |
| answerable_informative_no_value | **AUC** | -0.051 [-0.09, -0.01], .027 | | |

## Answer key `gpt5mini`

### Pair-level accuracy [95% CI]

AUC = area under accuracy vs k over k = 0..30, divided by the budget (average accuracy across budgets, 0–1).

| policy | k=0 | k=5 | k=10 | k=20 | k=30 | final | AUC | questions / patient |
|---|---|---|---|---|---|---|---|---|
| greedy_smt | 0.532 [0.39–0.66] | 0.564 [0.43–0.69] | 0.569 [0.44–0.70] | 0.590 [0.46–0.73] | 0.612 [0.50–0.73] | 0.612 [0.50–0.73] | 0.580 [0.46–0.71] | 27.9 |
| answerable_informative | 0.532 [0.39–0.66] | 0.601 [0.48–0.72] | 0.617 [0.51–0.71] | 0.686 [0.60–0.77] | 0.734 [0.66–0.80] | 0.734 [0.66–0.80] | 0.651 [0.56–0.74] | 26.1 |
| answerable_informative_no_answerability | 0.532 [0.39–0.66] | 0.601 [0.49–0.72] | 0.612 [0.50–0.71] | 0.665 [0.56–0.76] | 0.718 [0.64–0.80] | 0.718 [0.64–0.80] | 0.644 [0.55–0.73] | 26.4 |
| answerable_informative_no_value | 0.532 [0.39–0.66] | 0.601 [0.48–0.72] | 0.633 [0.51–0.74] | 0.665 [0.54–0.78] | 0.707 [0.60–0.81] | 0.707 [0.60–0.81] | 0.644 [0.53–0.75] | 26.1 |
| read_note `gpt5mini` (ceiling) | – | – | – | – | – | 0.824 | – | 0 |

### Where the questions go (all questions asked, final)

answered = the answer was not unknown; an unknown answer never changes a status. Two usefulness rules: **CA** = the answer could change the *trial's* status (the CA's `informative()`); **cohort** (ours, a superset) = it could change the status of any *open cohort* of an undetermined trial, so ruling out one cohort of a multi-cohort trial counts.

| policy | questions / patient | CA: useful, answered | CA: useful, unanswered | CA: not useful | cohort: useful, answered | cohort: useful, unanswered | cohort: not useful | F1 (eligible +) | patient set F1 |
|---|---|---|---|---|---|---|---|---|---|
| greedy_smt | 27.9 | 0.661 | 0.339 | 0.000 | 0.661 | 0.339 | 0.000 | 0.702 | 0.695 |
| answerable_informative | 26.1 | 0.677 | 0.289 | 0.034 | 0.696 | 0.304 | 0.000 | 0.769 | 0.739 |
| answerable_informative_no_answerability | 26.4 | 0.561 | 0.402 | 0.037 | 0.584 | 0.416 | 0.000 | 0.753 | 0.762 |
| answerable_informative_no_value | 26.1 | 0.696 | 0.225 | 0.079 | 0.756 | 0.244 | 0.000 | 0.770 | 0.779 |

### Paired tests vs `answerable_informative`

Differences are policy minus reference, with a paired bootstrap over patients (95% CI, two-sided p). **Pairs within a patient are not independent, so the patient bootstrap is the primary test; McNemar on pairs is secondary.**

| policy | k | Δ accuracy [95% CI], p | Δ set F1 [95% CI], p | McNemar (only policy – only ref), p |
|---|---|---|---|---|
| greedy_smt | 5 | -0.037 [-0.11, +0.03], .334 | -0.023 [-0.06, +0.01], .190 | 11–18, .265 |
| greedy_smt | 10 | -0.048 [-0.14, +0.03], .317 | -0.061 [-0.15, +0.00], .067 | 16–25, .211 |
| greedy_smt | 20 | -0.096 [-0.21, +0.01], .091 | -0.070 [-0.17, +0.01], .070 | 14–32, .011 |
| greedy_smt | 30 | -0.122 [-0.23, -0.02], .023 | -0.043 [-0.10, +0.01], .121 | 12–35, .001 |
| greedy_smt | final | -0.122 [-0.23, -0.02], .023 | -0.043 [-0.10, +0.01], .121 | 12–35, .001 |
| greedy_smt | **AUC** | -0.072 [-0.16, +0.00], .068 | | |
| answerable_informative_no_answerability | 5 | +0.000 [-0.03, +0.03], 1.000 | -0.001 [-0.02, +0.02], .937 | 7–7, 1.000 |
| answerable_informative_no_answerability | 10 | -0.005 [-0.05, +0.04], .891 | -0.052 [-0.14, +0.00], .088 | 10–11, 1.000 |
| answerable_informative_no_answerability | 20 | -0.021 [-0.07, +0.03], .451 | -0.013 [-0.12, +0.09], .743 | 7–11, .481 |
| answerable_informative_no_answerability | 30 | -0.016 [-0.08, +0.03], .675 | +0.023 [-0.05, +0.11], .583 | 7–10, .629 |
| answerable_informative_no_answerability | final | -0.016 [-0.08, +0.03], .675 | +0.023 [-0.05, +0.11], .583 | 7–10, .629 |
| answerable_informative_no_answerability | **AUC** | -0.008 [-0.05, +0.03], .654 | | |
| answerable_informative_no_value | 5 | +0.000 [-0.06, +0.07], 1.000 | +0.051 [-0.01, +0.15], .168 | 13–13, 1.000 |
| answerable_informative_no_value | 10 | +0.016 [-0.04, +0.07], .639 | +0.034 [-0.00, +0.08], .082 | 16–13, .711 |
| answerable_informative_no_value | 20 | -0.021 [-0.09, +0.05], .627 | +0.014 [-0.02, +0.05], .382 | 15–19, .608 |
| answerable_informative_no_value | 30 | -0.027 [-0.10, +0.05], .540 | +0.040 [-0.02, +0.12], .299 | 13–18, .473 |
| answerable_informative_no_value | final | -0.027 [-0.10, +0.05], .540 | +0.040 [-0.02, +0.12], .299 | 13–18, .473 |
| answerable_informative_no_value | **AUC** | -0.007 [-0.06, +0.04], .793 | | |

Files: `curves.csv`, `tests.csv`, `questions.csv`, `waste_breakdown.png`, `waste_breakdown_cohort.png`, `<key>/accuracy_vs_budget.png`, `<key>/answered_vs_budget.png`.
