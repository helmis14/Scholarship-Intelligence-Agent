"""Set R labels (round 35), written by hand from the official pages in pages/ before any extractor ran on set R.

Set R is the fresh test set for the rules as they stood after round 35 (timeline deadlines, host-country nationality,
funding sentences). It is small: 14 programmes. 239 pages were fetched on 2026-10-20 from hosts no earlier set used
(ministries and funding agencies, foundations, companies, professional associations and universities in about 40
countries), but almost all of them were lists, home pages, news, portals or pages of several awards, and are excluded
with the reason recorded. The code was frozen (the staged working tree after round 35) before any set-R page was fetched,
and no set-R page was read before the freeze. Labels follow the reading of sets L to Q. Close calls are recorded per
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
P.update({
 "ke-hel": dict(fields={"nationality": {"mode": "include", "countries": ["KE"]}, "levels": ["master", "phd"], "deadlines": [D("2026-08-31")], "cycle_status": "closed",
     "components": {"tuition": "partial"}, "funding_class": "partially_funded"},
     evidence={"nationality": "invites applications for the 2026-2027 Postgraduate partial scholarships from Kenyan students enrolled for master's and PhD programs",
               "deadlines": "The Application window Closes On 31st August 2026.",
               "cycle_status": "The Application window Closes On 31st August 2026.",
               "funding_class": "PARTIAL POSTGRADUATE SCHOLARSHIPS ... The value of the scholarship award is Kshs.200,000 and Kshs.450,000 for Master's and PhD programs respectively"}),
 "gh-mtn": dict(fields={"nationality": {"mode": "include", "countries": ["GH"]}, "levels": ["bachelor"], "deadlines": [], "cycle_status": "not_stated",
     "components": {"tuition": "full", "accommodation": "covered"}, "funding_class": "tuition_funded"},
     evidence={"nationality": "Must be a Ghanaian citizen.",
               "funding_class": "Scholarship package: Tuition and accommodation fees; A laptop computer; Stipend for reading materials"},
     ambiguous="'tuition and accommodation fees' without 'full'; a reading-materials stipend is not a living stipend"),
 "r-us-national-science-foundation-grfp": dict(fields={"nationality": {"mode": "include", "countries": ["US"]}, "levels": ["master", "phd"], "deadlines": [],
     "cycle_status": "not_stated", "funding_class": "not_stated"},
     evidence={"nationality": "Must, at the time of submission, be a U.S. citizen, national, or a permanent resident (\"green-card\" holder)."}),
 "r-us-nsf-reu": dict(fields={"nationality": {"mode": "include", "countries": ["US"]}, "levels": ["bachelor"], "deadlines": [], "cycle_status": "not_stated",
     "components": {"stipend": "covered"}, "funding_class": "stipend_only"},
     evidence={"nationality": "Undergraduates ... who are U.S. citizens, permanent residents or U.S. nationals are eligible to apply.",
               "funding_class": "REU participants receive competitive stipends and in many cases assistance with housing, meals and travel."},
     ambiguous="a research placement, not a degree; stipend amount and extras vary by site"),
 "r-us-doe-scgsr": dict(fields={"nationality": {"mode": "include", "countries": ["US"]}, "levels": ["phd"], "deadlines": [], "cycle_status": "not_stated", "funding_class": "not_stated"},
     evidence={"nationality": "Applicants must meet the following eligibility requirements: Minimum Age and U.S. Citizenship or Lawful Permanent Resident (LPR)"},
     ambiguous="the requirement is a heading with its text on another page"),
 "r-esa-research-fellow": dict(fields={"nationality": {"mode": "include", "countries": ["AT", "BE", "CZ", "DK", "EE", "FI", "FR", "DE", "GR", "HU", "IE", "IT", "LU", "NL", "NO", "PL", "PT", "RO", "SI", "ES", "SE", "CH", "GB", "LV", "LT", "SK", "CA"]},
     "levels": ["postdoc"], "deadlines": [D("2026-09-21")], "openings": ["2026-08-24"], "cycle_status": "closed", "funding_class": "not_stated"},
     evidence={"nationality": "Applications are only considered from nationals of one of the following States: Austria, Belgium, Czechia, Denmark, Estonia, Finland, France, Germany, Greece, Hungary, Ireland, Italy, Luxembourg, the Netherlands, Norway, Poland, Portugal, Romania, Slovenia, Spain, Sweden, Switzerland, and the United Kingdom. Nationals from Latvia, Lithuania and Slovakia as Associate Member States, or Canada as a Cooperating State ...",
               "deadlines": "The 2026 call opened on 24 August 2026 with a deadline on 21 September 2026.",
               "cycle_status": "The 2026 call opened on 24 August 2026 with a deadline on 21 September 2026."},
     ambiguous="the associate and cooperating states sentence is cut off in the extracted text"),
 "uk-clarendon": dict(fields={"nationality": {"mode": "any", "countries": []}, "levels": ["master", "phd"], "deadlines": [], "cycle_status": "not_stated",
     "components": {"tuition": "full", "living_allowance": "covered"}, "funding_class": "fully_funded"},
     evidence={"nationality": "open to new graduate students with no restrictions on nationality, ordinary residence or field of study.",
               "funding_class": "Full funding for graduate students ... Value: Course fees; Maintenance costs"},
     ambiguous="the January application deadline has no year on this page"),
 "r-us-asme": dict(fields={"nationality": "not_stated", "levels": ["bachelor", "master"], "deadlines": [], "cycle_status": "closed", "funding_class": "not_stated"},
     evidence={"cycle_status": "Application is CLOSED for academic school year 2026-27"}),
})
AMB.update({"gh-mtn": ["funding_class"], "r-us-nsf-reu": ["levels", "funding_class"], "r-us-doe-scgsr": ["nationality"], "r-esa-research-fellow": ["nationality"], "uk-clarendon": ["deadlines"]})
X.update({"af-ministry": "ministry home page", "au-menzies": "alumni page", "bd-ugc": "empty page", "by-president-fund": "scholarship list in Russian, not reviewed", "cm-ministry": "several scholarships",
          "cn-confucius": "empty page", "cv-ministry": "news", "dz-ministry": "several offers", "ee-archimedes": "list of programmes", "eg-misr-elkheir": "app page", "eg-sawiris": "near-empty page",
          "gh-getfund2": "empty page", "hu-tempus": "list", "id-bank-mandiri": "employee benefits", "id-kemenristek": "empty page", "in-csir": "PDF not reviewed", "in-icmr": "several fellowships",
          "in-nsfdc": "loan schemes", "jp-kumon": "unrelated page", "jp-mitsui": "page in Japanese not reviewed", "jp-toyota-foundation": "grants for projects", "ke-kenya-scholars": "empty page",
          "kr-posco": "corporate home page", "lk-ugc": "PDF not reviewed", "lt-lietuvos-mokslo-taryba": "PDF not reviewed", "lv-latvijas-banka": "PDF not reviewed", "mg-ministry": "several scholarships",
          "mk-ministry": "call in Macedonian, not reviewed", "mm-ministry": "page in Burmese", "mo-macau-scholarship": "near-empty page", "mv-ministry": "ministry home page", "mz-ministry": "ministry home page",
          "na-ministry": "ministry page", "ng-mtn2": "submission closed form", "no-sirius": "programme for institutions", "np-ugc": "page in Nepali", "pk-pm-laptop": "unrelated PDF",
          "ps-ministry": "ministry page in Arabic", "r-african-leadership": "entrepreneurship programme", "r-aliko-dangote": "news", "r-baden-wurttemberg": "several scholarship lines",
          "r-be-belspo": "PDF not reviewed", "r-carnegie-corp": "2005 news", "r-cern-fellowship": "member-state list is on another page", "r-ch-gebert-ruf": "project funding", "r-ch-hasler": "completed programmes",
          "r-ch-leenaards": "2023 news", "r-ch-swissuniv": "overview", "r-deutsche-welle": "fees overview", "r-erc-starting": "grant for hosts", "r-fes-intl": "list", "r-fondation-airbus": "news",
          "r-fondation-edf": "foundation home page", "r-gates-foundation": "statement", "r-giz": "trainee programmes list", "r-hewlett": "grant list", "r-kfw": "PDF not reviewed", "r-lindau": "meeting funding",
          "r-macarthur": "fellows list", "r-mellon": "list", "r-mo-ibrahim": "PDF not reviewed", "r-nl-erasmus-trustfonds": "near-empty page", "r-nrw": "PDF not reviewed", "r-one-young-world": "list",
          "r-tony-elumelu": "near-empty page", "r-uk-bhf": "programme for universities", "r-uk-cruk": "fellowship for hosts", "r-uk-wolfson-college": "college fees page", "r-us-aaja": "several scholarships",
          "r-us-acm": "near-empty page", "r-us-aia": "several scholarships", "r-us-aicpa": "several scholarships", "r-us-ala": "several scholarships", "r-us-asa": "several awards", "r-us-asce": "several scholarships",
          "r-us-ashoka": "fellowship for entrepreneurs", "r-us-aspen": "list", "r-us-bush-institute": "leadership programme", "r-us-clinton": "foundation home page", "r-us-ford-predoc": "unrelated report",
          "r-us-geological-society": "several grants", "r-us-ieee": "list", "r-us-nahj": "several scholarships", "r-us-nsta": "awards", "r-us-rwjf": "fellowship for professionals", "r-us-sme": "registration form",
          "r-us-tuition-exchange": "exchange scheme", "r-wipo": "fellowship overview", "r-wto-internship": "news", "ru-vladimir-potanin": "list of participating universities", "rw-ministry": "ministry page",
          "sa-kfupm": "student page", "sa-ksu": "near-empty page", "sa-moe": "ministry home page", "sa-sbs": "ministry portal", "se-sida": "training programmes list", "sg-astar": "graduate academy page",
          "sg-mfa": "embassy page", "sg-moe": "list", "sk-slsp": "near-empty page", "sy-ministry": "PDF not reviewed", "tr-yok": "list", "ug-ministry": "list", "uk-mrc": "unrelated page",
          "uk-nerc": "unrelated page", "ws-ministry": "forms notice", "za-dsi": "near-empty page", "za-sasol2": "job posting", "za-standard-bank": "job posting", "za-transnet": "job posting",
          "za-vodacom": "story", "zm-ministry": "FAQ", "zw-ministry": "list"})
P.update({
 "s-ubc-igs": dict(fields={"nationality": "not_stated", "levels": ["bachelor"], "deadlines": [D("2026-11-15", "current")], "cycle_status": "open",
     "funding_class": "partially_funded"},
     evidence={"nationality": "International Major Entrance Scholarships (IMES) are awarded to exceptional international students entering their undergraduate studies at UBC (fee status)",
               "deadlines": "Applications for the 2027 are now open, and will close on November 15th, 2026.",
               "cycle_status": "Applications for the 2027 are now open, and will close on November 15th, 2026.",
               "funding_class": "Awards ranging in value up to the full cost of the student's academic program and living costs ... Awards ranging in value up to $25,000"},
     ambiguous="'up to the full cost' is a cap, not a promise; several awards (IMES, Vantage One awards) on one page"),
 "s-pku-scholarship": dict(fields={"nationality": {"mode": "exclude", "countries": ["CN"]}, "levels": ["bachelor", "master", "phd"], "deadlines": [], "cycle_status": "not_stated",
     "components": {"tuition": "full", "living_allowance": "covered", "insurance": "covered"}, "funding_class": "fully_funded"},
     evidence={"nationality": "Applicants must be non-Chinese citizens of sound health",
               "funding_class": "Full scholarship covers tuition, living stipend (including accommodation subsidy) and Comprehensive Medical Insurance for International Students"},
     ambiguous="full and partial scholarship forms on one page; already-admitted students only"),
})
AMB.update({"s-ubc-igs": ["funding_class"], "s-pku-scholarship": ["funding_class"]})
X.update({"s-aku-scholarship": "financial assistance overview", "s-aun-scholarship": "news", "s-bocconi-scholarship": "staff page", "s-boun-scholarship": "institute page", "s-bracu-scholarship": "several scholarships",
          "s-buet-scholarship": "department notice", "s-ceu-scholarship": "several scholarships", "s-charles-scholarship": "faculty page, several", "s-cuhk-scholarship": "several scholarships",
          "s-edinburgh-global": "several scholarships", "s-hkust-scholarship": "fees page", "s-huji-scholarship": "department page", "s-iisc-scholarship": "regulations", "s-iitb-scholarship": "near-empty page",
          "s-jnu-scholarship": "several scholarships", "s-keio-scholarship": "news", "s-kuleuven-scholarship": "list", "s-lums-scholarship": "degree page", "s-mahidol-scholarship": "list",
          "s-oxford-clarendon": "faculty page", "s-sabanci-scholarship": "several levels on one page", "s-snu-gks": "near-empty page", "s-sun-scholarship": "department page", "s-todai-scholarship": "department page",
          "s-uc-scholarship": "news", "s-uct-scholarship": "faculty page", "s-ufrj-scholarship": "news", "s-ug-scholarship": "2017 news", "s-ugm-scholarship": "list", "s-ui-scholarship": "faculty page",
          "s-ukm-scholarship": "PDF not reviewed", "s-ukzn-scholarship": "portal", "s-ulb-scholarship": "list", "s-um-scholarship": "research assistantship scheme", "s-unam-scholarship": "mobility page",
          "s-unsw-scholarship": "near-empty page", "s-uoa-scholarship": "near-empty page", "s-uom-scholarship": "notices", "s-upm-scholarship": "list", "s-uq-scholarship": "resources page",
          "s-usp-scholarship": "list", "s-weizmann-scholarship": "visiting students programme", "s-york-global": "several scholarships", "s-zju-scholarship": "fees and several waivers"})
P.update({
 "t-american-legion": dict(fields={"nationality": "not_stated", "levels": ["bachelor", "master", "phd"], "deadlines": [], "cycle_status": "not_stated", "funding_class": "not_stated"},
     evidence={"nationality": "Who Can Apply? Children, adopted child or stepchild of U.S. military members who died while on active duty on or after Sept. 11, 2001 (parentage, not nationality)",
               "funding_class": "Each needs-based scholarship provides up to $20,000 for children of the fallen, and up to $5,000 for children of the disabled (what it pays for is not stated)"},
     ambiguous="levels are 'undergraduate or post-graduate college'; need-based cash tiers"),
})
AMB.update({"t-american-legion": ["levels", "funding_class"]})
X.update({"t-agbu": "several scholarships", "t-algeria": "several offers", "t-argentina-conicet": "list of calls", "t-asean": "near-empty page", "t-burger-king": "unrelated page",
          "t-czech-government": "unrelated page", "t-ethiopia": "boarding schools", "t-fulbright-us": "news", "t-gates-millennium": "empty page", "t-indian-american": "unrelated page",
          "t-itec": "course list", "t-jacl": "over 30 awards", "t-kenya-helb": "duplicate of ke-hel", "t-knight-hennessy": "application banner", "t-knights-columbus": "members only, several",
          "t-mozambique": "PDF not reviewed", "t-namibia": "list of scholarships", "t-nffa": "news", "t-niaf": "nearly 200 scholarships", "t-regeneron": "news", "t-russian-government": "list of universities",
          "t-rwanda": "ministry page", "t-saudi-moe": "ministry page", "t-sikh": "unrelated page", "t-singa": "several", "t-uae-moe": "job posting", "t-uganda": "PDF not reviewed",
          "t-ukrainian-national": "news", "t-unico": "several scholarships", "t-vfw-voice": "several", "t-zimbabwe": "ministry page"})
P.update({
 "u-id-bca": dict(fields={"nationality": {"mode": "include", "countries": ["ID"]}, "levels": ["bachelor"], "deadlines": [D("2026-09-30")], "openings": ["2026-08-03"],
     "cycle_status": "closed", "funding_class": "not_stated"},
     evidence={"nationality": "Indonesian citizen and unmarried.",
               "deadlines": "August 3, 2026 - September 30, 2026 (registration period in the timeline)",
               "cycle_status": "August 3, 2026 - September 30, 2026 (registration period; past on 2026-10-20)",
               "funding_class": "Bakti BCA Scholarship recipients receive financial support to aid their education (amount and use not stated)"},
     ambiguous="the timeline lists several steps; the page also holds a 2024 benefit period"),
 "u-ph-mapua": dict(fields={"nationality": "not_stated", "levels": ["bachelor"], "deadlines": [], "cycle_status": "not_stated",
     "components": {"tuition": "partial", "stipend": "covered"}, "funding_class": "partially_funded"},
     evidence={"nationality": "Must be a graduate of any recognized Public Science High School in the Philippines (school, not nationality)",
               "funding_class": "Eligible beneficiaries will receive: 40% tuition fee discount; Annual stipend of PhP 40,000.00"}),
 "u-tw-tsmc": dict(fields={"nationality": "not_stated", "levels": ["bachelor"], "deadlines": [D("2023-09-30")], "cycle_status": "closed",
     "components": {"stipend": "covered", "tuition": "partial"}, "funding_class": "partially_funded"},
     evidence={"nationality": "Undergraduate students from the universities in Vietnam, Indonesia, Singapore & Malaysia (universities, not nationality)",
               "deadlines": "Application Deadline: 9/30/2023",
               "funding_class": "NT15,000 per month (up to two years) provided by TSMC; Tuition reduction by NYCU"},
     ambiguous="a 2024 intake page; the 'universities in four countries' wording"),
})
AMB.update({"u-id-bca": ["deadlines", "cycle_status"], "u-tw-tsmc": ["nationality"]})
X.update({"u-bd-brac": "news", "u-id-bni": "2022 programme page", "u-id-djarum": "near-empty page", "u-id-gudang-garam": "news", "u-id-indofood": "corporate page", "u-id-kalbe": "home page",
          "u-id-pertamina": "news", "u-id-telkom": "news", "u-in-azim-premji": "several scholarships", "u-in-google": "empty page", "u-in-hdfc": "near-empty page", "u-in-ngo": "portal listing",
          "u-in-reliance": "undergraduate and postgraduate schemes on one page", "u-in-wipro": "news", "u-jp-hyogo": "PDF not reviewed", "u-jp-japan-foundation": "list of awardees", "u-jp-kdi": "unrelated page",
          "u-jp-keidanren": "unreadable encoding", "u-jp-kikkoman": "recipe site", "u-jp-kyoto-city": "unrelated page", "u-jp-nissan": "sustainability page", "u-jp-panasonic": "page in Japanese not reviewed",
          "u-jp-soka": "several scholarships", "u-kr-gs-caltex": "home page", "u-kr-hana": "home page", "u-kr-kf": "application portal", "u-kr-kookmin": "home page", "u-kr-ksf": "unrelated foundation",
          "u-lk-sri-lanka": "school-level scheme", "u-my-petronas": "news", "u-ph-gokongwei": "foundation overview", "u-ph-sm": "login page", "u-th-ptt": "financial statements", "u-th-scg": "empty page",
          "u-tw-foxconn": "PDF not reviewed", "u-tw-moe-hrd": "unrelated page"})
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
(M / "labels.json").write_text(json.dumps({"today": "2026-10-20", "version": "R-1",
    "note": "programme decisions labelled by hand from the official pages before any extractor ran on them; quotes per field",
    "pages": pages}, indent=1, ensure_ascii=False) + "\n")
print(len(pages), "labelled (all test);", sum(1 for p in urls["pages"] if p["split"] == "excluded"), "excluded")
