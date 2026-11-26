> Note: this write-up was produced with the full experiment harness in the original repo
> (https://github.com/ardadastan04/ddx-genie). Commands and file paths below refer to that repo.
> In this repo, `run.py` reproduces the main numbers.

# policy-v1 test results (one-time run, Nov 22, 2026)

**What this is for:** the single, pre-registered test-split evaluation of the frozen policy-v1
(`answerable_informative`, frozen at commit `ede13d9` after dev tuning, see `docs/tuning/v1_dev_grid.md`).
Arda confirmed the run on Nov 22. By the project's rule, test is run once per final system: these numbers are not to be used
to change policy-v1. Any later change is a new system (policy-v2), tuned on dev and tested once again.

- Split: test (29 patients, 175 pairs); budget 30 questions per patient; solver only, no LLM calls.
- Keys: `gpt5_oracle` (primary) and `gpt5mini` (robustness). Test patients use the answerability model fit on all of dev.
- Policies: `configs/main_test.yaml` (no_questions, random_stop, greedy_smt, ours, and two oracle references that read
  the answer key; the oracles are references, not methods or ceilings).
- Command: `uv run python -m smt_trial_matching.experiment --config configs/main_test.yaml --confirmed`
- Primary comparison: ours vs greedy_smt, paired bootstrap over patients (95% CI), McNemar on pairs secondary.

## Headline (gpt5_oracle)

| | k=10 | k=30 | AUC k=0..30 |
|---|---|---|---|
| greedy_smt | 0.594 | 0.646 | 0.599 |
| answerable_informative (policy-v1) | 0.640 | 0.760 | 0.663 |
| ours − greedy [95% CI] | +0.046 [−0.03, +0.13] | **+0.114 [+0.01, +0.22]**, p = .034 | +0.064 [−0.01, +0.14], p = .091 |

On gpt5mini: k=30 +0.103 [+0.02, +0.17], p = .023; AUC +0.045 [−0.01, +0.09], p = .102.
Ours beats greedy significantly at the full budget on both keys; the difference at small budgets and on AUC is
positive but not significant. The dev gap (AUC +0.10) shrank on test (+0.06).

---

The harness summary follows verbatim (`runs/main_test/summary.md`; run outputs themselves are not committed).

# main_test: accuracy vs question budget

Split `test` (29 patients, 175 pairs), answer keys `gpt5_oracle`, `gpt5mini`, budget 30, commit `ede13d96f25c`. 95% CIs bootstrap over patients (2,000 resamples, seed 0).

**Oracle policies (read the answer key; references, not methods):** `oracle_answerable_greedy`, `answerable_informative_oracle`.

## Answer key `gpt5_oracle`

### Pair-level accuracy [95% CI]

AUC = area under accuracy vs k over k = 0..30, divided by the budget (average accuracy across budgets, 0–1).

| policy | k=0 | k=5 | k=10 | k=20 | k=30 | final | AUC | questions / patient |
|---|---|---|---|---|---|---|---|---|
| no_questions | 0.514 [0.41–0.63] | 0.514 [0.41–0.63] | 0.514 [0.41–0.63] | 0.514 [0.41–0.63] | 0.514 [0.41–0.63] | 0.514 [0.41–0.63] | 0.514 [0.41–0.63] | 0.0 |
| random_stop | 0.514 [0.41–0.63] | 0.543 [0.45–0.65] | 0.554 [0.46–0.67] | 0.594 [0.50–0.71] | 0.646 [0.56–0.76] | 0.646 [0.56–0.76] | 0.580 [0.49–0.69] | 25.4 |
| greedy_smt | 0.514 [0.41–0.63] | 0.571 [0.46–0.71] | 0.594 [0.49–0.73] | 0.611 [0.51–0.74] | 0.646 [0.55–0.78] | 0.646 [0.55–0.78] | 0.599 [0.50–0.73] | 20.8 |
| answerable_informative | 0.514 [0.41–0.63] | 0.594 [0.51–0.70] | 0.640 [0.55–0.75] | 0.691 [0.60–0.81] | 0.760 [0.66–0.86] | 0.760 [0.66–0.86] | 0.663 [0.58–0.77] | 21.6 |
| oracle_answerable_greedy | 0.514 [0.41–0.63] | 0.617 [0.51–0.75] | 0.669 [0.56–0.81] | 0.697 [0.59–0.83] | 0.749 [0.66–0.85] | 0.749 [0.66–0.85] | 0.672 [0.58–0.79] | 16.7 |
| answerable_informative_oracle | 0.514 [0.41–0.63] | 0.669 [0.58–0.79] | 0.737 [0.68–0.82] | 0.800 [0.73–0.88] | 0.857 [0.78–0.94] | 0.857 [0.78–0.94] | 0.756 [0.70–0.83] | 17.8 |
| read_note `gpt5_oracle` (ceiling) | – | – | – | – | – | 0.960 | – | 0 |

### Where the questions go (all questions asked, final)

answered = the answer was not unknown; an unknown answer never changes a status. Two usefulness rules: **CA** = the answer could change the *trial's* status (the CA's `informative()`); **cohort** (ours, a superset) = it could change the status of any *open cohort* of an undetermined trial, so ruling out one cohort of a multi-cohort trial counts.

| policy | questions / patient | CA: useful, answered | CA: useful, unanswered | CA: not useful | cohort: useful, answered | cohort: useful, unanswered | cohort: not useful | F1 (eligible +) | patient set F1 |
|---|---|---|---|---|---|---|---|---|---|
| no_questions | 0.0 |  |  |  |  |  |  | 0.679 | 0.665 |
| random_stop | 25.4 | 0.201 | 0.295 | 0.504 | 0.253 | 0.352 | 0.394 | 0.739 | 0.788 |
| greedy_smt | 20.8 | 0.431 | 0.569 | 0.000 | 0.431 | 0.569 | 0.000 | 0.737 | 0.800 |
| answerable_informative | 21.6 | 0.509 | 0.410 | 0.082 | 0.557 | 0.443 | 0.000 | 0.806 | 0.831 |
| oracle_answerable_greedy | 16.7 | 1.000 | 0.000 | 0.000 | 1.000 | 0.000 | 0.000 | 0.796 | 0.834 |
| answerable_informative_oracle | 17.8 | 0.891 | 0.000 | 0.109 | 1.000 | 0.000 | 0.000 | 0.872 | 0.868 |

### Paired tests vs `greedy_smt`

Differences are policy minus reference, with a paired bootstrap over patients (95% CI, two-sided p). **Pairs within a patient are not independent, so the patient bootstrap is the primary test; McNemar on pairs is secondary.**

| policy | k | Δ accuracy [95% CI], p | Δ set F1 [95% CI], p | McNemar (only policy – only ref), p |
|---|---|---|---|---|
| no_questions | 5 | -0.057 [-0.11, -0.02], .004 | -0.091 [-0.19, -0.00], .040 | 1–11, .006 |
| no_questions | 10 | -0.080 [-0.14, -0.04], <.001 | -0.127 [-0.25, -0.02], .009 | 1–15, <.001 |
| no_questions | 20 | -0.097 [-0.19, -0.04], <.001 | -0.105 [-0.25, +0.03], .142 | 3–20, <.001 |
| no_questions | 30 | -0.131 [-0.23, -0.06], <.001 | -0.134 [-0.28, +0.01], .061 | 3–26, <.001 |
| no_questions | final | -0.131 [-0.23, -0.06], <.001 | -0.134 [-0.28, +0.01], .061 | 3–26, <.001 |
| no_questions | **AUC** | -0.085 [-0.15, -0.04], <.001 | | |
| random_stop | 5 | -0.029 [-0.08, +0.01], .195 | -0.040 [-0.12, +0.02], .275 | 3–8, .227 |
| random_stop | 10 | -0.040 [-0.09, -0.01], .034 | -0.038 [-0.12, +0.02], .288 | 4–11, .118 |
| random_stop | 20 | -0.017 [-0.09, +0.04], .691 | -0.009 [-0.11, +0.09], .882 | 11–14, .690 |
| random_stop | 30 | +0.000 [-0.08, +0.06], 1.000 | -0.011 [-0.05, +0.02], .514 | 12–12, 1.000 |
| random_stop | final | +0.000 [-0.08, +0.06], 1.000 | -0.011 [-0.05, +0.02], .514 | 12–12, 1.000 |
| random_stop | **AUC** | -0.020 [-0.07, +0.02], .379 | | |
| answerable_informative | 5 | +0.023 [-0.04, +0.08], .546 | +0.010 [-0.03, +0.05], .647 | 10–6, .454 |
| answerable_informative | 10 | +0.046 [-0.03, +0.13], .304 | +0.042 [-0.02, +0.13], .262 | 15–7, .134 |
| answerable_informative | 20 | +0.080 [-0.02, +0.18], .130 | +0.054 [-0.02, +0.15], .173 | 21–7, .013 |
| answerable_informative | 30 | +0.114 [+0.01, +0.22], .034 | +0.032 [+0.00, +0.07], .036 | 23–3, <.001 |
| answerable_informative | final | +0.114 [+0.01, +0.22], .034 | +0.032 [+0.00, +0.07], .036 | 23–3, <.001 |
| answerable_informative | **AUC** | +0.064 [-0.01, +0.14], .091 | | |
| oracle_answerable_greedy | 5 | +0.046 [+0.01, +0.09], .011 | +0.050 [+0.00, +0.13], .011 | 8–0, .008 |
| oracle_answerable_greedy | 10 | +0.074 [+0.02, +0.14], .002 | +0.043 [+0.01, +0.09], .006 | 13–0, <.001 |
| oracle_answerable_greedy | 20 | +0.086 [+0.03, +0.16], .002 | +0.054 [+0.01, +0.11], .002 | 15–0, <.001 |
| oracle_answerable_greedy | 30 | +0.103 [+0.02, +0.19], .011 | +0.035 [+0.00, +0.07], .023 | 19–1, <.001 |
| oracle_answerable_greedy | final | +0.103 [+0.02, +0.19], .011 | +0.035 [+0.00, +0.07], .023 | 19–1, <.001 |
| oracle_answerable_greedy | **AUC** | +0.073 [+0.03, +0.13], <.001 | | |
| answerable_informative_oracle | 5 | +0.097 [+0.02, +0.18], .016 | +0.092 [+0.01, +0.20], .029 | 22–5, .002 |
| answerable_informative_oracle | 10 | +0.143 [+0.06, +0.22], .004 | +0.038 [-0.00, +0.09], .057 | 30–5, <.001 |
| answerable_informative_oracle | 20 | +0.189 [+0.07, +0.30], .002 | +0.060 [-0.01, +0.13], .091 | 38–5, <.001 |
| answerable_informative_oracle | 30 | +0.211 [+0.08, +0.33], .001 | +0.068 [-0.00, +0.15], .063 | 41–4, <.001 |
| answerable_informative_oracle | final | +0.211 [+0.08, +0.33], .001 | +0.068 [-0.00, +0.15], .063 | 41–4, <.001 |
| answerable_informative_oracle | **AUC** | +0.156 [+0.07, +0.24], .001 | | |

## Answer key `gpt5mini`

### Pair-level accuracy [95% CI]

AUC = area under accuracy vs k over k = 0..30, divided by the budget (average accuracy across budgets, 0–1).

| policy | k=0 | k=5 | k=10 | k=20 | k=30 | final | AUC | questions / patient |
|---|---|---|---|---|---|---|---|---|
| no_questions | 0.514 [0.41–0.63] | 0.514 [0.41–0.63] | 0.514 [0.41–0.63] | 0.514 [0.41–0.63] | 0.514 [0.41–0.63] | 0.514 [0.41–0.63] | 0.514 [0.41–0.63] | 0.0 |
| random_stop | 0.514 [0.41–0.63] | 0.554 [0.47–0.66] | 0.560 [0.47–0.67] | 0.583 [0.50–0.69] | 0.611 [0.52–0.73] | 0.611 [0.52–0.73] | 0.569 [0.48–0.68] | 24.4 |
| greedy_smt | 0.514 [0.41–0.63] | 0.577 [0.47–0.72] | 0.611 [0.51–0.75] | 0.629 [0.53–0.76] | 0.646 [0.56–0.77] | 0.646 [0.56–0.77] | 0.610 [0.51–0.74] | 20.9 |
| answerable_informative | 0.514 [0.41–0.63] | 0.589 [0.51–0.69] | 0.623 [0.54–0.73] | 0.686 [0.61–0.78] | 0.749 [0.68–0.83] | 0.749 [0.68–0.83] | 0.656 [0.59–0.75] | 21.1 |
| oracle_answerable_greedy | 0.514 [0.41–0.63] | 0.600 [0.49–0.73] | 0.629 [0.53–0.76] | 0.640 [0.54–0.77] | 0.680 [0.59–0.80] | 0.680 [0.59–0.80] | 0.628 [0.54–0.75] | 18.6 |
| answerable_informative_oracle | 0.514 [0.41–0.63] | 0.646 [0.56–0.76] | 0.703 [0.64–0.78] | 0.749 [0.70–0.80] | 0.794 [0.73–0.86] | 0.794 [0.73–0.86] | 0.717 [0.67–0.78] | 19.0 |
| read_note `gpt5mini` (ceiling) | – | – | – | – | – | 0.851 | – | 0 |

### Where the questions go (all questions asked, final)

answered = the answer was not unknown; an unknown answer never changes a status. Two usefulness rules: **CA** = the answer could change the *trial's* status (the CA's `informative()`); **cohort** (ours, a superset) = it could change the status of any *open cohort* of an undetermined trial, so ruling out one cohort of a multi-cohort trial counts.

| policy | questions / patient | CA: useful, answered | CA: useful, unanswered | CA: not useful | cohort: useful, answered | cohort: useful, unanswered | cohort: not useful | F1 (eligible +) | patient set F1 |
|---|---|---|---|---|---|---|---|---|---|
| no_questions | 0.0 |  |  |  |  |  |  | 0.679 | 0.665 |
| random_stop | 24.4 | 0.295 | 0.236 | 0.470 | 0.361 | 0.274 | 0.365 | 0.719 | 0.708 |
| greedy_smt | 20.9 | 0.696 | 0.304 | 0.000 | 0.696 | 0.304 | 0.000 | 0.730 | 0.734 |
| answerable_informative | 21.1 | 0.667 | 0.260 | 0.074 | 0.719 | 0.281 | 0.000 | 0.794 | 0.725 |
| oracle_answerable_greedy | 18.6 | 1.000 | 0.000 | 0.000 | 1.000 | 0.000 | 0.000 | 0.748 | 0.748 |
| answerable_informative_oracle | 19.0 | 0.927 | 0.000 | 0.073 | 1.000 | 0.000 | 0.000 | 0.816 | 0.746 |

### Paired tests vs `greedy_smt`

Differences are policy minus reference, with a paired bootstrap over patients (95% CI, two-sided p). **Pairs within a patient are not independent, so the patient bootstrap is the primary test; McNemar on pairs is secondary.**

| policy | k | Δ accuracy [95% CI], p | Δ set F1 [95% CI], p | McNemar (only policy – only ref), p |
|---|---|---|---|---|
| no_questions | 5 | -0.063 [-0.12, -0.03], <.001 | -0.061 [-0.14, +0.00], .078 | 1–12, .003 |
| no_questions | 10 | -0.097 [-0.17, -0.05], <.001 | -0.098 [-0.21, -0.01], .019 | 1–18, <.001 |
| no_questions | 20 | -0.114 [-0.21, -0.05], <.001 | -0.067 [-0.20, +0.06], .326 | 4–24, <.001 |
| no_questions | 30 | -0.131 [-0.23, -0.06], <.001 | -0.069 [-0.20, +0.06], .318 | 6–29, <.001 |
| no_questions | final | -0.131 [-0.23, -0.06], <.001 | -0.069 [-0.20, +0.06], .318 | 6–29, <.001 |
| no_questions | **AUC** | -0.096 [-0.17, -0.05], <.001 | | |
| random_stop | 5 | -0.023 [-0.07, +0.01], .241 | -0.005 [-0.03, +0.03], .736 | 4–8, .388 |
| random_stop | 10 | -0.051 [-0.10, -0.02], .004 | -0.038 [-0.12, +0.03], .302 | 4–13, .049 |
| random_stop | 20 | -0.046 [-0.12, +0.01], .133 | -0.064 [-0.18, +0.05], .297 | 8–16, .152 |
| random_stop | 30 | -0.034 [-0.11, +0.03], .330 | -0.026 [-0.13, +0.08], .624 | 11–17, .345 |
| random_stop | final | -0.034 [-0.11, +0.03], .330 | -0.026 [-0.13, +0.08], .624 | 11–17, .345 |
| random_stop | **AUC** | -0.041 [-0.09, -0.01], .023 | | |
| answerable_informative | 5 | +0.011 [-0.05, +0.07], .796 | -0.025 [-0.11, +0.04], .584 | 10–8, .815 |
| answerable_informative | 10 | +0.011 [-0.05, +0.06], .811 | -0.037 [-0.12, +0.01], .290 | 10–8, .815 |
| answerable_informative | 20 | +0.057 [-0.02, +0.12], .145 | -0.007 [-0.12, +0.10], .920 | 19–9, .087 |
| answerable_informative | 30 | +0.103 [+0.02, +0.17], .023 | -0.010 [-0.10, +0.05], .887 | 23–5, <.001 |
| answerable_informative | final | +0.103 [+0.02, +0.17], .023 | -0.010 [-0.10, +0.05], .887 | 23–5, <.001 |
| answerable_informative | **AUC** | +0.045 [-0.01, +0.09], .102 | | |
| oracle_answerable_greedy | 5 | +0.023 [+0.01, +0.05], .022 | +0.037 [+0.00, +0.11], .022 | 4–0, .125 |
| oracle_answerable_greedy | 10 | +0.017 [+0.00, +0.04], .246 | +0.004 [+0.00, +0.01], .246 | 3–0, .250 |
| oracle_answerable_greedy | 20 | +0.011 [-0.01, +0.04], .574 | +0.004 [-0.01, +0.02], .767 | 3–1, .625 |
| oracle_answerable_greedy | 30 | +0.034 [-0.01, +0.08], .182 | +0.014 [-0.00, +0.04], .178 | 7–1, .070 |
| oracle_answerable_greedy | final | +0.034 [-0.01, +0.08], .182 | +0.014 [-0.00, +0.04], .178 | 7–1, .070 |
| oracle_answerable_greedy | **AUC** | +0.018 [+0.00, +0.04], .019 | | |
| answerable_informative_oracle | 5 | +0.069 [+0.00, +0.14], .050 | +0.011 [-0.09, +0.11], .783 | 17–5, .017 |
| answerable_informative_oracle | 10 | +0.091 [+0.01, +0.15], .033 | -0.037 [-0.13, +0.03], .389 | 23–7, .005 |
| answerable_informative_oracle | 20 | +0.120 [+0.02, +0.20], .031 | -0.024 [-0.12, +0.05], .618 | 29–8, <.001 |
| answerable_informative_oracle | 30 | +0.149 [+0.05, +0.24], .004 | +0.012 [-0.08, +0.08], .706 | 32–6, <.001 |
| answerable_informative_oracle | final | +0.149 [+0.05, +0.24], .004 | +0.012 [-0.08, +0.08], .706 | 32–6, <.001 |
| answerable_informative_oracle | **AUC** | +0.107 [+0.03, +0.17], .010 | | |

Files: `curves.csv`, `tests.csv`, `questions.csv`, `waste_breakdown.png`, `waste_breakdown_cohort.png`, `<key>/accuracy_vs_budget.png`, `<key>/answered_vs_budget.png`.
