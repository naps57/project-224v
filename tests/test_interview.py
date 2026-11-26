"""Question writer, answer reader and LLMPatient, with the model call replaced (no API key needed)."""

from smt_trial_matching import interview, llm

NCT = "NCT04772456"
BOOL_VAR = "patient_has_finding_of_lesion_of_brain_now@@interpreted_as_suspected_infiltrating_glioma"


def fake_model(monkeypatch, tmp_path, reply):
    monkeypatch.setattr(llm, "CACHE", tmp_path)
    monkeypatch.setattr(llm, "_call_gemini", lambda prompt: reply(prompt))


def test_reader_keeps_only_values_of_the_right_type(monkeypatch, tmp_path):
    facts = [(NCT, BOOL_VAR), (NCT, "patient_age_value_recorded_now_in_years")]
    fake_model(monkeypatch, tmp_path, lambda p: '```json\n{"1": "yes", "2": 34}\n```')
    assert interview.read_reply("q", "r", facts) == {facts[1]: 34}  # "yes" is not a bool: left unknown
    fake_model(monkeypatch, tmp_path / "b", lambda p: "nothing useful")
    assert interview.read_reply("q", "r", facts) == {}


def test_llm_patient_writes_asks_reads_and_logs(monkeypatch, tmp_path):
    def reply(prompt):
        if prompt.startswith("You are a research coordinator"):
            return "Have your doctors said the brain lesion might be a glioma?"
        if prompt.startswith("You are role-playing a patient"):
            return "Yes, they did."
        return '{"1": true}'

    fake_model(monkeypatch, tmp_path, reply)
    p = interview.LLMPatient()
    assert p.answer("trec-20211", NCT, BOOL_VAR) is True
    assert p.transcript[0]["reply"] == "Yes, they did."


def test_one_reply_fills_other_open_facts(monkeypatch, tmp_path):
    from smtstate import TrialState

    states = {NCT: TrialState(NCT, {})}
    p = interview.LLMPatient()
    p.attach(lambda s, a, r: None)(states, set(), None)
    facts = p.open_facts(NCT, BOOL_VAR)
    assert facts[0] == (NCT, BOOL_VAR) and len(facts) > 1
    i, other = next((i, v) for i, (n, v) in enumerate(facts[1:], 2) if states[NCT].types[v] == "Bool")
    fake_model(monkeypatch, tmp_path, lambda prompt: '{"%d": false}' % i if prompt.startswith("A research") else "No.")
    assert p.answer("trec-20211", NCT, BOOL_VAR) is None
    assert states[NCT].answers[other] is False


def test_buckets():
    assert interview.bucket(True, True) == interview.bucket(None, None) == interview.bucket(45.2, 45.0) == "agree"
    assert interview.bucket(None, False) == "missed"
    assert interview.bucket(True, None) == "made up"
    assert interview.bucket(False, True) == interview.bucket(30.0, 45.0) == "wrong"


def test_a_variable_without_a_meaning_is_described_by_its_name():
    v = {"name": "patient_has_finding_of_skin_lesion_now@@precludes_attachment_of_sensors", "meaning": None}
    assert interview.describe(v) == ("patient has finding of skin lesion now, "
                                     "specifically: precludes attachment of sensors")
