"""Study levels the award is for, not degrees the applicant already holds or other uses of level words.
Inline texts written for these tests; no model or network calls. Measured on the dev sets by tests/levels_eval.py."""

import sys
import unittest
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from scholarship_agent.extract import Page, extract_opportunity  # noqa: E402
from scholarship_agent.models import SourceType  # noqa: E402


def levels(*paragraphs):
    html = ("<html><head><title>Example Award</title></head><body>" + "".join(f"<p>{p}</p>" for p in paragraphs)
            + "</body></html>")
    o, _ = extract_opportunity(Page("https://x.example/award", html), provider_name="p", provider_type="other",
                               source_type=SourceType.OFFICIAL, country_hint=[], retrieved_at="t",
                               today=date(2026, 10, 23))
    return o.study_levels


class TestLevelsOffered(unittest.TestCase):
    def test_degree_already_held_is_not_a_level(self):
        self.assertEqual(levels("This fund pays two years of master's tuition in Lisbon.",
                                "Successful candidates will have a three-year bachelor's degree in biology."), ["master"])
        self.assertEqual(levels("Doctoral researchers in marine science can apply for the grant.",
                                "Applicants are graduates of a master's programme in physics or an equivalent course."),
                         ["phd"])

    def test_exclusions_teaching_and_stories_are_not_levels(self):
        self.assertEqual(levels("The award supports students on a taught master's course.",
                                "Undergraduates are not eligible for this award.",
                                "Fellows take part in teaching undergraduate seminars.",
                                "Last year's winner, Amira, is now starting her PhD in Leeds."), ["master"])

    def test_short_headings_are_not_levels(self):
        self.assertEqual(levels("PhD Programmes", "Undergraduate study",
                                "We offer scholarships to international master's students."), ["master"])

    def test_other_senses_of_level_words(self):
        self.assertEqual(levels("Grants are paid in euros at the current exchange rate.",
                                "Our early-bird promotion ends in May.",
                                "Students learn to master the basics of field research.",
                                "Contact our office in Boston, MA for details.",
                                "Non-degree visitors may use the library.",
                                "The scholarship is open to undergraduate students."), ["bachelor"])

    def test_offered_levels_are_still_found(self):
        self.assertEqual(levels("Scholarships for exchange students at our partner universities."), ["exchange"])
        self.assertEqual(levels("Das Stipendium fördert die Promotion an einer deutschen Hochschule."), ["phd"])
        self.assertEqual(levels("The award is open to undergraduate and master's students."), ["bachelor", "master"])


if __name__ == "__main__":
    unittest.main()
