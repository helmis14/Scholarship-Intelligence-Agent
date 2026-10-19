"""Set E labels, written by hand from the page text (no extractor or model output was used).
Run: python3 tests/heldout_e/make_labels.py  -> tests/heldout_e/labels.json. Every `quote` is checked to be on the page."""
import json, sys
from pathlib import Path
REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from scholarship_agent.heldout import load_page

E = REPO / "tests" / "heldout_e"
IYT = ["AR", "AM", "AZ", "BD", "BR", "CL", "CO", "EG", "ET", "GH", "IN", "ID", "IR", "KZ", "MX", "MN", "PY", "PE", "CN",
       "TN", "TR", "UY", "VN"]
TIPP = ["KH", "LA", "MM", "VN", "AF", "BD", "DJ", "SV", "ER", "FJ", "GM", "GN", "ID", "IR", "JO", "KE", "LS", "MW", "MV",
        "MH", "FM", "NP", "PK", "PG", "PH", "WS", "SB", "LK", "SD", "TZ", "TL", "UG", "VU"]
ICELAND = ["AT", "BG", "CA", "CN", "HR", "CZ", "DK", "EE", "FO", "FI", "FR", "DE", "NL", "HU", "IT", "JP", "LV", "LT", "NO",
           "PL", "RU", "SK", "ES", "SE", "CH", "GB", "US"]
P = {
 "co-icetex-oea": {"kind": "opportunity", "language": "es", "fields": {
     "deadlines": [{"kind": "scholarship", "date": "2026-03-30", "status": "historical"}],
     "nationality": {"mode": "include", "countries": ["CO"]}, "levels": ["master", "phd"], "cycle": "2026",
     "award_amount": {"amount": [10000], "currency": "USD"}, "duration_months_max": 24,
     "provider": {"name": "Organización de Estados Americanos", "role": "funder"},
     "note": "ICETEX is the national liaison; the OAS awards. 'Hasta USD 10.000' is a cap, not a fixed amount; the "
             "money may be used for tuition, insurance, living or flights, so no separate component is labelled"},
     "quotes": ["Convocatoria abierta hasta el 30 de marzo de 2026 a las 5:00 p. m. para profesionales colombianos.",
                "El programa ofrece hasta USD 10.000 por año académico, por un periodo de entre uno y dos años"]},
 "it-iyt-esteri": {"kind": "opportunity", "language": "en", "fields": {
     "deadlines": [], "nationality": {"mode": "include", "countries": IYT}, "levels": ["master"],
     "provider": {"name": "Ministry of Foreign Affairs", "role": "provider"},
     "note": "programme home page; 'NEW APPLICATION OPENS 2027!' without a date; the call (it-iyt-unipi) requires "
             "permanent residence in these countries, this page says the edition 'is open to the following Countries'"},
     "quotes": ["NEW APPLICATION OPENS 2027!", "Invest Your Talent in Italy current edition is open to the following Countries"]},
 "it-iyt-unipi": {"kind": "opportunity", "language": "en", "fields": {
     "deadlines": [{"kind": "scholarship", "date": "2026-05-11", "status": "historical"}], "cycle": "2026/2027",
     "levels": ["master"], "nationality": "not_stated", "award_amount": {"amount": [10800], "currency": "EUR"},
     "tuition": "covered", "components": {"tuition": "covered"},
     "provider": {"name": "Italian Ministry of Foreign Affairs and International Cooperation", "role": "provider"},
     "note": "eligibility is permanent RESIDENCE in 23 countries, not citizenship (trap); age as a birth date "
             "('born on or after 1 January 2000'); tuition exempt except regional tax and stamp duty; renewal "
             "deadline 20 July 2026 is for current scholars, not applicants"},
     "quotes": ["Deadline: May 11, 2026 at 6:00 p.m. (Italian time)", "financial contribution of €10,800, paid in quarterly instalments (Art. 11.1 of the call)",
                "be permanently resident in one of the following countries"]},
 "ae-ku-postgrad": {"kind": "opportunity", "language": "en", "fields": {
     "deadlines": [], "levels": ["master", "phd"], "nationality": "not_stated",
     "components": {"tuition": "covered", "accommodation": "covered", "insurance": "covered", "travel": "covered",
                    "living_allowance": "covered"},
     "provider": {"name": "Khalifa University", "role": "provider"},
     "note": "several schemes on one page (master's, PhD, UAE-national combined, CSC-KU for Chinese nationals); the "
             "CSC-KU deadline 'February 10 of the same academic year' has no year; stipend only for PhD"},
     "quotes": ["The application deadline is February 10 of the same academic year.", "Monthly stipend of 9,200 AED provided by Khalifa University."]},
 "ae-ku-grts": {"kind": "opportunity", "language": "en", "fields": {
     "deadlines": [], "levels": ["master", "phd"],
     "stipend_by_level": {"phd": [20000, 4000, 2000], "master": []},
     "components": {"tuition": "covered", "accommodation": "covered", "insurance": "covered", "travel": "covered",
                    "living_allowance": "covered"},
     "provider": {"name": "Khalifa University", "role": "provider"},
     "note": "benefits differ by tier (tuition 25-100%, stipends 2,000-20,000 AED, master's students get no stipend in "
             "some tiers); one amount or 'full tuition' for the whole programme would collapse tiers"},
     "quotes": ["Basic monthly stipend of 20,000 AED.", "50% waiver of tuition fees."]},
 "pt-camoes-coop": {"kind": "guidance", "language": "pt", "fields": {}, "quotes": ["Bolsas da Cooperação"]},
 "no-lanekassen-abroad": {"kind": "opportunity", "language": "en", "fields": {
     "deadlines": [], "nationality": "not_stated",
     "components": {"living_allowance": "covered", "travel": "covered"},
     "provider": {"name": "Lånekassen", "role": "provider"},
     "note": "student support (grants and loans) for people entitled to Norwegian support; annual deadlines '15 "
             "November' and '15 March' have no year; tuition support is a loan up to a maximum, so tuition is not "
             "labelled as covered; additional grant 4,493 NOK per month for six countries"},
     "quotes": ["15 November for the entire year or just the autumn semester", "All students receive basic support and travel support"]},
 "no-studyinnorway-degree": {"kind": "guidance", "language": "en", "fields": {},
     "quotes": ["The Norwegian government offers no individual scholarships to degree students."]},
 "id-satubeasiswa-bpi": {"kind": "opportunity", "language": "id", "fields": {
     "deadlines": [{"kind": "scholarship", "date": "2026-06-30", "status": "historical"}], "openings": ["2026-05-01"],
     "levels": ["bachelor", "master", "phd"], "tuition": "full",
     "components": {"tuition": "full", "living_allowance": "covered"},
     "provider": {"name": "Kementerian Pendidikan Tinggi, Sains dan Teknologi", "role": "provider"},
     "note": "the page also lists other ministry scholarships with their own closing dates (31 Oktober 2026 KIP "
             "Kuliah, 31 Agustus 2026, 30 Juni 2026 ADik): only 30 Juni 2026 under 'Penutupan pendaftaran' is BPI's"},
     "quotes": ["Penutupan pendaftaran", "30 Juni 2026", "Biaya pendidikan penuh"]},
 "fi-edufi": {"kind": "opportunity", "language": "en", "fields": {
     "deadlines": [{"kind": "scholarship", "date": "2025-10-17", "status": "historical"}], "levels": ["phd"],
     "stipend": {"amount": [1900], "currency": "EUR", "period": "month"}, "duration_months_max": 12,
     "nationality": {"mode": "exclude", "countries": ["FI"]},
     "components": {"living_allowance": "covered", "accommodation": "not_covered", "travel": "not_covered",
                    "insurance": "not_covered"},
     "provider": {"name": "Finnish National Agency for Education", "role": "provider"},
     "note": "the scheme ends at the end of 2025; the applicant is a Finnish university department, not the student"},
     "quotes": ["New applications cannot be submitted after 17.10.2025.", "Size of grant: EUR 1,900 per month",
                "We will not pay separate accommodation costs or contribute to travel, visa, residence permit or insurance costs."]},
 "th-tica-tipp": {"kind": "opportunity", "language": "en", "fields": {
     "deadlines": [], "nationality": {"mode": "include", "countries": TIPP}, "levels": ["master"],
     "provider": {"name": "Thailand International Development Cooperation Agency", "role": "provider"},
     "note": "page last updated 2022 and describes the 2014 courses: outdated; 'fully-funded fellowships' without components"},
     "quotes": ["designed to provide fully-funded fellowships to allow outstanding students to study in Thailand"]},
 "qa-hbku": {"kind": "opportunity", "language": "en", "fields": {
     "deadlines": [], "levels": ["master", "phd"],
     "stipend_by_level": {"phd": [11000, 9000, 5000], "master": [9000, 7000, 4000]}, "duration_months_max": 45,
     "components": {"tuition": "covered", "living_allowance": "covered", "accommodation": "own_cost", "travel": "covered"},
     "provider": {"name": "Hamad Bin Khalifa University", "role": "provider"},
     "note": "stipends differ by level and by Qatari / international / local status; housing is paid by the student from the stipend"},
     "quotes": ["HBKU does not provide direct payment for student housing.", "International students will be provided with a single round-trip airfare during their"]},
 "is-arnastofnun": {"kind": "opportunity", "language": "en", "fields": {
     "deadlines": [], "nationality": {"mode": "include", "countries": ICELAND}, "levels": ["bachelor"],
     "max_age": "not_stated", "components": {"tuition": "covered", "living_allowance": "covered"},
     "provider": {"name": "Icelandic Ministry of Culture, Innovation and Higher Education", "role": "funder"},
     "note": "'Preference ... under 35 years of age' is a preference, not a limit (trap); 'no later than December 1' "
             "has no year; US students apply via Fulbright with another deadline"},
     "quotes": ["Preference will, as a rule, be given to candidates under 35 years of age.",
                "The scholarship covers registration fees at the University of Iceland and a monthly stipend intended to cover room and board for one person."]},
 "dk-studyindenmark": {"kind": "guidance", "language": "en", "fields": {}, "quotes": ["How can I get a scholarship?"]},
 "br-gcub-paec": {"kind": "opportunity", "language": "pt", "fields": {
     "deadlines": [], "levels": ["master", "phd"], "cycle": "2020",
     "components": {"tuition": "covered", "living_allowance": "covered", "accommodation": "covered", "travel": "not_covered"},
     "provider": {"name": "Grupo de Cooperação Internacional de Universidades Brasileiras", "role": "provider"},
     "note": "2020 edition, registration closed; open to the 34 OAS member states except Brazil (not listed by name)"},
     "quotes": ["As inscrições para a edição Programa Bolsas Brasil PAEC OEA-GCUB 2020 foram encerradas.",
                "Passagens aéreas de ida e volta ao país de origem;"]},
 "hk-edb-scholarship": {"kind": "guidance", "language": "en", "fields": {}, "quotes": ["HKSAR Government Scholarship Fund"]},
 "hk-studyinhk": {"kind": "guidance", "language": "en", "fields": {},
     "quotes": ["A number of scholarships and awards are offered by the HKSAR Government"]},
}
urls = {p["id"]: p["url"] for p in json.loads((E / "urls.json").read_text())["pages"]}
assert set(P) == set(urls), set(P) ^ set(urls)
for pid, lab in P.items():
    text = " ".join(load_page(pid, urls[pid], E).text.split())
    for q in lab.pop("quotes"):
        assert " ".join(q.split()) in text, (pid, q)
    lab["official"] = True
out = {"today": "2026-10-18", "note": "labelled by hand from the page text before any extraction or model run",
       "pages": P}
(E / "labels.json").write_text(json.dumps(out, indent=1, ensure_ascii=False))
print(len(P), "pages", sum(l["kind"] == "opportunity" for l in P.values()), "opportunity")
