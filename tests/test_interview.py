"""Question writer, answer reader and LLMPatient, with the model call replaced (no API key needed)."""

from smt_trial_matching import interview, llm

NCT = "NCT04772456"
BOOL_VAR = "patient_has_finding_of_lesion_of_brain_now@@interpreted_as_suspected_infiltrating_glioma"


def fake_model(monkeypatch, tmp_path, reply):
    monkeypatch.setattr(llm, "CACHE", tmp_path)
    monkeypatch.setattr(llm, "_call_gemini", lambda prompt: reply(prompt))


def test_reader_turns_one_word_into_a_typed_value(monkeypatch, tmp_path):
    for word, value in [("true", True), ("False.", False), ("unknown", None), ("maybe", None)]:
        fake_model(monkeypatch, tmp_path / word, lambda p, w=word: w)
        assert interview.read_answer(NCT, BOOL_VAR, "q", "r") is value


def test_llm_patient_writes_asks_reads_and_logs(monkeypatch, tmp_path):
    def reply(prompt):
        if prompt.startswith("You are a research coordinator"):
            return "Have your doctors said the brain lesion might be a glioma?"
        if prompt.startswith("You are role-playing a patient"):
            return "Yes, they did."
        return "true"

    fake_model(monkeypatch, tmp_path, reply)
    p = interview.LLMPatient()
    assert p.answer("trec-20211", NCT, BOOL_VAR) is True
    assert p.transcript[0]["reply"] == "Yes, they did."


def test_buckets():
    assert interview.bucket(True, True) == interview.bucket(None, None) == interview.bucket(45.2, 45.0) == "agree"
    assert interview.bucket(None, False) == "missed"
    assert interview.bucket(True, None) == "made up"
    assert interview.bucket(False, True) == interview.bucket(30.0, 45.0) == "wrong"
