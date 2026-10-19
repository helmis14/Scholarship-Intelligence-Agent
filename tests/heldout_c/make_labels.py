"""Writes tests/heldout_c/labels.json. Labels were written by reading each page snapshot (2026-10-17); no model or
extractor output was used. Every quote is checked to be verbatim (whitespace-folded) on its page."""
import json, sys
from pathlib import Path
REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from scholarship_agent.heldout import load_page

ROOT = REPO / "tests" / "heldout_c"
urls = {p["id"]: p for p in json.loads((ROOT / "urls.json").read_text())["pages"]}
VLIR25 = ["BJ","BF","BI","CM","CD","ET","GN","KE","MG","MZ","NE","SN","ZA","TZ","UG","ZW","MA","PS","BO","CU","EC","PE","ID","PH","VN"]
AGE_VLIR = ("Age: Candidates for a bachelor or initial master programme cannot be older than 35 as of 1 January of the "
            "intake year, while candidates for an advanced master cannot be older than 45. Additionally, candidates for a "
            "bachelor programme must be at least 19 years old by 1 January of the intake year.")
AGE_VLIR_LEVELS = ["bachelor<=35", "master<=35", "advanced_master<=45", "bachelor>=19"]
VLIR_COMMON_FIELDS = {"age_by_level": {"bachelor": {"max": 35, "min": 19}, "master": {"max": 35}, "advanced_master": {"max": 45}},
                      "provider": "VLIRUOS"}

def C(field, value, quote, accept, why, kind="positive"):
    return {"field": field, "value": value, "quote": quote, "accept": accept, "why": why}

def vlir_prog(title, open_=None, close=None, ambiguous=False, available=True, duration_quote=None, organiser=None,
              conflict_quote=None):
    f = dict(VLIR_COMMON_FIELDS)
    f["nationality"] = "not_stated"   # "25 eligible countries", list on another page
    claims = [C("provider_name", "VLIRUOS", title, True, "'an ICP Connect Scholarship by VLIRUOS' names the funder"),
              C("max_age", 35, AGE_VLIR, False, "limits differ by level (35 / 45); one number would collapse them"),
              C("age_limits_by_level", AGE_VLIR_LEVELS, AGE_VLIR, True, "per-level limits stated")]
    if organiser:
        claims.append(C("provider_name", organiser, f"Organised by {organiser}", False,
                        "the university organises the programme; VLIRUOS funds the scholarship"))
    if available:
        line = f"Applications open: {open_[0]} | Application deadline: {close[0]} | Programme duration: "
        f["deadlines"] = [{"kind": "scholarship", "date": close[1], "status": "current"}]
        f["openings"] = [open_[1]]
        claims.append(C("opening_date", open_[1], line, not ambiguous,
                        "two-digit year; day/month order ambiguous on this page" if ambiguous else
                        "dd/mm/yy; order fixed by another date on the page"))
        claims.append(C("deadline_scholarship", close[1], line, not ambiguous,
                        "two-digit year; day/month order ambiguous on this page" if ambiguous else
                        "dd/mm/yy; order fixed by another date on the page"))
    else:
        f["deadlines"] = []
        f["available"] = False
    if duration_quote:
        claims.append(C("funding_duration_months", duration_quote[1], duration_quote[0], False,
                        "the study programme's length, not a stated funding period"))
    if conflict_quote:
        claims.append(C("page_conflicts", "programme duration Sept 2027 - Sept 2028 contradicts 'two-year programme'",
                        conflict_quote, True, "real contradiction on the page; reported, not resolved"))
    return {"kind": "opportunity", "fields": f, "claims": claims}

L = {}
L["be-vliruos-aquaculture-imaqua"] = vlir_prog(
    "Master of Aquaculture (IMAQUA), an ICP Connect Scholarship by VLIRUOS", ("01/10/26", "2026-10-01"), ("28/02/27", "2027-02-28"),
    organiser="UGent", conflict_quote="The Master in Aquaculture is a two-year programme (120 ECTS)")
L["be-vliruos-food-technology"] = vlir_prog(
    "Master of Science in Food Technology, an ICP Connect Scholarship by VLIRUOS", ("12/10/26", "2026-10-12"), ("01/02/27", "2027-02-01"),
    ambiguous=True, duration_quote=("This two-year Master’s programme (120 ECTS) intends to equip future personnel", 24))
L["be-vliruos-epidemiology"] = vlir_prog(
    "Master of Epidemiology, an ICP Connect Scholarship by VLIRUOS", available=False,
    duration_quote=("The Master of Epidemiology is a two-year programme (120 ECTS)", 24))
L["be-vliruos-statistics-and-data-science"] = vlir_prog(
    "Master of Statistics and Data Science, an ICP Connect Scholarship by VLIRUOS", available=False,
    duration_quote=("The two-year (120 ECTS) Master’s programme is accredited by the prestigious Royal Statistical Society", 24))
L["be-vliruos-transportation-sciences-road-s"] = vlir_prog(
    "Master of Transportation Sciences - Road Safety, an ICP Connect Scholarship by VLIRUOS", ("15/10/26", "2026-10-15"),
    ("01/02/27", "2027-02-01"), organiser="UHasselt")
L["be-vliruos-sustainable-land-management"] = vlir_prog(
    "Master of Science in Sustainable Land Management, an ICP Connect Scholarship by VLIRUOS", ("01/11/26", "2026-11-01"),
    ("28/02/27", "2027-02-28"),
    duration_quote=("The Master of Science in Sustainable Land Management is a two-year, full-time programme.", 24))
L["be-vliruos-human-settlements"] = vlir_prog(
    "Master of Human Settlementsm, an ICP Connect Scholarship by VLIRUOS", available=False,
    duration_quote=("This one-year intensive programme tackles the multi-faceted challenges", 12))
L["be-vliruos-water-resources-engineering-wr"] = vlir_prog(
    "Master of Water Resources Engineering (WRE), an ICP Connect Scholarship by VLIRUOS", available=False,
    duration_quote=("This two-year Master’s programme (120 ECTS) aims to equip future professionals", 24))

L["be-vliruos-countries"] = {"kind": "guidance", "fields": {"nationality": {"mode": "include", "countries": VLIR25},
                                                             "residency": VLIR25}, "claims": [
    C("eligible_nationalities", ["Benin", "Kenya", "Vietnam"],
      "Candidates for an VLIRUOS scholarship must hold the nationality of one of the eligible countries listed below.",
      False, "true value, but the quote names no country (the list is below it); conservative rejection expected"),
    C("residency_required", ["Kenya"], "They must also be residing in one of these countries at the time of application",
      False, "quote names no country")]}

L["be-vliruos-study"] = {"kind": "opportunity", "fields": {
    "deadlines": [], "cycle": "2027/2028", "previous_cycle": "2026/2027", "nationality": "not_stated",
    "age_by_level": VLIR_COMMON_FIELDS["age_by_level"],
    "tuition": "covered", "travel": True, "duration_months_max": 36,
    "components": {"tuition": "covered", "travel": "covered", "insurance": "covered", "living_allowance": "covered",
                   "accommodation": "part_of_living_expenses"},
    "conflict": "28 eligible countries on this page vs 25 on the programme pages and the country list"}, "claims": [
    C("academic_cycle", "2027/2028", "The call for the 2027–2028 academic year is expected to open by the end of October 2026.", True,
      "the upcoming call"),
    C("academic_cycle", "2026/2027", "The ICP Connect scholarship call for the 2026–2027 academic year is now closed.", False,
      "a closed, previous cycle is not the current call"),
    C("opening_date", "2026-10-31", "The call for the 2027–2028 academic year is expected to open by the end of October 2026.", False,
      "approximate ('by the end of October'), no exact date"),
    C("covers_travel", True, "VLIRUOS ICP Connect scholarships cover tuition fees, travel, insurance and living expenses (board and lodging).", True, "stated"),
    C("covers_health_insurance", True, "VLIRUOS ICP Connect scholarships cover tuition fees, travel, insurance and living expenses (board and lodging).", True, "stated"),
    C("covers_living_allowance", True, "VLIRUOS ICP Connect scholarships cover tuition fees, travel, insurance and living expenses (board and lodging).", True, "stated"),
    C("covers_accommodation", True, "VLIRUOS ICP Connect scholarships cover tuition fees, travel, insurance and living expenses (board and lodging).", False,
      "lodging is part of living expenses, not a separate accommodation benefit"),
    C("funding_duration_months", 36, "We only offer scholarships for the full duration of the study programme (12/24/36 months).", True, "longest stated period"),
    C("max_age", 35, "Age: Candidates for a bachelor or initial master programme cannot be older than 35 as of 1 January of the intake year, while candidates for an advanced master cannot be older than 45.", False, "per-level limits"),
    C("age_limits_by_level", AGE_VLIR_LEVELS, AGE_VLIR, True, "per-level limits")]}

ASEA_AGE = "Age limit: 35 years for undergraduates, graduates and postgraduates, 45 years for postdocs (at the time of the application)"
L["at-ernst-mach-main"] = {"kind": "opportunity", "fields": {
    "deadlines": [{"kind": "scholarship", "date": "2026-03-31", "status": "historical"}], "nationality": "not_stated",
    "max_age": [35, 45], "provider": "Austrian Federal Ministry of Women, Science and Research",
    "note": "multi-programme page: worldwide 1 December, FH and Follow-Up 1 February, ASEA 1 March (no years), Short-term ongoing"},
    "claims": [
    C("provider_name", "Austrian Federal Ministry of Women, Science and Research",
      "The grant programme is financed by the Austrian Federal Ministry of Women, Science and Research (BMFWF).", True, "funder stated"),
    C("deadline_scholarship", "2026-03-31", "Closing date for applications: 31.03.2026", True, "exact (historical) date"),
    C("deadline_scholarship", "2026-12-01", "Closing date for applications: online application is possible from September to December 1st", False, "no year stated"),
    C("max_age", 45, ASEA_AGE, False, "per-level limits"),
    C("age_limits_by_level", ["bachelor<=35", "master<=35", "phd<=35", "postdoc<=45"], ASEA_AGE, True, "per-level limits"),
    C("covers_travel", True, "Information on travel costs subsidy", False, "a link title, not a statement of a benefit"),
    C("funding_duration_months", 36, "Duration: undergraduates, graduates: 9 months; post docs: 4 to 9 months; postgraduates: max. 36 months", True, "longest stated")]}

L["at-ernst-mach-worldwide"] = {"kind": "opportunity", "fields": {
    "deadlines": [{"kind": "scholarship", "date": "2026-12-01", "status": "current"}], "cycle": "2027/2028", "max_age": 35,
    "components": {"insurance": "own_cost", "accommodation": "own_cost", "travel": "own_cost"}}, "claims": [
    C("deadline_scholarship", "2026-12-01", "The application deadline for this grant is December 1st, 2026, 23:59 (CET - Central European Time) for all applications for stays during the academic year 2027/28.", True, "exact"),
    C("academic_cycle", "2027/2028", "These FAQs only apply to the current call (for the Austrian academic year 2027/28)!", True, "short form 2027/28"),
    C("max_age", 35, "Applicants must not be older than 35 years when they start their research stay.", True, "single limit"),
    C("covers_health_insurance", True, "compulsory health insurance;", False, "item in a list of the applicant's own expenses"),
    C("covers_accommodation", True, "accommodation;", False, "item in a list of the applicant's own expenses")]}

L["eu-mundus-journalism"] = {"kind": "opportunity", "fields": {
    "deadlines": [], "nationality": {"mode": "any", "countries": []}, "tuition": "full",
    "stipend": {"amount": [1400], "currency": "EUR", "period": "month"}, "duration_months_max": 24,
    "components": {"tuition": "full", "living_allowance": "covered", "insurance": "covered",
                   "accommodation": "from_allowance", "travel": "from_allowance"}}, "claims": [
    C("tuition_coverage", "full", "A complete waiver of all tuition fees for both years of the programme", True, "stated"),
    C("stipend_amount", 1400, "€1,400 per month for up to 24 months, which you can use for housing, food, travel, visas, and any other costs related to studying and living in Europe", True, "stated"),
    C("funding_duration_months", 24, "€1,400 per month for up to 24 months, which you can use for housing, food, travel, visas, and any other costs related to studying and living in Europe", True, "stated"),
    C("covers_living_allowance", True, "€1,400 per month for up to 24 months, which you can use for housing, food, travel, visas, and any other costs related to studying and living in Europe", True, "monthly allowance"),
    C("covers_accommodation", True, "€1,400 per month for up to 24 months, which you can use for housing, food, travel, visas, and any other costs related to studying and living in Europe", False, "housing is paid from the allowance"),
    C("covers_travel", True, "€1,400 per month for up to 24 months, which you can use for housing, food, travel, visas, and any other costs related to studying and living in Europe", False, "travel is paid from the allowance"),
    C("covers_health_insurance", True, "Free health and liability insurance", True, "separate benefit"),
    C("nationality_mode", "any", "These scholarships are open to applicants of all nationalities.", True, "stated")]}

L["id-aminef-fulbright"] = {"kind": "opportunity", "fields": {
    "deadlines": [], "nationality": {"mode": "include", "countries": ["ID"]}, "travel": True, "duration_months_max": 36,
    "components": {"travel": "covered", "tuition": "covered", "living_allowance": "covered", "insurance": "covered",
                   "accommodation": "not_stated"},
    "note": "deadlines 'Feb 15' (Master/PhD) and 'November 1' (Visiting Scholar) without year; 'may be subject to change'"},
    "claims": [
    C("funding_duration_months", 36, "The MA and PhD scholarships support two and three years of graduate study respectively at a US university.", True, "written numbers: two / three years"),
    C("provider_name", "Indonesian Ministry of Research, Technology, and Higher Education", "funded by the Indonesian Ministry of Research, Technology, and Higher Education, provides Fulbright scholarships for current lecturers at Indonesian universities.", False,
      "funder of a separate, paused DIKTI programme, not of these scholarships"),
    C("deadline_scholarship", "2027-02-15", "Application Deadline*: Feb 15", False, "no year; 'may be subject to change'"),
    C("covers_travel", True, "Round-trip economy class air travel from scholarship recipient’s home city to the host institution in the US", True, "stated"),
    C("covers_health_insurance", True, "Accident and health insurance coverage per US Government guidelines", True, "stated"),
    C("eligible_nationalities", ["Indonesia"], "Be an Indonesian citizen and not a permanent resident or citizen of the US, or be currently living in the US", True, "stated"),
    C("residency_required", ["United States"], "Be an Indonesian citizen and not a permanent resident or citizen of the US, or be currently living in the US", False, "a US residence is an exclusion, not a requirement")]}

# ---------------- test pages
L["be-vliruos-icp-calls"] = {"kind": "opportunity", "fields": {
    "deadlines": [{"kind": "scholarship", "date": "2027-02-28", "status": "current"}], "cycle": "2027/2028",
    "duration_months_max": 36,
    "age_by_level": VLIR_COMMON_FIELDS["age_by_level"],
    "components": {"living_allowance": "covered", "tuition": "from_allowance", "insurance": "from_allowance",
                   "accommodation": "from_allowance"}}, "claims": [
    C("academic_cycle", "2027/2028", "ICP Connect Scholarships 2027-2028", True, "call year"),
    C("deadline_scholarship", "2027-02-28", "Call Submission Deadline 28 February 2027", True, "call deadline"),
    C("deadline_scholarship", "2027-09-01", "Project Start Date 01 September 2027", False, "a start date, not a deadline"),
    C("covers_living_allowance", True, "The monthly scholarship allowance covers living expenses and tuition fees.", True, "stated"),
    C("covers_accommodation", True, "Depending on the institution you pay for your own insurance, tuition fee, and/or accommodation out of the scholarship allowance OR the institution covers these costs directly and subtracts them from your monthly allowance.", False, "paid out of the allowance"),
    C("covers_health_insurance", True, "Depending on the institution you pay for your own insurance, tuition fee, and/or accommodation out of the scholarship allowance OR the institution covers these costs directly and subtracts them from your monthly allowance.", False, "paid out of the allowance"),
    C("funding_duration_months", 36, "Duration 12/24/36 months", True, "longest stated"),
    C("max_age", 35, "Yes, candidates for a bachelor or initial Master programme cannot be older than 35 as of January 1 of the intake year, while candidates for an advanced Master programme cannot be older than 45.", False, "per-level"),
    C("age_limits_by_level", ["bachelor<=35", "master<=35", "advanced_master<=45"], "Yes, candidates for a bachelor or initial Master programme cannot be older than 35 as of January 1 of the intake year, while candidates for an advanced Master programme cannot be older than 45.", True, "per-level")]}

ITS_AGE = "Maximum Age: Undergraduates, Graduates, and Postgraduates: 35 years; Postdocs: 45 years"
L["id-its-ernst-mach"] = {"kind": "opportunity", "fields": {
    "deadlines": [{"kind": "scholarship", "date": "2027-03-01", "status": "current"},
                  {"kind": "scholarship", "date": "2026-12-15", "status": "current"}],
    "openings": ["2026-09-15"], "nationality": {"mode": "include", "countries": ["ID", "MY", "PH", "TH", "VN"]},
    "age_by_level": {"bachelor": {"max": 35}, "master": {"max": 35}, "phd": {"max": 35}, "postdoc": {"max": 45}},
    "stipend": {"amount": [1300], "currency": "EUR", "period": "month"}, "travel": True,
    "duration_months_max": 36, "cycle": "2027/2028"}, "claims": [
    C("deadline_scholarship", "2027-03-01", "Closing Date (Full PhD & Postdoc): 1 March 2027", True, "programme-specific"),
    C("deadline_scholarship", "2026-12-15", "Closing Date (Music Practice Grant): 15 December 2026", True, "programme-specific"),
    C("opening_date", "2026-09-15", "Application Portal Opens: 15 September 2026 (via www.scholarships.at)", True, "stated"),
    C("eligible_nationalities", ["Indonesia", "Malaysia", "Philippines", "Thailand", "Vietnam"], "Citizenship: Indonesia, Malaysia, the Philippines, Thailand, or Vietnam (only applicants holding citizenship of one of these countries are eligible)", True, "stated"),
    C("max_age", 45, ITS_AGE, False, "per-level"),
    C("age_limits_by_level", ["bachelor<=35", "master<=35", "phd<=35", "postdoc<=45"], ITS_AGE, True, "per-level"),
    C("stipend_amount", 1300, "Grant Benefit: €1,300/month + travel subsidy up to €1,200 + mobility subsidy €300/month", True, "stated"),
    C("covers_travel", True, "Grant Benefit: €1,300/month + travel subsidy up to €1,200 + mobility subsidy €300/month", True, "travel subsidy"),
    C("funding_duration_months", 36, "Duration: 36 months", True, "Full PhD Grant duration"),
    C("provider_name", "Austrian Federal Ministry of Women, Science and Research", "Final decisions are made by the Austrian Federal Ministry of Women, Science and Research (BMFWF).", False, "decision-maker, not a funding statement")]}

L["tr-burslari-why"] = {"kind": "opportunity", "fields": {
    "tuition": "covered", "travel": True,
    "components": {"tuition": "covered", "accommodation": "covered", "insurance": "covered", "travel": "covered",
                   "living_allowance": "covered"},
    "stipend_by_level": {"bachelor": 6500, "master": 9500, "phd": 13000}}, "claims": [
    C("covers_accommodation", True, "Provides accommodation for students arriving in a new country.", True, "separate benefit (dormitories)"),
    C("covers_travel", True, "Covers your once-off flight ticket.", True, "stated"),
    C("covers_health_insurance", True, "Allows you to take full advantage of widespread health services with general health insurance.", True, "stated"),
    C("covers_living_allowance", True, "Also provides monthly stipend.", True, "stated"),
    C("stipend_amount", 13000, "Also provides monthly stipend. 6.500 TL at Associate’s and Bachelor’s levels, 9.500 TL at Master's level and 13.000 TL at PhD level per month.", False, "amounts differ by level")]}

L["tr-burslari-short"] = {"kind": "opportunity", "fields": {"note": "three programmes with different benefits"}, "claims": [
    C("covers_accommodation", True, "The program covers monthly stipend, accommodation and round trip airfare tickets.", True, "KATIP programme"),
    C("covers_accommodation", True, "The Success Scholarship Program only covers monthly stipend. Accommodation and other expenses are not covered.", False, "negated"),
    C("funding_duration_months", 12, "The student can benefit from this scholarship for 1 academic year.", True, "1 academic year")]}

L["nl-utwente-nl"] = {"kind": "opportunity", "fields": {
    "deadlines": [{"kind": "scholarship", "date": "2027-04-01", "status": "current"}], "openings": ["2026-10-15"],
    "cycle": "2027/2028", "award_amount": {"amount": [5000], "currency": "EUR"}, "tuition": "not_stated",
    "provider": "Dutch Ministry of Education, Culture and Science"}, "claims": [
    C("deadline_scholarship", "2027-04-01", "Application forms closes per 1 April 2027 16.00 CET (for programmes starting September 2027)", True, "stated"),
    C("opening_date", "2026-10-15", "Application form opens per 15 October 2026, 12.00 CET", True, "stated"),
    C("academic_cycle", "2027/2028", "Your programme starts in the academic year 2027/2028", True, "stated"),
    C("provider_name", "Dutch Ministry of Education, Culture and Science", "The NL Scholarship (formerly known as Holland Scholarship) is financed by the Dutch Ministry of Education, Culture and Science together with Dutch research universities and universities of applied sciences.", True, "funder stated"),
    C("tuition_coverage", "full", "Please note: This scholarship is meant as a compensation for study related costs. It is up to the scholarship student to decide how to spend the money. No costs (e.g. tuition fees) will be paid on your behalf.", False, "tuition is not paid")]}

L["at-ernst-mach-fh"] = {"kind": "opportunity", "fields": {
    "deadlines": [{"kind": "scholarship", "date": "2026-02-01", "status": "historical"}], "cycle": "2026/2027", "max_age": 35,
    "components": {"insurance": "own_cost", "accommodation": "own_cost", "travel": "own_cost"}}, "claims": [
    C("deadline_scholarship", "2026-02-01", "The deadline for all applications for stays during the academic year 2026/27 is February 1st, 2026, 23:59 (CET - Central European Time).", True, "historical, but correctly read"),
    C("academic_cycle", "2026/2027", "These FAQs refer to the call for the Austrian academic year 2026/27.", True, "the page's (previous) cycle"),
    C("max_age", 35, "The maximum age is 35 years.", True, "single limit"),
    C("covers_health_insurance", True, "compulsory health insurance;", False, "applicant's own expense"),
    C("covers_travel", True, "journey to Austria;", False, "applicant's own expense")]}

# ---------------- revision 3 (round 11): funder-identity and study-level answers, DEV pages only.
# Written before the round 11 validator changes. Test pages are not touched.
DEV_EXTRA = {
    "at-ernst-mach-worldwide": [
        C("provider_name", "OeAD", "You do not need to show proof of own funds to the OeAD.", False,
          "the applicant's own funds; nothing says OeAD funds the grant (the original failure pattern)")],
    "at-ernst-mach-main": [
        C("provider_name", "OeAD-GmbH", "Funding organisation: OeAD-GmbH on behalf and financed by the Austrian Federal Ministry of Women, Science and Research", True,
          "labelled as the funding organisation (administers on behalf of the ministry)"),
        C("study_levels", ["postdoc"], "The Ernst Mach Follow-Up Grant is aimed at postdocs from non-European developing countries who are former OeAD scholarship holders.", True, "target group"),
        C("study_levels", ["bachelor", "master", "phd", "postdoc"], "The Ernst Mach Grant worldwide is targeted at young researchers from all disciplines and countries (except Austria) who wish to pursue a research project in Austria.", False,
          "no level is named"),
        C("study_levels", ["bachelor", "master"], "Target group: undergraduates and graduates from non-European universities", True, "target group")],
    "eu-mundus-journalism": [
        C("study_levels", ["master"], "The tuition fee for the two-year Mundus Journalism Master’s programme remains among the lowest", True, "a master's programme"),
        C("study_levels", ["master", "phd"], "Please note that applicants who have already completed a master's degree of two years or more are not eligible for an Erasmus Mundus scholarship", False,
          "a completed master's is an exclusion, and no PhD is offered"),
        C("provider_name", "Aarhus University", "Aarhus University will apply for funding from the EU every academic year.", False,
          "the host applies for funding; it is not stated to fund the scholarship")],
    "id-aminef-fulbright": [
        C("study_levels", ["master", "phd"], "The MA and PhD scholarships support two and three years of graduate study respectively at a US university.", True, "MA and PhD scholarships"),
        C("study_levels", ["phd"], "The Visiting Scholar Program allows an Indonesian holding a doctoral degree to carry out research for three to six months at an American university.", False,
          "the doctorate is a prerequisite, not the level funded"),
        C("study_levels", ["postdoc"], "The Visiting Scholar Program allows an Indonesian holding a doctoral degree to carry out research for three to six months at an American university.", False,
          "'postdoc' is not stated")],
    "be-vliruos-epidemiology": [
        C("provider_name", "Global Health Institute", "Through a VLIRUOS grant programme, this Master's programme is supported by the Global Health Institute.", False,
          "the institute supports the study programme; VLIRUOS funds the grant"),
        C("provider_name", "UAntwerpen", "Organised by UAntwerpen", False, "host university")],
    "be-vliruos-aquaculture-imaqua": [
        C("provider_name", "Ghent University", "is organised by the Laboratory for Aquaculture & Artemia Reference Centre of Ghent University", False, "host"),
        C("study_levels", ["master"], "The Master in Aquaculture is a two-year programme (120 ECTS)", True, "a master's programme"),
        C("study_levels", ["bachelor", "master"], "The Master in Aquaculture is a two-year programme (120 ECTS)", False, "bachelor not stated")],
    "be-vliruos-study": [
        C("study_levels", ["bachelor", "master"], "Age: Candidates for a bachelor or initial master programme cannot be older than 35 as of 1 January of the intake year, while candidates for an advanced master cannot be older than 45.", True,
          "candidates for bachelor and master programmes"),
        C("study_levels", ["phd"], "Age: Candidates for a bachelor or initial master programme cannot be older than 35 as of 1 January of the intake year, while candidates for an advanced master cannot be older than 45.", False,
          "no doctoral level")],
}
for pid, extra in DEV_EXTRA.items():
    assert urls[pid]["split"] == "dev", pid
    L[pid]["claims"] = L[pid]["claims"] + extra

out = {"today": "2026-10-17", "revision": "3: r2 = per-level pages carry age_by_level only; r3 = funder and study-level answers on dev pages", "labelled_by": "assistant reading each page snapshot; no extractor or model output used",
       "written": "2026-10-17, before any validator change of round 10", "pages": {}}
bad = []
for pid, lab in L.items():
    pg = load_page(pid, urls[pid]["url"], ROOT)
    body = " ".join(pg.text.lower().split())
    for c in lab["claims"]:
        if " ".join(c["quote"].lower().split()) not in body:
            bad.append((pid, c["quote"][:80]))
    lab["split"] = urls[pid]["split"]
    out["pages"][pid] = lab
missing = set(urls) - set(L)
print("missing pages:", missing)
print("quotes not verbatim:", bad)
if not bad and not missing:
    (ROOT / "labels.json").write_text(json.dumps(out, indent=1, ensure_ascii=False))
    n = sum(len(v["claims"]) for v in L.values())
    print("written", len(L), "pages", n, "claims",
          "dev", sum(len(v["claims"]) for k, v in L.items() if urls[k]["split"] == "dev"),
          "test", sum(len(v["claims"]) for k, v in L.items() if urls[k]["split"] == "test"))
