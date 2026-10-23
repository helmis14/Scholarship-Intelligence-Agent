"""Round 43: the second reading can only hold an answered decision, never add or change one."""
import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scholarship_agent.ai_check import attach_second_reading  # noqa: E402
from scholarship_agent.audit import field_status  # noqa: E402
from scholarship_agent.extract import Page, extract_opportunity  # noqa: E402
from scholarship_agent.models import ProviderType, SourceType  # noqa: E402

TODAY = date(2026, 10, 21)
TEXT = ("Example Scholarship\nThe scholarship is open to citizens of Kenya and Uganda.\n"
        "It covers full tuition fees and a monthly stipend for living costs.\nApplication deadline: 15 January 2027.")


class FakeLLM:
    def __init__(self, fields):
        self.fields = fields

    def complete_json(self, system, user, fields=None, meta=None):
        return {"fields": [{"field": k, "value": v, "quote": ""} for k, v in self.fields.items()]}


class Broken:
    def complete_json(self, *a, **kw):
        raise RuntimeError("dry run")


def status(llm):
    o, _ = extract_opportunity(Page("https://example.org/s", TEXT), provider_name="x", provider_type=ProviderType.OTHER,
                               source_type=SourceType.OFFICIAL, country_hint=[], retrieved_at="t", today=TODAY)
    if llm:
        attach_second_reading(o, TEXT, llm, TODAY)
    return field_status(o, TODAY)


class TestSecondReading(unittest.TestCase):
    def test_agreeing_reading_changes_nothing(self):
        base = status(None)
        agree = {"nationality": "include: KE, UG", "funding_class": base["funding_type"]["state"],
                 "cycle_status": base["cycle"]["state"], "deadline": "2027-01-15"}
        got = status(FakeLLM(agree))
        for f in ("eligible_countries", "funding_type", "cycle", "deadline"):
            self.assertEqual(got[f]["state"], base[f]["state"], f)

    def test_disagreeing_reading_holds_the_answer(self):
        got = status(FakeLLM({"nationality": "not_stated", "funding_class": "partially_funded",
                              "cycle_status": "closed", "deadline": "2027-02-01"}))
        self.assertEqual(got["eligible_countries"]["state"], "needs_review")
        self.assertEqual(got["deadline"]["state"], "needs_review")

    def test_no_answer_keeps_the_rules(self):
        self.assertEqual(status(Broken())["eligible_countries"], status(None)["eligible_countries"])


if __name__ == "__main__":
    unittest.main()


class TestSecondReadingExclusions(unittest.TestCase):
    def test_silence_does_not_hold_an_exclusion(self):
        text = ("Example Scholarship\\nCitizens of EU/EEA countries are not eligible for this scholarship.\\n"
                "It covers full tuition fees.")
        o, _ = extract_opportunity(Page("https://example.org/e", text), provider_name="x", provider_type=ProviderType.OTHER,
                                   source_type=SourceType.OFFICIAL, country_hint=[], retrieved_at="t", today=TODAY)
        before = field_status(o, TODAY)["eligible_countries"]["state"]
        attach_second_reading(o, text, FakeLLM({"nationality": "not_stated"}), TODAY)
        self.assertEqual(field_status(o, TODAY)["eligible_countries"]["state"], before)
