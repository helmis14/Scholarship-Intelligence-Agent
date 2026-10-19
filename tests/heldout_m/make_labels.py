"""Set M labels (round 28), written by hand from the official pages in pages/ before any extractor ran on set M.

Set M is the frozen test set for the round-28 rules (dates by role, nationality negation). The rules were committed
(ead057a) before any set-M page was fetched, and nothing on set M was used to change a rule. Labels follow the same
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
 "uk-liverpool-intl": dict(fields={"nationality": "not_stated", "levels": ["bachelor"], "deadlines": [], "cycle_status": "not_stated",
     "tuition": "partial", "funding_class": "partially_funded"},
     evidence={"nationality": "Be liable to pay full tuition fees at the overseas rate (fee status)",
               "funding_class": "will receive a £7,500 tuition fee reduction for the first year of study"}),
 "uk-ncl-vc": dict(fields={"nationality": "not_stated", "levels": ["bachelor"], "deadlines": [A("2027-01-13")], "cycle_status": "open",
     "tuition": "partial", "funding_class": "partially_funded"},
     evidence={"nationality": "be domiciled in of one of the following countries/regions (domicile, not nationality)",
               "deadlines": "must submit a course application via UCAS by the Equal Consideration Deadline of 13th January 2027",
               "funding_class": "The value of the tuition fee award is £7,000 per academic year ... partial Vice-Chancellor's International Scholarships"},
     ambiguous="the deadline is the course application's; acceptance by 3 May 2027 is a later step"),
}
AMB = {"uk-ncl-vc": ["deadlines"]}
X = {"uk-lancaster-gs": "scholarship finder listing many awards"}
P.update({
 "uk-swansea-intl": dict(fields={"nationality": "not_stated", "levels": ["bachelor", "master"], "deadlines": [D("2026-11-27", "current")],
     "cycle_status": "open", "tuition": "partial", "funding_class": "partially_funded"},
     evidence={"nationality": "available to overseas students (fee status; the form depends on residence)",
               "deadlines": "Applications for this scholarship will close at 12:00 GMT on the 27th November 2026.",
               "funding_class": "awarded as a discount on tuition fees worth up to £5,000 for the first year of study"}),
 "uk-hw-intl": dict(fields={"nationality": "not_stated", "levels": ["bachelor", "master"], "deadlines": [], "cycle_status": "not_stated",
     "tuition": "partial", "funding_class": "partially_funded"},
     evidence={"nationality": "international fee-paying students ... residing overseas (fee status, residence)",
               "funding_class": "paid as a partial fee abatement for the first year of study only"}),
 "uk-stir-intl": dict(fields={"nationality": "not_stated", "levels": ["master"], "deadlines": [], "cycle_status": "open",
     "tuition": "partial", "funding_class": "partially_funded"},
     evidence={"nationality": "classed as International for tuition fee purposes (fee status)",
               "cycle_status": "Applications for September 2027 and January 2028 are now open.",
               "funding_class": "awarded in the form of a £7,000 tuition fee waiver for new students in the first year"},
     ambiguous="submission windows (01 September - 15 December 2026, ...) set offer dates; no single closing date"),
 "uk-soas-schol": dict(fields={"nationality": "not_stated", "levels": ["master"], "deadlines": [D("2026-02-28"), D("2026-04-30"), D("2026-06-30")],
     "cycle_status": "closed", "tuition": "partial", "funding_class": "partially_funded"},
     evidence={"nationality": "You must be an overseas fee-paying student (fee status)",
               "deadlines": "First round - 28 February 2026 ... Second round - 30 April 2026 ... Third round - 30 June 2026",
               "funding_class": "valued at £8,000 in the form of tuition fee waivers"},
     ambiguous="the page still says 'now open for 2026/2027' although every round has passed"),
})
AMB.update({"uk-stir-intl": ["deadlines"], "uk-soas-schol": ["cycle_status"]})
P["uk-qmul-intl"] = dict(fields={"nationality": "not_stated", "levels": ["master"], "deadlines": [], "cycle_status": "not_stated",
     "tuition": "partial", "funding_class": "partially_funded"},
     evidence={"nationality": "available to all international students ... Have overseas fee status (fee status)",
               "funding_class": "Global Excellence Scholarships worth £7,000 ... deducted from a recipient's tuition fees"})
X.update({"ie-ul-intl": "navigation page", "es-unav-schol": "overview of several aid programmes", "de-goettingen-schol": "list of funding sources"})
P.update({
 "de-mannheim-schol": dict(fields={"nationality": "not_stated", "levels": ["bachelor", "master"], "deadlines": [D("2026-06-01"), D("2026-07-15")],
     "openings": ["2026-04-27", "2026-06-10"], "cycle_status": "closed", "funding_class": "not_stated"},
     evidence={"deadlines": "27 April until 1 June 2026 The application period has ended. ... 10 June until 15 July 2026",
               "cycle_status": "The application period has ended.",
               "funding_class": "The selection committee individually decides on the amount of funding (components not stated)"}),
 "se-gu-schol": dict(fields={"nationality": "not_stated", "levels": ["bachelor", "master"], "deadlines": [A("2027-01-15")],
     "cycle_status": "open", "tuition": "covered", "funding_class": "tuition_funded"},
     evidence={"nationality": "be required to pay tuition fees in Sweden (fee status)",
               "deadlines": "submit your application for studies by 15 January 2027",
               "funding_class": "The scholarship is a tuition fee waiver"},
     ambiguous="'a tuition fee waiver' without its extent; the scholarship form itself arrives around 10 February 2027"),
 "fi-lut-schol": dict(fields={"nationality": {"mode": "exclude", "countries": EEA + ["CH"]}, "levels": ["master"], "deadlines": [],
     "cycle_status": "not_stated", "tuition": "partial", "funding_class": "partially_funded"},
     evidence={"nationality": "As a non-EU/EEA citizen (Swiss citizens excluded) you are required to pay a tuition fee but you are also eligible to apply a scholarship.",
               "funding_class": "a second year scholarship of 6 000 € ... a discount on the tuition fee"}),
})
AMB.update({"se-gu-schol": ["funding_class", "cycle_status"]})
P.update({
 "fi-jyu-schol": dict(fields={"nationality": {"mode": "exclude", "countries": EEA + ["CH"]}, "levels": ["bachelor", "master"],
     "deadlines": [], "cycle_status": "not_stated", "tuition": "partial", "funding_class": "partially_funded"},
     evidence={"nationality": "collects tuition fees from students ... who are citizens of countries outside the European Union (EU), the European Economic Area (EEA), or Switzerland ... students who are liable to pay tuition fees have the right to apply for a scholarship",
               "funding_class": "a scholarship that covers part of the fee"},
     ambiguous="eligibility follows fee liability (nationality plus residence-permit exceptions)"),
 "fi-utu-schol": dict(fields={"nationality": {"mode": "exclude", "countries": EEA + ["CH"]}, "levels": ["bachelor", "master"],
     "deadlines": [], "cycle_status": "not_stated", "tuition": "partial", "funding_class": "partially_funded"},
     evidence={"nationality": "Tuition fees will be charged from citizens of a country outside the European Union (EU) and the European Economic Area (EEA) or Switzerland ... for students who are subject to tuition fees",
               "funding_class": "a scholarship that covers 50% of the tuition fee for the next study year"},
     ambiguous="eligibility follows fee liability (nationality plus residence-permit exceptions)"),
 "tr-bilkent-schol": dict(fields={"nationality": {"mode": "exclude", "countries": ["TR"]}, "levels": ["bachelor"], "deadlines": [],
     "cycle_status": "not_stated", "tuition": "partial", "funding_class": "partially_funded"},
     evidence={"nationality": "Applicants and students, who previously had or already have Turkish citizenship are not eligible for international student scholarships.",
               "funding_class": "Tuition waiver scholarships are awarded at five levels, ranging from 20% to 100%"},
     ambiguous="a 100 % waiver level exists"),
})
AMB.update({"fi-jyu-schol": ["nationality"], "fi-utu-schol": ["nationality"], "tr-bilkent-schol": ["funding_class"]})
P["se-liu-schol"] = dict(fields={"nationality": "not_stated", "levels": ["master"], "deadlines": [], "cycle_status": "not_announced",
     "tuition": "partial", "funding_class": "partially_funded"},
     evidence={"nationality": "international master's degree students ... who are required to pay tuition fees (fee status)",
               "cycle_status": "The application period for LiU Scholarships 2027 will open in early April ... Exact dates and more information will be published on this page later.",
               "funding_class": "The tuition fees for a student awarded a LiU International Scholarship are normally reduced by 50%."},
     ambiguous="'will open in early April' could be read as an expected opening; the page also describes Swedish Institute scholarships")
AMB["se-liu-schol"] = ["cycle_status"]
X.update({"tr-sabanci-schol": "overview of admission and government scholarships", "uk-brunel-intl": "PDF without readable text",
          "ee-ut-schol": "overview of several scholarships", "ch-unibas-schol": "overview", "at-unigraz-schol": "financing overview",
          "cz-muni-schol": "international office page", "hk-cityu-schol": "language-centre resource page", "ae-aus-schol": "navigation page"})
P.update({
 "ca-ucalgary-intl": dict(fields={"nationality": {"mode": "exclude", "countries": ["CA"]}, "levels": ["bachelor"], "deadlines": [],
     "cycle_status": "not_stated", "funding_class": "not_stated", "award": {"amount": [20000], "currency": "CAD"}},
     evidence={"nationality": "International students who are required to pay international tuition fees and who are not Canadian citizens or Permanent Residents of Canada",
               "funding_class": "$20,000 (Renewable) (what it pays for is not stated)"}),
 "ca-sfu-intl": dict(fields={"nationality": "not_stated", "levels": ["bachelor"], "deadlines": [], "cycle_status": "not_stated",
     "funding_class": "not_stated"},
     evidence={"nationality": "available to both domestic and international students (scope)",
               "funding_class": "From $20,000 up to $60,000 for domestic students, and $140,000 for international students (components not stated)"}),
 "int-schmidt": dict(fields={"nationality": "not_stated", "levels": ["postdoc"], "deadlines": [], "cycle_status": "not_stated",
     "funding_class": "not_stated"},
     evidence={"nationality": "Be nominated by your PhD awarding institution, which must be one of our nominating partner organizations (no nationality rule)"}),
 "us-hertz": dict(fields={"nationality": {"mode": "include", "countries": ["US"]}, "levels": ["phd"], "deadlines": [],
     "cycle_status": "not_stated", "components": {"tuition": "covered", "stipend": "covered"}, "funding_class": "fully_funded"},
     evidence={"nationality": "be citizens or permanent residents of the United States.",
               "funding_class": "to coordinate paying the stipend, tuition, and other costs for our fellows via a 9-month stipend model"},
     ambiguous="tuition and stipend are named only where the page explains how payment works; extent not stated"),
 "us-gilman": dict(fields={"nationality": {"mode": "include", "countries": ["US"]}, "levels": ["bachelor"], "deadlines": [],
     "cycle_status": "not_stated", "funding_class": "not_stated"},
     evidence={"nationality": "an applicant must be A citizen or national of the United States"}),
})
AMB["us-hertz"] = ["funding_class"]
P.update({
 "int-embo-pf": dict(fields={"nationality": "not_stated", "levels": ["postdoc"], "deadlines": [D("2027-01-22", "current")],
     "cycle_status": "open", "components": {"stipend": "covered", "relocation": "covered"}, "funding_class": "stipend_only"},
     evidence={"deadlines": "Applications accepted throughout the year (next cutoff date – hard deadline: Friday 22 January 2027, 14:00 CET)",
               "funding_class": "The fellowship includes a salary or stipend, a relocation allowance and support for fellows with children."}),
 "int-hfsp": dict(fields={"nationality": {"mode": "any", "countries": []}, "levels": ["postdoc"],
     "deadlines": [D("2026-05-05"), D("2026-05-12"), D("2026-09-24")], "openings": ["2026-03-12"], "cycle_status": "closed",
     "components": {"living_allowance": "covered", "research": "covered", "travel": "covered"}, "funding_class": "stipend_only"},
     evidence={"nationality": "Applicants may be from any country and of any nationality. However, candidates cannot apply for a fellowship to work in the country of their nationality",
               "deadlines": "Initiation of a Letter of Intent must be completed BEFORE May 5, 2026 ... Submission of a Letter of Intent by May 12, 2026 ... Submission of Full Proposals for invited applicants by September 24, 2026",
               "cycle_status": "The Letter of Intent (LOI) Deadline for the 2027 Cycle has now passed.",
               "funding_class": "Fellows are granted a Living Allowance as well as a Research & Travel Allowance."},
     ambiguous="three applicant steps with their own dates; the full proposal is for invited applicants only"),
 "int-ba-postdoc": dict(fields={"nationality": "not_stated", "levels": ["postdoc"], "deadlines": [D("2026-09-30")], "cycle_status": "closed",
     "funding_class": "not_stated"},
     evidence={"nationality": "British citizens and any nationals from the EEA are [eligible] ... Anyone of any nationality who has a doctorate from a UK university is eligible ... 'strong prior association' (a mix of rules)",
               "deadlines": "The deadline for submissions and UK institutional approval is Wednesday 30 September 2026 (17:00 BST).",
               "cycle_status": "Closed for applications", "funding_class": "the Academy funds 80 per cent of salary costs ... under FEC (a salaried post)"},
     ambiguous="nationality is open to several groups at once; funding is 80 % of salary costs"),
})
AMB.update({"int-hfsp": ["deadlines"], "int-ba-postdoc": ["nationality", "funding_class"]})
P["ca-mitacs"] = dict(fields={"nationality": "not_stated", "levels": ["bachelor"], "deadlines": [], "cycle_status": "closed",
     "components": {"travel": "covered", "accommodation": "covered", "tuition": "covered", "living_allowance": "covered"},
     "funding_class": "fully_funded"},
     evidence={"nationality": "international undergraduates from the following countries and regions (country of study, see eligible institutions by country)",
               "cycle_status": "The Globalink Research Internship (GRI) call for Summer 2027 student applications has now concluded",
               "funding_class": "round-trip airfare ... Stipend for housing ... Stipend towards student enrollment fees ... Stipend for food and incidentals"},
     ambiguous="a research internship; the country list is where the student studies, not citizenship")
AMB["ca-mitacs"] = ["nationality", "funding_class"]
X.update({"int-isdb": "several programmes, page text for a past cycle", "gh-ashesi-schol": "overview of need-based aid"})
X.update({"za-uct-schol": "funding overview by faculty", "au-flinders-intl": "scholarship search page", "au-utas-intl": "list of scholarships",
          "au-jcu-intl": "support overview", "ca-carleton-intl": "awards index"})
P.update({
 "sa-kfupm-schol": dict(fields={"nationality": "not_stated", "levels": ["master", "phd"], "deadlines": [], "cycle_status": "not_stated",
     "tuition": "full", "components": {"tuition": "full", "stipend": "covered", "accommodation": "covered", "travel": "covered", "insurance": "covered"},
     "funding_class": "fully_funded"},
     evidence={"funding_class": "admitted as Full-time MS or Ph.D. students with a full scholarship ... Stipend according to category ... on-campus housing ... Free study, No tuition fee."}),
 "us-pickering": dict(fields={"nationality": "not_stated", "levels": ["master"], "deadlines": [], "cycle_status": "not_announced",
     "funding_class": "not_stated"},
     evidence={"cycle_status": "The 2026 application cycle ... has been postponed pending updates from the U.S. Department of State.",
               "funding_class": "The fellowship helps finance two-year graduate programs (components not stated)"}),
})
X.update({"kr-postech-schol": "several scholarship types, domestic and international", "us-udall": "PDF without readable text",
          "de-leuphana-schol": "overview of scholarship providers", "uk-rgu-intl": "another university's page about the Gilman programme"})
P.update({
 "tw-ntust-schol": dict(fields={"nationality": {"mode": "exclude", "countries": ["CN"]}, "levels": ["master", "phd"], "deadlines": [],
     "cycle_status": "not_stated", "components": {"tuition": "covered", "stipend": "covered"}, "funding_class": "fully_funded"},
     evidence={"nationality": "International students ... (excluding overseas Chinese students, students from China and exchange students)",
               "funding_class": "may include a one-year waiver of tuition and fees ... full-scholarships for master's programs: Monthly stipends of NT$ 12,000"},
     ambiguous="'may include' a tuition waiver; 'overseas Chinese students' is a status, not a country"),
 "vn-vinuni-schol": dict(fields={"nationality": "not_stated", "levels": ["master", "phd"], "deadlines": [], "cycle_status": "closed",
     "tuition": "full", "components": {"tuition": "covered", "living_allowance": "covered", "insurance": "covered", "travel": "covered"},
     "funding_class": "fully_funded"},
     evidence={"cycle_status": "Application form for the Vingroup Scholarship Program is currently close ... Applications for AY 2026-2027 are closed!",
               "funding_class": "Vingroup scholarships cover tuition fee, monthly living stipend, health insurance, return airfare, visa application fee, allowances, and other costs of attendance for the whole standard duration"},
     ambiguous="the page also lists sibling Vingroup programmes (doctoral, SMU, NTU)"),
 "dk-sdu-schol": dict(fields={"nationality": {"mode": "exclude", "countries": EEA}, "levels": ["bachelor", "master"], "deadlines": [],
     "cycle_status": "not_stated", "tuition": "full", "components": {"tuition": "full"}, "funding_class": "tuition_funded"},
     evidence={"nationality": "you must be a non-EU/EEA citizen enrolling in one of the following master programmes",
               "funding_class": "The scholarship is granted as a full tuition fee waiver and will cover the tuition fee for two years"},
     ambiguous="the admission deadline 'March 15' has no year"),
})
AMB.update({"tw-ntust-schol": ["funding_class"], "vn-vinuni-schol": ["nationality"], "dk-sdu-schol": ["deadlines"]})
X["fr-hec-schol"] = "several HEC scholarships on one page"
X.update({"si-unilj-schol": "list of scholarships", "in-ashoka-schol": "navigation page", "mx-tec-schol": "several scholarships",
          "us-boren": "study-programme selection page", "be-ulb-schol": "programme navigation", "be-uclouvain-schol": "enrolment navigation"})
P.update({
 "is-hi-schol": dict(fields={"nationality": "not_stated", "deadlines": [], "cycle_status": "not_stated", "funding_class": "not_stated"},
     evidence={"nationality": "Styrkir skulu veittir starfsmönnum eða nemendum Háskóla Íslands (staff or students of the University of Iceland; no nationality rule)",
               "cycle_status": "Einungis er opið fyrir umsóknir á auglýstum umsóknartíma (open only in advertised periods; none stated)"}),
 "tr-metu-schol": dict(fields={"nationality": "not_stated", "deadlines": [], "cycle_status": "not_stated", "tuition": "partial",
     "funding_class": "partially_funded"},
     evidence={"nationality": "tuition discounts or exemptions for international students (scope)",
               "funding_class": "Our University provides tuition discounts or exemptions for international students according to their academic success."},
     ambiguous="'discounts or exemptions': an exemption is full; the page also lists meal and dormitory scholarships"),
 "us-goldwater": dict(fields={"nationality": "not_stated", "levels": ["bachelor"], "deadlines": [], "cycle_status": "not_stated",
     "funding_class": "not_stated"},
     evidence={"deadlines": "Last Friday in January · 5:00 p.m. Central Time (no year)",
               "nationality": "(not stated on this page)"}),
})
AMB["tr-metu-schol"] = ["funding_class"]
X.update({"qa-qu-schol": "overview of scholarship types", "fr-unistra-schol": "university page about the Eiffel programme and others",
          "uk-westminster-fis": "list of awards", "uk-bangor-intl": "table of awards by country", "uk-port-intl": "summary of many scholarships",
          "uk-ulster-intl": "navigation", "fr-uga-schol": "overview", "tw-nycu-schol": "PDF without readable text", "cn-zju-schol": "list",
          "ca-umontreal-schol": "tuition rules page", "au-unisa-schol": "PDF without readable text", "au-uow-schol": "list", "nz-aut-schol": "list",
          "jp-hiroshima-schol": "navigation", "kr-skku-schol": "navigation", "jp-nagoya-schol": "list by programme", "ca-queensu-schol": "overview",
          "ca-umanitoba-schol": "list", "uk-coventry-intl": "fees overview", "uk-uea-intl": "portal", "es-uc3m-schol": "a master's course page",
          "hu-elte-schol": "list", "lt-vu-schol": "finance overview", "uk-reading-vc": "2020 staff news item", "uk-cranfield-schol": "blog post",
          "de-konstanz-schol": "study portal", "it-luiss-schol": "foundation home page", "it-unive-schol": "application portal",
          "fr-essec-schol": "foundation home page", "ch-unibe-schol": "a thesis PDF", "ch-unifr-schol": "short overview", "no-nhh-schol": "empty page",
          "pl-uj-schol": "repository download stub", "jp-sophia-schol": "law-school scholarship notes in Japanese (several)",
          "my-utm-schol": "home page", "id-ugm-schol": "office home page", "cl-uc-schol": "donations page"})
P.update({
 "au-bond-intl": dict(fields={"nationality": "not_stated", "levels": ["bachelor", "master"], "deadlines": [], "cycle_status": "rolling",
     "tuition": "partial", "funding_class": "partially_funded"},
     evidence={"nationality": "Be an offshore international student (ie not an Australian citizen, New Zealand citizen or permanent resident) with citizenship from a country listed above, or an international student currently residing in Australia (any nationality).",
               "cycle_status": "Applications for Bond programs are always open",
               "funding_class": "you will be awarded with 25% tuition remission"},
     ambiguous="nationality is a listed country OR any nationality when already in Australia"),
 "us-truman": dict(fields={"nationality": {"mode": "include", "countries": ["US"]}, "levels": ["bachelor"], "deadlines": [],
     "cycle_status": "not_stated", "funding_class": "not_stated"},
     evidence={"nationality": "US Citizens, US National residents of American Samoa, or expecting their citizenship by the date of the award"},
     ambiguous="US nationals resident in American Samoa are also eligible"),
 "nz-fulbright": dict(fields={"nationality": {"mode": "include", "countries": ["US"]}, "levels": ["master", "phd"], "deadlines": [],
     "cycle_status": "not_stated", "funding_class": "not_stated"},
     evidence={"nationality": "Fulbright US Graduate Awards are for promising American graduate students (the citizenship section is collapsed)",
               "funding_class": "Up to eight awards valued at up to NZ$49,000 ... towards one year of study or research (components not stated)"},
     ambiguous="the rule is a demonym in a description, the citizenship section is not expanded"),
})
AMB.update({"au-bond-intl": ["nationality"], "us-truman": ["nationality"], "nz-fulbright": ["nationality"]})
X.update({"us-iit-intl": "several institutional and donor scholarships", "hr-unizg": "another country's programme posted by Zagreb"})
SFF = ["AF", "GT", "NI", "AO", "GN", "NE", "BD", "GW", "PS", "BZ", "HT", "PG", "BJ", "HN", "PH", "BT", "ID", "RW", "BO", "IQ", "WS",
       "BW", "CI", "ST", "BF", "JM", "SN", "BI", "KE", "SL", "KH", "KI", "SB", "CM", "KG", "SO", "CV", "LA", "SS", "CF", "LS", "SD",
       "TD", "LR", "SR", "KM", "LY", "SY", "CG", "MG", "TJ", "CD", "MW", "TZ", "DJ", "ML", "TL", "SV", "MH", "TG", "GQ", "MR", "TV",
       "ER", "FM", "UG", "SZ", "MA", "UZ", "ET", "MZ", "VU", "FJ", "MM", "VE", "GA", "NA", "YE", "GM", "NR", "ZM", "GH", "NP", "ZW"]
P.update({
 "us-churchill": dict(fields={"nationality": {"mode": "include", "countries": ["US"]}, "levels": ["master"],
     "deadlines": [D("2026-11-02", "current")], "cycle_status": "open", "tuition": "full",
     "components": {"tuition": "covered", "travel": "covered", "stipend": "covered"}, "funding_class": "fully_funded"},
     evidence={"nationality": "An applicant for the Churchill Scholarship must be a citizen of the United States, either native-born or naturalized",
               "deadlines": "Monday, November 2, 2026, at 5pm Eastern Time.",
               "funding_class": "The award covers tuition, roundtrip airfare to the UK, visa fees and health surcharge, and a stipend"}),
 "us-peo-ips": dict(fields={"nationality": {"mode": "exclude", "countries": ["CA", "US"]}, "levels": ["master", "phd"], "deadlines": [],
     "cycle_status": "open", "funding_class": "not_stated"},
     evidence={"nationality": "Women outside the United States and Canada who are seeking advanced degrees",
               "cycle_status": "Applications are accepted through December 15.",
               "funding_class": "The maximum award amount is $12,500 (components not stated)"},
     ambiguous="'outside the United States and Canada' is where applicants are, not strictly citizenship; December 15 has no year"),
 "int-zonta": dict(fields={"nationality": {"mode": "any", "countries": []}, "levels": ["phd"], "deadlines": [D("2026-11-15", "current")],
     "cycle_status": "open", "funding_class": "not_stated"},
     evidence={"nationality": "Women of any nationality pursuing a Ph.D./doctoral degree ... are eligible.",
               "deadlines": "The 2027 Amelia Earhart Fellowship application must be submitted in full by 15 November 2026",
               "funding_class": "a US$12,000 Amelia Earhart Fellowship to support their advanced studies (components not stated)"}),
 "int-sff": dict(fields={"nationality": {"mode": "include", "countries": SFF}, "deadlines": [], "cycle_status": "not_stated",
     "funding_class": "not_stated"},
     evidence={"nationality": "are a female and are a citizen of a low or middle income country ... 2026-2027 ELIGIBLE COUNTRIES Afghanistan Guatemala ..."},
     ambiguous="dual citizens of a developed country are excluded"),
 "cz-cvut": dict(fields={"nationality": "not_stated", "levels": ["master", "phd"], "deadlines": [], "cycle_status": "not_stated",
     "stipend": {"amount": [10000, 16000], "currency": "CZK", "period": "month"}, "funding_class": "stipend_only"},
     evidence={"nationality": "foreign students (status, not a nationality list)",
               "funding_class": "a contribution towards covering the costs for a stay in the Czech Republic up to an amount of CzK 10 000 per month"},
     ambiguous="two schemes on one page (master's and doctoral)"),
 "jp-jds": dict(fields={"nationality": "not_stated", "levels": ["master"], "deadlines": [], "cycle_status": "open", "funding_class": "not_stated"},
     evidence={"nationality": "Click here to see information about your country (eligible countries elsewhere)",
               "cycle_status": "Oct 13, 2026 Application for JDS Maldives 2026 is now open. ... Application for JDS Bhutan 2026 is now open.",
               "deadlines": "the dated lines are news dates (announcements), not deadlines"},
     ambiguous="open for some countries, closed for others"),
})
AMB.update({"us-peo-ips": ["nationality", "cycle_status"], "int-sff": ["nationality"], "cz-cvut": ["funding_class"], "jp-jds": ["cycle_status"]})
X.update({"int-moibrahim": "two programmes on one page", "sk-stuba": "list of scholarship types"})
X.update({"sg-singa": "applicant portal login", "gr-iky-schol": "list of scholarships", "lu-unilu-schol": "a publication record",
          "au-vu-intl": "list", "au-murdoch-intl": "list", "au-ecu-intl": "list of offers", "us-berea-intl": "college home page",
          "ca-mcmaster-intl": "overview", "ca-usask-intl": "list", "ca-mun-intl": "funding overview", "us-luce": "page about current scholars",
          "za-allangray": "foundation home page", "int-santander": "portal of many calls", "int-imf-japan": "IMF home page",
          "int-osf": "grants overview", "ru-education": "empty page", "jp-jica": "report PDF stub", "my-taylors": "list of scholarships",
          "mt-um": "university home page"})

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
(M / "labels.json").write_text(json.dumps({"today": "2026-10-19", "version": "M-1",
    "note": "programme decisions labelled by hand from the official pages before any extractor ran on them; quotes per field",
    "pages": pages}, indent=1, ensure_ascii=False) + "\n")
print(len(pages), "labelled (all test);", sum(1 for p in urls["pages"] if p["split"] == "excluded"), "excluded")
