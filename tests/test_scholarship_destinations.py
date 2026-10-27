"""Destination countries read from the page's wording (scholarship_agent/destinations.py); sentences written for
these tests, not copied from pages."""
import unittest

from scholarship_agent.destinations import extract_destinations, host_destination


def codes(text, title=""):
    return extract_destinations(text, title)[0]


class TestDestinationWording(unittest.TestCase):
    def test_english_destination_phrases(self):
        self.assertEqual(codes("The award lets graduates study in Japan for two years."), ["JP"])
        self.assertEqual(codes("Fellows will study at universities in the U.S. or Canada."), ["US", "CA"])
        self.assertEqual(codes("The fellowship is hosted in Germany by a partner of your choice."), ["DE"])
        self.assertEqual(codes("Scholarships are tenable at any UK university for one year."), ["GB"])
        self.assertEqual(codes("The grant covers a research stay in Austria of up to six months."), ["AT"])
        self.assertEqual(codes("Awardees receive a flight allowance to travel to Panama in August."), ["PA"])
        self.assertEqual(codes("Host country: Norway"), ["NO"])

    def test_other_languages(self):
        self.assertEqual(codes("Das Stipendium richtet sich an Studierende, die in Deutschland studieren möchten."),
                         ["DE"])
        self.assertEqual(codes("Cette bourse permet d'étudier en France pendant un an."), ["FR"])
        self.assertEqual(codes("La beca permite estudiar en España durante un curso completo."), ["ES"])
        self.assertEqual(codes("Beasiswa ini untuk kuliah di Jepang selama empat tahun."), ["JP"])
        self.assertEqual(codes("Program ini membiayai mahasiswa untuk studi di Jepang."), ["JP"])

    def test_title_counts_award_words(self):
        self.assertEqual(codes("", "Becas de Doctorado en Alemania 2027"), ["DE"])
        # the site name after the separator is the publisher's seat, not the destination
        self.assertEqual(codes("", "Bourses d'études en France 2027 | La France en Mongolie"), ["FR"])

    def test_evidence_sentence_per_code(self):
        got, snips = extract_destinations("Applicants may apply online. Successful candidates study in Sweden.")
        self.assertEqual((got, snips), (["SE"], ["Successful candidates study in Sweden."]))


class TestNotADestination(unittest.TestCase):
    def test_nationality_and_residence(self):
        for s in ("Open to citizens of Kenya and nationals of Uganda with a good degree.",
                  "Applicants from Ghana are welcome to apply for this award.",
                  "Indonesian students may apply for this award each year.",
                  "Applicants must have been resident in Chile for at least five years."):
            self.assertEqual(codes(s), [], s)

    def test_earlier_degree_enrolment_office_and_negation(self):
        for s in ("Applicants must hold a degree from a recognised university in India.",
                  "Candidates who pursued their bachelor studies in Spain may also apply.",
                  "You must be enrolled at a university in Denmark to receive the grant for study abroad.",
                  "The Fulbright Commission in Egypt administers the programme.",
                  "This scholarship cannot be used for studying in India.",
                  "Eligible institutions in Brazil: all federal universities.",
                  "Visa rules apply to non-U.S. citizens coming to the U.S. for the project."):
            self.assertEqual(codes(s), [], s)

    def test_names_and_home_or_abroad(self):
        self.assertEqual(codes("You will join the American University of Beirut as a scholar."), [])
        self.assertEqual(codes("Students study in Georgia at the state's flagship university."), [])
        self.assertEqual(codes("The fund supports studies both in Ghana and abroad for two years."), [])

    def test_return_home_and_testimonial(self):
        self.assertEqual(codes("Scholars must return to Vietnam and work at a university in Vietnam."), [])
        self.assertEqual(codes("Studying in Australia was my dream since school."), [])

    def test_exclusion_list_under_a_heading(self):
        text = ("Who can't apply?\nYou are not eligible if you\nPlan to study at an Australian university\n"
                "Already hold a similar award\nWho can apply?\nAustralians who wish to study in the United Kingdom "
                "for a master's degree.")
        self.assertEqual(codes(text), ["GB"])


class TestAggregation(unittest.TestCase):
    def test_activity_beats_institution_only(self):
        text = ("The programme aims to support universities in Ukraine after the war. "
                "It funds a research stay at a host institute in Germany for six months.")
        self.assertEqual(codes(text), ["DE"])

    def test_title_beats_a_single_body_mention(self):
        text = "Postgraduate study in Jordan for Yemeni students. Are you looking to study in Canada next year?"
        self.assertEqual(codes(text, "Scholarships for Postgraduate Studies in Jordan"), ["JO"])

    def test_menu_items_are_not_read(self):
        self.assertEqual(codes("Study in Japan\nStudy in Korea\nContact us"), [])


class TestHostFallback(unittest.TestCase):
    INBOUND = "The award is a fee waiver for new international students starting a full-time master's degree here."

    def host(self, url, text=INBOUND, title="Excellence Scholarship", mode="", nats=None):
        return host_destination(url, text, title, mode, nats)[0]

    def test_university_domain_gives_its_country(self):
        self.assertEqual(self.host("https://www.example.ac.uk/funding/vc-award"), ["GB"])
        self.assertEqual(self.host("https://admissions.example.edu/aid"), ["US"])
        self.assertEqual(self.host("https://www.uni-example.de/stipendium"), ["DE"])
        self.assertEqual(self.host("https://scholarships.example.edu.au/merit"), ["AU"])

    def test_other_publishers_give_nothing(self):
        self.assertEqual(self.host("https://www.examplefoundation.de/fellowship"), [])
        self.assertEqual(self.host("https://www.education.gov.sg/scholarships"), [])
        self.assertEqual(self.host("https://www.example.org/award"), [])

    def test_sending_people_elsewhere_gives_nothing(self):
        self.assertEqual(self.host("https://www.example.ac.uk/go", "Grants help our students fund a semester abroad "
                                   "at a partner university.", "Go Abroad Grant"), [])
        self.assertEqual(self.host("https://www.example.ac.uk/x", mode="include", nats=["GB"]), [])
        self.assertEqual(self.host("https://www.univ-example.dz/news", "Applications are open for doctoral "
                                   "scholarships at a partner university in Mauritania this coming year."), [])
        self.assertEqual(self.host("https://qatar.example.edu/merit"), [])
        self.assertEqual(self.host("https://www.example.edu/x", title="Gates Cambridge - National Scholarships Office"),
                         [])
        self.assertEqual(self.host("https://www.example.edu/x", title="Conference Travel Scholarship"), [])

    def test_inbound_wording_testimonials_and_applicants_do_not_block(self):
        self.assertEqual(self.host("https://www.uni-example.de/x", "International students who study abroad in "
                                   "Germany with us receive a monthly stipend of 900 euros."), ["DE"])
        self.assertEqual(self.host("https://www.example.ac.uk/x", self.INBOUND + '\n"Studying abroad changed my '
                                   'life," says a former scholar.'), ["GB"])
        self.assertEqual(self.host("https://www.example.ac.uk/x", "This scholarship is for students from Pakistan "
                                   "joining a one-year master's programme at the university."), ["GB"])


if __name__ == "__main__":
    unittest.main()
