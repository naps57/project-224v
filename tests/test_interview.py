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


def test_facts_on_the_same_topic_share_one():
    t = interview.topic
    assert t("patient_has_finding_of_asthma_now") == t("patient_has_finding_of_asthma_inthehistory") \
        == t("patient_has_diagnosis_of_asthma_now") == t("patient_has_finding_of_asthma_now@@uncontrolled")
    assert t("patient_has_finding_of_asthma_now") != t("patient_has_finding_of_diabetes_mellitus_now")


def test_a_group_is_asked_in_one_question(monkeypatch, tmp_path):
    sent = []
    fake_model(monkeypatch, tmp_path, lambda p: sent.append(p) or "Have you had asthma, and do you still?")
    interview.write_question([("NCT00000577", "patient_has_diagnosis_of_asthma_now"),
                              ("NCT00000577", "patient_has_diagnosis_of_asthma_now"),  # same meaning: one line
                              ("NCT00512837", "patient_has_finding_of_uncontrolled_asthma_now")])
    assert sent[0].startswith("You are a research coordinator screening a patient for clinical trials")


def test_intake_comes_first_and_unknown_topics_are_skipped(monkeypatch, tmp_path):
    from smtstate import TrialState

    states = {NCT: TrialState(NCT, {})}
    p = interview.LLMPatient()
    fake_model(monkeypatch, tmp_path, lambda prompt: "I'm not sure." if prompt.startswith("You are role")
               else "{}" if prompt.startswith("A research") else "A question?")
    picks = iter([(NCT, BOOL_VAR), (NCT, BOOL_VAR), (NCT, "patient_age_value_recorded_now_in_years")])
    policy = p.attach(lambda s, asked, r: next(picks))
    policy(states, set(), None)
    for _ in interview.INTAKE:
        p.answer("trec-20211", NCT, BOOL_VAR)
    assert [t["question"] for t in p.transcript] == list(interview.INTAKE)
    assert not p.unknown_topics  # "not sure" to an intake question rules out no topic
    p.answer("trec-20211", NCT, BOOL_VAR)  # "not sure": this topic is now known to be unknown
    asked = set()
    assert policy(states, asked, None) == (NCT, "patient_age_value_recorded_now_in_years")  # skipped the topic
    assert (NCT, BOOL_VAR) in asked


def test_links_fill_the_same_and_implied_facts_only_when_unknown(monkeypatch, tmp_path):
    import json

    from smt_trial_matching import links
    from smtstate import TrialState

    table = tmp_path / "links.json"
    table.write_text(json.dumps({"same": [["patient_has_diagnosis_of_asthma_now", "patient_has_finding_of_asthma_now"]],
                                 "implies": [["patient_is_taking_steroid_now",
                                              "patient_has_undergone_administration_of_steroid_inthepast12months"]]}))
    monkeypatch.setattr(links, "TABLE", table)
    links._table.cache_clear()
    states = {n: TrialState(n, {}) for n in ("NCT00000577", "NCT00859274", "NCT00287378")}
    out = links.propagate(states, {("NCT00000577", "patient_has_diagnosis_of_asthma_now"): True,
                                   ("NCT00287378", "patient_is_taking_steroid_now"): True})
    assert out[("NCT00859274", "patient_has_finding_of_asthma_now")] is True  # "same as", in another trial
    assert out[("NCT00287378", "patient_has_undergone_administration_of_steroid_inthepast12months")] is True
    states["NCT00859274"].answers["patient_has_finding_of_asthma_now"] = False  # already answered: never overwritten
    assert ("NCT00859274", "patient_has_finding_of_asthma_now") not in links.propagate(
        states, {("NCT00000577", "patient_has_diagnosis_of_asthma_now"): True})
    links._table.cache_clear()
