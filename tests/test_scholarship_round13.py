"""Round 13: deadline wording and windows, applicant/programme scope, cycles, multilingual evidence, the three-way
verdict (accepted / needs_review / rejected) and the link between a quote and the value it is said to support.

Every sentence here was written for these tests; none is copied from the held-out sets."""

import unittest
from datetime import date

from scholarship_agent import countries
from scholarship_agent.ai_extract import Review, enrich, judge, validate
from scholarship_agent.evidence import clause_scope, study_levels_supported
from scholarship_agent.extract import parse_dates
from scholarship_agent.models import Opportunity, SourceType


def j(field, value, quote, page=None):
    return judge(field, value, quote, page if page is not None else quote)[0]


class TestDeadlineWording(unittest.TestCase):
    def test_applicant_deadline_phrasings_are_accepted(self):
        for q, d in [("Send the complete application on or before 15 March 2027.", "2027-03-15"),
                     ("The form must be completed by 31 May 2027 at the latest.", "2027-05-31"),
                     ("Submission of documents: by 2 February 2027.", "2027-02-02"),
                     ("Upload everything no later than 10 January 2027, 17:00 CET.", "2027-01-10")]:
            self.assertEqual(j("deadline_scholarship", d, q), "accepted", q)

    def test_deadline_heading_on_the_line_above(self):
        page = "Key dates\nApplication deadline\n12 December 2026, 23:59 (local time)\nInterviews\nFebruary 2027"
        self.assertEqual(j("deadline_scholarship", "2026-12-12", "12 December 2026, 23:59 (local time)", page), "accepted")

    def test_notification_heading_is_not_a_deadline(self):
        page = "Application deadline\n5 November 2026\nCandidates informed of the outcome\nby 20 January 2027"
        status, why = judge("deadline_scholarship", "2027-01-20", "by 20 January 2027", page)
        self.assertEqual(status, "rejected")
        self.assertIn("notification", why)

    def test_bare_by_date_needs_review(self):
        page = "Overview\nThe programme in brief.\nby 30 April 2027"
        self.assertEqual(j("deadline_scholarship", "2027-04-30", "by 30 April 2027", page), "needs_review")

    def test_application_window(self):
        page = "Calls for the 2027 intake\nApplications are accepted from 1 October 2026 to 28 February 2027."
        q = "Applications are accepted from 1 October 2026 to 28 February 2027."
        self.assertEqual(j("deadline_scholarship", "2027-02-28", q, page), "accepted")
        self.assertEqual(j("deadline_scholarship", "2026-10-01", q, page), "rejected")
        self.assertEqual(j("opening_date", "2026-10-01", q, page), "accepted")
        self.assertEqual(j("opening_date", "2027-02-28", q, page), "rejected")

    def test_window_heading_above_a_bare_range(self):
        page = "Scholarship applications for 2027 open\nfrom 3 November 2026 to 9 March 2027!"
        self.assertEqual(j("deadline_scholarship", "2027-03-09", "from 3 November 2026 to 9 March 2027!", page), "accepted")

    def test_status_checking_period_is_not_an_application_window(self):
        q = "The status checking period runs from 1 October 2026 to 15 December 2026."
        self.assertEqual(j("deadline_scholarship", "2026-12-15", q), "rejected")


class TestDeadlineScope(unittest.TestCase):
    def test_applicant_group_and_programme_scope(self):
        self.assertEqual(clause_scope("Deadline for US citizens resident in the USA: 9 October 2026")[0], "applicant_group")
        self.assertEqual(clause_scope("New students must apply by 1 June 2027")[0], "applicant_group")
        self.assertEqual(clause_scope("either 2 December 2026 or 7 January 2027",
                                      "Depending on your course, either 2 December 2026 or 7 January 2027")[0], "programme")
        self.assertEqual(clause_scope("Applications close on 1 March 2027.")[0], "general")
        self.assertEqual(clause_scope("Applicants from Kenya and Ghana: 30 November 2026")[0], "country")

    def test_claude_deadline_keeps_its_scope(self):
        page = ("Deadlines\nDependent on your course: Application deadline 6 January 2027.\n")

        class Fake:
            name = "anthropic:test"

            def complete_json(self, system, user):
                return {"fields": [{"field": "deadline_scholarship", "value": "2027-01-06",
                                    "quote": "Dependent on your course: Application deadline 6 January 2027."}]}
        opp = Opportunity(id="x", title="t", provider_name="p", info_url="https://example.org/a")
        enrich(opp, page, Fake(), source_type=SourceType.OFFICIAL, retrieved_at="2026-10-18T00:00:00+00:00",
               today=date(2026, 10, 18))
        d = [d for d in opp.deadlines if d.date == "2027-01-06"][0]
        self.assertEqual(d.scope, "programme")


class TestCycles(unittest.TestCase):
    def test_short_second_year(self):
        self.assertEqual(j("academic_cycle", "2027/2028", "Applications for entry in 2027/8 are open."), "accepted")

    def test_closed_future_and_date_only_cycles_need_review(self):
        self.assertEqual(j("academic_cycle", "2026/2027", "The 2026/2027 call has been closed."), "needs_review")
        self.assertEqual(j("academic_cycle", "2028/2029", "Grants for the 2028/2029 academic year will be advertised later."),
                         "needs_review")
        self.assertEqual(j("academic_cycle", "2027", "First payment: 15 September 2027."), "needs_review")
        self.assertEqual(j("academic_cycle", "2027/2028", "L'appel 2027-2028 est clôturé."), "needs_review")

    def test_pdf_split_year(self):
        self.assertEqual(j("academic_cycle", "2027", "GOVERNMENT SCHOLARSHIP FOR 202 7"), "accepted")


class TestMultilingual(unittest.TestCase):
    def test_deadline_words(self):
        for q, d in [("Le dossier doit être déposé au plus tard le 12 mars 2027.", "2027-03-12"),
                     ("Berkas dikirim paling lambat 31 Desember 2026.", "2026-12-31"),
                     ("Las solicitudes se reciben a más tardar el 15 de marzo de 2027.", "2027-03-15"),
                     ("Unterlagen bitte bis zum 30. September 2026 einreichen.", "2026-09-30")]:
            self.assertEqual(j("deadline_scholarship", d, q), "accepted", q)

    def test_dates_with_spaces(self):
        self.assertIn(date(2026, 8, 1), [d for d, _ in parse_dates("Start: 1. 8. 2026")])

    def test_numbers(self):
        self.assertEqual(j("min_gpa", 2.75, "IPK minimal 2,75 pada skala 4 untuk jenjang sarjana."), "accepted")
        self.assertEqual(j("min_work_years", 2, "Justifier d'une expérience professionnelle d'au moins deux ans."), "accepted")
        self.assertEqual(j("funding_duration_months", 24, "Das Stipendium wird für zwei Jahre gewährt."), "accepted")
        self.assertEqual(j("funding_duration_months", 36, "Beasiswa diberikan selama tiga tahun."), "accepted")

    def test_benefits(self):
        page = "Ce que la bourse comprend\nFrais de déplacement.\nAllocation de subsistance.\nAssurance maladie."
        self.assertEqual(j("covers_travel", True, "Frais de déplacement.", page), "accepted")
        self.assertEqual(j("covers_living_allowance", True, "Allocation de subsistance.", page), "accepted")
        self.assertEqual(j("covers_health_insurance", True, "Assurance maladie.", page), "accepted")
        self.assertEqual(j("covers_accommodation", True, "Every fellow is offered a hall place for the first year."), "accepted")
        self.assertEqual(j("covers_health_insurance", True, "Fellows receive a medical aid allowance each term."), "accepted")
        self.assertEqual(j("tuition_coverage", "full", "La beca cubre la colegiatura completa del programa."), "accepted")

    def test_levels_and_countries(self):
        self.assertEqual(study_levels_supported(["bachelor", "master"], "bourses de bachelier et de master"), [])
        self.assertEqual(study_levels_supported(["phd"], "becas para estudios de doctorado"), [])
        self.assertEqual(study_levels_supported(["phd"], "Stipendien für die Promotion"), [])
        self.assertEqual(study_levels_supported(["master"], "USD 18,000 per year for M.S. students"), [])
        self.assertEqual(countries.mentions("les personnes de nationalité palestinienne"), ["PS"])

    def test_ages(self):
        self.assertEqual(j("max_age", 31, "belum memasuki usia 32 tahun pada saat mendaftar"), "accepted")
        self.assertEqual(j("max_age", 32, "belum memasuki usia 32 tahun pada saat mendaftar"), "needs_review")
        q = "Candidates must be between the ages of 21 and 33 when they apply."
        self.assertEqual(j("min_age", 21, q), "accepted")
        self.assertEqual(j("max_age", 33, q), "accepted")

    def test_funder_through_an_agency_needs_review(self):
        q = "El Gobierno, a través de la Agencia Nacional de Becas (ANB), convoca a estudiantes extranjeros."
        self.assertEqual(j("provider_name", "Agencia Nacional de Becas (ANB)", q), "needs_review")


class TestThreeWayVerdict(unittest.TestCase):
    def test_review_is_a_reason_but_not_a_rejection(self):
        why = validate("stipend_amount", 900, "€ 900, -.", "€ 900, -.")
        self.assertIsInstance(why, Review)
        self.assertEqual(judge("stipend_amount", 900, "€ 900, -.", "€ 900, -.")[0], "needs_review")
        self.assertEqual(judge("stipend_amount", 900, "The grant is 900 euros per month.",
                               "The grant is 900 euros per month.")[0], "accepted")
        self.assertEqual(judge("stipend_amount", 950, "The grant is 900 euros per month.",
                               "The grant is 900 euros per month.")[0], "rejected")

    def test_review_values_are_not_stored(self):
        page = "Funding\n€ 900, -.\n"

        class Fake:
            name = "anthropic:test"

            def complete_json(self, system, user):
                return {"fields": [{"field": "stipend_amount", "value": 900, "quote": "€ 900, -."}]}
        opp = Opportunity(id="x", title="t", provider_name="p", info_url="https://example.org/a")
        st = enrich(opp, page, Fake(), source_type=SourceType.OFFICIAL, retrieved_at="2026-10-18T00:00:00+00:00",
                    today=date(2026, 10, 18))
        self.assertEqual([r["field"] for r in st["needs_review"]], ["stipend_amount"])
        self.assertFalse(any(c.kind == "stipend" and c.amount for c in opp.funding))
        self.assertTrue(any(u.startswith("needs review: model read stipend_amount") for u in opp.uncertainties))

    def test_ambiguous_funder_and_tuition(self):
        q = "Set up by the National Research Council in 2010, the fellowship scheme attracts PhD students."
        self.assertEqual(j("provider_name", "National Research Council", q), "needs_review")
        q = "Full tuition coverage (worth up to EUR 20,000 per year)."
        self.assertEqual(j("tuition_coverage", "full", q), "needs_review")
        q = "Tuition fees (only for one-year specialised master's programmes)."
        self.assertEqual(j("tuition_coverage", "full", q), "needs_review")


class TestQuoteSupportsTheClaim(unittest.TestCase):
    def test_negated_funder(self):
        q = "Please note that this call is not offered by the Regional Education Office."
        self.assertEqual(j("provider_name", "Regional Education Office", q), "rejected")

    def test_scholar_pays(self):
        q = "Housing and meals are covered by the scholarship holders from their monthly payment."
        self.assertEqual(j("covers_accommodation", True, q), "rejected")

    def test_programme_length_is_not_the_funding_period(self):
        self.assertEqual(j("funding_duration_months", 48, "Doctoral Programs: 4 years"), "rejected")
        q = "Les bourses permettent de suivre un master de spécialisation d'un an."
        self.assertEqual(j("funding_duration_months", 12, q), "needs_review")
        q = "The scholarship covers a two-year master's programme and is paid for 24 months."
        self.assertEqual(j("funding_duration_months", 24, q), "accepted")
        page = "Call 2027\nDuration\n12/24 months\nBudget"
        self.assertEqual(j("funding_duration_months", 24, "12/24 months", page), "accepted")
        self.assertEqual(j("funding_duration_months", 24, "12/24 months", "Overview\n12/24 months"), "needs_review")

    def test_band_minimum_is_not_the_overall_score(self):
        q = "An IELTS score of 7.0 overall (with no band below 6.5) is required."
        self.assertEqual(j("ielts_min", 6.5, q), "rejected")
        self.assertEqual(j("ielts_min", 7.0, q), "accepted")
        self.assertEqual(j("ielts_min", 6.5, "IELTS Academic: Overall Band Score of 6.5 or higher."), "accepted")

    def test_amount_for_one_level_needs_review(self):
        q = "A stipend of USD 18,000 per year for M.S. students and USD 24,000 for Ph.D. students."
        self.assertEqual(j("stipend_amount", 24000, q), "needs_review")
        q = "Students enrolled in doctoral courses receive 150,000 yen per month."
        self.assertEqual(j("stipend_amount", 150000, q), "needs_review")

    def test_exclusions_with_curly_quotes_and_adverbs(self):
        self.assertTrue(study_levels_supported(["master"], "Have never started, nor completed a master’s degree."))
        self.assertTrue(study_levels_supported(["phd"], "Awards are not currently available to PhD candidates."))

    def test_residence_is_not_citizenship(self):
        q = "You live and work permanently in one of the 20 partner countries."
        self.assertEqual(j("nationality_mode", "include", q), "needs_review")

    def test_list_item_needs_a_benefit_heading(self):
        page = "Costs you must plan for\nhealth insurance;\nrent;"
        self.assertEqual(j("covers_health_insurance", True, "health insurance;", page), "rejected")
        page = "Practical information\nhealth insurance;\nrent;"
        self.assertEqual(j("covers_health_insurance", True, "health insurance;", page), "needs_review")


if __name__ == "__main__":
    unittest.main()
