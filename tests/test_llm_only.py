"""The LLM-only baseline, with scripted model replies (no API key needed). Real-Gemini checks are in test_live.py."""

from smt_trial_matching import llm, llm_only

TRIALS = ["NCT04772456", "NCT00001640"]


def scripted(monkeypatch, tmp_path, questioner):
    monkeypatch.setattr(llm, "CACHE", tmp_path)
    monkeypatch.setattr(llm, "_call_gemini", lambda p: "I'm not sure." if p.startswith("You are role-playing")
                        else questioner(p))


def test_asks_then_stops_with_verdicts(monkeypatch, tmp_path):
    def questioner(prompt):
        if prompt.count("Coordinator:") < 2:
            return '{"action": "ask", "question": "How old are you? %d"}' % prompt.count("Coordinator:")
        return '```json\n{"action": "stop", "verdicts": {"NCT04772456": "ineligible"}}\n```'

    scripted(monkeypatch, tmp_path, questioner)
    log = llm_only.interview("trec-20211", TRIALS, budget=15)
    assert len(log["turns"]) == 2 and log["turns"][0]["answer"] == "I'm not sure."
    assert log["final_verdicts"] == {"NCT04772456": "ineligible", "NCT00001640": "eligible"}  # missing -> eligible
    assert all(t["verdicts"] == log["final_verdicts"] for t in log["turns"])


def test_budget_forces_a_stop_and_bad_json_means_eligible(monkeypatch, tmp_path):
    def questioner(prompt):
        if llm_only.STOP_NOW in prompt:
            return "sorry, no JSON here"
        return '{"action": "ask", "question": "Q%d?"}' % prompt.count("Coordinator:")

    scripted(monkeypatch, tmp_path, questioner)
    log = llm_only.interview("trec-20211", TRIALS, budget=3)
    assert len(log["turns"]) == 3
    assert set(log["final_verdicts"].values()) == {"eligible"}


def test_intake_comes_first_and_counts_toward_the_budget(monkeypatch, tmp_path):
    from smt_trial_matching.interview import INTAKE

    scripted(monkeypatch, tmp_path, lambda p: '{"action": "ask", "question": "Q%d?"}' % p.count("Coordinator:")
             if llm_only.STOP_NOW not in p else '{"action": "stop", "verdicts": {}}')
    log = llm_only.interview("trec-20211", TRIALS, budget=6, intake=True)
    assert [t["question"] for t in log["turns"]][:4] == list(INTAKE) and len(log["turns"]) == 6


def test_judge_reads_one_word_and_defaults_to_eligible(monkeypatch, tmp_path):
    scripted(monkeypatch, tmp_path, lambda p: "Ineligible.")
    assert llm_only.judge(TRIALS[0], [("Q?", "A.")]) == "ineligible"
    scripted(monkeypatch, tmp_path / "b", lambda p: "Hard to say.")
    assert llm_only.judge(TRIALS[0], [("Q?", "A.")]) == "eligible"
