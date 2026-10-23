"""Set U labels (round 42), written by hand from the official pages in pages/ before any extractor ran on set U.

Set U is the third fresh test set, collected after the round-41 code was finished (tests/heldout_u/collect.py: country searches
for programmes for students from each country and for each country's university scholarships, official-looking hosts only,
every host of sets A to T left out). 556 pages were fetched on 2026-10-21; 44 single-programme pages were labelled and the
rest are excluded without a per-page reason (generic aid pages, lists, news, several programmes on one page, near-empty
pages, or not reviewed). Labels follow the reading of sets L to T: fee status, residence, enrolment, tribal or programme
membership and region names are "not_stated" nationality; a cash award whose use is not stated is "not_stated" funding (paid
per month or year: "stipend_only", marked as a close call); a stated share, cap or fixed amount towards tuition is
"partially_funded"; deadlines are applicant dates with a year; cycle_status as of 2026-10-21. Close calls are recorded per
decision in AMB ("ambiguous_fields"); results are reported with and without them. Run once to write labels.json;
manifest.json then freezes it."""
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
NS = "not_stated"
def L(nat=NS, levels=(), dl=(), cycle=NS, funding=NS, comp=None, openings=None):
    f = {"nationality": nat, "levels": list(levels), "deadlines": list(dl), "cycle_status": cycle, "funding_class": funding}
    if comp:
        f["components"] = comp
    if openings:
        f["openings"] = openings
    return f
INC = lambda *c: {"mode": "include", "countries": list(c)}  # noqa: E731
EXC = lambda *c: {"mode": "exclude", "countries": list(c)}  # noqa: E731
TF, ST = {"tuition": "full"}, {"tuition": "full", "stipend": "covered"}
P.update({
 "u-af-3-1": dict(fields=L(levels=["master"]), evidence={"levels": "applicants must currently be completing either a Master of Architecture, M.S. ..."}),
 "u-at-1-2": dict(fields=L(), evidence={"nationality": "You are a student at the University of Potsdam (enrolment, not nationality)"}),
 "u-bi-4-2": dict(fields=L(INC("CD"), ["master"], [D("2022-11-27")], "closed"),
     evidence={"nationality": "Être de nationalité congolaise", "deadlines": "pour le 27 Novembre 2022 au plus tard"}),
 "u-bi-4-3": dict(fields=L(INC("CD"), ["phd"], [D("2022-11-27")], "closed"),
     evidence={"nationality": "Etre de nationalité congolaise", "deadlines": "pour le 27 Novembre 2022 au plus tard"}),
 "u-bj-1": dict(fields=L(NS, ["master", "phd"], [D("2025-02-28")], "closed"),
     evidence={"deadlines": "on or before February 28, 2025", "levels": "Master and Doctorate degrees are tenable in LOCAL Universities only"},
     ambiguous="open to the university's academic staff; tenable in Nigerian universities (a place, not a nationality)"),
 "u-bn-1": dict(fields=L(NS, ["bachelor", "master"], [D("2025-02-15")], "closed"),
     evidence={"nationality": "Foreign students are encouraged to apply", "deadlines": "The closing date for application of the Scholarship is February 15, 2025."}),
 "u-ch-2-1": dict(fields=L(NS, ["bachelor"], funding="fully_funded"),
     evidence={"nationality": "students who have been granted refugee status in Switzerland (status)", "funding_class": "SWB recipients are provided with a full scholarship"},
     ambiguous="'a full scholarship' without saying what it covers"),
})
AMB.update({"u-bj-1": ["nationality"], "u-ch-2-1": ["funding_class"]})
P.update({
 "u-ch-4-1": dict(fields=L(funding="stipend_only"), evidence={"funding_class": "einen monatlichen Beitrag von 1650 CHF"},
     ambiguous="only for members of the Studienstiftung; a monthly cash amount read as a stipend"),
 "u-ch-4-2": dict(fields=L(), evidence={"funding_class": "Jahresstipendien (20 000 CHF) (a cash amount)"}),
 "u-co-2-1": dict(fields=L(levels=["phd"]), evidence={"funding_class": "Value and duration $135,787 (use not stated)", "deadlines": "End Date of Scholarship Eligibility 31 December 2026"},
     ambiguous="'end date of scholarship eligibility' is not stated as an application deadline"),
 "u-cr-1-1": dict(fields=L(NS, ["master"], [D("2027-03-03", "current")], "open", "stipend_only"),
     evidence={"nationality": "Be an enrolled member of a federally recognized U.S. tribal nation (tribal membership)",
               "deadlines": "Application deadline: March 3, 2027", "funding_class": "$7,000 scholarship award per academic year"},
     ambiguous="the date is the MSW admission deadline; a yearly cash award read as stipend_only; tribal membership is not a nationality"),
 "u-cr-4-1": dict(fields=L(NS, ["bachelor"], funding="partially_funded"), evidence={"funding_class": "covers up to $6000 of total tuition costs", "cycle_status": "approved on a rolling basis"}),
 "u-de-3-1": dict(fields=L(NS, ["bachelor", "master"], [D("2026-04-30")], "closed", "stipend_only", openings=["2026-04-06"]),
     evidence={"deadlines": "Application period: from 6 April 2026 to 30 April 2026", "funding_class": "EUR 300 per month (non-repayable grant)"},
     ambiguous="title also names doctoral candidates; a monthly grant read as stipend_only"),
 "u-de-3-3": dict(fields=L(NS, [], [D("2026-05-15")], "closed"),
     evidence={"deadlines": "Die Bewerbungsphase für das Deutschlandstipendium 2026/27 ... ist seit dem 15. Mai 2026 beendet."}),
 "u-dj-1-2": dict(fields=L(NS, ["master"], [A("2026-03-15", "historical")], "closed", "fully_funded", ST),
     evidence={"deadlines": "Submit your program application by March 15, 2026.", "funding_class": "Full scholarship – covers tuition fees and your first year of living expenses; Half scholarship – covers tuition fees only"},
     ambiguous="two tiers (full and half); the date is the programme application date"),
})
AMB.update({"u-ch-4-1": ["funding_class"], "u-co-2-1": ["deadlines", "cycle_status", "funding_class"], "u-cr-1-1": ["nationality", "deadlines", "cycle_status", "funding_class"],
  "u-de-3-1": ["levels", "funding_class"], "u-dj-1-2": ["deadlines", "funding_class"]})
P.update({
 "u-dk-1": dict(fields=L(INC("DK"), ["bachelor", "master"], funding="tuition_funded", comp=TF),
     evidence={"nationality": "Som dansk statsborger har du ret til en videregående uddannelse ... Du kan kun få udlandsstipendium, hvis du er SU-berettiget.",
               "funding_class": "Udlandsstipendiets primære formål er hjælp til at betale selve studieafgiften (tuition fee) i udlandet."},
     ambiguous="the rule is SU eligibility, which the page links to Danish citizenship"),
 "u-ec-4-2": dict(fields=L(funding="fully_funded", comp=ST),
     evidence={"nationality": "Students from eligible partner countries in the following regions may apply (countries not listed)",
               "funding_class": "fully funded study ... covers most of the costs of studying including your fees, travel, insurance, and a fortnightly living allowance"},
     ambiguous="eligible countries are on another page"),
 "u-gn-3-1": dict(fields=L(NS, ["bachelor"], [D("2026-07-02")], "closed"),
     evidence={"deadlines": "on or before the deadline – Thursday, July 2, 2026."}),
 "u-gn-3-3": dict(fields=L(NS, ["bachelor"], [D("2023-03-14")], "closed", "fully_funded", TF),
     evidence={"deadlines": "DEADLINE for the submission of applications for the Baker Hughes Scholarship is TUESDAY MARCH 14th, 2023",
               "funding_class": "The Scholarship covers academic and residential fees and book allowance."},
     ambiguous="tuition and residence fees covered, no living allowance"),
})
AMB.update({"u-dk-1": ["nationality"], "u-ec-4-2": ["nationality"], "u-gn-3-3": ["funding_class"]})
P.update({
 "u-gq-3-2": dict(fields=L(INC("LR"), ["bachelor"], [D("2026-01-15")], "closed"),
     evidence={"nationality": "invites qualified Liberians to apply for admission into ... Medical and Dental Colleges/Institutes in Bangladesh",
               "deadlines": "Application Deadline: January 15, 2026"},
     ambiguous="medicine and dentistry degrees read as bachelor level"),
 "u-gr-3-2": dict(fields=L(NS, ["bachelor"]),
     evidence={"nationality": "First preference is for undergraduate students from Latin America (a preference, not a rule)",
               "deadlines": "apply for admission to IU by November 1 ... We recommend applying by February 1 (no year)"}),
 "u-hk-2": dict(fields=L(NS, ["bachelor"], [D("2026-09-04")], "closed", "fully_funded", ST, openings=["2026-06-22"]),
     evidence={"nationality": "be permanent residents of Hong Kong (residence)",
               "deadlines": "Commencement Date: 22 June 2026 (Monday) Closing Date: 4 September 2026 (Friday)",
               "funding_class": "The maximum is HK$280,000 per year ... taking into account the actual university fees, necessary living expenses"},
     ambiguous="a yearly maximum adjusted to fees and living costs; the dates are 'for reference only'"),
 "u-hk-4": dict(fields=L(NS, ["bachelor", "master"], [D("2024-12-31")], "closed", "tuition_funded", TF, openings=["2024-10-14"]),
     evidence={"nationality": "eligible Hong Kong students (residence status, not defined here)",
               "deadlines": "from today until December 31, be open for applications (news of October 14, 2024)",
               "funding_class": "a non-means-tested scholarship to cover their tuition fees, subject to a ceiling of $300,000 per annum"},
     ambiguous="tuition covered up to a ceiling; year of 31 December taken from the news date"),
})
AMB.update({"u-gq-3-2": ["levels"], "u-hk-2": ["deadlines", "funding_class"], "u-hk-4": ["nationality", "deadlines", "funding_class"]})
P.update({
 "u-hu-2-2": dict(fields=L(NS, ["bachelor", "master", "phd"], funding="fully_funded", comp=ST),
     evidence={"funding_class": "Tuition-free education ... Monthly stipend ... Accommodation contribution ... Medical insurance",
               "nationality": "based on bilateral education agreements between Hungary and the governments of the sending countries (not listed)"},
     ambiguous="the page says the provisions are only a contribution to living expenses"),
 "u-iq-1-3": dict(fields=L(INC("ID"), ["bachelor", "master", "phd"], [D("2026-12-05", "current")], "open", "stipend_only", {"stipend": "covered"}),
     evidence={"nationality": "Indonesian citizens who graduated from Universitas Gadjah Mada, Institut Teknologi Bandung, Universitas Indonesia and Universitas Airlangga",
               "deadlines": "The application deadline is 5 December 2026 for students planning to begin their studies in April 2027",
               "funding_class": "Scholarship allowance of 130,000 yen per month for living expenses (students are self-financing)"}),
 "u-jo-4-2": dict(fields=L(INC("YE"), ["master"]),
     evidence={"nationality": "Scholarships for Postgraduate Studies in Jordan for Yemenis ... Candidates from Yemen"},
     ambiguous="the nationality is in the title and 'candidates from Yemen'"),
 "u-ke-2-2": dict(fields=L(INC("US"), ["bachelor", "master"], [D("2027-01-27", "current"), D("2027-01-20", "current")], "open"),
     evidence={"nationality": "U.S. citizens; undergraduate and graduate level.",
               "deadlines": "Scholarships: January 27, 2027 ... Fellowships: January 20, 2027 (campus deadline January 19, 2027)",
               "funding_class": "receive up to $30,000 (a cash cap)"},
     ambiguous="two programmes (scholarship and fellowship) with their own dates; cycle not stated as open"),
})
AMB.update({"u-hu-2-2": ["funding_class"], "u-jo-4-2": ["nationality"], "u-ke-2-2": ["levels", "deadlines", "cycle_status"]})
P.update({
 "u-ke-3": dict(fields=L(INC("KE"), ["bachelor"], funding="fully_funded", comp=ST),
     evidence={"nationality": "two full scholarships to qualifying Kenya students on an annual basis",
               "funding_class": "The scholarship covers tuition, fees, room and board.", "deadlines": "The deadline ... is February 1 (no year)"},
     ambiguous="'Kenya students' read as Kenyan nationals"),
 "u-kz-1": dict(fields=L(INC("KZ"), ["bachelor", "master", "phd"]),
     evidence={"nationality": "Citizens of the Republic of Kazakhstan who meet the requirements ... may apply"}),
 "u-kz-4-3": dict(fields=L(NS, ["bachelor", "master"], [], "open", "stipend_only", {"stipend": "covered"}),
     evidence={"cycle_status": "Mahasarakham University is now accepting applications for the MSU Inbound Scholarship ... First Round (news of July 7, 2026)",
               "funding_class": "Selected students will receive a monthly living allowance ... 5,000 THB per month"},
     ambiguous="'graduate' read as master; the first round may be over by the scoring date"),
 "u-lv-2-1": dict(fields=L(NS, ["phd"], [D("2026-06-30")], "closed", openings=["2026-06-15"]),
     evidence={"deadlines": "Application: June 15, 2026 (Mon.) - June 30, 2026 (Tue.) 16:45",
               "nationality": "You are enrolled in a doctoral course at Keio University (enrolment)"}),
})
AMB.update({"u-ke-3": ["nationality"], "u-kz-4-3": ["levels", "cycle_status"]})
P.update({
 "u-lv-3-1": dict(fields=L(INC("KR"), ["bachelor", "master", "phd"], [D("2026-04-01")], "closed"),
     evidence={"nationality": "Latvian government offers three types of scholarships to Korean students and researchers",
               "deadlines": "Application deadline: 1 April 2026"},
     ambiguous="three award types on one page with the same date; 'Korean students' read as nationals"),
 "u-mx-1": dict(fields=L(NS, ["bachelor", "master", "phd", "postdoc"], [D("2023-07-21")], "closed", "stipend_only", {"stipend": "covered"}),
     evidence={"deadlines": "Application deadline before: July 21, 2023",
               "funding_class": "a scholarship ranging from 12,614 Mexican pesos ($700) to 15,768 Mexican pesos ($876) per month, with full coverage of transportation and treatement costs"},
     ambiguous="'first, second and third cycles' read as the three degree levels; tuition not mentioned"),
 "u-ne-1": dict(fields=L(NS, ["bachelor", "master"], [], "open", "fully_funded", ST),
     evidence={"nationality": "Be a registered beneficiary of the Presidential Amnesty Programme (status)",
               "cycle_status": "invites applications from eligible beneficiaries for its 2026/2027 Scholarship Programme",
               "funding_class": "Tuition fees. Monthly In-Training Allowance (ITA). Book allowance."},
     ambiguous="no closing date; cycle read from the invitation"),
})
AMB.update({"u-lv-3-1": ["nationality"], "u-mx-1": ["levels", "funding_class"], "u-ne-1": ["cycle_status"]})
P.update({
 "u-no-3": dict(fields=L(INC("NO"), ["master", "phd"], funding="fully_funded", comp=ST),
     evidence={"nationality": "available to Masters and PhD applicants from Norway or with a strong link to Norway",
               "funding_class": "Award purpose: Fees (International), Maintenance, Student visa cost, Student immigration health surcharge"},
     ambiguous="'or with a strong link to Norway' widens the rule"),
 "u-ps-1": dict(fields=L(INC("PS"), ["bachelor", "master"], [], "closed", "fully_funded", ST),
     evidence={"nationality": "Be Palestinian, priority will be given to those who normally reside in the West Bank, Gaza or one of the Palestinian refugee camps",
               "cycle_status": "Applications are now closed for 2026/27 entry. Applications will reopen in January 2027.",
               "funding_class": "a full tuition fee waiver and a living allowance of GBP 20,500 per year"},
     ambiguous="also open to holders of Palestinian travel documents residing in Palestine"),
 "u-pt-3": dict(fields=L(INC("AO"), ["bachelor"], [D("2026-06-10")], "closed", openings=["2026-06-03"]),
     evidence={"nationality": "dirige-se a cidadãos angolanos", "deadlines": "Período de candidaturas: 3 a 10 de junho de 2026"}),
 "u-qa-2": dict(fields=L(NS, [], [], "upcoming"),
     evidence={"nationality": "aimed on excellent students from South-Eastern Europe (a region)", "cycle_status": "Next call for academic year 2027.2028 opens in November 2026.",
               "funding_class": "Max. EUR 12.000 in scholarship funds (use not stated)"},
     ambiguous="South-Eastern Europe is a region, not a list"),
})
AMB.update({"u-no-3": ["nationality"], "u-ps-1": ["nationality"], "u-qa-2": ["nationality"]})
P.update({
 "u-sg-4": dict(fields=L(INC("SG"), ["bachelor"], [D("2027-03-15", "current")], "open"),
     evidence={"nationality": "Singapore citizens or permanent residents intending to take up citizenship",
               "deadlines": "Applications are now open and will close on 15 March 2027."},
     ambiguous="permanent residents intending to take up citizenship also eligible"),
 "u-sy-3": dict(fields=L(INC("JO", "LB", "PS", "SY"), ["master"], [D("2026-10-30", "current")], "open", "fully_funded", ST),
     evidence={"nationality": "Hold Lebanese, Syrian, Palestinian or Jordanian nationality.",
               "deadlines": "Application deadline 30 October 2026",
               "funding_class": "fully funded scholarships which include tuition fees, full maintenance/living costs"},
     ambiguous="cycle read as open from a future deadline (no opening date on the page)"),
 "u-td-4": dict(fields=L(INC("US"), ["bachelor"], [D("2026-10-01")], "closed"),
     evidence={"nationality": "A citizen of the United States",
               "deadlines": "Next Gilman Deadline: October 1, 2026 ... After October 2026, the next Gilman application deadline will be in March 2027.",
               "funding_class": "Award amounts will vary up to $5,000 (a cash cap)"},
     ambiguous="'mid August' opening; between two rounds on the scoring date"),
})
AMB.update({"u-sg-4": ["nationality"], "u-sy-3": ["cycle_status"], "u-td-4": ["cycle_status"]})
P.update({
 "u-sg-2": dict(fields=L(INC("SG"), ["bachelor"]),
     evidence={"nationality": "Who is eligible: Singapore Citizens who have completed at least 1 academic semester in an overseas university",
               "funding_class": "SGD 60,000 grant ... SGD 40,000 grant (use not stated)"}),
})
P.update({
 "u-th-4-1": dict(fields=L(NS, ["master"]),
     evidence={"nationality": "Any overseas applicant (fee status)", "funding_class": "GBP 2,000 (use not stated)"}),
 "u-th-4-3": dict(fields=L({"mode": "any", "countries": []}, ["master"], funding="fully_funded", comp=ST),
     evidence={"nationality": "All nationalities consider who intend to return there at the end of the period of study.",
               "funding_class": "paid as a full tuition fee waiver and as a monthly allowance for other expenses",
               "deadlines": "The deadlines are country specific, ... usually between August and November each year"},
     ambiguous="Chevening has its own country list; the page says all nationalities"),
})
AMB.update({"u-th-4-3": ["nationality"]})

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
(M / "labels.json").write_text(json.dumps({"today": "2026-10-21", "version": "U-1",
    "note": "programme decisions labelled by hand from the official pages before any extractor ran on them; quotes per field",
    "pages": pages}, indent=1, ensure_ascii=False) + "\n")
print(len(pages), "labelled (all test);", sum(1 for p in urls["pages"] if p["split"] == "excluded"), "excluded")
