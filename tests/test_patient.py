"""The simulated patient and the model cache, with the model call replaced (no API key needed)."""

from smt_trial_matching import llm, patient
from smt_trial_matching.data import patient_note


def test_patient_prompt_holds_the_note_and_the_question(monkeypatch, tmp_path):
    sent = []
    monkeypatch.setattr(llm, "CACHE", tmp_path)
    monkeypatch.setattr(llm, "_call_gemini", lambda prompt: sent.append(prompt) or "Yes, I do.")

    assert patient.ask_patient("trec-202112", "Do you have Marfan syndrome?") == "Yes, I do."
    assert patient_note("trec-202112") in sent[0]
    assert "Do you have Marfan syndrome?" in sent[0]
    assert "{" not in sent[0].replace(patient_note("trec-202112"), "")  # every placeholder filled


def test_repeat_call_comes_from_the_cache(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(llm, "CACHE", tmp_path)
    monkeypatch.setattr(llm, "_call_gemini", lambda prompt: calls.append(prompt) or "No.")

    assert llm.ask_llm("hello") == llm.ask_llm("hello") == "No."
    assert len(calls) == 1
