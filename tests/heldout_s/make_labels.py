"""Set S labels (round 36), written by hand from the official pages in pages/ before any extractor ran on set S.

Set S is the fresh test set built by following lists: each page was reached from a list, home or several-award page of sets P, Q
and R (never labelled, never used for a rule) by taking the link whose text names a scholarship, fellowship, grant or award
on the same site (tests/heldout_s/collect.py). 661 pages were fetched on 2026-10-20 after the code was frozen; 30 were
single-programme pages with enough information to label, and the remaining 631 are excluded without a per-page reason
(generic aid pages, lists, news, PDFs, near-empty pages, or not reviewed). Labels follow the reading of sets L to R: fee status,
residence, status and group names that are not countries are "not_stated" nationality; a cash award whose use is not stated is
"not_stated" funding; deadlines are applicant dates with a year; cycle_status as of 2026-10-20. Close calls are recorded per decision in AMB
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
SEA = ["BN", "KH", "ID", "LA", "MY", "MM", "PH", "SG", "TH", "TL", "VN"]
P.update({
 "s-de-fazit-1": dict(fields={"nationality": {"mode": "any", "countries": []}, "levels": ["phd"], "deadlines": [], "cycle_status": "not_stated", "funding_class": "not_stated"},
     evidence={"nationality": "Es können sich deutsche und ausländische Nachwuchswissenschaftler mit Wohnsitz in Deutschland aller Fachrichtungen ... bewerben",
               "cycle_status": "Die Antragsunterlagen sollten mindestens drei Monate und frühestens sechs Monate vor dem gewünschten Förderbeginn eingereicht werden (rolling, no dates)"},
     ambiguous="open to German and foreign applicants resident in Germany (residence rule); continuous submission"),
 "s-ca-unb-international-2": dict(fields={"nationality": "not_stated", "levels": ["bachelor"], "deadlines": [], "cycle_status": "not_stated", "funding_class": "not_stated"},
     evidence={"nationality": "Awarded to a top international student who is beginning an undergraduate degree program (fee status)",
               "funding_class": "Value: $10,000. (what it pays for is not stated)"},
     ambiguous="a cash award"),
 "s-ca-wlu-international-1": dict(fields={"nationality": "not_stated", "levels": ["bachelor"], "deadlines": [], "cycle_status": "not_stated", "funding_class": "not_stated"},
     evidence={"nationality": "available exclusively to international students beginning their undergraduate studies (fee status)",
               "funding_class": "The scholarship is valued at $500 to $5,000 CAD (what it pays for is not stated)"},
     ambiguous="a cash award"),
 "s-fi-fulbright-finland-3": dict(fields={"nationality": "not_stated", "levels": ["master"], "deadlines": [], "cycle_status": "not_stated",
     "components": {"stipend": "covered", "tuition": "full"}, "funding_class": "fully_funded"},
     evidence={"funding_class": "Fulbright-Aalto University Graduate Award EUR 1000 per month (paid for nine months). ... Aalto University awards a scholarship ... to cover the annual tuition fee"},
     ambiguous="the tuition sentence is cut off in the extracted text"),
 "s-fi-fulbright-finland-4": dict(fields={"nationality": "not_stated", "levels": ["master"], "deadlines": [], "cycle_status": "not_stated",
     "components": {"stipend": "covered", "tuition": "full"}, "funding_class": "fully_funded"},
     evidence={"funding_class": "The Fulbright-LUT University Graduate Award includes a monthly grant of EUR 1 000 (paid for nine months). ... LUT awards a scholarship ... to cover the annual [tuition fee]"},
     ambiguous="the tuition sentence is cut off in the extracted text"),
 "s-hu-pte-3": dict(fields={"nationality": "not_stated", "levels": ["bachelor", "master", "phd"], "deadlines": [], "cycle_status": "not_stated",
     "components": {"tuition": "full", "stipend": "covered"}, "funding_class": "fully_funded"},
     evidence={"funding_class": "Tuition-free education: exemption from the payment of tuition fees. Monthly stipend: ... monthly HUF 43 700 contributions to the living expenses ... doctoral level: monthly HUF 140 000"},
     ambiguous="'contribution to living expenses' is a stipend; accommodation and insurance lines are cut"),
 "s-jp-tmu-international-3": dict(fields={"nationality": "not_stated", "levels": ["bachelor"], "deadlines": [], "cycle_status": "not_stated",
     "components": {"stipend": "covered"}, "funding_class": "stipend_only"},
     evidence={"nationality": "Academically outstanding privately financed international students (status, not nationality)",
               "funding_class": "100,000 JPY per month (for 12 months)"}),
 "s-jp-tmu-international-4": dict(fields={"nationality": "not_stated", "levels": ["bachelor"], "deadlines": [], "cycle_status": "not_stated",
     "components": {"stipend": "covered", "tuition": "partial"}, "funding_class": "partially_funded"},
     evidence={"funding_class": "Stipend: 100,000 JPY per month (1,200,000 JPY per year). Tuition Support: Half-Tuition Reduction"}),
 "s-no-fulbright-norway-3": dict(fields={"nationality": "not_stated", "levels": ["postdoc"], "deadlines": [D("2026-10-01")], "cycle_status": "closed", "funding_class": "not_stated"},
     evidence={"deadlines": "Søknadsfrist: 1. oktober 2026.",
               "cycle_status": "Søknadsfrist: 1. oktober 2026 (past on 2026-10-20)",
               "funding_class": "Stipendbeløpet er pålydende NOK 350.000,- (a cash amount)"},
     ambiguous="a research award for PhD holders; a cash amount"),
 "s-np-fulbright-nepal-1": dict(fields={"nationality": {"mode": "include", "countries": ["US"]}, "levels": ["master", "phd"], "deadlines": [D("2026-10-06")], "cycle_status": "closed",
     "funding_class": "not_stated"},
     evidence={"nationality": "In Nepal, the program offers American graduate students ... (Fulbright U.S. Student Researcher Program)",
               "deadlines": "Application Deadline: October 06, 2026, 5:00 PM EDT"},
     ambiguous="'American graduate students' is the only nationality wording; graduate level only"),
 "s-nl-fulbright-2": dict(fields={"nationality": {"mode": "include", "countries": ["NL"]}, "levels": ["bachelor"], "deadlines": [], "cycle_status": "not_stated",
     "funding_class": "fully_funded"},
     evidence={"nationality": "provides the opportunity for talented Dutch high school graduates to study at an American college",
               "funding_class": "This scholarship covers all costs with this year-long study program including ... A budget of $23,000 for tuition, fees, room and board"},
     ambiguous="'Dutch' read as nationality; 'covers all costs' for a one-year programme"),
 "s-th-ku-international-1": dict(fields={"nationality": {"mode": "include", "countries": SEA}, "levels": ["phd"], "deadlines": [], "cycle_status": "not_stated",
     "components": {"tuition": "full", "stipend": "covered"}, "funding_class": "fully_funded"},
     evidence={"nationality": "Citizens of Southeast Asian countries",
               "funding_class": "fully funded Ph.D. ... Full tuition & fees ... Monthly stipend (living expenses)"},
     ambiguous="'Southeast Asian countries' is a group name read as the eleven SEARCA member states"),
 "s-tw-ndhu-international-1": dict(fields={"nationality": "not_stated", "levels": ["master", "phd"], "deadlines": [D("2026-09-30")], "cycle_status": "closed", "funding_class": "not_stated"},
     evidence={"nationality": "Scholarship for Foreign Graduate Students (status, not nationality)",
               "deadlines": "Application Deadline: By 12:00 PM, Wed., September 30, 2026",
               "cycle_status": "Application Deadline: Wed., September 30, 2026 (past on 2026-10-20)"}),
 "s-se-fulbright-sweden-1": dict(fields={"nationality": {"mode": "include", "countries": ["SE"]}, "levels": ["postdoc"], "deadlines": [D("2027-01-11", "current")], "openings": ["2026-09-01"],
     "cycle_status": "open", "funding_class": "not_stated"},
     evidence={"nationality": "Swedish citizenship (dual U.S. and Swedish citizens may NOT apply)",
               "deadlines": "January 11, 2027: application deadline",
               "cycle_status": "September 2026: online application open; January 11, 2027: application deadline"},
     ambiguous="a fellowship for holders of a terminal degree (levels fit loosely)"),
 "s-us-caltech-intl-1": dict(fields={"nationality": {"mode": "include", "countries": ["TW"]}, "levels": ["master", "phd"], "deadlines": [], "cycle_status": "not_stated", "funding_class": "not_stated"},
     evidence={"nationality": "Each year, two Taiwanese graduate students of superior academic achievement are chosen for the J. Yang Scholarship."},
     ambiguous="'Taiwanese graduate students' read as nationality"),
 "s-us-caltech-intl-2": dict(fields={"nationality": "not_stated", "levels": ["phd"], "deadlines": [], "cycle_status": "not_stated", "funding_class": "not_stated"},
     evidence={"nationality": "The applicant must have obtained a Master's degree from a Finnish university (degree, not nationality)"}),
 "s-us-babson-intl-2": dict(fields={"nationality": "not_stated", "levels": ["bachelor"], "deadlines": [], "cycle_status": "not_stated",
     "components": {"tuition": "full"}, "funding_class": "tuition_funded"},
     evidence={"funding_class": "The Arthur M. Blank School for Entrepreneurial Leadership Scholarship is a four-year, full-tuition, merit-based scholarship."}),
 "s-us-case-international-3": dict(fields={"nationality": {"mode": "include", "countries": ["US"]}, "levels": ["master", "phd"], "deadlines": [], "cycle_status": "not_stated", "funding_class": "not_stated"},
     evidence={"nationality": "Eligibility: an American citizen",
               "deadlines": "Campus Deadline: Sept. 11, 2026 (the university's internal date, not the foundation's)"},
     ambiguous="only the campus deadline is given; levels not stated on the page"),
 "s-us-simmons-intl-2": dict(fields={"nationality": "not_stated", "levels": ["bachelor"], "deadlines": [], "cycle_status": "not_stated",
     "components": {"tuition": "full", "accommodation": "covered"}, "funding_class": "fully_funded"},
     evidence={"funding_class": "This scholarship covers full tuition, mandatory fees (except health insurance), room & board for four years"}),
 "s-us-unt-international-2": dict(fields={"nationality": "not_stated", "levels": ["bachelor"], "deadlines": [], "cycle_status": "not_stated", "funding_class": "not_stated"},
     evidence={"funding_class": "$12,000 per year ... $10,000 per year ... $8,000 per year (what it pays for is not stated)"},
     ambiguous="cash tiers"),
 "s-us-wayne-intl-1": dict(fields={"nationality": "not_stated", "levels": ["bachelor"], "deadlines": [D("2027-04-01", "current")], "cycle_status": "open", "funding_class": "not_stated"},
     evidence={"deadlines": "The final deadline for scholarship consideration is April 1, 2027",
               "funding_class": "The Warrior Award ... is $6,500 per year for four consecutive years (what it pays for is not stated)"},
     ambiguous="the page does not say the cycle is open; a cash award"),
 "s-us-wofford-intl-3": dict(fields={"nationality": "not_stated", "levels": ["bachelor"], "deadlines": [], "cycle_status": "not_stated",
     "components": {"tuition": "full", "accommodation": "covered", "stipend": "covered"}, "funding_class": "fully_funded"},
     evidence={"funding_class": "The Richardson Family Scholarship provides a full, four-year scholarship ... Full tuition, fees, room and board. A monthly stipend for books and miscellaneous expenses."}),
 "s-us-pdx-international-2": dict(fields={"nationality": "not_stated", "levels": ["bachelor"], "deadlines": [], "cycle_status": "not_stated",
     "components": {"tuition": "partial"}, "funding_class": "partially_funded"},
     evidence={"nationality": "Eligibility: Nonresident of Oregon (residence, not nationality)",
               "funding_class": "Nonresidents receive up to $6,000 to cover tuition. Award Amount: up to $6,000 annually"}),
 "s-us-sjsu-international-1": dict(fields={"nationality": "not_stated", "levels": ["bachelor", "master"], "deadlines": [], "cycle_status": "not_stated", "funding_class": "not_stated"},
     evidence={"nationality": "provide financial support to our new and continuing, matriculated international students (status, not nationality)",
               "funding_class": "The number and amount of scholarships available are (not stated)"}),
 "s-r-us-asce-2": dict(fields={"nationality": "not_stated", "levels": ["bachelor"], "deadlines": [], "cycle_status": "not_stated", "funding_class": "not_stated"},
     evidence={"deadlines": "Submission Deadline: January 15 (no year)",
               "funding_class": "The scholarship may be used toward tuition expenses and other academic fees (no amount)"},
     ambiguous="a yearly deadline without a year"),
 "s-r-us-ala-4": dict(fields={"nationality": {"mode": "include", "countries": ["US", "CA"]}, "levels": ["master"], "deadlines": [D("2026-03-01")], "cycle_status": "closed", "funding_class": "not_stated"},
     evidence={"nationality": "be a citizen or permanent resident of the U.S. or Canada",
               "deadlines": "Next Deadline: March 1, 2026",
               "cycle_status": "Next Deadline: March 1, 2026 (past on 2026-10-20; the next cycle is not stated)",
               "funding_class": "Each scholar receives $5,000 from ALA (what it pays for is not stated)"},
     ambiguous="'Next Deadline' is in the past; a cash award"),
 "s-us-washington-intl-1": dict(fields={"nationality": {"mode": "include", "countries": ["US"]}, "levels": ["bachelor"], "deadlines": [], "cycle_status": "not_stated", "funding_class": "not_stated"},
     evidence={"nationality": "Eligibility: A citizen or national of the United States"}),
 "s-us-rollins-intl-2": dict(fields={"nationality": "not_stated", "levels": ["bachelor"], "deadlines": [D("2026-11-15", "current")], "cycle_status": "open", "funding_class": "not_stated"},
     evidence={"deadlines": "Apply for admission for fall 2027 as a first-year student by November 15, 2026",
               "funding_class": "Earn a $4,000 scholarship by visiting (what it pays for is not stated)"},
     ambiguous="the page does not say the cycle is open; a cash award"),
 "s-us-uc-international-3": dict(fields={"nationality": "not_stated", "levels": ["bachelor"], "deadlines": [], "cycle_status": "closed", "funding_class": "not_stated"},
     evidence={"cycle_status": "Applications for the 2026-2027 academic year are currently closed.",
               "funding_class": "NIS provides financial support to participating students through scholarships for undergraduate tuition and supplemental educational experiences (amount not stated)"},
     ambiguous="'scholarships for undergraduate tuition' without an extent"),
 "s-us-simmons-intl-3": dict(fields={"nationality": "not_stated", "levels": ["bachelor"], "deadlines": [], "cycle_status": "not_stated",
     "components": {"tuition": "full"}, "funding_class": "tuition_funded"},
     evidence={"nationality": "International students are not eligible for the Boston Scholarship (fee status)",
               "deadlines": "Deadline: January 10 (no year)",
               "funding_class": "The Boston Scholarship is a four-year, full-tuition scholarship."},
     ambiguous="'international students are not eligible' is a status rule; a yearly deadline without a year"),
})
AMB.update({"s-de-fazit-1": ["nationality", "cycle_status"], "s-ca-unb-international-2": ["funding_class"], "s-ca-wlu-international-1": ["funding_class"],
  "s-fi-fulbright-finland-3": ["funding_class"], "s-fi-fulbright-finland-4": ["funding_class"], "s-hu-pte-3": ["funding_class"], "s-no-fulbright-norway-3": ["levels", "funding_class"],
  "s-np-fulbright-nepal-1": ["nationality", "levels"], "s-nl-fulbright-2": ["nationality", "funding_class"], "s-th-ku-international-1": ["nationality"], "s-se-fulbright-sweden-1": ["levels"],
  "s-us-caltech-intl-1": ["nationality"], "s-us-case-international-3": ["deadlines", "levels"], "s-us-unt-international-2": ["funding_class"], "s-us-wayne-intl-1": ["cycle_status", "funding_class"],
  "s-r-us-asce-2": ["deadlines"], "s-r-us-ala-4": ["deadlines", "funding_class"], "s-us-rollins-intl-2": ["cycle_status", "funding_class"], "s-us-uc-international-3": ["funding_class"],
  "s-us-simmons-intl-3": ["nationality", "deadlines"]})

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
(M / "labels.json").write_text(json.dumps({"today": "2026-10-20", "version": "S-1",
    "note": "programme decisions labelled by hand from the official pages before any extractor ran on them; quotes per field",
    "pages": pages}, indent=1, ensure_ascii=False) + "\n")
print(len(pages), "labelled (all test);", sum(1 for p in urls["pages"] if p["split"] == "excluded"), "excluded")
