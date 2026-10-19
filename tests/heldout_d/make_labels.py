"""Writes tests/heldout_d/labels.json: set D, a held-out set of pages from providers and sites not in sets A, B or C.

Labels were written by reading each page snapshot (fetched 2026-10-17). No extractor or model output was used.
Every quote is checked to be verbatim (whitespace-folded) on its page. All pages are test pages: nothing in set D
is used to develop the agent.
"""
import json, sys
from pathlib import Path
REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from scholarship_agent.heldout import load_page

ROOT = REPO / "tests" / "heldout_d"
urls = {p["id"]: p for p in json.loads((ROOT / "urls.json").read_text())["pages"]}


from scholarship_agent.countries import COUNTRIES
# "a citizen of an African country": the 54 African states (territories such as Réunion, Mayotte, Western Sahara out)
AFRICA = sorted(c for c, (_, r) in COUNTRIES.items() if r == "Africa" and c not in ("EH", "RE", "YT"))
assert len(AFRICA) == 54


def C(field, value, quote, accept, why):
    return {"field": field, "value": value, "quote": quote, "accept": accept, "why": why}


L = {}
# ---------------------------------------------------------------- Switzerland (federal, relay)
L["ch-sges-main"] = {"kind": "opportunity", "official": True, "language": "en", "fields": {
    "deadlines": [], "openings": ["2026-08-20"], "max_age": 35, "levels": ["phd", "master"], "cycle": "2027/2028",
    "stipend": {"amount": [2450], "currency": "CHF", "period": "month"},
    "provider": {"name": "Swiss Confederation", "role": "funder"},
    "note": "country deadlines published elsewhere; art scholarships (master) for limited countries"}, "claims": [
    C("opening_date", "2026-08-20", "Applications are open starting August 20, 2026.", True, "stated"),
    C("max_age", 35, "(max. age: 35 / funding: CHF 2450.--/month)", True, "stated"),
    C("stipend_amount", 2450, "(max. age: 35 / funding: CHF 2450.--/month)", True, "stated"),
    C("provider_name", "Swiss Confederation", "Each year the Swiss Confederation awards Government Excellence Scholarships to encourage international exchange and research cooperation between Switzerland and over 180 other countries.", True, "the Confederation awards them"),
    C("provider_name", "Federal Commission for Scholarships for Foreign Students", "Recipients are selected by the awarding body, the Federal Commission for Scholarships for Foreign Students (FCS aka ESKAS).", False, "selects recipients; the Confederation funds"),
    C("academic_cycle", "2028/2029", "Scholarships for the 2028–2029 academic year will be advertised online from August 2027.", False, "a future cycle, not this call"),
    C("deadline_scholarship", "2026-08-31", "Information on application deadlines and scholarship available by country of origin will be published here in August 2026.", False, "no deadline stated")]}
L["ch-sges-glance"] = {"kind": "opportunity", "official": True, "language": "en", "fields": {
    "deadlines": [], "levels": ["phd", "master"], "stipend": {"amount": [2450], "currency": "CHF", "period": "month"},
    "duration_months_max": 36, "tuition": "not_covered",
    "components": {"tuition": "not_covered", "insurance": "covered", "travel": "covered", "living_allowance": "covered"},
    "note": "three scholarship types: research fellowship (12 months max), PhD (up to 36), art master (up to 21); "
            "insurance and return flight only for non-EU/EFTA holders; age as 'date of birth after 31 December 1991'"}, "claims": [
    C("funding_duration_months", 36, "12 months, renewable twice for up to 36 months (subject to academic progress during the first 12 months).", True, "PhD scholarship"),
    C("max_age", 35, "Date of birth after 31 December 1991.", False, "the age is stated as a birth date; 35 is not in the quote"),
    C("tuition_coverage", "full", "The Federal Excellence Scholarship does not cover tuition or semester fees.", False, "tuition not covered"),
    C("tuition_coverage", "none", "The Federal Excellence Scholarship does not cover tuition or semester fees.", True, "stated"),
    C("covers_health_insurance", True, "Health insurance: FCS covers the premiums for compulsory health insurance for scholarship holders from non-EU/EFTA countries.", True, "for non-EU/EFTA holders"),
    C("covers_living_allowance", True, "CHF 2,450 per month to cover basic living expenses for one person", True, "stated"),
    C("study_levels", ["phd"], "This scholarship is intended to support selected applicants in pursuing a PhD at a Swiss university or recognised research institute.", True, "PhD scholarships"),
    C("study_levels", ["master"], "Highly qualified researchers who have completed a master’s degree in any academic field", False, "a completed master's is the prerequisite of the PhD scholarship")]}
L["za-dhet-switzerland"] = {"kind": "opportunity", "official": True, "language": "en", "fields": {
    "deadlines": [{"kind": "scholarship", "date": "2026-11-30", "status": "current", "scope": "country", "applies_to": ["ZA"]}],
    "nationality": {"mode": "include", "countries": ["ZA"]}, "levels": ["phd"], "duration_months_max": 36,
    "provider": {"name": "Swiss Confederation", "role": "funder"},
    "note": "South African government relay of the Swiss scheme; deadline for South African applicants"}, "claims": [
    C("deadline_scholarship", "2026-11-30", "Application Deadline 30 November 2026 at 11:59 PM (Swiss local time)", True, "country-specific deadline (South Africa)"),
    C("eligible_nationalities", ["South Africa"], "Be South African citizens;", True, "for this country call"),
    C("provider_name", "Swiss Confederation", "The scholarships are offered by the Swiss Confederation to promote international exchange and research cooperation between Switzerland and countries around the world.", True, "offered by"),
    C("provider_name", "Department of Higher Education and Training", "Please note that this opportunity is not offered by the Department of Higher Education and Training.", False, "explicitly not the provider"),
    C("max_age", 35, "Have been born after 31 December 1991;", False, "birth date, not a number")]}
# ---------------------------------------------------------------- Australia Awards (Indonesia)
L["au-awards-id-en"] = {"kind": "opportunity", "official": True, "language": "en", "fields": {
    "max_age": 42, "language": {"IELTS": [6.5], "TOEFL_IBT": [84]}, "nationality": "not_stated",
    "note": "LPDP-Australia Awards (co-funded with LPDP, which is in set A as a provider)"}, "claims": [
    C("max_age", 42, "Must not exceed the age of 42 years by the 31st of December in the year of application.", True, "stated"),
    C("ielts_min", 6.5, "Meet the minimum English language requirement of IELTS 6.5 (with no band less than 6.0), equivalent to TOEFL iBT 84 (with a minimum of 21 in all sub-tests), and PTE Academic 58 (with no communicative skill score less than 50).", True, "overall"),
    C("ielts_min", 6.0, "Meet the minimum English language requirement of IELTS 6.5 (with no band less than 6.0), equivalent to TOEFL iBT 84 (with a minimum of 21 in all sub-tests), and PTE Academic 58 (with no communicative skill score less than 50).", False, "6.0 is the band minimum, not the overall"),
    C("toefl_min", 84, "Meet the minimum English language requirement of IELTS 6.5 (with no band less than 6.0), equivalent to TOEFL iBT 84 (with a minimum of 21 in all sub-tests), and PTE Academic 58 (with no communicative skill score less than 50).", True, "stated"),
    C("min_gpa", 3.0, "Have a minimum GPA of 3.0 (on a 4.0 scale) from their relevant undergraduate qualification.", True, "stated")]}
L["au-awards-id-id"] = {"kind": "opportunity", "official": True, "language": "id", "fields": {
    "nationality": {"mode": "include", "countries": ["ID"]}, "residency": ["ID"], "levels": ["phd", "master"],
    "note": "GPA and English minimums differ by level AND applicant group (government / equity target group / non-target)"}, "claims": [
    C("eligible_nationalities", ["Indonesia"], "merupakan warga negara Indonesia dan tinggal di Indonesia serta mengajukan permohonan beasiswa dari Indonesia.", True, "citizen"),
    C("residency_required", ["Indonesia"], "merupakan warga negara Indonesia dan tinggal di Indonesia serta mengajukan permohonan beasiswa dari Indonesia.", True, "must live in Indonesia"),
    C("ielts_min", 6.5, "IELTS 6.5", False, "one cell of a table: applies only to PhD non-target applicants"),
    C("study_levels", ["phd", "master"], "Persyaratan Umum untuk Beasiswa PhD dan Master", True, "both levels")]}
# ---------------------------------------------------------------- UK
L["uk-gates-timeline"] = {"kind": "opportunity", "official": True, "language": "en", "fields": {
    "deadlines": [{"kind": "scholarship", "date": "2026-10-14", "status": "current", "scope": "applicant_group",
                   "applies_to": ["US citizens resident in the USA"]},
                  {"kind": "scholarship", "date": "2026-12-08", "status": "current", "scope": "programme"},
                  {"kind": "scholarship", "date": "2027-01-06", "status": "current", "scope": "programme"}],
    "openings": ["2026-09-11"], "cycle": "2027/2028"}, "claims": [
    C("deadline_scholarship", "2026-10-14", "Wednesday 14th October 2026 (Full application must be submitted by 11:59pm UK time on the date given)", True, "US-resident round"),
    C("deadline_scholarship", "2027-01-06", "Dependent on your course – either Tuesday 8th December 2026 or Wednesday 6th January 2027 (see Course Directory).", True, "course-dependent round"),
    C("deadline_scholarship", "2026-12-14", "by 11:59pm UK time on Monday 14th December 2026", False, "notification date, not a deadline"),
    C("opening_date", "2026-09-11", "Applications open 11th September 2026", True, "stated"),
    C("academic_cycle", "2027/2028", "Applications for entry in the academic year 2027/8 are now open.", True, "2027/8")]}
# ---------------------------------------------------------------- South Africa
L["za-mandela-rhodes"] = {"kind": "opportunity", "official": True, "language": "en", "fields": {
    "deadlines": [{"kind": "scholarship", "date": "2027-04-14", "status": "current"}], "openings": ["2027-03-09"],
    "min_age": 19, "max_age": 29, "levels": ["master"], "duration_months_max": 24,
    "nationality": {"mode": "include", "countries": AFRICA},
    "components": {"tuition": "covered", "accommodation": "covered", "insurance": "covered", "travel": "covered",
                   "living_allowance": "covered"},
    "provider": {"name": "The Mandela Rhodes Foundation", "role": "funder"},
    "note": "Honours (1 year) or Masters (up to 2 years); applications for 2027 closed, 2028 intake opens 9 March 2027"}, "claims": [
    C("deadline_scholarship", "2027-04-14", "April: Applications close by the end of Wednesday, 14 April 2027 23:59 GMT+2.", True, "stated"),
    C("deadline_scholarship", "2027-04-14", "The deadline is 14 April, by which time all application documentation needs to have been uploaded.", False, "no year in this quote"),
    C("opening_date", "2027-03-09", "March: Applications open on Tuesday, 9 March 2027.", True, "stated"),
    C("max_age", 29, "If you are between the ages of 19 and 29 in the year of applying, you are eligible.", True, "stated"),
    C("min_age", 19, "If you are between the ages of 19 and 29 in the year of applying, you are eligible.", True, "stated"),
    C("study_levels", ["phd"], "No. The Mandela Rhodes Scholarship is only for postgraduate study (Honours and Masters).", False, "no PhD"),
    C("covers_accommodation", True, "Accommodation and meal allowances as set by the MRF", True, "a separate accommodation allowance"),
    C("covers_travel", True, "Economy-class flights for international scholars from their home countries to their institutions at the start and end of their studies", True, "for international scholars"),
    C("provider_name", "The Mandela Rhodes Foundation", "The Mandela Rhodes Foundation does not pay for your application fees for university", False, "the quote is about what it does not pay")]}
# ---------------------------------------------------------------- Saudi Arabia
L["sa-kaust-funding"] = {"kind": "opportunity", "official": True, "language": "en", "fields": {
    "deadlines": [], "levels": ["master", "phd"], "tuition": "full",
    "stipend_by_level": {"master": 20000, "phd": [25000, 30000]},
    "components": {"tuition": "full", "living_allowance": "covered", "accommodation": "covered", "insurance": "covered",
                   "travel": "covered"}}, "claims": [
    C("covers_accommodation", True, "Base accommodation is included (shared accommodation for single students, and 2-bed accommodation for married students).", True, "provided"),
    C("covers_health_insurance", True, "Health insurance for students and eligible dependents living on campus", True, "stated"),
    C("stipend_amount", 30000, "A monthly stipend (worth USD $20,000 per year for M.S. students, and USD $25,000 to $30,000 for Ph.D. students depending on qualifications and academic progress)", False, "amounts differ by level"),
    C("tuition_coverage", "full", "Full tuition and bench fee coverage (worth up to USD $35,000 per year)", True, "stated"),
    C("covers_travel", True, "Relocation support (visa, relocation and travel costs)", True, "stated")]}
# ---------------------------------------------------------------- Taiwan
L["tw-icdf-list"] = {"kind": "opportunity", "official": True, "language": "en", "fields": {
    "deadlines": [{"kind": "scholarship", "date": "2027-03-15", "status": "current"}], "openings": ["2026-12-01"],
    "cycle": "2027", "provider": {"name": "TaiwanICDF", "role": "provider"}}, "claims": [
    C("deadline_scholarship", "2027-03-15", "The 2027 TaiwanICDF Scholarship applications open from December 1, 2026 to March 15, 2027!", True, "end of window"),
    C("opening_date", "2026-12-01", "The 2027 TaiwanICDF Scholarship applications open from December 1, 2026 to March 15, 2027!", True, "start of window"),
    C("provider_name", "TaiwanICDF", "The International Higher Education Scholarship Program, central to the TaiwanICDF, offers full scholarships to outstanding students from partner countries to pursue higher education in Taiwan", False,
      "the programme (not the TaiwanICDF) is the subject of 'offers'; conservative reject")]}
L["tw-icdf-item"] = {"kind": "guidance", "official": True, "language": "en", "fields": {}, "claims": [
    C("deadline_scholarship", "2027-03-15", "(Application Dates: December 1, 2026 - March 15, 2027).", True, "window end")]}
L["tw-roc-israel"] = {"kind": "opportunity", "official": True, "language": "en", "fields": {
    "deadlines": [{"kind": "scholarship", "date": "2026-04-30", "status": "historical"}], "cycle": "2026/2027",
    "stipend": {"amount": [20000], "currency": "TWD", "period": "month"},
    "conflict": "'tuition of up to 40,000 NTD per semester' and a stipend vs 'The scholarship recipient is responsible for tuition and all living expenses.'",
    "provider": {"name": "Ministry of Education (MOE) of the Republic of China (Taiwan)", "role": "provider"}}, "claims": [
    C("deadline_scholarship", "2026-04-30", "Application Submission: By April 30, 2026.", True, "historical (previous cycle)"),
    C("stipend_amount", 20000, "The MOE offers each recipient undertaking graduate studies a monthly stipend of 20,000 NTD (approx. 620 US$).", True, "graduate stipend"),
    C("page_conflicts", "tuition up to 40,000 NTD per semester is paid, yet the recipient is responsible for tuition and all living expenses", "The scholarship recipient is responsible for tuition and all living expenses.", True, "real contradiction"),
    C("tuition_coverage", "full", "The MOE awards each recipient tuition of up to 40,000 NTD per semester (approx. 1,235 US$).", False, "capped amount, not full"),
    C("funding_duration_months", 48, "Ph.D. Programs: 4 years", False, "programme length heading, not a funding statement")]}
# ---------------------------------------------------------------- Brunei
L["bn-ubd-scholarship"] = {"kind": "opportunity", "official": True, "language": "en", "fields": {
    "deadlines": [], "levels": ["bachelor", "master", "phd"],
    "note": "several schemes; the eligibility list on the page is for Brunei citizens (local scheme) only"}, "claims": [
    C("eligible_nationalities", ["Brunei"], "Citizen of Brunei Darussalam (Yellow IC)", False, "applies only to the local-student scheme, not the international one"),
    C("age_limits_by_level", ["bachelor<=25", "master<=29"], "Under 26 years of age for admission to an Undergraduate Degree programme", False, "quote covers only the undergraduate limit"),
    C("ielts_min", 6.5, "IELTS Academic: Overall Band Score of 6.5 or above (obtained within the last two years)", True, "stated (local scheme)"),
    C("covers_accommodation", True, "Apart from tuitions borne by the government, the scholarship will also include the bursaries for accommodation, books, food, personal spending as well as complementary medical treatment at any Brunei Government hospital whilst travel expenses will be arranged by the Brunei Darussalam Foreign Mission", True, "accommodation bursary"),
    C("study_levels", ["phd"], "The UBD Graduate Research Scholarship is a competitive scheme awarded to quality PhD students with a strong desire to work in an international and competitive research-intensive environment.", True, "PhD scheme")]}
# ---------------------------------------------------------------- Malaysia
L["my-mis"] = {"kind": "opportunity", "official": True, "language": "en", "fields": {
    "deadlines": [], "cycle": "2026/2027", "levels": ["master", "phd"],
    "provider": {"name": "Malaysian Government", "role": "provider"},
    "note": "2026/2027 call closed; checking period is not a deadline"}, "claims": [
    C("deadline_scholarship", "2026-12-31", "The Checking period is from 08 October 2026 to 31 December 2026.", False, "status-checking period, not an application deadline"),
    C("academic_cycle", "2026/2027", "The application for the 2026/2027 academic year is now closed.", False, "closed cycle"),
    C("provider_name", "Malaysian Government", "Malaysia International Scholarship (MIS) is an initiative by the Malaysian Government to attract top talents from around the world to pursue postgraduate studies in Malaysia.", False,
      "'an initiative by' is not stated as funding; conservative reject")]}
# ---------------------------------------------------------------- Germany
L["de-studienstiftung-faq"] = {"kind": "guidance", "official": True, "language": "de", "fields": {
    "max_age": "not_stated", "nationality": "not_stated", "note": "no age limit ('Nein'); non-Germans may apply if formal conditions are met"}, "claims": [
    C("max_age", 30, "Gibt es eine Altersgrenze für einen Vorschlag oder eine Bewerbung?", False, "the answer is 'Nein' (no limit)")]}
L["de-kas-pdf"] = {"kind": "opportunity", "official": True, "language": "de", "fields": {
    "deadlines": [], "note": "information sheet dated 01.06.2014 (outdated); text extraction splits words",
    "duration_months_max": 36}, "claims": [
    C("stipend_amount", 920, "€ 920, -.", False, "a bare amount; the page does not say which level it is for in this quote"),
    C("covers_health_insurance", True, "Der Stipendiat erhält einen monatlichen Zuschuss zur Kranken- und Pfleg e-versicherung", True, "monthly insurance subsidy (quote as extracted)")]}
# ---------------------------------------------------------------- Canada
L["ca-vanier"] = {"kind": "opportunity", "official": True, "language": "en", "fields": {
    "deadlines": [], "institutional_deadlines": [{"date": "2024-10-30", "status": "historical"}], "levels": ["phd"],
    "duration_months_max": 36, "award_amount": {"amount": [50000], "currency": "CAD"},
    "provider": {"name": "Government of Canada", "role": "provider"},
    "note": "timeline is for the 2024 competition (outdated); 30 Oct is the institutions' nomination deadline; applicants' internal deadline varies"}, "claims": [
    C("deadline_scholarship", "2024-10-30", "October 30, 2024 (20:00 EDT) Deadline for institutions to submit nominations to the Vanier CGS program.", False, "institutions' deadline, and a past cycle"),
    C("funding_duration_months", 36, "3 years (non-renewable)", False, "a bare duration heading (no funding wording in the quote); conservative"),
    C("study_levels", ["phd"], "The Government of Canada launched the Vanier Canada Graduate Scholarships (Vanier CGS) program in 2008 to strengthen Canada's ability to attract and retain world-class doctoral students", True, "doctoral"),
    C("provider_name", "Government of Canada", "The Government of Canada launched the Vanier Canada Graduate Scholarships (Vanier CGS) program in 2008", True, "launched the scholarship programme")]}
L["ca-mcgill-mcf-elig"] = {"kind": "opportunity", "official": True, "language": "en", "fields": {
    "deadlines": [], "levels": ["master"], "nationality": {"mode": "include", "countries": AFRICA},
    "note": "Fall 2027 cohort closed; citizen of and living in an African country"}, "claims": [
    C("study_levels", ["master"], "Have NEVER registered for, nor completed a master’s degree.", False, "an exclusion, not the level offered"),
    C("residency_required", ["Kenya"], "Be a citizen of and live in an African country (view eligible countries).", False, "no single country named"),
    C("provider_name", "McGill University", "The application period for the Fall 2027 cohort is now closed.", False, "not named / no funding statement")]}
# ---------------------------------------------------------------- Czech Republic
L["cz-studyin-340"] = {"kind": "opportunity", "official": True, "language": "en", "fields": {
    "deadlines": [{"kind": "scholarship", "date": "2026-09-30", "status": "historical"}], "openings": ["2026-08-01"],
    "cycle": "2027/2028", "nationality": {"mode": "include", "countries": ["BA", "GE", "UA", "BY"]},
    "components": {"accommodation": "own_cost", "tuition": "covered", "living_allowance": "covered"},
    "conflict": "'follow-up master's degree programmes' vs 'Education level: higher (Bachelor study programme)'; stipend listed for doctoral too",
    "provider": {"name": "Government of the Czech Republic", "role": "provider"}}, "claims": [
    C("deadline_scholarship", "2026-09-30", "All applicants are required to complete the online application form by 30 September 2026 at the latest.", True, "historical"),
    C("eligible_nationalities", ["Bosnia and Herzegovina", "Georgia", "Ukraine", "Belarus"], "For the academic year 2027/2028, Czech Government scholarships for studies in the Czech language are offered exclusively to citizens of the following countries", False, "the quote names no country"),
    C("covers_accommodation", True, "The costs of accommodation, meals and public transport are covered by the scholarship holders from their scholarship, under the same conditions as those applicable to students who are citizens of the Czech Republic.", False, "paid by the holder"),
    C("stipend_amount", 24960, "24 960 CZK for students in a doctoral degree programmes.", False, "per-level amount; the record is not doctoral-specific"),
    C("study_levels", ["bachelor"], "Education level: higher (Bachelor study programme)", False, "contradicts 'follow-up master's'; conflicting"),
    C("provider_name", "Government of the Czech Republic", "Under its Strategy for Foreign Development Assistance, the Government of the Czech Republic offers scholarships to foreign nationals from selected developing countries", True, "offers scholarships")]}
# ---------------------------------------------------------------- Japan
L["jp-utokyo-k-mext"] = {"kind": "opportunity", "official": True, "language": "en", "fields": {
    "deadlines": [{"kind": "scholarship", "date": "2027-01-22", "status": "expected"}], "cycle": "2027", "note": "deadline only 'expected' (Jan 22, 2027) and the programme may not run; research students not eligible in AY2027"}, "claims": [
    C("deadline_scholarship", "2027-01-22", "The deadline for submitting the complete set of scholarship application documents is expected to be January 22, 2027.", True,
      "the value is stated (as expected); it must stay unconfirmed"),
    C("study_levels", ["short_course"], "Applicants who wish to enroll as Research Students should refer to the following website for detailed", False, "research students are not eligible in AY2027 through GSFS")]}
L["jp-utokyo-mext-pdf"] = {"kind": "unreadable", "official": True, "language": "en", "fields": {}, "claims": []}
L["jp-mext-guidelines-pdf"] = {"kind": "opportunity", "official": True, "language": "en", "fields": {
    "deadlines": [], "levels": ["master", "phd"], "tuition": "full",
    "stipend_by_level": {"research_student": 143000, "master": 144000, "phd": 145000},
    "provider": {"name": "Ministry of Education, Culture, Sports, Science and Technology (MEXT)", "role": "provider"},
    "note": "deadline varies by Japanese diplomatic mission"}, "claims": [
    C("stipend_amount", 145000, "③ Regular students enrolled in doctoral courses: 145,000 yen per month.", False, "doctoral-only amount; amounts differ by level"),
    C("deadline_scholarship", "2027-01-01", "The deadline for submission of application documents varies according to each Japanese diplomatic mission.", False, "no date"),
    C("tuition_coverage", "full", "(2 ) Education fees : Fees for the entrance examination, matriculation, and tuition at universities are waivered .", True, "waived")]}
# ---------------------------------------------------------------- Hong Kong
L["hk-hkpfs"] = {"kind": "opportunity", "official": True, "language": "en", "fields": {
    "deadlines": [], "levels": ["phd"], "nationality": {"mode": "any", "countries": []},
    "provider": {"name": "Research Grants Council", "role": "provider"},
    "conflict": "400 fellowships (RGC page) vs around 300 (HKU page)"}, "claims": [
    C("nationality_mode", "any", "Candidates who are seeking admission as new full time PhD students in the following eight universities, irrespective of their country of origin,", True, "stated"),
    C("study_levels", ["phd"], "Candidates who are seeking admission as new full time PhD students in the following eight universities, irrespective of their country of origin,", True, "PhD"),
    C("provider_name", "Research Grants Council", "Established by the Research Grants Council (RGC) of Hong Kong in 2009, the Hong Kong PhD Fellowship Scheme (HKPFS) aims at attracting the best and brightest students", False,
      "'established by' is not a funding statement; conservative")]}
L["hk-hku-hkpfs"] = {"kind": "opportunity", "official": True, "language": "en", "fields": {
    "deadlines": [{"kind": "scholarship", "date": "2026-12-01", "status": "current"}], "levels": ["phd"], "cycle": "2027/2028",
    "stipend": {"amount": [28700], "currency": "HKD", "period": "month"},
    "components": {"tuition": "covered", "accommodation": "covered", "travel": "covered", "living_allowance": "covered"}}, "claims": [
    C("deadline_scholarship", "2026-12-01", "Step 1: Submit an initial on-line application through the RGC’s HKPFS Electronic System on or before December 1, 2026 at 12:00 noon, Hong Kong Time (GMT +8 hours) and obtain an HKPFS Reference Number.", True, "stated"),
    C("stipend_amount", 28700, "Each HKPFS awardee will receive a Postgraduate Scholarship of HK$28,700 per month, and conference and research-related travel allowance of HK$14,400 per year for a period up to three years*.", True, "stated"),
    C("covers_accommodation", True, "A guaranteed hall place in Year 1, with possibility of renewal", True, "hall place provided"),
    C("tuition_coverage", "full", "Waiver of composition fees for the whole normative study period (i.e. HK$49,500 per year)", False, "no tuition word in the quote (composition fees); conservative")]}
# ---------------------------------------------------------------- Belgium (French)
L["be-ares-formations"] = {"kind": "opportunity", "official": True, "language": "fr", "fields": {
    "deadlines": [{"kind": "scholarship", "date": "2026-09-18", "status": "historical"}], "cycle": "2027/2028",
    "note": "residency + work in 32 countries; Palestinians eligible without residence; call closed"}, "claims": [
    C("deadline_scholarship", "2026-09-18", "Date limite : Vendredi 18 septembre 2026", True, "historical"),
    C("academic_cycle", "2027/2028", "L'appel bourses 2027-2028 est clôturé.", False, "closed"),
    C("residency_required", ["Kenya"], "Être résidente permanente et travailler dans l’un des 32 pays éligibles (voir liste ci-dessous).", False, "no country named in the quote"),
    C("eligible_nationalities", ["Palestine"], "Exception : les personnes de nationalité palestinienne sont éligibles même si elles ne résident pas dans l’un de ces 32 pays.", True, "explicit exception")]}
L["be-ares-belgique"] = {"kind": "opportunity", "official": True, "language": "fr", "fields": {
    "deadlines": [{"kind": "scholarship", "date": "2026-09-18", "status": "historical"}], "cycle": "2027/2028"}, "claims": [
    C("deadline_scholarship", "2026-09-18", "Les candidatures se clôturent le 18 septembre 2026 à 12h (heure belge, UTC+1).", True, "historical"),
    C("funding_duration_months", 12, "Les bourses de l'ARES offrent la possibilité de suivre un bachelier de spécialisation ou un master de spécialisation d’un an, ou une formation continue de 6 mois", False, "'d’un an' is not read as a number; programme length")]}
# ---------------------------------------------------------------- Indonesia (PDF, Indonesian)
L["id-bu-pedoman-pdf"] = {"kind": "opportunity", "official": True, "language": "id", "fields": {
    "deadlines": [], "levels": ["bachelor", "master", "phd"], "nationality": "not_stated",
    "age_by_level": {"master": {"max": 31}, "phd": {"max": 45}},
    "note": "age limits differ by level AND by new vs ongoing students (S2 <32 / <33, S3 <46 / <47)"}, "claims": [
    C("max_age", 46, "(1) belum memasuki usia 46 tahun pada tanggal 31 Desember tahun pendaftaran bagi mahasiswa baru atau belum memasuki usia 47 tahun untuk yang sedang menempuh perkuliahan;", False, "differs by applicant category (new vs ongoing) and by level"),
    C("min_gpa", 3.0, "(3) memiliki nilai IPK S1 paling rendah 3,00 (tiga koma nol) pada skala 4 (empat) baik bagi", True, "master's GPA (Indonesian decimal comma)")]}
# ---------------------------------------------------------------- Mastercard Foundation
L["int-mastercard-fdn"] = {"kind": "guidance", "official": True, "language": "en", "fields": {
    "levels": ["bachelor", "master"], "provider": {"name": "Mastercard Foundation", "role": "funder"}}, "claims": [
    C("study_levels", ["bachelor", "master"], "The Mastercard Foundation Scholars Program provides scholarships at the secondary, undergraduate, and master’s levels.", True, "stated"),
    C("study_levels", ["phd"], "However, scholarships are not currently available to PhD candidates.", False, "excluded"),
    C("provider_name", "Mastercard Foundation", "The Mastercard Foundation Scholars Program is managed through our partner universities and non-governmental organizations.", False, "managed through partners; not a funding statement")]}
# ---------------------------------------------------------------- Mexico (Spanish / English)
L["mx-amexcid"] = {"kind": "opportunity", "official": True, "language": "es", "fields": {
    "deadlines": [], "cycle": "2026", "provider": {"name": "AMEXCID", "role": "provider"}}, "claims": [
    C("provider_name", "Agencia Mexicana de Cooperación Internacional para el Desarrollo (AMEXCID)", "La Secretaría de Relaciones Exteriores (SRE), a través de la Agencia Mexicana de Cooperación Internacional para el Desarrollo (AMEXCID), convoca a extranjeros (as) interesados (as) en realizar estudios en México", False,
      "'convoca' (calls for applications) is not read as a funding verb; conservative")]}

out = {"today": "2026-10-17", "set": "D", "split": "all pages are held-out test pages",
       "labelled_by": "assistant reading each page snapshot; no extractor or model output used",
       "written": "2026-10-17, before any Claude run on these pages", "pages": {}}
bad = []
for pid, lab in L.items():
    pg = load_page(pid, urls[pid]["url"], ROOT)
    body = " ".join(pg.text.lower().split()) if pg else ""
    for c in lab["claims"]:
        if " ".join(c["quote"].lower().split()) not in body:
            bad.append((pid, c["quote"][:90]))
    out["pages"][pid] = lab
print("missing pages:", set(urls) - set(L), "extra:", set(L) - set(urls))
print("quotes not verbatim:", bad)
if not bad and set(urls) == set(L):
    (ROOT / "labels.json").write_text(json.dumps(out, indent=1, ensure_ascii=False))
    print("written", len(L), "pages", sum(len(v["claims"]) for v in L.values()), "claims",
          sum(c["accept"] for v in L.values() for c in v["claims"]), "accept")
