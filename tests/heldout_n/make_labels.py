"""Set N labels (round 29), written by hand from the official pages in pages/ before any extractor ran on set N.

Set N is the frozen test set for the round-29 rules (negation by scope, deadline ownership, review checks). The
rules were committed (26af974) before any set-N page was fetched, and nothing on set N was used to change a rule. Labels follow the same
reading as set L (tests/heldout_l/make_labels.py): fee status, domicile, "international students" and invitations are
"not_stated" nationality; "fully_funded" needs tuition and living costs both covered; a stated discount, share or cap is
"partially_funded"; deadlines are applicant deadline dates with a year for this programme (not nominations, openings,
payments, news dates or other steps); cycle_status as of 2026-10-19 (the day the pages were fetched).
Close calls are recorded per decision in AMB ("ambiguous_fields"); results are reported with and without them.
Country lists were transcribed by hand from the page.
Run once to write labels.json; manifest.json then freezes it."""
import json
from pathlib import Path
M = Path(__file__).resolve().parent
EU = ["AT", "BE", "BG", "HR", "CY", "CZ", "DK", "EE", "FI", "FR", "DE", "GR", "HU", "IE", "IT", "LV", "LT", "LU", "MT", "NL",
      "PL", "PT", "RO", "SK", "SI", "ES", "SE"]
EEA = EU + ["IS", "LI", "NO"]
D = lambda d, s="historical": {"kind": "scholarship", "date": d, "status": s}  # noqa: E731
A = lambda d, s="current": {"kind": "admission", "date": d, "status": s}  # noqa: E731
P = {
 "es-upf-schol": dict(fields={"nationality": "not_stated", "levels": ["master"],
     "deadlines": [D("2026-06-18"), D("2026-09-03"), D("2026-11-26", "current"), D("2027-01-21", "current")],
     "cycle_status": "open", "tuition": "partial", "funding_class": "partially_funded"},
     evidence={"deadlines": "Deadline for application and submission of documentation: June 18, 2026 ... September 3, 2026 ... November 26, 2026 ... January 21, 2027",
               "funding_class": "The Merit Based Scholarship covers 25% of the total tuition fee ... could be enlarged up to an additional 25%"}),
 "de-tuebingen-schol": dict(fields={"nationality": {"mode": "include", "countries": ["CN"]}, "levels": ["phd"],
     "deadlines": [D("2027-01-15", "current")], "openings": ["2026-10-20"], "cycle_status": "upcoming",
     "components": {"living_allowance": "covered", "travel": "covered"}, "funding_class": "stipend_only"},
     evidence={"nationality": "supports Chinese nationals inside and outside of China ... Excellent postgraduate and doctoral students from the People's Republic of China",
               "deadlines": "The application system will be open from 20th October 2026 to 15th January 2027. (supervisors' topics by 15 September 2026 are not the applicant's)",
               "funding_class": "Annual living allowance as prescribed by the Chinese Government ... Return airfare to Germany"}),
}
AMB = {}
X = {"uk-keele-vc": "table of many awards", "uk-northumbria-ies": "scholarship search page", "uk-ntu-intl": "list of scholarships",
     "uk-brookes-intl": "overview with a short note on one award", "se-ki-gms": "KI and external scholarships listed together"}
P["at-univie-schol"] = dict(fields={"nationality": "not_stated", "deadlines": [], "cycle_status": "not_stated", "tuition": "partial",
     "funding_class": "partially_funded"},
     evidence={"funding_class": "A limited number of partial scholarships ranging from € 1,000 to € 3,000 ... The remaining amount to cover the program fee ... must be paid by the applicant.",
               "deadlines": "The application deadline for scholarship applications is February 28. (no year)"})
X.update({"it-sns-schol": "list of topic scholarships", "it-sissa-phd": "list of PhD fellowships", "uk-lshtm-schol": "table of several scholarships",
          "fr-sorbonne-schol": "overview of aid types", "be-uhasselt-schol": "overview of scholarships by programme"})
P.update({
 "se-umu-schol": dict(fields={"nationality": {"mode": "exclude", "countries": EEA + ["CH"]}, "levels": ["bachelor", "master"],
     "deadlines": [A("2026-01-15", "historical")], "cycle_status": "closed", "tuition": "partial", "funding_class": "partially_funded"},
     evidence={"nationality": "are a citizen of a country outside of the EU/EEA and Switzerland",
               "deadlines": "have completed your application for programme studies before the application deadline on 15 January 2026",
               "funding_class": "Scholarships are offered in the form of tuition-waivers. Selected candidates receive a full or partial waiver of the tuition fee."},
     ambiguous="the timeline repeats yearly dates without a year (15 January, 5 March); a full waiver also exists"),
 "uk-hud-intl": dict(fields={"nationality": "not_stated", "levels": ["bachelor", "master"], "deadlines": [], "cycle_status": "not_stated",
     "funding_class": "not_stated"},
     evidence={"nationality": "be an international fee-paying student who is self-funding (fee status)",
               "funding_class": "a merit-based scholarship of up to £4,000 (what it pays for is not stated)"}),
})
AMB.update({"se-umu-schol": ["deadlines", "cycle_status", "funding_class"]})
X.update({"jp-tsukuba-schol": "PDF without readable text", "nl-saxion-schol": "two scholarships (STS, NLS) on one page",
          "de-rwth-schol": "list", "uk-salford-ies": "list", "uk-mdx-intl": "several awards", "uk-gcu-ies": "portal",
          "jp-ritsumei-schol": "list", "fr-polytechnique-schol": "aid overview"})
X.update({"uk-plymouth-intl": "index of UG and PG scholarships", "uk-bradford-gds": "search page", "uk-kingston-intl": "list",
          "uk-herts-intl": "fees overview", "uk-bbk-intl": "support overview", "ie-rcsi-schol": "home page",
          "dk-aau-schol": "grants for going abroad (list)", "ee-taltech-schol": "list of allowances", "lt-ktu-schol": "admissions page",
          "ro-ubbcluj-schol": "international centre home", "es-ub-schol": "a master's course page", "de-freiburg-schol": "financing overview",
          "be-vub-schol": "list of programmes", "kr-hanyang-schol": "home page", "kr-ewha-schol": "template page", "cn-fudan-schol": "list",
          "cn-sjtu-schol": "navigation", "hk-polyu-schol": "overview", "uk-gre-vc": "financial report PDF"})
P.update({
 "us-questbridge": dict(fields={"nationality": "not_stated", "levels": ["bachelor"], "deadlines": [], "cycle_status": "closed",
     "funding_class": "fully_funded"},
     evidence={"cycle_status": "The deadline for the 2026 QuestBridge National College Match was Thursday, October 1, at 11:59 p.m. Pacific Time.",
               "funding_class": "connects ... with full four-year scholarships — valued at over $360,000"},
     ambiguous="the past deadline has no year; 'full four-year scholarships' without components"),
 "us-gates-sch": dict(fields={"nationality": {"mode": "include", "countries": ["US"]}, "levels": ["bachelor"],
     "deadlines": [D("2026-09-15")], "openings": ["2026-07-15"], "cycle_status": "closed",
     "components": {"tuition": "covered", "accommodation": "covered", "living_allowance": "covered"}, "funding_class": "fully_funded"},
     evidence={"nationality": "A US citizen or permanent resident",
               "deadlines": "Available July 15 2026 Deadline Sept 15 2026",
               "funding_class": "funding for the full cost of attendance* not already covered by other financial aid ... *Cost of attendance includes tuition, fees, books, housing and food"},
     ambiguous="the page still shows 'Status: Open' after the deadline (semifinalist phase)"),
 "us-hsf": dict(fields={"nationality": {"mode": "include", "countries": ["US"]}, "levels": ["bachelor", "master"],
     "deadlines": [D("2026-02-15")], "openings": ["2026-01-05"], "cycle_status": "closed", "funding_class": "not_stated"},
     evidence={"nationality": "US Citizen, Permanent Legal Resident, or DACA",
               "deadlines": "Available January 5 2026 Deadline February 15 2026", "cycle_status": "Status: Closed",
               "funding_class": "scholarships, which range from $500-$5,000 (components not stated)"},
     ambiguous="DACA recipients are also eligible"),
 "us-coca-cola": dict(fields={"nationality": {"mode": "include", "countries": ["US"]}, "levels": ["bachelor"], "deadlines": [],
     "cycle_status": "closed", "funding_class": "not_stated"},
     evidence={"nationality": "U.S. Citizens, U.S. Nationals, U.S. Permanent Residents, Refugees, Asylees, ... Applicants may not be ... International students",
               "cycle_status": "The 2027 Coca-Cola Scholars application is now closed.",
               "funding_class": "$20,000 College Scholarship (components not stated)"},
     ambiguous="refugees, asylees and other statuses are also eligible"),
 "ca-loran": dict(fields={"nationality": "not_stated", "levels": ["bachelor"], "deadlines": [], "cycle_status": "closed",
     "tuition": "full", "components": {"tuition": "full", "stipend": "covered"}, "funding_class": "fully_funded"},
     evidence={"cycle_status": "Applications for the 2027 Loran Award are closed.",
               "funding_class": "An annual stipend of $12,000 A full tuition waiver annually",
               "deadlines": "the dated lines (September 30, 2026 ...) are news items"}),
 "ca-schulich": dict(fields={"nationality": "not_stated", "levels": ["bachelor"], "deadlines": [], "cycle_status": "open",
     "funding_class": "not_stated"},
     evidence={"deadlines": "Nomination deadline is January 27, 2027 (the high school's nomination, not the student's application)",
               "nationality": "Graduate high school or cégep in Canada (schooling, not citizenship)"},
     ambiguous="students cannot apply directly; the nomination round is open"),
})
AMB.update({"us-questbridge": ["deadlines", "cycle_status", "funding_class"], "us-gates-sch": ["cycle_status"], "us-hsf": ["nationality"],
            "us-coca-cola": ["nationality"], "ca-schulich": ["cycle_status"]})
P["de-hamburg-schol"] = dict(fields={"nationality": {"mode": "exclude", "countries": ["DE"]}, "levels": ["bachelor", "master", "phd"],
     "deadlines": [], "cycle_status": "not_announced", "stipend": {"amount": [992], "currency": "EUR", "period": "month"},
     "funding_class": "stipend_only"},
     evidence={"nationality": "do not hold German citizenship; are not eligible for the federal student loan scheme",
               "cycle_status": "(currently no further calls for applications) ... No further calls for applications are currently planned",
               "funding_class": "The maximum monthly funding sum is €992."},
     ambiguous="students eligible for BAföG are also excluded")
AMB["de-hamburg-schol"] = ["nationality"]
X.update({"sg-sutd-schol": "list", "kz-nu-schol": "navigation", "lb-lau-schol": "several scholarships", "ae-nyuad-aid": "Emirati scholarship and need-based aid",
          "fr-bordeaux-schol": "university page about the Eiffel programme", "ca-fulbright": "home page with several awards", "us-beinecke": "foundation home page"})
P["be-uliege-schol"] = dict(fields={"nationality": "not_stated", "levels": ["master"], "deadlines": [], "cycle_status": "not_stated",
     "tuition": "full", "stipend": {"amount": [1400], "currency": "EUR", "period": "month"},
     "components": {"tuition": "full", "insurance": "covered", "living_allowance": "covered", "travel": "covered"},
     "funding_class": "fully_funded"},
     evidence={"funding_class": "Exemption to participation costs ... Registration fee to the master (€13.500) ... Health and accident insurance ... contribution to travel, subsistence and installation of €1,400 per month"},
     ambiguous="the page ends with a list of other funding sources")
AMB["be-uliege-schol"] = ["funding_class"]
X.update({"ae-uaeu-schol": "list", "tr-boun-schol": "department page", "za-ru-schol": "postgraduate centre home", "ca-ulaval-schol": "overview",
          "ca-guelph-schol": "admissions page", "ca-tmu-schol": "list", "au-newcastle-schol": "list", "au-wsu-schol": "several scholarships",
          "au-scu-schol": "list", "au-une-schol": "list", "de-dresden-schol": "overview", "de-lmu-schol": "overview",
          "at-tuwien-schol": "faculty grants list", "fr-uparis-schol": "two programmes", "jp-tohoku-schol": "list",
          "jp-kyushu-schol": "JASSO repayment page with broken encoding", "my-usm-schol": "news item about another programme",
          "om-squ-schol": "journal article", "br-usp-bolsas": "list of grants", "ma-um6p-schol": "empty page", "es-usal-schol": "a poster record"})
P.update({
 "uk-felix": dict(fields={"nationality": {"mode": "exclude", "countries": EEA}, "levels": ["master"], "deadlines": [],
     "cycle_status": "not_stated", "funding_class": "not_stated"},
     evidence={"nationality": "underprivileged nationals of India ... or ... individuals who are not nationals of India or an EEA country (together: everyone outside the EEA)"},
     ambiguous="two groups: Indian nationals, and non-EEA non-Indian nationals recommended by their university"),
 "de-bifonds": dict(fields={"nationality": "not_stated", "levels": ["phd"], "deadlines": [], "cycle_status": "not_stated",
     "components": {"stipend": "covered", "travel": "covered"}, "funding_class": "stipend_only"},
     evidence={"nationality": "to outstanding junior scientists worldwide (an invitation)",
               "funding_class": "On top of the monthly stipend, we offer our fellows seminars, travel allowances"}),
 "us-ndseg": dict(fields={"nationality": {"mode": "include", "countries": ["US"]}, "levels": ["phd"], "deadlines": [],
     "cycle_status": "not_stated", "funding_class": "not_stated"},
     evidence={"nationality": "The NDSEG Fellowship Program is open only to applicants who are citizens or nationals of the United States."},
     ambiguous="'nationals' includes residents of US possessions such as American Samoa; the page text dates from 2022"),
})
AMB.update({"uk-felix": ["nationality"], "us-ndseg": ["nationality"]})
X["pt-fct-phd"] = "list of calls"
P.update({
 "us-krell": dict(fields={"nationality": {"mode": "include", "countries": ["US"]}, "levels": ["phd"], "deadlines": [],
     "cycle_status": "not_stated", "funding_class": "not_stated"},
     evidence={"nationality": "The DOE CSGF is open to U.S. citizens or lawful permanent residents"}),
 "au-john-monash": dict(fields={"nationality": "not_stated", "levels": ["master", "phd"], "deadlines": [D("2026-06-30")],
     "openings": ["2026-05-01"], "cycle_status": "closed",
     "components": {"tuition": "covered", "accommodation": "covered", "living_allowance": "covered"}, "funding_class": "fully_funded"},
     evidence={"nationality": "enables outstanding Australians (a description; the eligibility rules are on another page)",
               "deadlines": "Applications opened 1 May 2026 ... Applications closed 30 June 2026 at 5pm AEST.",
               "cycle_status": "Applications for 2027 scholarships have now closed.",
               "funding_class": "$100,000 AUD for each year of study ... can be used towards tuition fees, accommodation and other living expenses"},
     ambiguous="a fixed sum towards tuition and living; full coverage is not stated; 'Australians' is a description"),
 "int-unu": dict(fields={"nationality": {"mode": "include", "countries": ["CN"]}, "levels": ["master"], "max_age": 27,
     "deadlines": [A("2026-03-22", "historical"), D("2026-04-10")], "cycle_status": "closed", "tuition": "full",
     "components": {"tuition": "full", "living_allowance": "covered", "insurance": "covered", "travel": "covered"},
     "funding_class": "fully_funded"},
     evidence={"nationality": "A citizen of the People's Republic of China",
               "deadlines": "22 March 2026: Deadline to complete your application to the MPP programme ... 10 April 2026: Deadline for MPP-accepted applicants to apply to CSC",
               "funding_class": "The tuition fee for one academic year; Monthly cost-of-living financial assistance; Health insurance ...; A return international airfare"},
     ambiguous="the page is about the CSC-funded track of the UNU scholarships"),
 "int-iaea-mcfp": dict(fields={"nationality": "not_stated", "levels": ["master"], "deadlines": [D("2026-10-31", "current")],
     "cycle_status": "open", "funding_class": "partially_funded"},
     evidence={"nationality": "open to students from IAEA Member States (a group, not listed here)",
               "deadlines": "The application period is now open and will close on 31 October 2026.",
               "funding_class": "awarded up to €20,000 for tuition costs and up to €20,000 for living costs"},
     ambiguous="caps on tuition and living costs; whether that is full coverage depends on the programme"),
})
AMB.update({"au-john-monash": ["nationality", "funding_class"], "int-unu": ["deadlines"], "int-iaea-mcfp": ["funding_class"]})
P.update({
 "int-embl-phd": dict(fields={"nationality": "not_stated", "levels": ["phd"], "deadlines": [], "cycle_status": "not_stated",
     "components": {"stipend": "covered", "insurance": "covered"}, "funding_class": "stipend_only"},
     evidence={"funding_class": "The stipend is competitive by international standards and offers broad benefits including health care and pension."}),
 "de-fulbright": dict(fields={"nationality": {"mode": "include", "countries": ["DE"]}, "levels": ["phd"], "deadlines": [],
     "cycle_status": "closed", "funding_class": "stipend_only"},
     evidence={"nationality": "Die deutsche Staatsangehörigkeit ist Voraussetzung zur Teilnahme am Stipendienprogramm",
               "cycle_status": "Die Frist zur Bewerbung im Doktorand:innenprogramm 2027-28 ist verstrichen. Die Ausschreibung für 2028-29 wird voraussichtlich ab Sommer 2027 veröffentlicht",
               "funding_class": "... auf die monatliche Stipendienleistung angerechnet (a monthly stipend; tuition not mentioned)"},
     ambiguous="the stipend's amount and other components are on a collapsed section"),
 "at-fulbright": dict(fields={"nationality": "not_stated", "deadlines": [], "cycle_status": "not_stated",
     "components": {"travel": "covered", "stipend": "covered", "insurance": "covered", "tuition": "covered"}, "funding_class": "fully_funded"},
     evidence={"funding_class": "Travel and relocation allowance of €2,000 ... Monthly net salary of approximately €1,600 ... accident and sickness coverage ... Enrollment and tuition remission at the Austrian public university"},
     ambiguous="a salary for part-time teaching rather than a stipend; US applicants implied, not stated"),
 "int-wmo": dict(fields={"nationality": "not_stated", "deadlines": [], "cycle_status": "not_stated", "funding_class": "not_stated"},
     evidence={"nationality": "Applicants must be staff members of National Meteorological and Hydrological Services ... nominated by their country's Permanent Representative",
               "funding_class": "Tuition and academic costs ... International travel ... Note: Coverage varies depending on the fellowship and partner institution."}),
 "uk-qmu": dict(fields={"nationality": "not_stated", "deadlines": [D("2026-10-31", "current")], "cycle_status": "open", "tuition": "partial",
     "funding_class": "partially_funded"},
     evidence={"nationality": "for new applicant international fee-paying students (fee status)",
               "deadlines": "We welcome applications from those who have applied to study with us in January 2027. We will communicate decisions as soon as we can after the initial deadline of 31st October 2026.",
               "funding_class": "The scholarship is worth £3000 and is granted as a reduction of the tuition fee."}),
 "tw-nsysu": dict(fields={"nationality": "not_stated", "levels": ["phd"], "deadlines": [D("2023-02-09")], "cycle_status": "closed",
     "funding_class": "not_stated"},
     evidence={"deadlines": "(Deadline 2023/2/9) ... Application for International Elite Doctoral Student Scholarship"},
     ambiguous="an outdated 2023 page"),
 "in-iisc": dict(fields={"nationality": "not_stated", "levels": ["bachelor"], "deadlines": [], "cycle_status": "not_stated",
     "stipend": {"amount": [7000], "currency": "INR", "period": "month"}, "funding_class": "stipend_only"},
     evidence={"funding_class": "Monthly Scholarship: Rs 7,000/- for four years", "nationality": "Open to Undergraduate women students (no nationality rule)"}),
})
AMB.update({"de-fulbright": ["funding_class"], "at-fulbright": ["funding_class"], "tw-nsysu": ["cycle_status"]})
X.update({"sg-moe-tg": "portal", "nz-mfat": "operational guidelines PDF for several schemes", "us-cls": "home page", "us-horatio": "home page",
          "us-nap-ford": "2020 news article", "int-upeace": "several scholarships", "uk-abertay": "list", "uk-aru": "list", "uk-uwe": "list",
          "uk-aber": "list", "uk-chester": "list", "uk-lincoln": "list", "uk-derby": "list", "uk-cardiffmet": "list", "uk-uws": "portal",
          "es-fulbright": "home page", "be-fulbright": "home page", "cn-pku-schol": "navigation", "jp-hokudai-schol": "list",
          "jp-osaka-schol": "list", "th-cmu-schol": "list", "ie-tcd-x": "empty page", "it-polimi-x": "home page", "ng-aust": "home page",
          "za-ukzn": "home page"})
P.update({
 "us-cobell": dict(fields={"nationality": "not_stated", "deadlines": [], "cycle_status": "not_stated", "funding_class": "not_stated"},
     evidence={"nationality": "Enrolled member of a U.S. Federally-recognized American Indian Tribe or Alaska Native Corporation (membership, not a nationality rule)"}),
 "uk-snowdon": dict(fields={"nationality": "not_stated", "levels": ["master"], "deadlines": [], "cycle_status": "closed",
     "components": {"tuition": "partial", "living_allowance": "covered"}, "funding_class": "partially_funded"},
     evidence={"cycle_status": "the Scholarship application round for the 2026/27 academic year which has now closed ... before the 2027/28 academic year application round opens in January 2027",
               "funding_class": "worth up to £30,000 payable as contribution of up to £15,000 towards fees ... and a further £15,000 ... to cover living expenses"},
     ambiguous="the next round opens in January 2027 (month only); fee and living support are capped"),
 "uk-kennedy": dict(fields={"nationality": {"mode": "include", "countries": ["GB"]}, "levels": ["master", "phd"],
     "deadlines": [D("2026-10-18")], "cycle_status": "closed", "tuition": "full",
     "components": {"tuition": "full", "insurance": "covered", "living_allowance": "covered"}, "funding_class": "fully_funded"},
     evidence={"nationality": "To apply you must be all of the following A British citizen Ordinarily resident in the UK",
               "deadlines": "The closing date for applications for a 2027/28 Kennedy Scholarship is 18 October 2026.",
               "funding_class": "A Kennedy Scholarship typically covers the full costs of tuition and health insurance, and a means-tested bursary of up to $33,000 to cover living costs."},
     ambiguous="'typically covers'"),
 "uk-fulbright-uk": dict(fields={"nationality": {"mode": "include", "countries": ["US"]}, "levels": ["master", "phd"], "deadlines": [],
     "cycle_status": "closed", "components": {"stipend": "covered", "insurance": "covered"}, "funding_class": "stipend_only"},
     evidence={"nationality": "Be a US citizen and a non-UK resident ... Dual US-UK citizens are eligible to apply.",
               "cycle_status": "Applications for US Postgraduate Awards are closed for 2027-28.",
               "funding_class": "A personal living allowance (stipend) Sickness and accident coverage"},
     ambiguous="several named awards on the page also cover the first year's tuition"),
 "de-dbu": dict(fields={"nationality": "not_stated", "levels": ["phd"], "deadlines": [], "cycle_status": "not_stated",
     "stipend": {"amount": [1650], "currency": "EUR", "period": "month"}, "funding_class": "stipend_only"},
     evidence={"funding_class": "monatliche Grundförderung: 1.650 € monatliche Sach- und Reisemittel: 150 €"}),
 "lu-fnr": dict(fields={"nationality": "not_stated", "levels": ["phd", "postdoc"], "deadlines": [D("2026-03-11")], "cycle_status": "closed",
     "funding_class": "not_stated"},
     evidence={"deadlines": "Deadline: 11-03-2026 14:00", "cycle_status": "Results 2026 AFR Call"},
     ambiguous="a funding-instrument page; the next call is not mentioned"),
 "int-owsd": dict(fields={"nationality": "not_stated", "levels": ["phd"], "deadlines": [], "cycle_status": "not_announced",
     "funding_class": "not_stated"},
     evidence={"cycle_status": "OWSD regrets there will be no call for PhD applications in 2025 ... any relevant information will be shared on this page.",
               "nationality": "women scientists from the South (a group)"},
     ambiguous="the notice concerns 2025; nothing is said about 2026 or 2027"),
 "us-gem": dict(fields={"nationality": "not_stated", "levels": ["master", "phd"], "deadlines": [], "cycle_status": "open", "tuition": "full",
     "components": {"tuition": "full", "stipend": "covered"}, "funding_class": "fully_funded"},
     evidence={"cycle_status": "GEM application is now open. Apply today!",
               "funding_class": "Full tuition and fees provided by a GEM University Member ... At least $8,000 stipend per year"}),
 "us-hhmi": dict(fields={"nationality": "not_stated", "levels": ["phd"], "deadlines": [D("2026-10-27", "current")], "cycle_status": "open",
     "components": {"stipend": "covered", "tuition": "covered"}, "funding_class": "partially_funded"},
     evidence={"nationality": "Open To: US citizens, permanent residents, DACA recipients, and international students eligible to study and receive funding at their institution",
               "deadlines": "Applications Close: Tuesday, October 27, 2026 at 11:59 PM ET",
               "funding_class": "Support Includes: Annual stipend, discretionary allowance, and institutional allowance to support tuition and fees"},
     ambiguous="the eligible groups together cover almost everyone; an allowance 'to support' tuition"),
 "be-wbi": dict(fields={"nationality": "not_stated", "levels": ["postdoc"], "deadlines": [], "cycle_status": "not_stated",
     "stipend": {"amount": [2120], "currency": "EUR", "period": "month"}, "components": {"living_allowance": "covered", "travel": "covered"},
     "funding_class": "stipend_only"},
     evidence={"nationality": "IN candidates may have stayed in Belgium for a maximum of 12 months (residence history, not nationality)",
               "funding_class": "Coverage by WBI of a net monthly scholarship of €2,120 ... international return travel"}),
 "int-kaiciid": dict(fields={"nationality": "not_stated", "deadlines": [], "cycle_status": "open", "funding_class": "not_stated"},
     evidence={"cycle_status": "In 2027, we are accepting applications for one international cohort of up to 20 Fellows.",
               "nationality": "at least one international, globally diverse cohort open to all applicants (no nationality rule)"}),
 "ke-equity": dict(fields={"nationality": "not_stated", "deadlines": [], "cycle_status": "not_stated",
     "components": {"tuition": "covered", "accommodation": "covered", "living_allowance": "covered", "travel": "covered"},
     "funding_class": "fully_funded"},
     evidence={"funding_class": "provision of tuition fees, accommodation, books, uniform, shopping, pocket money and transport ... during their 4 years of secondary education"},
     ambiguous="a secondary-school programme"),
})
AMB.update({"uk-snowdon": ["cycle_status", "funding_class"], "uk-kennedy": ["funding_class"], "uk-fulbright-uk": ["funding_class"],
            "lu-fnr": ["cycle_status"], "int-owsd": ["cycle_status"], "us-hhmi": ["nationality", "funding_class"], "ke-equity": ["funding_class"]})
X.update({"ca-terryfox": "home page", "jp-sato": "home page with event dates", "us-amgen": "regional programme home", "us-apiasf": "home page",
          "jp-hnf": "empty page", "kr-posco": "a prize, not a scholarship", "us-posse": "home page", "us-tmcf": "list",
          "uk-thouron": "home page with alumni", "int-afdb": "home page", "int-unesco": "World Heritage home", "int-cgiar": "archive page",
          "us-ffaf": "home page", "uk-commonwealth-x": "home page", "ch-ethx": "home page", "int-iie": "list", "int-agfund": "home page",
          "int-cee": "press release", "us-knight": "news article"})
X["us-smart"] = "near-empty page"

urls = json.loads((M / "urls.json").read_text())
ids = {p["id"] for p in urls["pages"]}
assert set(P) <= ids and not set(P) & set(X) and ids <= set(P) | set(X), (set(P) - ids, set(P) & set(X), ids - set(P) - set(X))
assert set(AMB) == {k for k, v in P.items() if v.get("ambiguous")}
pages = {}
for p in urls["pages"]:
    pid = p["id"]
    if pid in P:
        p["split"] = "test"
        lab = P[pid]
        pages[pid] = {"kind": "opportunity", "fields": lab["fields"],
                      "evidence": {k: {"quote": v, "url": p["url"]} for k, v in lab["evidence"].items()},
                      "ambiguous": lab.get("ambiguous", ""), "ambiguous_fields": AMB.get(pid, [])}
    else:
        p["split"] = "excluded"
        p["excluded_because"] = X[pid]
(M / "urls.json").write_text(json.dumps(urls, indent=1, ensure_ascii=False) + "\n")
(M / "labels.json").write_text(json.dumps({"today": "2026-10-19", "version": "N-1",
    "note": "programme decisions labelled by hand from the official pages before any extractor ran on them; quotes per field",
    "pages": pages}, indent=1, ensure_ascii=False) + "\n")
print(len(pages), "labelled (all test);", sum(1 for p in urls["pages"] if p["split"] == "excluded"), "excluded")
