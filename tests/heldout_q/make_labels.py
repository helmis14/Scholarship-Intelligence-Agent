"""Set Q labels (round 33), written by hand from the official pages in pages/ before any extractor ran on set Q.

Set Q is the frozen test set for the round-33 rules (nationality definitions and procedural sentences, cycle states,
funding sentences that are questions or instructions) and the round-32 funding-class rules. Unlike sets L to P it holds
no university pages: the funders are governments, foundations, companies, research councils and binational
commissions. The round-33 code was finished before any set-Q page was fetched (2026-10-20), and nothing on set Q was
used to change a rule. Labels follow the reading of sets L to P: fee status, residence, visa status, "international
students", "foreign students" and definitions are "not_stated" nationality; "fully_funded" needs tuition and living costs
both covered (or the page says so outright); a stated discount, share or cap is "partially_funded"; a cash award whose
use is not stated is "not_stated" funding unless it is paid per month (then "stipend_only"; per year or semester is a
close call); deadlines are applicant deadline dates with a year for this programme; cycle_status as of 2026-10-20. Pages
listing several awards, home pages, news, guidance, PDFs and pages not reviewed are excluded with the reason recorded.
Close calls are recorded per decision in AMB ("ambiguous_fields"); results are reported with and without them.
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
 "de-gerda-henkel": dict(fields={"nationality": {"mode": "any", "countries": []}, "levels": ["phd"], "deadlines": [], "cycle_status": "rolling",
     "components": {"stipend": "covered", "travel": "covered"}, "funding_class": "stipend_only"},
     evidence={"nationality": "Scholarships are awarded independently of the applicant's nationality or location",
               "cycle_status": "The application can be submitted at any time (no deadline)",
               "funding_class": "Monthly scholarship award: 1,920 euros ... no college or tuition fees"}),
 "in-aditya-birla": dict(fields={"nationality": "not_stated", "levels": ["bachelor", "master"], "deadlines": [], "cycle_status": "not_stated",
     "components": {"tuition": "partial", "accommodation": "covered"}, "funding_class": "partially_funded"},
     evidence={"funding_class": "The Aditya Birla Scholarships cover a large part of academic fees as well as the hostel fees for the engineering stream and partly the tuition fee for the management and law streams"},
     ambiguous="students of named Indian institutions only; no nationality rule stated"),
 "in-fulbright-nehru": dict(fields={"nationality": "not_stated", "levels": ["master"], "deadlines": [D("2025-05-14")], "cycle_status": "closed",
     "components": {"tuition": "full", "living_allowance": "covered", "travel": "covered", "insurance": "covered"}, "funding_class": "fully_funded"},
     evidence={"nationality": "Must have completed an equivalent of a U.S. bachelor's degree from a recognized Indian university (an Indian degree, not Indian citizenship, on this page)",
               "deadlines": "Application Deadline: May 14, 2025, 23:59:59 hrs (IST)",
               "funding_class": "funding for tuition and fees, living and related costs, and accident and sickness coverage ... USIEF funding may not cover all costs"},
     ambiguous="the general prerequisites (Indian citizenship) are on another page; 'may not cover all costs'"),
 "jp-honjo": dict(fields={"nationality": "not_stated", "levels": ["master", "phd"], "deadlines": [D("2026-10-31", "current")], "cycle_status": "open",
     "openings": ["2026-09-01"], "components": {"stipend": "covered"}, "funding_class": "stipend_only"},
     evidence={"nationality": "This scholarship is open to foreign students who study or plan to study in a Japanese graduate school (foreign students, not a nationality list)",
               "deadlines": "Application period: 11am on September 1, 2026 ~ October 31, 2026",
               "cycle_status": "September 1, 2026 ~ October 31, 2026 | Application period",
               "funding_class": "The scholarship will be provided monthly ... ¥230,000 per month for 1 ~ 2 years degree (tuition not mentioned)"}),
 "ph-ched-scholarship": dict(fields={"nationality": {"mode": "include", "countries": ["PH"]}, "levels": ["bachelor"], "deadlines": [D("2025-06-20")],
     "cycle_status": "closed", "components": {"tuition": "full", "stipend": "covered"}, "funding_class": "fully_funded"},
     evidence={"nationality": "ELIGIBILITY REQUIREMENTS: Filipino Citizen",
               "deadlines": "The deadline for submission is on June 20, 2025.",
               "cycle_status": "CHED Merit Scholarship Program for incoming or current first-year college students for AY 2025-2026 is now CLOSED!",
               "funding_class": "This scholarship program shall cover tuition and other school fees (TOSF), stipend which shall be released directly to the scholars ..., and book connectivity allowance"}),
 "sa-kaust-fellowship": dict(fields={"nationality": "not_stated", "levels": ["postdoc"], "deadlines": [], "cycle_status": "not_stated",
     "components": {"stipend": "covered", "research": "covered", "insurance": "covered", "accommodation": "covered"}, "funding_class": "stipend_only"},
     evidence={"funding_class": "Global Fellows receive up to $40,000 in dedicated research funding ..., along with a yearly living stipend of $75,000 plus a comprehensive benefits package, including medical insurance, on-campus housing"},
     ambiguous="a postdoctoral fellowship: there is no tuition to cover, so the classes fit poorly"),
})
AMB.update({"in-aditya-birla": ["nationality"], "in-fulbright-nehru": ["nationality", "funding_class"], "sa-kaust-fellowship": ["funding_class"]})
X.update({"ca-sbw-elap": "institutions apply, not students", "de-hss": "home page", "de-thyssen": "home page", "de-volkswagen": "list of fellows",
          "eg-mohe-scholarships": "ministry home page", "id-astra": "news", "id-sampoerna": "home page", "id-tahir": "home page",
          "id-van-deventer": "near-empty page", "int-adb-jsp": "unrelated page", "jp-nippon-foundation": "workshop page", "lb-hopes": "home page",
          "mx-conahcyt-extranjero": "near-empty page", "my-mis": "FAQ", "my-mtcp": "near-empty page", "my-sime-darby": "several scholarships",
          "np-moest": "unrelated document", "pk-punjab-peef": "home page", "qa-qf-scholarship": "home page", "rw-hec": "list", "sg-singa": "news article",
          "bd-pm-fellowship": "login page", "az-state-program": "PDF (to check)", "lk-presidential": "PDF (to check)"})
P.update({
 "zw-beit-trust": dict(fields={"nationality": {"mode": "include", "countries": ["MW", "ZM", "ZW"]}, "levels": ["master"],
     "deadlines": [D("2027-02-12", "current")], "openings": ["2026-12-01"], "cycle_status": "upcoming",
     "components": {"tuition": "full", "living_allowance": "covered"}, "funding_class": "fully_funded"},
     evidence={"nationality": "the Beit Trust supports only applicants who: Are nationals of Zambia, Zimbabwe, or Malawi. Are permanent residents of one of these countries.",
               "deadlines": "The next application window will be as follows: Open: 1 December 2026. Close: 12 February 2027. No applications can be processed after this date.",
               "cycle_status": "Open: 1 December 2026",
               "funding_class": "Full tuition and academic fees, paid directly to the university. Living allowance. Additional allowances for Arrival, Laptop, Departure."}),
})
X.update({"gr-bodossaki": "several programmes (postgraduate, postdoctoral, visiting)", "mx-funed": "loan tiers, several programmes", "do-mescyt": "ministry page",
          "es-mujeres-africa": "2023 registration page, near-empty", "et-moe": "PDF (unrelated)", "gh-mastercard-ashesi": "business incubation programme",
          "it-cariplo": "foundation home page", "it-crui": "news", "it-maeci": "near-empty page", "ng-nnpc-total": "near-empty page", "ng-shell-spdc": "empty page"})
P.update({
 "ar-fulbright": dict(fields={"nationality": {"mode": "include", "countries": ["AR"]}, "levels": ["master", "phd"],
     "deadlines": [D("2026-03-25")], "openings": ["2026-01-30"], "cycle_status": "closed",
     "components": {"stipend": "covered", "travel": "covered", "insurance": "covered", "tuition": "not_covered"}, "funding_class": "stipend_only"},
     evidence={"nationality": "Tener ciudadanía argentina (ser ciudadano argentino nativo o naturalizado). ... No son elegibles quienes posean doble nacionalidad, argentina y estadounidense",
               "deadlines": "Cierre de la convocatoria: miércoles 25 de marzo de 2026 (inclusive)",
               "cycle_status": "Apertura de la convocatoria: viernes 30 de enero de 2026 ... Cierre de la convocatoria: miércoles 25 de marzo de 2026 (inclusive)",
               "funding_class": "Las becas cubren pasaje de ida y vuelta, estipendio mensual para manutención hasta $3,231 ..., una cobertura de salud de emergencias, y la asistencia en el proceso de admisión y en la búsqueda de ayuda económica total o parcial para matrícula y aranceles (tuition is not paid by the grant)"},
     ambiguous="the 2027-28 call is described but its dates are the 2026 ones; dual AR-US citizens are excluded"),
})
AMB.update({"ar-fulbright": ["cycle_status"]})
P.update({
 "dk-novo-nordisk": dict(fields={"nationality": "not_stated", "levels": ["postdoc"], "deadlines": [D("2026-08-20")], "openings": ["2026-06-04"],
     "cycle_status": "closed", "funding_class": "not_stated"},
     evidence={"nationality": "Nordic Countries (incl. Denmark) (where the research is hosted, not the applicant's nationality)",
               "deadlines": "Call closes 20 August 2026 2:00pm (Copenhagen time)",
               "funding_class": "Up to DKK 3.3 million per grant (a research grant; what it pays for is not stated on this page)"},
     ambiguous="a research grant for postdocs; the funding classes fit poorly"),
 "uk-nuffield": dict(fields={"nationality": "not_stated", "levels": ["phd"], "deadlines": [], "cycle_status": "closed", "funding_class": "not_stated"},
     evidence={"deadlines": "Applicants should complete the application before the deadline at 23:55 on 23 March (no year; interviews April 2026)",
               "cycle_status": "Applications for POST Fellowships are closed.",
               "funding_class": "Successful applicants will receive a grant totalling £8,000 paid in two instalments (a cash grant)"},
     ambiguous="a deadline without a year; a cash grant"),
 "us-davis-putter": dict(fields={"nationality": "not_stated", "levels": ["bachelor"], "deadlines": [], "cycle_status": "not_stated", "funding_class": "not_stated"},
     evidence={"deadlines": "Application Deadline: April 1 (no year)",
               "funding_class": "The maximum grant available is $15,000 per year ..., however the average grant for 2025-26 was $7,700 (what it pays for is not stated)"},
     ambiguous="degree, trade or technical programmes of any level; a yearly deadline without a year; a yearly cash grant"),
 "de-daimler-benz": dict(fields={"nationality": "not_stated", "levels": ["postdoc"], "deadlines": [D("2026-09-30"), D("2027-09-30", "current")],
     "openings": ["2026-06-01", "2027-06-01"], "cycle_status": "upcoming", "funding_class": "not_stated"},
     evidence={"deadlines": "Die Bewerbungsfrist für 2027 ist am 30.09.2026 abgelaufen. ... Bewerbungen sind ab diesem Zeitpunkt bis einschließlich 30.09.2027 möglich.",
               "cycle_status": "Das Online-Portal für Bewerbungen im Stipendienprogramm für Postdoktoranden 2028 wird ab dem 01.06.2027 zur Verfügung stehen."},
     ambiguous="the current call has closed and the next opens in 2027: closed or upcoming"),
})
AMB.update({"dk-novo-nordisk": ["funding_class"], "uk-nuffield": ["deadlines", "funding_class"], "us-davis-putter": ["levels", "deadlines", "funding_class"],
            "de-daimler-benz": ["cycle_status"]})
X.update({"de-bosch": "fellowship for leaders, not a study award", "de-fazit": "checklist", "de-hertie": "list of fellows", "dk-lundbeck": "grants to research groups",
          "fr-axa-research": "PDF (to check)", "fr-bettencourt": "several prizes", "fr-fondation-france": "guidance page", "fr-ile-de-france": "PDF (to check)",
          "fr-loreal-fwis": "overview of 50 programmes", "uk-churchill-fellowship": "post-learning grant for fellows", "uk-rotary-global-grant": "guide",
          "uk-saltire": "list", "uk-sasakawa": "small project grants", "uk-sutton-trust": "summer schools", "uk-ukri-fellowship": "institutional fellowship",
          "us-echoing-green": "fellowship for entrepreneurs", "us-guggenheim": "fellowship for established scholars", "us-nasa-fineSST": "institutional proposals",
          "us-neh-fellowships": "news", "us-russell-sage": "visiting scholars", "us-watson": "travel fellowship, not a study award"})
P.update({
 "de-dfg-emmy-noether": dict(fields={"nationality": "not_stated", "levels": ["postdoc"], "deadlines": [], "cycle_status": "rolling", "funding_class": "not_stated"},
     evidence={"nationality": "Applicants from abroad are expected to continue their research careers in Germany after the funding comes to an end (no nationality rule)",
               "cycle_status": "Proposal Deadlines: Proposals may be submitted at any time.",
               "funding_class": "Type and Extent of Funding (a junior research group's budget; no classes of student support stated)"},
     ambiguous="research-group funding; the funding classes fit poorly"),
})
AMB.update({"de-dfg-emmy-noether": ["funding_class"]})
P.update({
 "be-fwo": dict(fields={"nationality": "not_stated", "levels": ["phd"], "deadlines": [D("2027-03-01", "current")], "openings": ["2026-12-03"],
     "cycle_status": "upcoming", "components": {"stipend": "covered"}, "funding_class": "stipend_only"},
     evidence={"deadlines": "01 March 2027 at 5pm CET: closing call (last application date)",
               "cycle_status": "03 December 2026: opening call",
               "funding_class": "Grant amount (0 years seniority): € 2,700 /month (index 2.2080 from 1/09/2026)"}),
 "cz-visegrad": dict(fields={"nationality": {"mode": "include", "countries": ["AL", "AM", "AZ", "BA", "BY", "CZ", "GE", "HU", "MD", "ME", "MK", "PL", "RS", "SK", "UA", "XK"]},
     "levels": ["master", "phd", "postdoc"], "deadlines": [D("2027-04-15", "current")], "openings": ["2027-01-01"], "cycle_status": "upcoming",
     "components": {"stipend": "covered"}, "funding_class": "stipend_only"},
     evidence={"nationality": "Their citizenship/residence (CZ, HU, PL, SK or EaP/WB countries) must differ from the host institution's country.",
               "deadlines": "Apr 15, 2027 at 12:00 PM: Final application deadline",
               "cycle_status": "Opens on Jan 1, 2027 at 12:00 PM",
               "funding_class": "Funding: €3,500/semester for scholar + €2,000/semester for the host institution"},
     ambiguous="'EaP/WB countries' are abbreviations (Eastern Partnership, Western Balkans) and citizenship or residence counts; a per-semester cash award"),
 "ch-jacobs": dict(fields={"nationality": "not_stated", "levels": ["postdoc"], "deadlines": [], "cycle_status": "closed", "funding_class": "not_stated"},
     evidence={"cycle_status": "Closed ... The 2027 call for applications opens on 24 November.",
               "deadlines": "The call for applications is posted each year by the end of November with a deadline in early February (no date)",
               "funding_class": "Funding from Jacobs CIFAR Research Fellowships is awarded directly to the fellow's institution (amount and use not stated)"},
     ambiguous="closed now, the next call opens 24 November (no year); research funding"),
})
AMB.update({"cz-visegrad": ["nationality", "funding_class"], "ch-jacobs": ["cycle_status", "funding_class"]})
X.update({"be-fnrs": "near-empty page", "ch-snsf-postdoc": "regulations document", "fi-kone": "guidance page", "fi-kordelin": "list of grants",
          "fi-skr": "instructions", "fi-wihuri": "list of projects", "hr-ministry-scholarship": "several categories, 2020 call",
          "lt-state-scholarship": "2024/25 Italian government call in Lithuanian, several categories", "nl-prins-bernhard": "project grant",
          "no-forskningsradet": "research programme call", "ro-mae-scholarship": "visa page", "rs-world-in-serbia": "unrelated page",
          "se-kempe": "foundation page with grants", "se-wallenberg": "list of fellows"})
P.update({
 "au-fulbright": dict(fields={"nationality": {"mode": "include", "countries": ["AU"]}, "levels": ["master"], "deadlines": [], "cycle_status": "closed",
     "components": {"stipend": "covered", "travel": "covered", "tuition": "partial"}, "funding_class": "partially_funded"},
     evidence={"nationality": "Must be an Australian citizen. Must not be a dual citizen of the U.S.",
               "cycle_status": "Applications are now closed.",
               "funding_class": "Valued at USD $75K for one-year Master's programs ... The award includes a monthly stipend for the program duration; round-trip, economy class airfares ... Fulbright Australia works with IIE to seek tuition waivers, which may be full or partial"},
     ambiguous="tuition waivers 'may be full or partial': partially or fully funded"),
 "ca-fqrnt": dict(fields={"nationality": "not_stated", "levels": ["master"], "deadlines": [], "cycle_status": "not_stated", "funding_class": "not_stated"},
     evidence={"funding_class": "La valeur annuelle de la bourse de maîtrise est de 20 000 $. Le montant maximal pouvant être alloué est de 40 000 $ (what it pays for is not stated)"},
     ambiguous="a yearly cash award; the residence rules are in the programme rules, not on this page"),
 "ca-trudeau": dict(fields={"nationality": "not_stated", "levels": ["phd"], "deadlines": [], "cycle_status": "not_stated",
     "components": {"tuition": "full", "living_allowance": "covered", "research": "covered", "travel": "covered"}, "funding_class": "fully_funded"},
     evidence={"funding_class": "Recevez jusqu'à 50 000 $ par année pendant trois ans pour couvrir les frais de scolarité et de subsistance liée à vos études doctorales. ... jusqu'à 20 000 $ par année ... recherche ... déplacements"},
     ambiguous="tuition and living costs are covered up to a yearly cap: fully or partially funded"),
 "nz-woolf-fisher": dict(fields={"nationality": "not_stated", "levels": ["phd"], "deadlines": [], "cycle_status": "not_stated",
     "components": {"tuition": "full", "stipend": "covered"}, "funding_class": "fully_funded"},
     evidence={"nationality": "Awarded to up to three outstanding New Zealand graduate students each year ... first-class honours degree from a New Zealand university (a degree, not a citizenship rule, on this page)",
               "funding_class": "a stipend of £21,500 per annum; payment of approved University and College fees"},
     ambiguous="'New Zealand graduate students' may mean citizenship elsewhere in the rules"),
 "us-apsa": dict(fields={"nationality": "not_stated", "levels": ["phd"], "deadlines": [], "cycle_status": "not_stated", "funding_class": "not_stated"},
     evidence={"funding_class": "awards between 12 and 14 funded fellowships in the amount of $5,000 over two years to students applying to doctoral programs (a cash award)"},
     ambiguous="a cash award"),
 "us-hispanic-heritage": dict(fields={"nationality": "not_stated", "levels": ["bachelor"], "deadlines": [D("2026-11-01", "current")], "cycle_status": "open",
     "funding_class": "not_stated"},
     evidence={"deadlines": "Deadline: November 1st, 2026",
               "funding_class": "receive a one-time innovation grant to fund their college education or support a community service effort (amount not stated)"},
     ambiguous="the cycle is read from a future deadline; the page does not say 'open'"),
 "us-shpe": dict(fields={"nationality": {"mode": "any", "countries": []}, "levels": ["bachelor", "master", "phd"], "deadlines": [D("2026-02-16")],
     "openings": ["2026-02-02"], "cycle_status": "closed", "funding_class": "not_stated"},
     evidence={"nationality": "Citizenship is NOT required for SHPE scholarships. However, some of our sponsor funded scholarships ...",
               "deadlines": "Application opens: February 2, 2026. Application closes: February 16, 2026",
               "funding_class": "(award amounts are not stated on this page)"},
     ambiguous="enrolment in the United States is required; several award categories under one application"),
 "us-soroptimist": dict(fields={"nationality": "not_stated", "levels": ["bachelor"], "deadlines": [], "cycle_status": "not_stated", "funding_class": "not_stated"},
     evidence={"nationality": "Resides in one of Soroptimist International of the Americas' member countries/territories (residence, not nationality)",
               "deadlines": "Eligible applicants can submit their application from August 1 to November 15 (no year)",
               "funding_class": "Recipients have the potential to receive $1,000 - $16,000 to further their education (cash tiers)"},
     ambiguous="a yearly window without a year; cash tiers"),
 "at-marshall-plan": dict(fields={"nationality": "not_stated", "levels": ["bachelor", "master"], "deadlines": [D("2026-10-30", "current"), D("2027-04-30", "current")],
     "openings": ["2026-09-01", "2027-03-01"], "cycle_status": "open", "components": {"travel": "covered"}, "funding_class": "not_stated"},
     evidence={"nationality": "scholarships to Austrian and American students (students of the partner universities; no citizenship rule stated)",
               "deadlines": "Application: September 1, 2026 to October 30, 2026 ... Application: March 1, 2027 to April 30, 2027",
               "cycle_status": "Open Call. Application: September 1, 2026 to October 30, 2026",
               "funding_class": "Stays of 3 months (90 days): €4,000 ... Stays of 5 months (150 days): €6,000 (a research-visit grant)"},
     ambiguous="levels are set by the universities; a research-visit grant"),
 "us-fulbright-us-student": dict(fields={"nationality": {"mode": "include", "countries": ["US"]}, "levels": ["master", "phd"], "deadlines": [],
     "cycle_status": "closed", "funding_class": "not_stated"},
     evidence={"nationality": "Applicants must be citizens or nationals of the United States of America at the time of the application deadline. Permanent residents are not eligible.",
               "cycle_status": "The application for the 2027-2028 Competition is now closed."},
     ambiguous="study, research and teaching grants after a bachelor's degree: the levels fit loosely"),
 "us-whitaker": dict(fields={"nationality": {"mode": "include", "countries": ["US"]}, "levels": ["master"], "deadlines": [], "cycle_status": "not_stated",
     "components": {"living_allowance": "covered", "travel": "covered", "insurance": "covered", "tuition": "partial"}, "funding_class": "fully_funded"},
     evidence={"nationality": "Can non-U.S. citizens apply? Non-citizens may apply as long as they are legal permanent U.S. residents.",
               "funding_class": "The grants will cover cost-of-living expenses (housing, food, transportation, etc.), costs for international travel, health insurance and tuition ... up to a pre-determined limit"},
     ambiguous="an FAQ page; tuition is covered up to a limit; a post-bachelor year abroad"),
 "ca-alberta-innovates": dict(fields={"nationality": {"mode": "any", "countries": []}, "levels": ["master", "phd"], "deadlines": [], "cycle_status": "open",
     "funding_class": "not_stated"},
     evidence={"nationality": "This scholarship program is open to Canadian, permanent resident, and international graduate students conducting full-time research",
               "cycle_status": "Intake Status: Open",
               "funding_class": "The program offers funding ranging from $12,000 to $31,000 per year (what it pays for is not stated)"},
     ambiguous="'Intake Status: Open' without a closing date; a yearly cash award"),
 "de-claussen-simon": dict(fields={"nationality": "not_stated", "levels": ["bachelor"], "deadlines": [], "cycle_status": "not_stated", "funding_class": "not_stated"},
     evidence={"nationality": "Bewerbungsvoraussetzungen für B-First: Sie stehen am Anfang Ihres Studiums ... nicht älter als 25 Jahre (no nationality rule)"}),
 "us-american-indian-college-fund": dict(fields={"nationality": "not_stated", "levels": ["bachelor"], "deadlines": [], "cycle_status": "not_stated", "funding_class": "not_stated"},
     evidence={"nationality": "open to most enrolled California tribal members (tribal membership, not nationality)",
               "deadlines": "APPLICATION DEADLINE IS MAY 31st (no year)",
               "funding_class": "Up to $20,000 is available each year to students seeking vocational, associates or bachelors degrees (what it pays for is not stated)"},
     ambiguous="a yearly deadline without a year; a yearly cash award"),
})
AMB.update({"au-fulbright": ["funding_class"], "ca-fqrnt": ["funding_class"], "ca-trudeau": ["funding_class"], "nz-woolf-fisher": ["nationality"],
            "us-apsa": ["funding_class"], "us-hispanic-heritage": ["cycle_status"], "us-shpe": ["nationality"], "us-soroptimist": ["deadlines", "funding_class"],
            "at-marshall-plan": ["levels", "funding_class"], "us-fulbright-us-student": ["levels"], "us-whitaker": ["funding_class"],
            "ca-alberta-innovates": ["cycle_status", "funding_class"], "us-american-indian-college-fund": ["deadlines", "funding_class"]})
X.update({"ca-terry-fox": "merchandise page", "ch-swiss-study-foundation": "workshop page", "de-dr-hans-riegel": "near-empty page", "de-haniel": "overview",
          "de-mawista": "discontinued award", "nl-fulbright": "guide to athletic scholarships", "us-jet-programme": "employment programme",
          "be-vocatio": "grant for personal projects, not a study award"})
P.update({
 "bd-dutch-bangla": dict(fields={"nationality": "not_stated", "levels": ["bachelor"], "deadlines": [], "cycle_status": "not_stated",
     "components": {"stipend": "covered"}, "funding_class": "stipend_only"},
     evidence={"nationality": "awarding scholarships to meritorious students in need of financial aid studying at higher secondary and graduation levels (Bangladeshi institutions; no citizenship rule stated)",
               "funding_class": "Monthly Scholarship (Taka) ... Annual grant for reading materials (Taka) ... Annual grant for clothing (Taka)"},
     ambiguous="SSC-2026 batch, i.e. students entering higher secondary and then graduation level; amounts in a table"),
 "id-baznas": dict(fields={"nationality": {"mode": "include", "countries": ["ID"]}, "levels": ["bachelor"], "deadlines": [], "cycle_status": "not_stated",
     "components": {"tuition": "partial", "research": "covered"}, "funding_class": "partially_funded"},
     evidence={"nationality": "persyaratan dokumen ...: 1. Warga Negara Indonesia (WNI)",
               "cycle_status": "Beasiswa Cendekia BAZNAS Dalam Negeri 2025 Dibuka (a news item of 05/08/2025; no closing date)",
               "funding_class": "Beasiswa ini mencakup bantuan UKT/SPP maksimal Rp4 juta per semester selama 4 semester, bantuan biaya riset sebesar Rp3 juta"},
     ambiguous="a 2025 opening announcement without a closing date: not stated or closed"),
 "in-icssr": dict(fields={"nationality": {"mode": "include", "countries": ["IN"]}, "levels": ["phd"], "deadlines": [], "cycle_status": "not_stated",
     "components": {"stipend": "covered", "research": "covered"}, "funding_class": "stipend_only"},
     evidence={"nationality": "Doctoral Fellowships shall be awarded to Indian research scholars, who are registered for Ph.D. in UGC recognized Universities",
               "cycle_status": "ICSSR announces calls for Doctoral Fellowships every year",
               "funding_class": "The value of Full-Term Doctoral Fellowship is Rs 20,000 per month plus Rs 20,000 contingency grant per annum"},
     ambiguous="'Indian research scholars' read as a nationality rule"),
 "jp-atsumi": dict(fields={"nationality": "not_stated", "levels": ["phd"], "deadlines": [], "cycle_status": "not_stated",
     "components": {"stipend": "covered"}, "funding_class": "stipend_only"},
     evidence={"nationality": "recruiting Atsumi Scholars for international students and Japanese students enrolled in the Ph.D. programs at graduate schools in the Kanto region",
               "deadlines": "Application documents should be (postal) mailed to the Atsumi Foundation Secretariat every year from September 1st to 30th (no year)",
               "funding_class": "The Atsumi Scholarship is 250,000 yen per month and will be provided to 16 people"},
     ambiguous="a yearly window without a year"),
 "jp-jees": dict(fields={"nationality": "not_stated", "levels": ["bachelor", "master", "phd"], "deadlines": [D("2026-05-20")], "cycle_status": "closed",
     "components": {"stipend": "covered"}, "funding_class": "stipend_only"},
     evidence={"nationality": "providing financial support to self-funded international students enrolled at Japanese universities (status, not nationality; the nationality section is not readable in the text)",
               "deadlines": "Submission Deadline: Wednesday, May 20, 2026",
               "funding_class": "Monthly amount ... The monthly amount for students selected in 2025 will be 40,000 JPY until the end of the scholarship period"},
     ambiguous="'Applicant's nationality' is a heading whose content did not survive extraction"),
 "ph-sm-foundation": dict(fields={"nationality": "not_stated", "levels": ["bachelor"], "deadlines": [D("2026-02-28")], "openings": ["2026-02-01"],
     "cycle_status": "closed", "components": {"tuition": "full", "stipend": "covered"}, "funding_class": "fully_funded"},
     evidence={"deadlines": "SM College Scholarship Online Application Period: Feb 1-28, 2026",
               "funding_class": "Our College Scholars enjoy: Full Tuition, Monthly Allowance"},
     ambiguous="the page still shows 'Apply Now' beside a past window; the technical-vocational scholarship shares the page"),
 "sg-temasek": dict(fields={"nationality": "not_stated", "levels": ["bachelor"], "deadlines": [], "cycle_status": "not_stated",
     "components": {"living_allowance": "covered", "tuition": "not_stated"}, "funding_class": "stipend_only"},
     evidence={"funding_class": "Two components: a) Living expenses for the student recipient b) A family recognition award ... Living Expenses (Annual) | $3,000 | $4,000 | $5,000"},
     ambiguous="three named scholarships with identical terms described together; ITE, polytechnic and university levels"),
})
AMB.update({"bd-dutch-bangla": ["levels", "funding_class"], "id-baznas": ["cycle_status"], "in-icssr": ["nationality"], "jp-atsumi": ["deadlines"],
            "jp-jees": ["nationality"], "ph-sm-foundation": ["cycle_status"], "sg-temasek": ["levels", "funding_class"]})
X.update({"tn-mes": "ministry notices in Arabic", "cn-li-ka-shing": "news", "hk-croucher": "near-empty page", "hk-k-c-wong": "list in Chinese",
          "id-dompet-dhuafa": "two programmes", "id-xl-future": "PDF (to check)", "in-dst-inspire": "programme overview", "in-nsp-central": "PDF (to check)",
          "in-tata-trusts": "several programmes", "jp-ajinomoto": "corporate home page", "jp-hirose": "near-empty page", "jp-iwatani": "page in Japanese (to check)",
          "jp-kyoritsu": "page in Japanese (to check)", "kr-lotte": "home page", "my-cimb": "foundation programmes", "ph-ayala": "news"})
P.update({
 "eg-fulbright-egypt": dict(fields={"nationality": {"mode": "include", "countries": ["EG"]}, "levels": ["master"], "deadlines": [], "cycle_status": "not_stated",
     "funding_class": "fully_funded"},
     evidence={"nationality": "Eligibility Criteria: Egyptian citizenship. ... U.S. citizens and green card holders and applicants are not eligible to apply.",
               "funding_class": "The program provides fully funded master's degree grants for university graduates to study in the U.S. for a maximum of two years."},
     ambiguous="'fully funded' is stated without its components"),
 "fr-fulbright-france": dict(fields={"nationality": {"mode": "include", "countries": ["FR"]}, "levels": ["master", "phd"], "deadlines": [D("2026-12-01", "current")],
     "cycle_status": "open", "components": {"stipend": "covered", "travel": "covered"}, "funding_class": "stipend_only"},
     evidence={"nationality": "Être de nationalité française",
               "deadlines": "Date limite de dépôt de candidature : 1er décembre 2026 à 23h59 (heure de Paris) pour le cycle 2027/2028",
               "cycle_status": "Cycle 2027-2028 : L'appel est ouvert",
               "funding_class": "Une bourse de maintenance de $40 000 pour soutenir la première année d'études aux Etats-Unis (non renouvelable) ... Une allocation forfaitaire de voyage de 1200 € (tuition is not paid)"}),
 "pl-fulbright-poland": dict(fields={"nationality": {"mode": "include", "countries": ["PL"]}, "levels": ["master", "phd"], "deadlines": [D("2026-04-27")],
     "openings": ["2026-02-09"], "cycle_status": "closed", "funding_class": "not_stated"},
     evidence={"nationality": "Hold Polish citizenship and do not possess dual Polish–U.S. citizenship or a U.S. permanent resident card (Green Card).",
               "deadlines": "The call for applications is open from February 9 to April 27, 2026, until 3:00 PM (Polish time).",
               "funding_class": "(the award's benefits are not stated on this page)"},
     ambiguous="graduate degree studies after a master's: the levels fit loosely"),
 "ro-fulbright-romania": dict(fields={"nationality": {"mode": "include", "countries": ["RO"]}, "levels": ["master"], "deadlines": [], "cycle_status": "closed",
     "components": {"tuition": "partial", "stipend": "covered", "travel": "covered", "insurance": "covered"}, "funding_class": "fully_funded"},
     evidence={"nationality": "have Romanian citizenship; green card holders and persons with dual (Romanian and U.S.) citizenship are ineligible",
               "cycle_status": "The 2027-2028 competition is now closed! The next competition will be announced in February 2027.",
               "funding_class": "Tuition and university fees within established budget limits. Monthly stipend for accommodation and living expenses. ... International travel ... ASPE Health Benefits Plan"},
     ambiguous="tuition within budget limits: fully or partially funded"),
 "za-study-trust": dict(fields={"nationality": {"mode": "include", "countries": ["ZA"]}, "levels": ["bachelor"], "deadlines": [], "cycle_status": "not_stated",
     "funding_class": "fully_funded"},
     evidence={"nationality": "Only applications from South African citizens will be considered.",
               "deadlines": "Application Season: 01 June to 30 September. (no year)",
               "funding_class": "Investec offers full-cost bursaries to students who are currently in Gr 12 or their first year of tertiary study"},
     ambiguous="a yearly window without a year; 'full-cost bursaries' without components"),
 "br-fapesp-pd": dict(fields={"nationality": {"mode": "any", "countries": []}, "levels": ["postdoc"], "deadlines": [], "cycle_status": "not_stated",
     "components": {"stipend": "covered"}, "funding_class": "stipend_only"},
     evidence={"nationality": "A oportunidade de pós-doutorado está aberta a brasileiros e estrangeiros.",
               "funding_class": "O selecionado receberá Bolsa de Pós-Doutorado da FAPESP no valor de R$ 7.373,10 mensais e Reserva Técnica"},
     ambiguous="a single position announced by a news agency page"),
 "it-fulbright-italy": dict(fields={"nationality": {"mode": "include", "countries": ["IT"]}, "levels": ["master"], "deadlines": [D("2026-09-14")], "cycle_status": "closed",
     "components": {"stipend": "covered", "travel": "covered"}, "funding_class": "stipend_only"},
     evidence={"nationality": "I candidati devono rispettare i seguenti requisiti: cittadinanza italiana; residenza in Italia o, eventualmente, in un paese europeo",
               "deadlines": "da completare entrambe entro lunedì 14 settembre 2026 (h23:59)",
               "funding_class": "maintenance allowance di $ 5,400 ... stipendio mensile di $500-600 per mese finanziati dall'istituzione ospitante ... travel allowance di €1.100"},
     ambiguous="a teaching assistantship year, not a degree: the level fits loosely"),
 "br-instituto-ling": dict(fields={"nationality": {"mode": "include", "countries": ["BR"]}, "levels": ["master"], "deadlines": [D("2026-04-06")], "openings": ["2026-01-05"],
     "cycle_status": "closed", "components": {"tuition": "partial"}, "funding_class": "partially_funded"},
     evidence={"nationality": "Para participar do processo seletivo 2026, você precisa ... 2. Ser brasileiro;",
               "deadlines": "Cronograma 2026: Inscrições – 5/janeiro a 6/abril de 2026",
               "funding_class": "O Programa START MBA/MPA oferece bolsas de estudo parciais para MBA ... e MPA"}),
 "tr-tubitak-2213": dict(fields={"nationality": "not_stated", "levels": ["phd"], "deadlines": [D("2026-12-31", "current")], "cycle_status": "open",
     "components": {"stipend": "covered", "tuition": "full", "insurance": "covered"}, "funding_class": "fully_funded"},
     evidence={"deadlines": "Başvurular 31 Aralık 2026 saat 17:30'a kadar TÜBİTAK Yönetim Bilgi Sistemi (TYBS) üzerinden alınacaktır",
               "cycle_status": "DUYURU (13.05.2026): 2026 yılı başvuruları başlamıştır.",
               "funding_class": "yaşam gideri, öğrenim harçları ve sağlık sigortası da dâhil olmak üzere ... Aylık burs miktarı tüm ülkeler için 1900 ABD doları"},
     ambiguous="the citizenship rule is in the call document; the monthly amount must cover living and tuition together"),
 "gr-latsis": dict(fields={"nationality": "not_stated", "levels": ["master"], "deadlines": [], "cycle_status": "not_announced", "funding_class": "not_stated"},
     evidence={"nationality": "scholarship applications can be submitted by all Greek high school graduates, irrespective of whether they have acquired Greek citizenship",
               "cycle_status": "Currently there are no calls available",
               "funding_class": "the granted amount can cover either tuition fees either living expenses (the scholar chooses; the amount is in the call)"},
     ambiguous="no call open: not announced or closed; a cash amount of the scholar's choice"),
})
AMB.update({"eg-fulbright-egypt": ["funding_class"], "pl-fulbright-poland": ["levels"], "ro-fulbright-romania": ["funding_class"],
            "za-study-trust": ["deadlines", "funding_class"], "br-fapesp-pd": ["cycle_status"], "it-fulbright-italy": ["levels"],
            "tr-tubitak-2213": ["nationality", "funding_class"], "gr-latsis": ["cycle_status", "funding_class"]})
X.update({"ar-conicet": "near-empty page", "bg-fulbright-bulgaria": "list of grants", "de-einstein-foundation": "institutions apply", "es-fulbright-spain": "blog summary",
          "es-fundacion-mapfre": "training grants for professionals, assigned", "gr-eugenides": "unrelated page", "gr-fulbright-greece": "list", "hu-fulbright-hungary": "empty page",
          "il-azrieli": "several fellowships", "it-fondazione-crt": "home page", "jm-slb": "loan bureau page", "pa-ifarhu": "list of national scholarships",
          "pl-fnp-start": "news item without a deadline or rule", "tr-fulbright-turkey": "list", "za-moshal": "team page",
          "az-state-program": "PDF not reviewed", "lk-presidential": "PDF not reviewed", "fr-axa-research": "PDF not reviewed", "fr-ile-de-france": "PDF not reviewed",
          "et-moe": "PDF not reviewed", "id-xl-future": "PDF not reviewed", "in-nsp-central": "PDF not reviewed", "ke-kcb-foundation": "PDF not reviewed",
          "pe-concytec": "PDF not reviewed", "za-nsfas": "PDF not reviewed", "jp-iwatani": "page in Japanese not reviewed", "jp-kyoritsu": "page in Japanese not reviewed"})
P.update({
 "br-fulbright-brasil": dict(fields={"nationality": {"mode": "include", "countries": ["BR"]}, "levels": ["phd"], "deadlines": [], "cycle_status": "not_announced",
     "components": {"stipend": "covered", "relocation": "covered"}, "funding_class": "stipend_only"},
     evidence={"nationality": "Possuir nacionalidade brasileira e não ter nacionalidade norte-americana;",
               "cycle_status": "Previsão para abertura das inscrições: Junho de 2027",
               "funding_class": "Bolsa mensal, com duração de um ano acadêmico, de valor compatível com o custo de vida no campus ... Auxílio instalação de US$ 2.000"},
     ambiguous="only an expected opening month is given: not announced or upcoming"),
 "ec-fulbright-ecuador": dict(fields={"nationality": {"mode": "include", "countries": ["EC"]}, "levels": ["master", "phd"], "deadlines": [], "cycle_status": "not_stated",
     "components": {"stipend": "covered", "insurance": "covered", "travel": "covered", "relocation": "covered"}, "funding_class": "stipend_only"},
     evidence={"nationality": "Contar con ciudadanía ecuatoriana. No se acepta doble nacionalidad con los Estados Unidos.",
               "funding_class": "La beca Fulbright cubrirá los siguientes rubros: manutención, seguro médico suplementario, boleto aéreo, materiales de estudio y un estipendio de instalación. La beca de colegiatura ... (tuition is handled separately)"},
     ambiguous="the tuition sentence is cut off on the page: stipend-only or fully funded"),
 "jp-fulbright-japan": dict(fields={"nationality": {"mode": "include", "countries": ["JP"]}, "levels": ["master", "phd"], "deadlines": [], "cycle_status": "not_stated",
     "funding_class": "not_stated"},
     evidence={"nationality": "Citizenship: Applicants must be citizens of Japan. Persons holding dual Japan-U.S. citizenship or permanent U.S. residency are NOT eligible"},
     ambiguous="three grant types (graduate study, dissertation research, research) under one eligibility page"),
 "mx-comexus": dict(fields={"nationality": {"mode": "include", "countries": ["MX"]}, "levels": ["master", "phd"], "deadlines": [D("2027-01-15", "current")],
     "openings": ["2026-09-02"], "cycle_status": "open", "funding_class": "not_stated"},
     evidence={"nationality": "La beca Fulbright-García Robles es otorgada a estudiantes de nacionalidad MEXICANA. ... Quienes cuenten con residencia o nacionalidad estadounidense (o doble mexicana-estadounidense) (not eligible)",
               "deadlines": "Convocatoria abierta del 2 de septiembre de 2026 al 15 de enero de 2027, para iniciar estudios en agosto de 2028 sin excepción.",
               "cycle_status": "CONVOCATORIA ABIERTA",
               "funding_class": "Hasta $37,000 dólares por año escolar hasta 18 meses para maestría, y hasta $25,000 por año escolar por tres años para doctorado. Esta cantidad no está etiquetada"},
     ambiguous="a yearly cash amount 'not earmarked' for any cost"),
 "my-fulbright-malaysia": dict(fields={"nationality": {"mode": "include", "countries": ["MY"]}, "levels": ["master", "phd"], "deadlines": [D("2026-05-18")],
     "openings": ["2026-03-12"], "cycle_status": "closed", "funding_class": "not_stated"},
     evidence={"nationality": "To be eligible ... you must: Be a Malaysian citizen",
               "deadlines": "Open - 12 March, 2026. Close - 18 May, 2026"}),
 "ph-fulbright-philippines": dict(fields={"nationality": {"mode": "include", "countries": ["PH"]}, "levels": ["master", "phd"], "deadlines": [D("2026-04-30")],
     "cycle_status": "closed", "funding_class": "not_stated"},
     evidence={"nationality": "General Eligibility Requirements: Philippine citizenship ... Individuals holding dual citizenship, are permanent residents and/or are presently studying in the U.S. are not eligible.",
               "deadlines": "Application period for the 2027-2028 Fulbright Foreign Student Program (for Filipinos) is now OPEN. Deadline of Applications is on April 30, 2026.",
               "cycle_status": "is now OPEN ... Deadline of Applications is on April 30, 2026 (past on 2026-10-20)"},
     ambiguous="the page still says OPEN after its own deadline"),
 "uy-fulbright-uruguay": dict(fields={"nationality": {"mode": "include", "countries": ["UY"]}, "levels": ["master", "phd"], "deadlines": [D("2026-05-14")],
     "openings": ["2026-02-04"], "cycle_status": "closed", "components": {"tuition": "partial"}, "funding_class": "partially_funded"},
     evidence={"nationality": "Requisitos: Ciudadanía uruguaya.",
               "deadlines": "El llamado estará abierto desde el 4 de febrero hasta el 14 de mayo de 2026 a las 23:59.",
               "funding_class": "Descuentos en las matrículas. (the benefits list; a stipend is not stated in the extracted text)"},
     ambiguous="the benefit list is partly lost in extraction: partially funded or more"),
})
AMB.update({"br-fulbright-brasil": ["cycle_status"], "ec-fulbright-ecuador": ["funding_class"], "jp-fulbright-japan": ["levels"], "mx-comexus": ["funding_class"],
            "ph-fulbright-philippines": ["cycle_status"], "uy-fulbright-uruguay": ["funding_class"]})
X.update({"fi-fulbright-finland": "several university awards", "is-fulbright-iceland": "list", "kr-fulbright-korea": "near-empty page", "no-fulbright-norway": "list",
          "np-fulbright-nepal": "specialist programme for host institutions", "pe-fulbright-peru": "list", "pk-fulbright-pakistan": "mid-career non-degree fellowship",
          "se-fulbright-sweden": "list", "sk-fulbright-slovakia": "PDF not reviewed", "th-fulbright-thailand": "FAQ", "tw-fulbright-taiwan": "award for U.S. faculty",
          "ua-fulbright-ukraine": "empty page"})
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
(M / "labels.json").write_text(json.dumps({"today": "2026-10-20", "version": "Q-1",
    "note": "programme decisions labelled by hand from the official pages before any extractor ran on them; quotes per field",
    "pages": pages}, indent=1, ensure_ascii=False) + "\n")
print(len(pages), "labelled (all test);", sum(1 for p in urls["pages"] if p["split"] == "excluded"), "excluded")
