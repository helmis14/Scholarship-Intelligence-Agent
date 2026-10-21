"""Set T labels (round 41), written by hand from the official pages in pages/ before any extractor ran on set T.

Set T is the second fresh test set built from country-by-country searches of official hosts (tests/heldout_t/collect.py: a
search per country for scholarships, kept only when the host is a university, ministry, agency, embassy, foundation or
national programme site). 584 pages were fetched on 2026-10-20 after the code was frozen; 40 were single-programme pages
with enough information to label, and the remaining 544 are excluded without a per-page reason (generic aid pages, lists,
news, several programmes on one page, near-empty pages, or not reviewed). Labels follow the reading of sets L to S: fee
status, residence, status and group names that are not countries are "not_stated" nationality; a cash award whose use is not
stated is "not_stated" funding; a stated share, cap or fixed amount towards tuition is "partially_funded"; deadlines are
applicant dates with a year; cycle_status as of 2026-10-21. Close calls are recorded per decision in AMB
("ambiguous_fields"); results are reported with and without them. Run once to write labels.json; manifest.json then freezes it."""
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
 "o-ae-3-1": dict(fields={"nationality": "not_stated", "levels": ["master"], "deadlines": [A("2026-12-01"), D("2027-01-15", "current")], "cycle_status": "open",
     "components": {"tuition": "full", "stipend": "covered"}, "funding_class": "fully_funded"},
     evidence={"deadlines": "Admission Application Deadline December 1, 2026 ... Financial Aid Application Deadline January 15, 2027",
               "cycle_status": "This application is currently open and will be due on December 1, 2026.",
               "funding_class": "Full tuition scholarship, health insurance, and living stipend"},
     ambiguous="open to people from or committed to the Arab region (a region, not a list of nationalities)"),
 "o-ae-3-3": dict(fields={"nationality": "not_stated", "levels": ["master"], "deadlines": [], "cycle_status": "not_stated", "funding_class": "not_stated"},
     evidence={"funding_class": "a need-based scholarship plus a stipend for the course of their study at HKS (no amounts)"},
     ambiguous="need-based amount not stated"),
 "o-bj-1-1": dict(fields={"nationality": "not_stated", "levels": ["bachelor"], "deadlines": [D("2026-09-17")], "cycle_status": "closed", "funding_class": "not_stated"},
     evidence={"deadlines": "La date limite de dépôt de dossier physique est fixée au jeudi 17 septembre 2026 à 12 heures",
               "cycle_status": "17 septembre 2026 (past on 2026-10-21)"},
     ambiguous="offered to the government of Benin; no nationality line in the criteria"),
 "o-bj-1-2": dict(fields={"nationality": {"mode": "include", "countries": ["BJ"]}, "levels": ["master"], "deadlines": [D("2026-09-17")], "cycle_status": "closed",
     "components": {"tuition": "full"}, "funding_class": "tuition_funded"},
     evidence={"nationality": "Etre de nationalité béninoise",
               "deadlines": "La date limite de dépôt de dossier physique est fixée au jeudi 17 septembre 2026",
               "funding_class": "les bourses couvrent uniquement les frais de scolarité annuels"}),
 "o-bn-1": dict(fields={"nationality": "not_stated", "levels": ["bachelor", "master"], "deadlines": [D("2022-02-15")], "cycle_status": "closed",
     "components": {"tuition": "full", "stipend": "covered"}, "funding_class": "fully_funded"},
     evidence={"deadlines": "not later than 1600 hrs (Brunei time) on 15 February 2022",
               "funding_class": "exemption from paying tuition fees ... monthly personal allowance of BND$500.00 ... accommodation"},
     ambiguous="open to citizens of 'ASEAN, Commonwealth and OIC member countries ... but not limited to' (group names)"),
 "o-ch-3-1": dict(fields={"nationality": {"mode": "include", "countries": ["CH"]}, "levels": ["bachelor"], "deadlines": [D("2026-02-09")], "cycle_status": "closed",
     "components": {"tuition": "full", "stipend": "covered"}, "funding_class": "fully_funded"},
     evidence={"nationality": "Swiss nationality: An applicant who has Japanese nationality at the time of application is not eligible.",
               "deadlines": "Application deadline | Monday, 9 February 2026",
               "funding_class": "117,000 yen per month ... Fees for the entrance examination, matriculation and tuition at universities are waived"},
     ambiguous="Swiss nationality line is worded as an exclusion of Japanese nationals"),
 "o-ch-3-2": dict(fields={"nationality": {"mode": "any", "countries": []}, "levels": ["bachelor", "master", "phd"], "deadlines": [D("2026-02-20")], "cycle_status": "closed",
     "components": {"tuition": "full", "stipend": "covered"}, "funding_class": "fully_funded"},
     evidence={"nationality": "scholarships to international students from all over the world",
               "deadlines": "Application deadline | 20.02.2026",
               "funding_class": "financial support, tuition fee, accommodation and health insurance ... Monthly stipend"},
     ambiguous="'from all over the world' read as any nationality"),
 "o-ch-3-3": dict(fields={"nationality": {"mode": "include", "countries": ["CH", "LI"]}, "levels": ["master", "phd"], "deadlines": [D("2026-06-08")], "cycle_status": "closed",
     "components": {"tuition": "full", "stipend": "covered"}, "funding_class": "fully_funded"},
     evidence={"nationality": "scholarships to students of Switzerland and Liechtenstein",
               "deadlines": "Application deadline | 08.06.2026",
               "funding_class": "144,000 yen per month ... Fees for the entrance examination, matriculation, and tuition at universities are waived"},
     ambiguous="'students of Switzerland and Liechtenstein' read as nationals"),
 "o-ch-4-2": dict(fields={"nationality": {"mode": "include", "countries": ["US"]}, "levels": ["bachelor"], "deadlines": [], "cycle_status": "not_stated", "funding_class": "not_stated"},
     evidence={"nationality": "U.S. citizen, U.S. national, or permanent resident",
               "funding_class": "Goldwater Scholarships provide up to $7500 (a cash amount)"},
     ambiguous="permanent residents also allowed; the only date is a campus (internal) deadline"),
 "o-ch-4-3": dict(fields={"nationality": {"mode": "exclude", "countries": ["GB"]}, "levels": ["master", "phd"], "deadlines": [], "cycle_status": "not_stated", "funding_class": "not_stated"},
     evidence={"nationality": "Citizen of any country outside the United Kingdom"},
     ambiguous="only campus (internal) deadlines are listed; funding amount not given"),
 "o-cn-2-1": dict(fields={"nationality": {"mode": "exclude", "countries": ["CN"]}, "levels": ["bachelor", "master", "phd"], "deadlines": [], "cycle_status": "not_stated", "funding_class": "not_stated"},
     evidence={"nationality": "Applicants must be non-Chinese citizens and in good health."},
     ambiguous="'non-Chinese citizens' read as an exclusion"),
 "o-co-2": dict(fields={"nationality": {"mode": "exclude", "countries": ["CO"]}, "levels": ["master"], "deadlines": [D("2026-06-05")], "cycle_status": "closed",
     "components": {"tuition": "full", "stipend": "covered"}, "funding_class": "fully_funded"},
     evidence={"nationality": "ser ciudadano extranjero, no tener nacionalidad colombiana",
               "deadlines": "inscripciones abiertas hasta el 5 de junio (news dated 15 de abril de 2026)",
               "funding_class": "exención de matrícula, apoyo para gastos de sostenimiento, seguro médico"},
     ambiguous="year of 5 June taken from the news date"),
 "o-co-4-2": dict(fields={"nationality": "not_stated", "levels": ["bachelor"], "deadlines": [], "cycle_status": "not_stated",
     "components": {"tuition": "full"}, "funding_class": "tuition_funded"},
     evidence={"funding_class": "pago del 100% del costo total de la matrícula"}),
 "o-co-4-3": dict(fields={"nationality": "not_stated", "levels": ["bachelor"], "deadlines": [], "cycle_status": "not_stated",
     "components": {"tuition": "full"}, "funding_class": "tuition_funded"},
     evidence={"funding_class": "cubre el 100 % del valor total de los derechos de matrícula del pregrado"}),
 "o-co-5": dict(fields={"nationality": "not_stated", "levels": [], "deadlines": [D("2022-06-28")], "cycle_status": "closed",
     "components": {"tuition": "full", "stipend": "covered"}, "funding_class": "fully_funded"},
     evidence={"deadlines": "está abierta hasta el 28 de junio de 2022",
               "funding_class": "Matrícula. Seguro médico. Visa de cortesía. Estipendio mensual. Gastos de instalación."},
     ambiguous="programme for foreigners but no citizenship wording on the page"),
 "o-de-4": dict(fields={"nationality": {"mode": "include", "countries": ["US"]}, "levels": ["bachelor"], "deadlines": [], "cycle_status": "not_stated",
     "funding_class": "partially_funded"},
     evidence={"nationality": "40 additional scholarships for U.S. undergraduate students per year",
               "funding_class": "a study grant of up to $5,000 to be used toward tuition, housing, travel"},
     ambiguous="'U.S. students' means students of US institutions; funding is a capped amount"),
 "o-gr-3-2": dict(fields={"nationality": "not_stated", "levels": ["bachelor"], "deadlines": [], "cycle_status": "not_stated", "funding_class": "not_stated"},
     evidence={"cycle_status": "Applications for admission are accepted throughout the year. Recommended deadlines for the SNF Program for 2026-27 ... Fall semester: September 10, 2026 ..."},
     ambiguous="five recommended admission dates per year, not one applicant deadline"),
 "o-hu-2": dict(fields={"nationality": {"mode": "include", "countries": ["PK"]}, "levels": ["bachelor", "master", "phd"], "deadlines": [D("2024-01-15")], "cycle_status": "closed", "funding_class": "not_stated"},
     evidence={"nationality": "invites applications from Pakistani/AJ&K nationals",
               "deadlines": "Deadline to apply is January 15, 2024, 1600 hrs. (Pakistan Standard Time)"},
     ambiguous="the programme levels sentence is cut in the extracted text"),
 "o-jo-4": dict(fields={"nationality": {"mode": "include", "countries": ["SY", "JO", "LB", "PS"]}, "levels": ["master"], "deadlines": [D("2026-10-30", "current")], "openings": ["2026-09-01"],
     "cycle_status": "open", "components": {"tuition": "full", "stipend": "covered"}, "funding_class": "fully_funded"},
     evidence={"nationality": "Hold Syrian, Jordanian, Lebanese or Palestinian nationality and be permanently resident in one of these countries",
               "deadlines": "Applications for 2027/28 ... will open on Tuesday 1st September and close on Friday 30th October.",
               "funding_class": "fully-funded scholarships ... 75% tuition fees, full maintenance/living costs (King's covers 25% of tuition)"},
     ambiguous="year of the dates inferred from the weekday (1 September is a Tuesday in 2026)"),
 "o-lu-4-1": dict(fields={"nationality": "not_stated", "levels": ["bachelor"], "deadlines": [], "cycle_status": "not_stated", "funding_class": "partially_funded"},
     evidence={"funding_class": "Accommodation fees in a Residential College (around $21,000) in First Year. $7,000 towards tuition fees in Second and Third Year (~ $35,000)"},
     ambiguous="international = overseas qualification (fee status)"),
 "o-lu-4-2": dict(fields={"nationality": "not_stated", "levels": ["bachelor"], "deadlines": [], "cycle_status": "not_stated", "funding_class": "partially_funded"},
     evidence={"funding_class": "$10,000 ... payable only as a credit towards tuition fees"},
     ambiguous="closing dates 10 December / 30 April have no year"),
})
P.update({
 "o-nl-1-1": dict(fields={"nationality": {"mode": "include", "countries": ["DZ", "EG", "IR", "IQ", "JO", "LB", "LY", "MR", "MA", "OM", "SD", "TN", "SY"]}, "levels": [], "deadlines": [], "cycle_status": "not_stated", "funding_class": "not_stated"},
     evidence={"nationality": "open to professionals who are nationals of - and living and working in - one of the countries listed below"},
     ambiguous="also requires living and working there; Sudan and Syria excluded for current rounds; the next round date (April 2025) is old"),
 "o-pk-4": dict(fields={"nationality": {"mode": "include", "countries": ["PK"]}, "levels": ["master"], "deadlines": [], "cycle_status": "closed",
     "components": {"tuition": "full", "stipend": "covered"}, "funding_class": "fully_funded"},
     evidence={"nationality": "Open to students from, and domiciled in, Pakistan",
               "cycle_status": "The deadline for the 2026/27 academic year has now passed.",
               "funding_class": "5 scholarships of GBP 26,000 (Tuition fees plus maintenance)"},
     ambiguous="'from and domiciled in' Pakistan"),
 "o-ru-1-1": dict(fields={"nationality": "not_stated", "levels": ["master"], "deadlines": [D("2026-06-05")], "cycle_status": "closed",
     "components": {"tuition": "full", "stipend": "covered"}, "funding_class": "fully_funded"},
     evidence={"nationality": "open to Home-fee status applicants (fee status)",
               "deadlines": "by 23:59pm (UK Time) on Friday 5th June 2026",
               "funding_class": "tuition fees at the Home fee rate of GBP 13,700 and a stipend ... of GBP 20,780"}),
 "o-ru-1-2": dict(fields={"nationality": "not_stated", "levels": ["master"], "deadlines": [D("2027-03-31", "current")], "cycle_status": "open", "funding_class": "partially_funded"},
     evidence={"nationality": "be a national of South Asia or South-East Asia",
               "deadlines": "The deadline for applying for this scholarship will be 23:59 (UK Time) 31st March 2027.",
               "funding_class": "GBP 12,000 each ... automatically deducted from your tuition fee"},
     ambiguous="'a national of South Asia or South-East Asia' is a group name; cycle read as open because the application is described and the deadline is in the future"),
 "o-sg-3": dict(fields={"nationality": {"mode": "include", "countries": ["SG"]}, "levels": ["bachelor"], "deadlines": [], "cycle_status": "not_stated",
     "components": {"tuition": "full", "stipend": "covered"}, "funding_class": "fully_funded"},
     evidence={"nationality": "Singapore Citizens or Permanent Residents (PRs)",
               "funding_class": "Tuition and other compulsory fees; Monthly maintenance allowance"},
     ambiguous="permanent residents also eligible; bond of 4-6 years"),
 "o-sv-3-2": dict(fields={"nationality": "not_stated", "levels": ["bachelor", "master"], "deadlines": [D("2023-06-09")], "cycle_status": "closed",
     "components": {"tuition": "full", "stipend": "covered"}, "funding_class": "fully_funded"},
     evidence={"deadlines": "Candidatures should be submitted ... by midnight (Central Europe time), 9 June 2023",
               "funding_class": "Free tuition ... Monthly allowance of 1500 PLN for BSc ... 2200 PLN for MSc ... Air travel ticket ... Health insurance"},
     ambiguous="open to 71 invited Member States (Annex I, not on the page)"),
 "o-sv-3-3": dict(fields={"nationality": {"mode": "include", "countries": ["AL", "AO", "AR", "AM", "AZ", "BY", "BA", "BR", "ME", "PH", "GE", "IN", "ID", "IQ", "IR", "JO", "KZ", "KE", "XK", "LB", "MK", "MX", "MD", "MN", "NG", "PS", "PG", "PE", "RW", "SN", "RS", "TZ", "TN", "UA", "UZ", "VN"]},
     "levels": ["master"], "deadlines": [], "cycle_status": "not_stated", "components": {"tuition": "full", "stipend": "covered"}, "funding_class": "fully_funded"},
     evidence={"nationality": "addressed to citizens of 36 countries covered by Polish Aid: Albania, Angola, Argentina, ... Vietnam",
               "funding_class": "a monthly stipend, exemption from tuition fees at public universities ..., a travel allowance to Poland"}),
})
P.update({
 "o-rw-2": dict(fields={"nationality": {"mode": "include", "countries": AFRICA}, "levels": ["bachelor", "master"], "deadlines": [], "cycle_status": "not_stated",
     "components": {"tuition": "full"}, "funding_class": "fully_funded"},
     evidence={"nationality": "Be a citizen of Rwanda or any African country, a refugee, or a displaced young person in Africa.",
               "funding_class": "Comprehensive financial support, including full tuition fees, fully paid on-campus accommodation, a laptop, learning materials"},
     ambiguous="refugees and displaced young people are also eligible; the sentence is cut off after 'an'"),
 "o-sg-2-1": dict(fields={"nationality": {"mode": "include", "countries": ["SG"]}, "levels": ["master"], "deadlines": [D("2027-03-15", "current")], "cycle_status": "open",
     "components": {"tuition": "full", "stipend": "covered"}, "funding_class": "fully_funded"},
     evidence={"nationality": "Be a Singapore Citizen",
               "deadlines": "Applications for PSC Master's Scholarships for 2027 are now open and will close on 15 March 2027.",
               "funding_class": "Tuition fees and other approved charges ... Maintenance and other allowances."}),
 "o-sg-2-3": dict(fields={"nationality": {"mode": "include", "countries": ["SG"]}, "levels": ["bachelor"], "deadlines": [D("2027-03-15", "current")], "cycle_status": "open", "funding_class": "not_stated"},
     evidence={"nationality": "Be a Singapore Citizen",
               "deadlines": "Applications for PSC Scholarships for 2027 are now open and will close on 15 March 2027."}),
 "o-tl-3-1": dict(fields={"nationality": "not_stated", "levels": ["bachelor", "master"], "deadlines": [D("2027-01-10", "current")], "cycle_status": "open",
     "components": {"tuition": "full", "stipend": "covered"}, "funding_class": "fully_funded"},
     evidence={"nationality": "Available to students on specific Australian visas (visa status)",
               "deadlines": "applications for Study Period 1, 2027 are now open and will close on 10 January 2027.",
               "funding_class": "fully cover the international student tuition fees ... plus include a stipend of $4,000 per year"},
     ambiguous="the stipend is small (A$4,000 a year), so 'fully funded' is a close call"),
 "o-tl-3-2": dict(fields={"nationality": "not_stated", "levels": ["bachelor"], "deadlines": [D("2026-11-30", "current")], "cycle_status": "open", "funding_class": "not_stated"},
     evidence={"deadlines": "applications for Study Period 1, 2027 are now open and will close on 30 November 2026."},
     ambiguous="separate domestic and international applicants"),
 "o-st-2-2": dict(fields={"nationality": "not_stated", "levels": ["bachelor"], "deadlines": [], "cycle_status": "not_stated", "funding_class": "partially_funded"},
     evidence={"funding_class": "may cover living expenses and travel costs ... partially ... up to 3.500 USD per student"}),
 "o-ua-2": dict(fields={"nationality": "not_stated", "levels": [], "deadlines": [], "cycle_status": "not_stated", "components": {"tuition": "full"}, "funding_class": "tuition_funded"},
     evidence={"funding_class": "Free education ... Monthly allowance (if provided by the international agreement) ... Accommodation in a student dormitory"},
     ambiguous="the allowance is conditional on the bilateral agreement; open to citizens of countries with agreements (list on another page)"),
 "o-pa-1": dict(fields={"nationality": {"mode": "include", "countries": ["TW", "JP", "KR", "IN", "EG", "JM", "DO"]}, "levels": ["bachelor"], "deadlines": [D("2018-06-25")], "cycle_status": "closed",
     "components": {"tuition": "full", "stipend": "covered"}, "funding_class": "fully_funded"},
     evidence={"nationality": "Directed to Republic of China, Japan, Korea, India, Egypt, Jamaica, Dominican Republic ... Nationality of some of the countries mentioned above",
               "deadlines": "Application deadline: June 25, 2018.",
               "funding_class": "Registration exemption; Air ticket; Lodging; Monthly stipend ... (500 USD)"},
     ambiguous="'Republic of China' read as Taiwan"),
 "o-vn-5-1": dict(fields={"nationality": "not_stated", "levels": ["bachelor"], "deadlines": [], "cycle_status": "not_stated", "funding_class": "partially_funded"},
     evidence={"funding_class": "50% and 25% of the remaining program tuition fees"}),
 "o-ly-2": dict(fields={"nationality": "not_stated", "levels": ["bachelor"], "deadlines": [], "cycle_status": "open", "components": {"tuition": "full"}, "funding_class": "tuition_funded"},
     evidence={"funding_class": "Full coverage of tuition fees throughout the program's duration",
               "cycle_status": "announces the launch of the 4th edition of its scholarship program for the academic year 2026-2027 ... Apply Now"},
     ambiguous="no date; 'by the announced deadline'; cycle read from the launch announcement"),
 "o-gr-3-3": dict(fields={"nationality": "not_stated", "levels": ["bachelor"], "deadlines": [], "cycle_status": "not_stated", "funding_class": "partially_funded"},
     evidence={"funding_class": "A total of 1400 euro for each qualified applicant to cover tuition"}),
 "o-gr-4-2": dict(fields={"nationality": "not_stated", "levels": ["master"], "deadlines": [], "cycle_status": "not_stated", "funding_class": "partially_funded"},
     evidence={"funding_class": "A 20% Corporate Scholarship on the tuition fees ... A 30% Corporate Scholarship"},
     ambiguous="for employees of Greek companies and their children (employer, not nationality)"),
})
AMB.update({"o-ae-3-1": ["nationality"], "o-ae-3-3": ["funding_class"], "o-bj-1-1": ["nationality"], "o-bn-1": ["nationality"], "o-ch-3-1": ["nationality"],
  "o-ch-3-2": ["nationality"], "o-ch-3-3": ["nationality"], "o-ch-4-2": ["nationality", "deadlines"], "o-ch-4-3": ["deadlines", "funding_class"], "o-cn-2-1": ["nationality"],
  "o-co-2": ["deadlines"], "o-co-5": ["nationality"], "o-de-4": ["nationality", "funding_class"], "o-gr-3-2": ["deadlines", "cycle_status"], "o-hu-2": ["levels"],
  "o-jo-4": ["deadlines"], "o-lu-4-1": ["nationality"], "o-lu-4-2": ["deadlines"], "o-nl-1-1": ["nationality", "cycle_status"], "o-pk-4": ["nationality"],
  "o-ru-1-2": ["nationality", "cycle_status"], "o-sg-3": ["nationality"], "o-sv-3-2": ["nationality"], "o-rw-2": ["nationality", "funding_class"], "o-tl-3-1": ["funding_class"],
  "o-tl-3-2": ["nationality"], "o-ua-2": ["nationality", "funding_class"], "o-pa-1": ["nationality"], "o-ly-2": ["cycle_status", "deadlines"], "o-gr-4-2": ["nationality"]})

for _p in __import__("json").loads((M / "urls.json").read_text())["pages"]:
    X.setdefault(_p["id"], "not a single-programme page or not reviewed (generic page, list, news, PDF)") if _p["id"] not in P else None
for _k in list(P):
    X.pop(_k, None)

urls = json.loads((M / "urls.json").read_text())
ids = {p["id"] for p in urls["pages"]}
assert set(P) <= ids and not set(P) & set(X) and ids <= set(P) | set(X), (set(P) - ids, set(P) & set(X), ids - set(P) - set(X))
assert set(AMB) == {k for k, v in P.items() if v.get("ambiguous")}, set(AMB) ^ {k for k, v in P.items() if v.get("ambiguous")}
pages = {}
for p in urls["pages"]:
    pid = p["id"]
    p["file"] = next(f.name for f in (M / "pages").glob(pid + ".*"))
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
(M / "labels.json").write_text(json.dumps({"today": "2026-10-21", "version": "T-1",
    "note": "programme decisions labelled by hand from the official pages before any extractor ran on them; quotes per field",
    "pages": pages}, indent=1, ensure_ascii=False) + "\n")
print(len(pages), "labelled (all test);", sum(1 for p in urls["pages"] if p["split"] == "excluded"), "excluded")
