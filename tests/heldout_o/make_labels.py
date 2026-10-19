"""Set O labels (round 30), written by hand from the official pages in pages/ before any extractor ran on set O.

Set O is the frozen test set for the round-30 rules (funding extent, nationality groups and definitions, list-item
quotations, date roles stage 3). The rules were committed (f2e3295) before any set-O page was fetched, and nothing on
set O was used to change a rule. Labels follow the same reading as sets L, M and N: fee status, domicile, residence,
"international students", "foreign students" and invitations are "not_stated" nationality; "fully_funded" needs tuition
and living costs both covered (or the page states the full cost of attendance); a stated discount, share or cap is
"partially_funded"; a cash award whose use is not stated is "not_stated" funding unless it is paid per month or year
(then "stipend_only", marked as a close call); deadlines are applicant deadline dates with a year for this programme
(not nominations, openings, payments, notifications, programme stays or other steps); cycle_status as of 2026-10-19
(the day the pages were fetched). Pages listing several awards, home pages, news, fee pages and indexes are excluded.
Close calls are recorded per decision in AMB ("ambiguous_fields"); results are reported with and without them.
Country lists were transcribed by hand from the page; "African students" uses the 54 African states (as in set D).
Run once to write labels.json; manifest.json then freezes it."""
import json
import sys
from pathlib import Path
M = Path(__file__).resolve().parent
sys.path.insert(0, str(M.parents[1]))
from scholarship_agent.countries import COUNTRIES  # noqa: E402
EU = ["AT", "BE", "BG", "HR", "CY", "CZ", "DK", "EE", "FI", "FR", "DE", "GR", "HU", "IE", "IT", "LV", "LT", "LU", "MT", "NL",
      "PL", "PT", "RO", "SK", "SI", "ES", "SE"]
EEA = EU + ["IS", "LI", "NO"]
AFRICA = sorted(c for c, (_, r) in COUNTRIES.items() if r == "Africa" and c not in ("EH", "RE", "YT"))
assert len(AFRICA) == 54
D = lambda d, s="historical": {"kind": "scholarship", "date": d, "status": s}  # noqa: E731
A = lambda d, s="current": {"kind": "admission", "date": d, "status": s}  # noqa: E731
P, AMB, X = {}, {}, {}
P.update({
 "uk-bristol-think": dict(fields={"nationality": "not_stated", "levels": ["bachelor", "master"], "deadlines": [D("2026-04-10")],
     "openings": ["2025-10-21"], "cycle_status": "closed", "funding_class": "not_stated"},
     evidence={"nationality": "These scholarships are for applicants with overseas fee status (fee status)",
               "deadlines": "Think Big Scholarship applications closed on 10 April 2026 at 10 am UK time.",
               "cycle_status": "Applications for September 2026 entry are closed.",
               "funding_class": "Think Big postgraduate scholarships are valued at £6,500, £13,000 and £26,000 for your first year of study (what the main award pays for is not stated)"},
     ambiguous="an umbrella scheme with many sub-awards; the main award's use is not stated"),
 "uk-bcu": dict(fields={"nationality": "not_stated", "levels": ["bachelor"], "deadlines": [], "cycle_status": "not_stated",
     "tuition": "partial", "funding_class": "partially_funded"},
     evidence={"nationality": "Be confirmed as a self-funded international fee payer (fee status)",
               "funding_class": "The scholarship will be applied as a tuition fee discount of £3,000 in year one and £2,000 in year two."},
     ambiguous="automatic award with no application; available for September 2026 or January 2027 entry"),
 "se-miun": dict(fields={"nationality": {"mode": "exclude", "countries": EEA + ["CH"]}, "levels": ["master"],
     "deadlines": [A("2026-01-15", "historical"), D("2026-02-26")], "openings": ["2026-02-10"], "cycle_status": "closed",
     "tuition": "partial", "funding_class": "partially_funded"},
     evidence={"nationality": "Citizens from countries outside the EU/EEA/Switzerland that are required to pay tuition fees",
               "deadlines": "applied through University Admissions ... before the 15 January 2026 ... Applications for Mid Sweden University Tuition Fee Scholarship will be open from 10 February 2026 until 26 February 2026",
               "funding_class": "The scholarship covers 75% of the tuition fee."},
     ambiguous="the admission deadline is a prerequisite step; the scholarship window is separate"),
 "fi-abo": dict(fields={"nationality": "not_stated", "levels": ["master"], "deadlines": [], "cycle_status": "not_stated",
     "tuition": "partial", "funding_class": "partially_funded"},
     evidence={"nationality": "students liable to pay tuition fees (fee status)",
               "funding_class": "The early commitment offer is a discount of 4000 € ... For the second year, all admitted students are awarded a tuition fee reduction of 4000 €"}),
 "be-ugent": dict(fields={"nationality": "not_stated", "levels": ["master"], "deadlines": [], "cycle_status": "not_stated",
     "components": {"stipend": "covered", "tuition": "partial"}, "funding_class": "partially_funded"},
     evidence={"nationality": "All new international students who have been (academically) admitted ... are eligible",
               "deadlines": "The application for academic admission should be submitted before the 1st of April (no year; nomination by the programme coordinator)",
               "funding_class": "maximum scholarship of €10.000 per academic year ... a tuition fee that equals the lowest rate"},
     ambiguous="the page describes the 2025-2026 call; tuition reduced to the lowest rate, not waived"),
 "de-fu": dict(fields={"nationality": {"mode": "exclude", "countries": ["DE"]}, "levels": ["bachelor", "master"],
     "deadlines": [D("2026-01-11")], "cycle_status": "closed", "stipend": {"amount": [861], "currency": "EUR", "period": "month"},
     "funding_class": "stipend_only"},
     evidence={"nationality": "International students are invited to apply who ... are not currently German citizens",
               "deadlines": "Application Deadline January 11, 2026",
               "funding_class": "additional funding up to the amount of a full scholarship of 861 euros/month"}),
 "de-hu": dict(fields={"nationality": {"mode": "any", "countries": []}, "levels": ["bachelor", "master"],
     "deadlines": [D("2026-12-06", "current")], "openings": ["2026-11-09"], "cycle_status": "upcoming",
     "stipend": {"amount": [300], "currency": "EUR", "period": "month"}, "funding_class": "stipend_only"},
     evidence={"nationality": "fördert Studierende aller Nationalitäten",
               "deadlines": "Der Bewerbungszeitraum für die Deutschlandstipendien findet vom 9. November bis zum 6. Dezember 2026 statt.",
               "funding_class": "mit 300 Euro monatlich für mindestens zwei Semester"},
     ambiguous="the Themenklasse track closes on 20 December 2026"),
})
AMB.update({"uk-bristol-think": ["funding_class"], "uk-bcu": ["cycle_status"], "se-miun": ["deadlines"], "be-ugent": ["cycle_status", "funding_class"],
            "de-hu": ["deadlines"]})
X.update({"uk-aston": "list of scholarships", "uk-leicester": "list", "uk-surrey": "course list", "uk-napier": "fees overview",
          "uk-rhul": "scholarship search", "uk-city": "research paper", "uk-dmu": "list", "uk-shu": "list", "uk-clarendon": "college list of awards",
          "au-adelaide": "home page", "au-cdu": "list", "au-unisq": "fees overview", "au-cqu": "list", "au-canberra": "package of several awards",
          "au-acu": "list", "au-federation": "list", "au-csu": "list", "nz-lincoln": "index", "au-dfat": "portal news",
          "fi-uef": "fee page with several waivers", "fi-oulu": "fee page with programme tables", "fi-hanken": "fee page for enrolled students",
          "se-lnu": "study planning page", "se-mau": "several scholarships", "se-kau": "list", "se-oru": "fees page", "se-slu": "several scholarships",
          "se-ltu": "fees page", "no-ntnu": "funding overview", "dk-cbs": "admission page", "dk-ruc": "fees and waivers overview",
          "nl-nuffic": "programme index", "nl-hva": "research paper (PDF)", "nl-fontys": "index", "nl-han": "student news", "nl-avans": "index",
          "be-kuleuven": "login page", "de-tu-berlin": "list of external funders", "de-bonn": "list", "de-koeln": "introductory programme, not funding",
          "de-muenster": "list"})
P.update({
 "de-fau": dict(fields={"nationality": {"mode": "exclude", "countries": ["DE"]}, "levels": ["master"],
     "deadlines": [D("2026-10-28", "current")], "cycle_status": "open",
     "stipend": {"amount": [1000], "currency": "EUR", "period": "total"}, "funding_class": "stipend_only"},
     evidence={"nationality": "only international students without German citizenship or permanent residence may apply",
               "deadlines": "The application deadline for the Graduation Scholarship for Winter Semester 2026/27 is 28 October 2026 at 12:00 noon.",
               "funding_class": "intended to support international students during the last months before graduation ... amounting to 1000 EUR in total"},
     ambiguous="a one-off payment for the final months"),
 "it-sapienza": dict(fields={"nationality": "not_stated", "levels": ["master"], "deadlines": [D("2026-10-30", "current")],
     "cycle_status": "open", "stipend": {"amount": [3000], "currency": "EUR", "period": "year"}, "funding_class": "stipend_only"},
     evidence={"nationality": "students who have obtained a first degree in other Italian universities than Sapienza (no nationality rule)",
               "deadlines": "Deadline: October 30, 2026;",
               "funding_class": "85 two-year scholarships of € 3,000.00 per year (what it pays for is not stated)"},
     ambiguous="a cash award whose use is not stated"),
})
AMB.update({"de-fau": ["funding_class"], "it-sapienza": ["funding_class"]})
X.update({"de-stuttgart": "list", "at-uibk": "exchange students page", "at-tugraz": "information page", "ch-unilu": "index",
          "ch-unine": "degree programme page", "fr-dauphine": "several scholarships", "fr-edhec": "several scholarships",
          "fr-emlyon": "MBA programme page", "fr-amu": "several programmes", "it-polito": "several calls"})
P.update({
 "cz-vut": dict(fields={"nationality": "not_stated", "levels": ["master", "phd"], "deadlines": [D("2026-09-30")],
     "openings": ["2026-09-01"], "cycle_status": "closed",
     "stipend": {"amount": [7500, 10000], "currency": "CZK", "period": "month"}, "funding_class": "stipend_only"},
     evidence={"nationality": "Foreign students currently enrolled in Master or Ph.D. English study programmes (no nationality named)",
               "deadlines": "from September 1 till September 30, 2026",
               "funding_class": "Master students: monthly scholarship of 7.500 CZK ... Ph.D. students: monthly scholarship of 10.000 CZK"},
     ambiguous="'foreign student' may mean non-Czech citizens"),
})
AMB.update({"cz-vut": ["nationality"]})
X.update({"es-uam": "mobility programmes overview", "es-ie": "search tool", "pt-uminho": "exchange mobility call", "ie-ucc": "list",
          "pl-uw": "overview of external scholarships", "cz-muni": "fees and aid overview", "cz-vse": "exchange grants", "hu-bme": "several scholarships"})
P.update({
 "af-pau": dict(fields={"nationality": "not_stated", "deadlines": [], "cycle_status": "not_stated",
     "components": {"tuition": "full", "living_allowance": "covered"}, "funding_class": "fully_funded"},
     evidence={"funding_class": "The PAU offers full scholarships (covering tuition and living expenses) for all successful applicants in all its institutes."}),
 "hk-lingnan": dict(fields={"nationality": "not_stated", "levels": ["bachelor"], "deadlines": [], "cycle_status": "not_stated",
     "components": {"tuition": "full", "accommodation": "covered", "living_allowance": "covered"}, "funding_class": "fully_funded"},
     evidence={"nationality": "Non-local applicants who applied for the University's UGC-funded first-year Economics programme (fee status)",
               "funding_class": "support, including full tuition, hostel accommodation, and partial coverage of academic and living expenses"},
     ambiguous="living expenses only partly covered"),
 "jp-oist": dict(fields={"nationality": "not_stated", "levels": ["phd"], "deadlines": [D("2026-11-15", "current")],
     "openings": ["2026-07-31"], "cycle_status": "open", "funding_class": "fully_funded"},
     evidence={"deadlines": "Application Period: July 31, 2026 - November 15, 2026",
               "funding_class": "A fully-funded 5-year program ... comprehensive financial packages ... on-campus housing"},
     ambiguous="an admissions hub; the internship programme on the same page closes on October 15, 2026; 'fully-funded' without components"),
 "rw-ur": dict(fields={"nationality": {"mode": "include", "countries": AFRICA}, "levels": ["bachelor"], "deadlines": [],
     "cycle_status": "not_stated", "funding_class": "fully_funded"},
     evidence={"nationality": "This scholarship opportunity is open to African students",
               "funding_class": "Full Undergraduate Scholarships under Mastercard Foundation Scholars Program"},
     ambiguous="the call is for 2025/2026; 'full' scholarships without components"),
})
AMB.update({"hk-lingnan": ["funding_class"], "jp-oist": ["deadlines", "funding_class"], "rw-ur": ["nationality", "cycle_status", "funding_class"]})
X.update({"ar-utdt": "several scholarships", "br-unicamp": "2016 news", "cl-uc": "department news", "cn-ustc": "empty page",
          "co-javeriana": "faculty page", "co-urosario": "near-empty page", "cr-earth": "admission costs page", "hk-hkbu": "table of many scholarships",
          "il-huji": "index", "jp-apu": "list", "jp-jasso": "study-abroad scholarship index", "jp-jica": "programme index", "mx-itam": "list",
          "mx-udlap": "2017 news", "sg-smu": "empty page", "tr-itu": "information page", "us-yale": "financial aid home", "za-nwu": "fees page",
          "za-ufs": "bursary overview", "za-uj": "bursary index", "za-uwc": "index"})
P.update({
 "us-acls": dict(fields={"nationality": "not_stated", "levels": ["postdoc"], "deadlines": [D("2026-09-17")], "cycle_status": "closed",
     "stipend": {"amount": [60000], "currency": "USD", "period": "year"}, "funding_class": "stipend_only"},
     evidence={"deadlines": "no later than 5:00 PM Eastern Time, September 17, 2026 (the NYPL application of September 25 is another programme's)",
               "funding_class": "The fellowship stipend is set at $60,000 for a 12-month fellowship."}),
 "us-ssrc": dict(fields={"nationality": {"mode": "include", "countries": ["JP", "US"]}, "levels": ["postdoc"], "deadlines": [],
     "cycle_status": "not_announced", "funding_class": "not_stated"},
     evidence={"nationality": "This competition is open to citizens of the United States and Japan as well as to nationals of other countries who can demonstrate strong and serious long-term affiliations",
               "cycle_status": "the Abe Fellowship Program will no longer be accepting applications",
               "funding_class": "a minimum of 3 and maximum of 12 months of full-time support (no amount or components)"},
     ambiguous="other nationals with long-term affiliations may apply; the programme has ended"),
 "us-wennergren": dict(fields={"nationality": {"mode": "any", "countries": []}, "levels": ["phd"], "deadlines": [],
     "cycle_status": "open", "funding_class": "not_stated"},
     evidence={"nationality": "Qualified students of any nationality or institutional affiliation may apply.",
               "deadlines": "Application deadlines are May 1 ... and November 1 (no year)",
               "cycle_status": "The application portal opens 2 months before the deadline (the November 1 deadline is ahead)",
               "funding_class": "The maximum Dissertation Fieldwork Grant is $25,000 (research costs, not tuition or living)"},
     ambiguous="recurring yearly deadlines without a year"),
})
AMB.update({"us-ssrc": ["nationality", "cycle_status"], "us-wennergren": ["cycle_status", "funding_class"]})
X.update({"us-aises": "list", "us-jrf": "home page", "us-macalester": "need-based aid page", "us-nsbe": "list", "us-point": "FAQ",
          "us-princeton": "admissions information", "us-spie": "empty page", "us-uncf": "list"})
P.update({
 "us-davidson": dict(fields={"nationality": {"mode": "include", "countries": ["US"]}, "levels": ["bachelor"], "deadlines": [],
     "cycle_status": "upcoming", "funding_class": "not_stated"},
     evidence={"nationality": "Be a U.S. citizen residing in the United States, or a Permanent Resident of the United States",
               "cycle_status": "The 2027 application will open in the Fall of 2026.",
               "funding_class": "We award $100,000, $50,000 and $25,000 scholarships (what they pay for is not stated)"},
     ambiguous="'Fall of 2026' has begun; whether the call is already open is not stated"),
 "us-nvidia": dict(fields={"nationality": "not_stated", "levels": ["phd"], "deadlines": [D("2026-10-30", "current")],
     "openings": ["2026-09-30"], "cycle_status": "open", "funding_class": "not_stated"},
     evidence={"nationality": "International PhD students are eligible to apply. (no nationality rule)",
               "deadlines": "2027–2028 applications open September 30, 2026. Apply by October 30, 2026.",
               "funding_class": "provides up to $60,000 per award for PhD research (components not stated)"}),
 "ca-ubc": dict(fields={"nationality": "not_stated", "levels": ["bachelor"], "deadlines": [], "openings": ["2026-10-05"],
     "cycle_status": "open", "funding_class": "not_stated"},
     evidence={"nationality": "You are an international student who will be studying in Canada on a Canadian study permit (study permit status)",
               "deadlines": "The International Scholars Program application is due November 15. (no year)",
               "cycle_status": "Applications for the September 2027 intake will open on October 5, 2026.",
               "funding_class": "need-and-merit-based awards (value not stated for the main awards)"},
     ambiguous="the November 15 deadline is written without a year"),
})
AMB.update({"us-davidson": ["cycle_status"], "ca-ubc": ["deadlines"]})
X.update({"us-siebel": "PDF brochure", "us-apple": "announcement of recipients", "us-microsoft": "corporate home page", "ca-uwo": "list",
          "ca-td": "bank home page", "int-adb": "bond market page", "int-esa": "traineeship (employment)", "int-hague": "list of sponsors"})
P.update({
 "de-avicenna": dict(fields={"nationality": "not_stated", "levels": ["master", "phd"], "deadlines": [D("2026-04-15")],
     "openings": ["2026-03-01"], "cycle_status": "closed",
     "components": {"stipend": "covered", "insurance": "covered", "travel": "covered"}, "funding_class": "stipend_only"},
     evidence={"nationality": "The ISP is designed for international muslim students and doctoral candidates ... Resident educational students can't be funded (no nationality rule)",
               "deadlines": "Application window 01.03. – 15.04.2026 (for funding starting on 1. October 2026)",
               "cycle_status": "The application period is closed.",
               "funding_class": "The financial support consists of a monthly scholarship ... basic scholarship per month ... supplementary support for health insurance ... travel allowance"},
     ambiguous="the page also describes the domestic Avicenna scholarship"),
})
AMB.update({"de-avicenna": ["funding_class"]})
X.update({"de-cusanus": "home page", "id-knb": "near-empty page"})
X.update({"rs-world": "application form (PDF)"})
P.update({
 "uk-carnegie": dict(fields={"nationality": "not_stated", "levels": ["bachelor"], "deadlines": [], "cycle_status": "not_stated",
     "components": {"living_allowance": "covered"}, "funding_class": "stipend_only"},
     evidence={"nationality": "open to students from low-income households who are ordinarily resident in Scotland (residence, not nationality)",
               "funding_class": "Scholarships are intended to cover recipients living costs while they undertake their research"}),
 "us-cameron": dict(fields={"nationality": {"mode": "include", "countries": ["US"]}, "levels": ["bachelor"],
     "deadlines": [D("2027-05-01", "current")], "openings": ["2027-02-01"], "cycle_status": "upcoming",
     "tuition": "full", "funding_class": "tuition_funded"},
     evidence={"nationality": "Be a full citizen of the United States of America;",
               "deadlines": "will close the application when we reach 3,000 OR on May 1, 2027 - whichever occurs first",
               "cycle_status": "APPLICATIONS WILL OPEN FOR THE CLASS OF 2028 ON FEBRUARY 1, 2027",
               "funding_class": "a four-year, full-tuition, impact-driven undergraduate scholarship"},
     ambiguous="the application may close earlier when 3,000 applications are received"),
 "us-jefferson": dict(fields={"nationality": "not_stated", "levels": ["bachelor"], "deadlines": [], "cycle_status": "not_stated",
     "funding_class": "fully_funded"},
     evidence={"funding_class": "The award for the Jefferson Scholarship and the Walentas Scholarship is intended to cover the entire cost of attendance for four years"},
     ambiguous="two programmes share one description; 'entire cost of attendance' without listed components"),
 "es-lacaixa": dict(fields={"nationality": {"mode": "include", "countries": ["ES", "PT"]}, "levels": ["master", "phd"],
     "deadlines": [D("2025-02-05")], "cycle_status": "closed",
     "components": {"tuition": "full", "stipend": "covered", "travel": "covered", "insurance": "covered"}, "funding_class": "fully_funded"},
     evidence={"nationality": "Applicants must have Spanish or Portuguese nationality.",
               "deadlines": "The call for applications will open on the date it is published and will close on 5 February 2025 at 14:00h (the 19 February 2025 date is for language accreditation)",
               "funding_class": "Tuition fees of the university where the fellow has been admitted to, with no limits to the amount ... Monthly allowance"},
     ambiguous="an old call document; the current cycle is not stated"),
})
AMB.update({"us-cameron": ["deadlines"], "us-jefferson": ["funding_class"], "es-lacaixa": ["cycle_status"]})
X.update({"de-eles": "home page", "de-sdw": "home page", "uk-wolfson": "index of partner programmes", "uk-said": "placeholder text",
          "us-stamps": "home page", "us-morehead": "home page", "us-robertson": "home page with news", "us-park": "home page with news",
          "us-scgsr": "list of programmes", "au-rtp": "survey page", "au-westpac": "home page", "au-ramsay": "home page with news",
          "za-canoncollins": "overview", "es-botin": "foundation home page", "es-delpino": "index", "es-barrie": "FAQ",
          "br-estudar": "home page", "id-tanoto": "home page", "id-djarum": "training page", "my-khazanah": "index", "jp-ito": "index",
          "kr-kf": "home page", "in-jindal": "foundation page", "ae-ghurair": "home page"})
P.update({
 "uk-uel": dict(fields={"nationality": "not_stated", "levels": ["bachelor", "master"], "deadlines": [], "cycle_status": "not_stated",
     "tuition": "partial", "funding_class": "partially_funded"},
     evidence={"funding_class": "Scholarships range from £500 to £5,000 off your first-year tuition fees."}),
 "se-mdu": dict(fields={"nationality": {"mode": "exclude", "countries": EEA + ["CH", "BD", "BO", "BF", "KH", "ET", "KE", "ML", "MZ", "RW", "TZ", "UG", "ZM"]},
     "levels": ["master"], "deadlines": [D("2027-02-01", "current")], "cycle_status": "open", "tuition": "partial",
     "funding_class": "partially_funded"},
     evidence={"nationality": "students coming from countries outside of EU/EEA/Switzerland ... NOT open for students from the twelve countries with which Sweden has long-term development cooperation (Bangladesh, Bolivia, Burkina Faso, Cambodia, Ethiopia, Kenya, Mali, Mozambique, Rwanda, Tanzania, Uganda and Zambia)",
               "deadlines": "Deadline for supporting documents for the application and Scholarship application is 1 February 2027.",
               "cycle_status": "The application period is open",
               "funding_class": "The scholarship will cover a part of the tuition fee"}),
 "se-his": dict(fields={"nationality": "not_stated", "levels": ["master"],
     "deadlines": [A("2027-01-15", "current"), D("2027-02-15", "current")], "openings": ["2026-10-16"], "cycle_status": "open",
     "tuition": "partial", "funding_class": "partially_funded"},
     evidence={"nationality": "students required to pay tuition fees (fee status)",
               "deadlines": "15 January 2027: application deadline on University Admissions ... 15 February 2027: Deadline to submit the scholarship application",
               "cycle_status": "16 October 2026: scholarship application opens on University of Skövde",
               "funding_class": "The scholarships are partial tuition fee waivers (50% of the tuition fee)."},
     ambiguous="the admission deadline is a prerequisite step; the Spring 2027 round is closed"),
 "ie-setu": dict(fields={"nationality": {"mode": "exclude", "countries": EEA}, "levels": ["master", "phd"],
     "deadlines": [D("2026-03-12")], "openings": ["2026-01-29"], "cycle_status": "closed",
     "components": {"tuition": "full", "stipend": "covered"}, "funding_class": "fully_funded"},
     evidence={"nationality": "a prestigious scholarship for non-EU/non-EEA students in Ireland",
               "deadlines": "Application closing date | Thursday, 12 March 2026",
               "funding_class": "Full tuition fee waiver and €10,000 stipend for one year."}),
 "jp-hitu": dict(fields={"nationality": {"mode": "exclude", "countries": ["JP"]}, "levels": ["exchange"], "deadlines": [],
     "cycle_status": "not_stated", "stipend": {"amount": [80000], "currency": "JPY", "period": "month"}, "funding_class": "stipend_only"},
     evidence={"nationality": "Must have non-Japanese nationality.",
               "funding_class": "Monthly stipend: 80,000 yen"}),
})
AMB.update({"se-his": ["deadlines"]})
X.update({"uk-bournemouth": "student stories", "uk-gold": "donation page", "uk-leedsbeckett": "two scholarships", "uk-mmu": "several scholarships",
          "uk-tees": "list", "uk-bathspa": "application how-to", "uk-glos": "several packages", "se-hh": "several scholarships",
          "se-bth": "two scholarships (BTH and SI)", "se-du": "two scholarships", "se-hb": "regulations PDF without readable text",
          "se-hig": "two scholarships", "fi-uwasa": "admissions page", "fi-hamk": "fees page", "fi-metropolia": "fees page", "fi-laurea": "fees page",
          "fi-tamk": "near-empty page", "fi-jamk": "fees page", "fi-xamk": "fees page", "fi-lab": "near-empty page", "fi-turkuamk": "fees page",
          "fi-haaga": "fees page", "fi-arcada": "criteria by admission year", "fi-novia": "several scholarships", "ie-mtu": "fees and scholarship table",
          "ie-griffith": "fees and several bursaries", "jp-kobe": "several MEXT programmes", "kr-sogang": "notice board"})

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
(M / "labels.json").write_text(json.dumps({"today": "2026-10-19", "version": "O-1",
    "note": "programme decisions labelled by hand from the official pages before any extractor ran on them; quotes per field",
    "pages": pages}, indent=1, ensure_ascii=False) + "\n")
print(len(pages), "labelled (all test);", sum(1 for p in urls["pages"] if p["split"] == "excluded"), "excluded")
