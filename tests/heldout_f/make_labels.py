"""Set F labels, written by hand from the page text before any rules or model output was looked at for these pages.
Run: python3 tests/heldout_f/make_labels.py -> tests/heldout_f/labels.json. Every `quote` is checked to be on the page."""
import json, sys
from pathlib import Path
REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from scholarship_agent.heldout import load_page

F = REPO / "tests" / "heldout_f"
LATVIA = ["AZ", "BE", "BG", "HR", "CY", "EG", "FI", "FR", "GE", "IL", "IT", "KZ", "KG", "LT", "MX", "MD", "MN", "PE", "PL",
          "KR", "ES", "TJ", "CN", "TR", "TM", "UA", "UZ", "VN", "AT", "CZ", "EE", "DE", "HU", "IS", "ID", "JP", "SK", "CH", "US"]
ECOWAS = ["BJ", "BF", "CV", "CI", "GM", "GN", "GW", "LR", "ML", "NE", "NG", "SN", "SL", "TG"]
G = lambda q: {"kind": "guidance", "language": "en", "fields": {}, "quotes": [q]}  # noqa: E731
P = {
 "ec-senescyt-2026": {"kind": "opportunity", "language": "es", "fields": {
     "deadlines": [{"kind": "scholarship", "date": "2026-03-27", "status": "historical"}],
     "nationality": {"mode": "include", "countries": ["EC"]}, "levels": ["master", "phd"], "cycle": "2026",
     "provider": {"name": "OEA", "role": "funder"},
     "note": "OAS scholarships relayed by Ecuador's ministry (Globo Común, Minedec); the page writes only the acronym "
             "OEA; the OAS general rule 'ciudadano o residente permanente legal de un Estado Miembro' is wider than "
             "this national call for Ecuadorian citizens"},
     "quotes": ["POSTULA HASTA", "27 de marzo, 2026", "Ciudadanos/as ecuatorianos/as interesados en realizar estudios de posgrado"]},
 "gh-gsa-programmes": G("Scholarship programmes"),
 "gh-gsa-opportunities": G("Current scholarship opportunities and public notices."),
 "om-moheri-a": G("About Scholarships"), "om-moheri-b": G("Graduate studies and scholarships"),
 "si-cmepius-bilateral": G("Slovenian Government announces a limited number of scholarships for exchange of foreign students annualy."),
 "si-govsi-diaspora": G("Slovenians outside Slovenia"),
 "lv-viaa-state": {"kind": "opportunity", "language": "en", "fields": {
     "deadlines": [], "cycle": "2026/2027", "nationality": {"mode": "include", "countries": LATVIA},
     "provider": {"name": "Ministry of Education and Science of Latvia", "role": "provider"},
     "note": "the ministry delegates administration to the State Education Development Agency (VIAA): administrator, "
             "not payer; two groups of eligible citizens, one per line"},
     "quotes": ["Call for applications for the Latvian state scholarships 2026/2027",
                "I. Citizens from countries that have signed an Agreement* on co-operation in education and science"]},
 "lv-rsu-state": {"kind": "opportunity", "language": "en", "fields": {
     "deadlines": [], "levels": ["bachelor", "master", "phd"],
     "stipend_by_level": {"bachelor": [500], "master": [600], "phd": [700]}, "duration_months_max": 11,
     "components": {"travel": "not_covered", "insurance": "not_covered"},
     "provider": {"name": "State Education Development Agency of Latvia", "role": "provider"},
     "note": "university relay; the scholarship may be spent on tuition or housing (not separate benefits); the "
             "country list is on the VIAA page, not here"},
     "quotes": ["for PhD students – 700 EUR per month", "Travel expenses from a home country to and from Latvia are not covered by the Latvian scholarship."]},
 "mu-mass-2025": G("Mauritius Africa Scholarships Scheme 2025"),
 "kw-ku-scholarships": G("Department of Scholarships and Cultural Relations"),
 "eg-study-in-egypt": G("Study in Egypt"),
 "az-studyinaz": G("Intergovernmental Scholarship Program"),
 "az-heydar-aliyev-grant": {"kind": "opportunity", "language": "en", "fields": {
     "deadlines": [], "levels": ["bachelor", "master", "phd"],
     "components": {"tuition": "covered", "accommodation": "covered", "living_allowance": "covered", "travel": "covered"},
     "provider": {"name": "Ministry of Science and Education of the Republic of Azerbaijan", "role": "provider"},
     "note": "eligible countries are named as groups (OIC, Non-Aligned Movement, small island states, related "
             "nations), not as a list: nationality is not labelled; 'Medical assistance' is not labelled as insurance"},
     "quotes": ["Member countries of the Islamic Cooperation Organisation", "Daily sustenance"]},
 "az-mfa-hanoi-grant": {"kind": "opportunity", "language": "en", "fields": {
     "deadlines": [], "cycle": "2026/2027", "levels": ["bachelor", "master", "phd"],
     "provider": {"name": "Ministry of Science and Education of the Republic of Azerbaijan", "role": "provider"},
     "note": "embassy news item; announced jointly with the Ministry of Foreign Affairs; established by presidential decree"},
     "quotes": ["announce the “Heydar Aliyev - International Education Grant Program” for 2026-2027 academic year."]},
 "gh-gsa-pwasi-2026": {"kind": "opportunity", "language": "en", "fields": {
     "deadlines": [], "institutional_deadlines": [{"date": "2026-08-30", "status": "historical"}],
     "nationality": {"mode": "include", "countries": ECOWAS}, "levels": ["bachelor", "master", "phd"],
     "cycle": "2026/2027", "duration_months_max": 48,
     "provider": {"name": "Government of Republic of Ghana", "role": "provider"},
     "note": "applicant deadline 'Not specified'; 30 August 2026 is for nominating agencies; ECOWAS citizens other "
             "than Ghana, countries taken from the quota table; GSA administers"},
     "quotes": ["Be citizens of ECOWAS member states other than Ghana", "latest by 30Th August, 2026"]},
 "gh-gsa-algeria-2026": {"kind": "opportunity", "language": "en", "fields": {
     "deadlines": [{"kind": "scholarship", "date": "2026-09-21", "status": "historical"}],
     "nationality": {"mode": "include", "countries": ["GH"]}, "max_age": 23, "levels": ["bachelor", "master"],
     "cycle": "2026/2027",
     "note": "who pays is not stated (title: joint Algeria/Ghana government awards; GSA only receives applications): "
             "no provider label; Ghanaian citizens resident in Ghana"},
     "quotes": ["a) Be Ghanaian citizens resident in Ghana", "d) Not be more than twenty-three (23) years of age.", "September 21, 2026"]},
 "ph-ched-cmsp": {"kind": "opportunity", "language": "en", "fields": {
     "deadlines": [], "cycle": "2024/2025", "nationality": {"mode": "include", "countries": ["PH"]}, "levels": ["bachelor"],
     "award_amount": {"amount": [120000], "currency": "PHP"},
     "provider": {"name": "Commission on Higher Education", "role": "provider"},
     "note": "'Up to ₱120,000 per year' is a cap; the page also says 'Open' while showing AY 2024-2025"},
     "quotes": ["Up to ₱120,000 per year", "Must be a Filipino citizen"]},
}
urls = {p["id"]: p["url"] for p in json.loads((F / "urls.json").read_text())["pages"]}
assert set(P) == set(urls), set(P) ^ set(urls)
for pid, lab in P.items():
    text = " ".join(load_page(pid, urls[pid], F).text.split())
    for q in lab.pop("quotes"):
        assert " ".join(q.split()) in text, (pid, q)
    lab["official"] = True
(F / "labels.json").write_text(json.dumps({"today": "2026-10-18", "note": "labelled by hand from the page text",
                                           "pages": P}, indent=1, ensure_ascii=False))
print(len(P), "pages", sum(l["kind"] == "opportunity" for l in P.values()), "opportunity")
