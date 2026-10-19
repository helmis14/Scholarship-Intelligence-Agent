"""Set P labels (round 31), written by hand from the official pages in pages/ before any extractor ran on set P.

Set P is the frozen test set for the round-31 rules (date roles stage 4, exclusion lists, residence conditions, the
full cost of attendance, European demonyms). The round-31 code was finished before any set-P page was fetched, and
nothing on set P was used to change a rule. Labels follow the same reading as sets L to O: fee status, domicile,
residence, visa status, "international students", "nonresidents" and invitations are "not_stated" nationality (a page
that defines "international" as "not a US citizen or permanent resident" is an exclusion, marked as a close call);
"fully_funded" needs tuition and living costs both covered (or the page states the full cost of attendance); a stated
discount, share or cap is "partially_funded"; a cash award whose use is not stated is "not_stated" funding unless it is
paid per month or year (then "stipend_only", marked as a close call); deadlines are applicant deadline dates with a
year for this programme (not nominations, openings, payments, notifications, programme stays or other steps; dates
without a year are recorded in the evidence only); cycle_status as of 2026-10-19 (the day the pages were fetched).
Pages listing several awards, home pages, news, fee pages, admissions guides and indexes are excluded. Close calls are
recorded per decision in AMB ("ambiguous_fields"); results are reported with and without them. Country lists were
transcribed by hand from the page. Run once to write labels.json; manifest.json then freezes it."""
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
 "us-berkeley-regents": dict(fields={"nationality": "not_stated", "levels": ["bachelor"], "deadlines": [], "cycle_status": "not_stated",
     "funding_class": "not_stated"},
     evidence={"nationality": "All students who apply to UC Berkeley are automatically considered for the scholarship. This includes California resident, out-of-state, and international students",
               "funding_class": "Scholars with financial need receive grant and scholarship support up to their full need ... The minimum award amount is $2,500 per year (need-based; what it pays for depends on need)"},
     ambiguous="a need-based award whose coverage varies per student"),
 "us-duke-robertson": dict(fields={"nationality": {"mode": "exclude", "countries": ["US"]}, "levels": ["bachelor"], "deadlines": [],
     "cycle_status": "not_stated", "components": {"tuition": "full", "accommodation": "covered", "living_allowance": "covered"},
     "funding_class": "fully_funded"},
     evidence={"nationality": "Can a student who is a citizen of any country outside the U.S. be considered for this scholarship? Yes. Can a student who has dual U.S./other country citizenship be considered for this scholarship? No.",
               "funding_class": "Your tuition, room and board, mandatory fees, demonstrated need that exceeds those costs, and three summers of funding"}),
 "us-mit-presidential": dict(fields={"nationality": "not_stated", "levels": ["master", "phd"], "deadlines": [], "cycle_status": "not_stated",
     "components": {"tuition": "full", "stipend": "covered", "insurance": "covered"}, "funding_class": "fully_funded"},
     evidence={"nationality": "to recruit the most outstanding students worldwide (no nationality rule; students cannot apply directly)",
               "funding_class": "nine-month fellowships that fund the tuition, monthly stipend ... and the student extended insurance plan"}),
 "us-northwestern-presidential": dict(fields={"nationality": "not_stated", "levels": ["phd"], "deadlines": [D("2027-02-01", "current")],
     "cycle_status": "open", "components": {"tuition": "full", "stipend": "covered", "research": "covered", "travel": "covered"},
     "funding_class": "fully_funded"},
     evidence={"deadlines": "The deadline for applicants to submit application materials is Monday, February 1, 2027 (by 11:59 pm) for fellowships beginning in Fall 2027 Quarter (the January 27, 2027 date is the programmes' nomination deadline)",
               "funding_class": "Monthly stipend and tuition (at the advanced rate) starting in fall quarter of the award period for 24 months"},
     ambiguous="the page states the 2027 deadline without saying the call is open"),
 "us-rice-wagoner": dict(fields={"nationality": "not_stated", "levels": ["master", "phd"], "deadlines": [D("2026-11-05", "current")],
     "cycle_status": "open", "components": {"travel": "covered"}, "funding_class": "not_stated"},
     evidence={"deadlines": "The application deadline for the 2026-27 award will be November 5, 2026.",
               "cycle_status": "The online application for the 2026-27 Wagoner Foreign Study Scholarship is now open.",
               "funding_class": "Wagoner funding will be available in the following award amounts ($2K, $3K, $5K, $7K) (a travel grant, not tuition or living costs)"},
     ambiguous="a research-travel grant; the funding classes do not describe it"),
 "us-ucsd-regents": dict(fields={"nationality": {"mode": "include", "countries": ["US"]}, "levels": ["bachelor"], "deadlines": [],
     "cycle_status": "not_stated", "funding_class": "not_stated"},
     evidence={"nationality": "Eligibility requirements ... United States citizens, permanent residents, or California Dream Act students",
               "deadlines": "File your UC Application for Admission and Scholarships by the Nov. 30 deadline. (no year)",
               "funding_class": "First-Year Regents Scholars receive a $20,000 scholarship paid at $5,000 per year (what it pays for is not stated)"},
     ambiguous="a yearly deadline without a year; a cash award"),
 "us-uci-regents": dict(fields={"nationality": {"mode": "include", "countries": ["US"]}, "levels": ["bachelor"], "deadlines": [],
     "cycle_status": "not_stated", "funding_class": "not_stated"},
     evidence={"nationality": "students must be a U.S. citizen, an eligible non-citizen, or students qualifying under AB130 or AB131"}),
 "us-ucsb-regents": dict(fields={"nationality": {"mode": "include", "countries": ["US"]}, "levels": ["bachelor"], "deadlines": [],
     "cycle_status": "closed", "funding_class": "not_stated"},
     evidence={"nationality": "you must be a U.S. citizen, permanent resident, or a non-citizen student qualifying under California Assembly Bill",
               "cycle_status": "All Regents Scholarships for the 2026-27 Year Have Been Awarded. Decisions Are Final.",
               "funding_class": "Currently the award is $5,000 per year for four years (a cash award plus guaranteed housing)"},
     ambiguous="a cash award with a housing guarantee, not housing costs"),
 "us-uga-foundation": dict(fields={"nationality": "not_stated", "levels": ["bachelor"], "deadlines": [], "cycle_status": "not_stated",
     "components": {"stipend": "covered", "tuition": "full", "travel": "covered"}, "funding_class": "fully_funded"},
     evidence={"nationality": "Annual stipend for international students: $30,000 plus a Presidential waiver (open to international students)",
               "deadlines": "The deadline to apply for the Foundation Fellowship is November 1 of each year. (no year)",
               "funding_class": "The stipend approximates the cost of attendance ... Annual stipend for international students: $30,000 plus a Presidential waiver (worth $21,740 per year)"},
     ambiguous="a yearly deadline without a year; the tuition waiver is named only for out-of-state and international students"),
 "us-umd-banneker": dict(fields={"nationality": "not_stated", "levels": ["bachelor"], "deadlines": [], "cycle_status": "not_stated",
     "components": {"tuition": "full", "accommodation": "covered", "living_allowance": "covered"}, "funding_class": "fully_funded"},
     evidence={"deadlines": "All freshman applicants ... who meet the early action deadline of November 1 ... are considered for nomination (no year; an admission deadline)",
               "funding_class": "The full Banneker/Key provides full tuition, room, board, and a book allowance."},
     ambiguous="two levels: the partial Banneker/Key pays $8,000 or $12,000 towards tuition"),
 "us-vanderbilt-cornelius": dict(fields={"nationality": "not_stated", "levels": ["bachelor"], "deadlines": [D("2026-12-01", "current")],
     "cycle_status": "open", "tuition": "full", "funding_class": "tuition_funded"},
     evidence={"deadlines": "Cornelius Vanderbilt Scholarship - December 1, 2026 ... Deadline to electronically submit Cornelius Vanderbilt Scholarship application",
               "funding_class": "Cornelius Vanderbilt Scholars receive full tuition, plus a one-time summer stipend for an immersive experience"},
     ambiguous="the one-time summer stipend is not a living stipend; the Ingram deadline on the same page is another programme's"),
 "us-wisc-chancellor": dict(fields={"nationality": "not_stated", "levels": ["bachelor"], "deadlines": [], "cycle_status": "not_stated",
     "tuition": "full", "funding_class": "tuition_funded"},
     evidence={"funding_class": "a four-year, full tuition scholarship program for undergraduate students"}),
 "us-nd-stamps": dict(fields={"nationality": "not_stated", "levels": ["bachelor"], "deadlines": [], "cycle_status": "not_stated",
     "components": {"tuition": "full", "travel": "covered"}, "funding_class": "tuition_funded"},
     evidence={"nationality": "All applicants to the University of Notre Dame -- both Restrictive Early Action (REA) and Regular Decision (RD) -- are considered",
               "funding_class": "An annual scholarship that covers tuition and fees as well as the estimated cost of books, personal expenses, and transportation (room and board are not named)"},
     ambiguous="books, personal expenses and transportation are covered but not room and board"),
})
AMB.update({"us-berkeley-regents": ["funding_class"], "us-northwestern-presidential": ["cycle_status"], "us-rice-wagoner": ["funding_class"],
            "us-ucsd-regents": ["deadlines", "funding_class"], "us-ucsb-regents": ["funding_class"], "us-uga-foundation": ["deadlines", "funding_class"],
            "us-umd-banneker": ["funding_class"], "us-vanderbilt-cornelius": ["funding_class", "deadlines"], "us-nd-stamps": ["funding_class"]})
X.update({"nl-leiden-excellence": "department page", "us-asu-nae": "cost page", "us-bu-trustee": "home page", "us-cornell-sage": "several fellowships",
          "us-emory-scholars": "several scholar programmes", "us-gatech-stamps": "home page", "us-georgetown-ggd": "home page",
          "us-illinois-fellowship": "dates list", "us-indiana-wells": "home page", "us-osu-morrill": "list", "us-pitt-chancellor": "news",
          "us-psu-schreyer": "cost page", "us-purdue-trustees": "list", "us-rutgers-presidential": "list", "us-tamu-presidents": "news",
          "us-tulane-dhs": "list", "us-ucla-regents": "overview", "us-ufl-presidential": "tiers list", "us-unc-morehead": "home page",
          "us-usc-trustee": "three awards", "us-utah-presidential": "faculty award", "us-utexas-forty": "giving page", "us-wustl-danforth": "PhD programme page",
          "us-uiowa-presidential": "library news"})
P.update({
 "us-colorado-chancellor": dict(fields={"nationality": "not_stated", "levels": ["bachelor"], "deadlines": [], "cycle_status": "not_stated",
     "funding_class": "not_stated"},
     evidence={"nationality": "offered to incoming nonresident first-year students (residency for tuition, not nationality)",
               "funding_class": "a scholarship of $6,250 per year ... credited towards your university bill ... isn't limited to paying just tuition and fees"},
     ambiguous="a cash award credited to the bill"),
 "us-uoregon-icsp": dict(fields={"nationality": "not_stated", "levels": ["bachelor", "master"], "deadlines": [D("2027-02-01", "current")],
     "cycle_status": "open", "tuition": "partial", "funding_class": "partially_funded"},
     evidence={"nationality": "New and continuing international students may apply (fee status)",
               "deadlines": "Application Deadline: February 1, 2027 at 4:00 p.m. (PST)",
               "funding_class": "a scholarship covering approximately half their tuition ... a partial tuition-waiver scholarship"},
     ambiguous="the page states the 2027 deadline without saying the call is open"),
 "us-miami-stamps": dict(fields={"nationality": "not_stated", "levels": ["bachelor"], "deadlines": [], "cycle_status": "not_stated",
     "components": {"tuition": "full", "accommodation": "covered", "living_allowance": "covered", "insurance": "covered"},
     "funding_class": "fully_funded"},
     evidence={"funding_class": "Stamps Scholars receive the full cost of attendance for eight semesters ... includes tuition and fees, on-campus housing, a meal plan, University health insurance"}),
})
AMB.update({"us-colorado-chancellor": ["funding_class"], "us-uoregon-icsp": ["cycle_status"]})
X.update({"us-auburn-international": "cost page", "us-buffalo-international": "list", "us-byu-international": "catalog aid page",
          "us-fiu-international": "list with old dates", "us-fsu-international": "list", "us-kstate-international": "list",
          "us-ku-international": "tiers list", "us-lsu-international": "online programmes page", "us-okstate-international": "list",
          "us-oregonstate-international": "list", "us-ou-international": "LLM programme page", "us-rochester-international": "list of external awards",
          "us-stonybrook-international": "aid overview", "us-syr-international": "aid overview", "us-ttu-international": "aid overview",
          "us-ua-international": "ISSS home", "us-ucf-international": "aid policy page", "us-uconn-international": "several awards",
          "us-udel-international": "fees page", "us-uh-international": "ISSS home", "us-uky-international": "tiers list",
          "us-umass-chancellor": "department page", "us-unl-global": "list", "us-usf-international": "home page"})
P.update({
 "ca-lakehead-international": dict(fields={"nationality": {"mode": "exclude", "countries": ["CA"]}, "levels": ["bachelor"], "deadlines": [],
     "cycle_status": "not_stated", "tuition": "partial", "funding_class": "partially_funded"},
     evidence={"nationality": "Non-Canadian citizens who are entering Lakehead University from a high school ... will be considered for the Undergraduate Entrance Scholarships",
               "funding_class": "$40,000 ($10,000 x 4 years) ... Your Entrance Scholarship will be applied to your first-year tuition"},
     ambiguous="tiered amounts applied to tuition; the page also lists graduate assistantships"),
 "ca-laurentian-international": dict(fields={"nationality": "not_stated", "levels": ["bachelor"], "deadlines": [], "cycle_status": "not_stated",
     "funding_class": "not_stated"},
     evidence={"nationality": "students ... who pay International fees to Laurentian University (fee status)",
               "funding_class": "Up to $60,000 in scholarship awards ... $15,000 in first year (what it pays for is not stated)"},
     ambiguous="a cash award in tiers"),
 "us-iastate-international": dict(fields={"nationality": "not_stated", "levels": ["bachelor"], "deadlines": [], "cycle_status": "not_stated",
     "tuition": "partial", "funding_class": "partially_funded"},
     evidence={"nationality": "Offered admission to Iowa State University as an international first-year student. Assessed international tuition rates. (fee status)",
               "deadlines": "Fall | Feb. 15 | May 1 (no year)",
               "funding_class": "Award of Achievement | Up to $40,000 | $5,000–$10,000 ... Apply funds only toward undergraduate tuition and fees."},
     ambiguous="yearly deadlines without a year; first-year and transfer tiers"),
 "us-nmsu-international": dict(fields={"nationality": "not_stated", "levels": ["bachelor", "master", "phd"], "deadlines": [], "cycle_status": "not_stated",
     "tuition": "partial", "funding_class": "partially_funded"},
     evidence={"deadlines": "The deadline to submit scholarship applications depends on the number of awards available for that semester.",
               "funding_class": "a discount to pay in-state tuition instead of out-of-state tuition ... plus awards a $100 stipend cash award each fall and spring"},
     ambiguous="the $100 per term is not a living stipend"),
 "us-olemiss-international": dict(fields={"nationality": "not_stated", "levels": ["bachelor"], "deadlines": [], "cycle_status": "not_stated",
     "tuition": "partial", "funding_class": "partially_funded"},
     evidence={"nationality": "for incoming freshman undergraduate international students who attended secondary/high school outside of the U.S. (fee status and schooling, not nationality)",
               "funding_class": "Total Scholarship $28,893 per year for 4 years (93% of tuition per year)"},
     ambiguous="tiers by GPA; the SAT/ACT scholarship on the same page is another award"),
 "us-uidaho-international": dict(fields={"nationality": "not_stated", "levels": ["bachelor"], "deadlines": [], "cycle_status": "not_stated",
     "tuition": "partial", "funding_class": "partially_funded"},
     evidence={"nationality": "All eligible international undergraduate students are automatically considered for the Invitation to Idaho Scholarship",
               "funding_class": "a renewable scholarship for up to four years of study that can cover up to 50% tuition"},
     ambiguous="a cost page that describes one award"),
 "us-villanova-presidential": dict(fields={"nationality": "not_stated", "levels": ["bachelor"], "deadlines": [], "cycle_status": "not_stated",
     "components": {"tuition": "full", "accommodation": "covered", "living_allowance": "covered"}, "funding_class": "fully_funded"},
     evidence={"funding_class": "covering undergraduate Villanova University tuition (fall and spring semesters), on-campus housing, a meal plan that includes up to 21 meals per week, the general fee"}),
})
AMB.update({"ca-lakehead-international": ["funding_class"], "ca-laurentian-international": ["funding_class"], "us-iastate-international": ["deadlines", "funding_class"],
            "us-nmsu-international": ["funding_class"], "us-olemiss-international": ["funding_class"], "us-uidaho-international": ["funding_class"]})
X.update({"ca-ontariotech-international": "awards portal", "ca-trentu-international": "home page", "ca-tru-international": "list", "ca-uleth-international": "repository",
          "ca-unb-international": "overview", "ca-unbc-international": "awards competition portal", "ca-uqam-bourse": "home page", "ca-uregina-international": "three awards",
          "ca-usherbrooke": "several programmes", "ca-uwindsor-international": "list", "ca-wlu-international": "fees page", "us-boisestate-international": "deadlines overview",
          "us-clemson-international": "news", "us-drexel-international": "visa page", "us-fordham-international": "several awards", "us-hawaii-international": "list",
          "us-howard-international": "aid application page", "us-montana-international": "placeholder page", "us-msstate-international": "policy page",
          "us-sc-international": "giving page", "us-temple-international": "several scholarships", "us-uark-international": "list of external awards",
          "us-unlv-international": "student union awards (closed)", "us-unm-amigo": "list", "us-unr-international": "overview", "us-usu-international": "list",
          "us-uwyo-international": "list of external awards", "us-vt-international": "study centre page"})
X.update({"au-nd-international": "2009 news", "au-torrens-international": "list", "au-usq-international": "application system login",
          "ca-acadia-international": "near-empty overview", "ca-mtroyal-international": "home page", "ca-smu-international": "near-empty page",
          "ca-upei-international": "overview without values", "hk-eduhk-international": "graduate school home", "hk-ust-international": "faculty page",
          "tw-ccu-international": "university news", "tw-nchu-international": "fees and scholarship overview", "tw-ncu-international": "office home page",
          "tw-ndhu-international": "announcements list", "tw-tku-international": "several scholarships"})
P.update({
 "kr-kookmin-international": dict(fields={"nationality": {"mode": "exclude", "countries": ["KR"]}, "levels": ["master", "phd"], "deadlines": [],
     "cycle_status": "not_stated", "components": {"tuition": "full", "stipend": "covered", "travel": "covered", "relocation": "covered", "research": "covered"},
     "funding_class": "fully_funded"},
     evidence={"nationality": "The applicant and his/her parents must have foreign citizenships. Applicants who hold Korean citizenship are not permitted to apply for this program.",
               "funding_class": "Airfare: Round-trip economy class ticket. Monthly Allowance : 900,000 won (KRW) per month ... The tuition is paid by NIIED."},
     ambiguous="a university page relaying the national GKS programme; no dates on the page"),
})
AMB.update({"kr-kookmin-international": ["cycle_status"]})
X.update({"jp-chuo-international": "list", "jp-hosei-international": "list", "kr-ajou-international": "home page", "kr-cau-international": "campus services page",
          "kr-hufs-international": "several scholarships", "kr-inha-international": "home page", "kr-knu-international": "department page",
          "kr-pusan-international": "several scholarships", "jp-kansai-international": "admissions overview", "jp-kwansei-international": "fees page",
          "jp-rikkyo-international": "portal notices", "kr-sejong-international": "home page"})
P.update({
 "cn-hit-international": dict(fields={"nationality": {"mode": "exclude", "countries": ["CN"]}, "levels": ["bachelor", "master", "phd"],
     "deadlines": [D("2026-05-31")], "openings": ["2025-10-01"], "cycle_status": "closed", "tuition": "partial", "funding_class": "partially_funded"},
     evidence={"nationality": "Applicants must be citizens of a country other than the People's Republic of China.",
               "deadlines": "October 1st, 2025 2026 Application Opens ... May 31st, 2026 Application Deadline",
               "funding_class": "Elite: 100%tuition fee waiver ... First: Half tuition fee waiver ... Second: 30% tuition fee waiver"},
     ambiguous="tiers from 20% to 100% of tuition"),
 "cn-tju-international": dict(fields={"nationality": {"mode": "exclude", "countries": ["CN"]}, "levels": ["bachelor", "master"],
     "deadlines": [D("2025-05-31")], "openings": ["2024-10-15"], "cycle_status": "closed",
     "components": {"tuition": "full", "living_allowance": "covered", "insurance": "covered"}, "funding_class": "fully_funded"},
     evidence={"nationality": "Applicants must be a citizen of a country other than the People's Republic of China, and be in good health;",
               "deadlines": "October 15, 2024- May 31, 2025",
               "funding_class": "Tuition: 30000RMB, Living allowance: 1700RMB/month (10 months in total) Comprehensive medical insurance： 800RMB"},
     ambiguous="the page describes the 2025 cycle; the tuition line states the amount paid"),
 "id-ipb-international": dict(fields={"nationality": "not_stated", "levels": ["bachelor", "master"], "deadlines": [], "cycle_status": "closed",
     "components": {"tuition": "full", "accommodation": "covered", "travel": "covered"}, "funding_class": "tuition_funded"},
     evidence={"nationality": "International students coming from abroad or those who are already in the country (priority country: ...) (no nationality rule)",
               "deadlines": "The Rector's Scholarship application is open from April 1st to June 30th each year. (no year)",
               "cycle_status": "open from April 1st to June 30th each year (the window has passed for this year)",
               "funding_class": "Full Coverage: Tuition and fees waiver (2000 USD/year), Accommodation, International flights (no living allowance; a tuition-only package also exists)"},
     ambiguous="yearly window without a year; several coverage packages"),
 "id-binus-international": dict(fields={"nationality": "not_stated", "levels": ["bachelor"], "deadlines": [], "cycle_status": "not_stated",
     "funding_class": "not_stated"},
     evidence={"funding_class": "financial support of up to IDR 127.5 million (what it pays for is not stated)"},
     ambiguous="a cash cap only"),
 "my-utp-international": dict(fields={"nationality": {"mode": "include", "countries": ["MY"]}, "levels": ["bachelor"],
     "deadlines": [D("2026-09-22")], "cycle_status": "closed", "tuition": "partial", "funding_class": "partially_funded"},
     evidence={"nationality": "Malaysian citizen;", "deadlines": "Deadline: 22 September 2026",
               "funding_class": "Award: Full tuition fees / Partial tuition fees"},
     ambiguous="full or partial tuition; the page also lists other UTP funds"),
 "co-eafit-becas": dict(fields={"nationality": "not_stated", "levels": ["bachelor"], "deadlines": [D("2026-11-16", "current")],
     "openings": ["2026-09-07"], "cycle_status": "open", "tuition": "partial", "funding_class": "partially_funded"},
     evidence={"nationality": "Bachilleres graduados en Colombia (schooling, not nationality)",
               "deadlines": "El formato de aplicación a las becas estará disponible hasta el 16 de noviembre de 2026",
               "cycle_status": "Postúlate a partir del 07 de septiembre de 2026.",
               "funding_class": "Un porcentaje sobre el valor de la matrícula que puede ser del 40%, 50%, 60%, 70%, 80% o 100%"},
     ambiguous="one call with several partner awards; 40% to 100% of tuition"),
})
AMB.update({"cn-hit-international": ["funding_class"], "cn-tju-international": ["cycle_status", "deadlines"], "id-ipb-international": ["deadlines", "cycle_status", "funding_class"],
            "id-binus-international": ["funding_class"], "my-utp-international": ["funding_class"], "co-eafit-becas": ["funding_class"]})
for k in """ar-austral-becas ar-uca-becas ar-udesa-becas ar-unc-becas ar-unlp-becas br-pucrio-bolsas br-ufba-bolsas br-ufmg-bolsas br-ufpe-bolsas br-ufpr-bolsas br-ufrj-bolsas br-ufsc-bolsas br-unb-bolsas br-unesp-bolsas cl-uai-becas cl-udp-becas cl-usach-becas cn-bnu-international cn-buaa-international cn-hust-international cn-nankai-international cn-ruc-international cn-scu-international cn-seu-international cn-sysu-international cn-tongji-international cn-xjtu-international cn-xmu-international eg-alexu-international eg-cu-international id-telkom-international id-ui-international id-undip-international id-unpad-international in-bits-international in-du-international in-iitb-international in-iitm-international in-manipal-international in-snu-international in-vit-international jp-chiba-international jp-kanazawa-international jp-kumamoto-international jp-niigata-international jp-okayama-international jp-tmu-international ma-uca-international mx-anahuac-becas mx-buap-becas mx-ibero-becas mx-uanl-becas my-iium-international my-monash-international my-nottingham-international ng-oau-international ng-ui-international ng-unn-international ph-ateneo-international ph-up-international ph-ust-international th-kku-international th-ku-international th-psu-international uy-ort-becas uy-ucu-becas uy-udelar-becas vn-tdtu-international za-unisa-international""".split():
    X.setdefault(k, "list, home page, news, fees page or several awards")
X["jp-okayama-international"] = "two awards (MEXT special selection and the Discovery Scholarship)"
P.update({
 "de-uni-ulm": dict(fields={"nationality": "not_stated", "levels": ["bachelor", "master", "phd"], "deadlines": [], "cycle_status": "not_stated",
     "stipend": {"amount": [250], "currency": "EUR", "period": "month"}, "funding_class": "stipend_only"},
     evidence={"nationality": "International students of Ulm University who have registered their thesis ... can apply (enrolment, not nationality)",
               "funding_class": "Grants are awarded for at least 250 euros per month."},
     ambiguous="a short-term grant for the final semester"),
})
AMB.update({"de-uni-ulm": ["funding_class"]})
X.update({"de-hhu": "professor page", "de-tu-darmstadt": "two scholarships (equal opportunities and graduation)", "de-uni-bielefeld": "costs page",
          "de-uni-bremen": "outgoing mobility list", "de-uni-frankfurt": "international home", "de-uni-jena": "guest studies page",
          "de-uni-kiel": "student union page", "de-uni-leipzig": "near-empty page", "de-uni-mainz": "application overview", "de-uni-wuerzburg": "overview"})
P.update({
 "de-uni-bayreuth": dict(fields={"nationality": "not_stated", "levels": ["bachelor", "master"], "deadlines": [D("2026-10-21", "current")],
     "cycle_status": "open", "stipend": {"amount": [500], "currency": "EUR", "period": "month"}, "funding_class": "stipend_only"},
     evidence={"nationality": "International students may apply to the International Office for a degree completion grant (status, not nationality)",
               "deadlines": "The application deadline is 21 October 2026.",
               "funding_class": "Funding is provided at a rate of €500/month for 3 months."}),
 "de-uni-kassel": dict(fields={"nationality": "not_stated", "levels": ["bachelor", "master"], "deadlines": [], "cycle_status": "not_stated",
     "funding_class": "stipend_only"},
     evidence={"deadlines": "1 March, 1 July and 1 November of every year (no year)",
               "funding_class": "The scholarship can be granted for up to three months and at least one month (a cash grant; the amount is not stated)"},
     ambiguous="yearly deadlines without a year; no amount"),
 "de-uni-regensburg": dict(fields={"nationality": {"mode": "include", "countries": ["BG", "HR", "CZ", "HU", "PL", "RO", "RU", "RS", "SK", "UA"]},
     "levels": ["master", "phd"], "deadlines": [D("2026-12-01", "current"), D("2027-02-28", "current")], "cycle_status": "open",
     "funding_class": "not_stated"},
     evidence={"nationality": "one-year scholarships to graduates (with appropriate citizenship) from Bulgaria, Croatia, Czechia, Hungary, Poland, Romania, Russia, Serbia, Slovakia and Ukraine",
               "deadlines": "Deadline: December 1, 2026 ... Deadline: February 28, 2027",
               "funding_class": "one-year scholarships ... intended to finance postgraduate studies (no amount or components on the page)"},
     ambiguous="two calls with different deadlines; the amount is in the PDF call"),
 "it-unige": dict(fields={"nationality": "not_stated", "levels": ["master"], "deadlines": [D("2026-07-31")], "cycle_status": "closed",
     "funding_class": "not_stated"},
     evidence={"nationality": "the candidate must be resident in the Palestinian territories (residence, not nationality)",
               "deadlines": "Application deadline: 31st July 2026 - ATTENTION: deadline for submitting applications expired",
               "funding_class": "Amount of each scholarship: EUR 12500 (before tax) (what it pays for is not stated)"},
     ambiguous="an information page carrying one call; a lump sum"),
 "it-imtlucca": dict(fields={"nationality": "not_stated", "levels": ["phd"], "deadlines": [], "cycle_status": "open",
     "components": {"stipend": "covered", "accommodation": "covered", "living_allowance": "covered"}, "funding_class": "fully_funded"},
     evidence={"cycle_status": "Our new PhD call is out.",
               "funding_class": "All students enrolled in the PhD program receive a scholarship of 1,353.58 € per month ... on-campus housing and meals at the IMT canteen for free"},
     ambiguous="a PhD programme page without the call's dates; no tuition is charged"),
 "it-luiss": dict(fields={"nationality": {"mode": "any", "countries": []}, "levels": ["master"], "deadlines": [], "cycle_status": "not_announced",
     "funding_class": "not_stated"},
     evidence={"nationality": "Scholarships are available for international students, whether or not they hold EU/Schengen citizenship",
               "cycle_status": "There are currently no open calls."}),
 "no-nmbu": dict(fields={"nationality": "not_stated", "levels": ["master"], "deadlines": [D("2024-12-01")], "cycle_status": "closed",
     "components": {"tuition": "full", "stipend": "covered", "relocation": "covered"}, "funding_class": "fully_funded"},
     evidence={"nationality": "Be a citizen and resident of the country of the selected partner institution. (the countries follow from a list of partner institutions)",
               "deadlines": "Autumn 2025 Admission - Deadline for applications: 1 December 2024",
               "funding_class": "Full tuition fee ... Scholarship of 13,297NOK per month ... Start-up scholarship - a one-time payment of 15,000NOK"},
     ambiguous="the nationality rule is implied by partner institutions; the page describes the 2025 admission"),
})
AMB.update({"de-uni-kassel": ["deadlines", "funding_class"], "de-uni-regensburg": ["deadlines", "funding_class"], "it-unige": ["nationality", "funding_class"],
            "it-imtlucca": ["cycle_status", "funding_class"], "no-nmbu": ["nationality", "cycle_status"]})
for k in ("ae-sharjah", "am-aua", "at-boku", "at-jku", "at-plus", "be-umons", "be-unamur", "bg-uni-sofia", "cy-cut", "cz-mendelu", "cz-tul", "cz-upol", "cz-vscht", "cz-zcu", "de-rub", "de-tu-braunschweig", "de-tu-dortmund", "de-uni-bamberg", "de-uni-bayreuth", "de-uni-due", "de-uni-hannover", "de-uni-hohenheim", "de-uni-kassel", "de-uni-oldenburg", "de-uni-paderborn", "de-uni-passau", "de-uni-potsdam", "de-uni-regensburg", "dk-itu", "ee-emu", "ee-tlu", "es-ehu", "es-iese", "es-uab", "es-ucm", "es-udc", "es-udg", "es-ull", "es-uma", "es-unican", "es-uniovi", "es-unizar", "es-upc", "es-upm", "es-upv", "es-urv", "es-usc", "es-uv", "es-uvigo", "fr-audencia", "fr-centralesupelec", "fr-escp", "fr-kedge", "fr-neoma", "fr-tbs", "fr-univ-cotedazur", "fr-univ-lille", "fr-univ-lyon1", "fr-univ-nantes", "ge-tsu", "gr-auth", "gr-ntua", "gr-uoa", "hr-uniri", "hr-unist", "hu-corvinus", "hu-pte", "hu-sze", "hu-szeged", "hu-unideb", "is-ru", "it-gssi", "it-imtlucca", "it-luiss", "it-unicatt", "it-unife", "it-unige", "it-unina", "it-unipr", "it-unipv", "it-uniroma2", "it-uniroma3", "it-uniud", "it-univr", "kz-kbtu", "lt-ktu", "lt-lsmu", "lv-lu", "lv-rtu", "no-nmbu", "no-ntnu", "no-oslomet", "no-uio", "no-uis", "no-uit", "pl-agh", "pl-amu", "pl-put", "pl-pw", "pl-pwr", "pl-ug", "pl-umk", "pt-ua", "pt-ualg", "pt-ubi", "pt-uc", "pt-uevora", "pt-unl", "ro-uaic", "ro-unibuc", "ro-upb", "ro-utcluj", "ro-uvt", "sa-ksu", "si-um", "sk-tuke", "sk-uniza", "tr-boun", "us-albany-international", "us-binghamton-international", "us-gmu-international", "us-jmu-international", "us-lehigh-international", "us-njit-international", "us-northeastern-international", "us-odu-international", "us-rpi-international", "us-stevens-international", "us-tufts-international", "us-unh-international", "us-uri-international", "us-uvm-presidential", "us-vcu-international", "us-wm-1693", "us-wpi-international"):
    X.setdefault(k, "list, home page, news, fees page, portal or several awards")
X["cz-vscht"] = "two scholarships (merit and Vlček)"; X["de-uni-hannover"] = "two grants (emergency and degree completion)"
X["hu-corvinus"] = "several scholarships"; X["hr-uniri"] = "2022 call"; X["ee-tlu"] = "several schemes"
P.update({
 "us-memphis-international": dict(fields={"nationality": {"mode": "exclude", "countries": ["US"]}, "levels": ["bachelor"], "deadlines": [],
     "cycle_status": "not_stated", "funding_class": "not_stated"},
     evidence={"nationality": "for newly admitted degree-seeking international students on a J-1 or F-1 visa ... Dual citizens and/or permanent residents are not eligible for this scholarship."},
     ambiguous="the exclusion is stated through dual citizenship and visa status"),
 "us-nau-international": dict(fields={"nationality": "not_stated", "levels": ["bachelor", "master"], "deadlines": [], "cycle_status": "not_stated",
     "tuition": "partial", "funding_class": "partially_funded"},
     evidence={"nationality": "Designed for first-time, degree-seeking F-1 undergraduate and graduate students (visa status, not nationality)",
               "funding_class": "up to $11,000 per year toward NAU tuition and fees through the International Excellence Award ... Disbursed as an out-of-state tuition waiver only."}),
 "us-colostate-international": dict(fields={"nationality": "not_stated", "levels": ["bachelor"], "deadlines": [], "cycle_status": "not_stated",
     "funding_class": "not_stated"},
     evidence={"funding_class": "Scholarships for first-year students range from $2,000 to $12,000 per year (what they pay for is not stated)"},
     ambiguous="a cash range"),
 "us-kent-international": dict(fields={"nationality": "not_stated", "levels": ["bachelor", "master"], "deadlines": [], "cycle_status": "not_stated",
     "tuition": "partial", "funding_class": "partially_funded"},
     evidence={"nationality": "You ARE eligible if you are... An F1 visa holder. (visa status)",
               "funding_class": "our international undergraduate and graduate scholarships are partial scholarships and do not cover full tuition, fees, and living expenses"},
     ambiguous="the Global Scholarship with tiers; the page also lists an Honors add-on"),
})
AMB.update({"us-memphis-international": ["nationality"], "us-colostate-international": ["funding_class"], "us-kent-international": ["funding_class"]})
for k in ("us-baylor-international", "us-case-international", "us-colostate-international", "us-du-international", "us-kent-international", "us-louisville-international", "us-memphis-international", "us-nau-international", "us-ohio-international", "us-sdsu-international", "us-smu-international", "us-tcu-international", "us-uc-international", "us-unt-international", "us-uta-international", "us-utdallas-international", "us-utsa-international"):
    X.setdefault(k, "list, home page, fees page or several awards")
X["us-uc-international"] = "several awards"; X["us-utsa-international"] = "two programmes (grant and Good Neighbor)"
P.update({
 "us-ndsu-international": dict(fields={"nationality": "not_stated", "levels": ["bachelor"], "deadlines": [], "cycle_status": "not_stated",
     "funding_class": "not_stated"},
     evidence={"deadlines": "You must be admitted to NDSU by July 1 (for August start) or January 1 (for January start). (admission dates without a year)",
               "funding_class": "$12,000 ($1,500/semester) ... guaranteed awards (what they pay for is not stated)"},
     ambiguous="admission deadlines without a year; a cash award"),
 "us-uab-international": dict(fields={"nationality": "not_stated", "levels": ["bachelor"], "deadlines": [], "cycle_status": "not_stated",
     "funding_class": "not_stated"},
     evidence={"nationality": "available to applicants who are currently living outside of the US ... Anticipate holding an F-1 visa (residence and visa, not nationality)",
               "funding_class": "The UAB International Scholarship, valued at US $7,500 per year (what it pays for is not stated)"},
     ambiguous="a cash award"),
})
AMB.update({"us-ndsu-international": ["deadlines", "funding_class"], "us-uab-international": ["funding_class"]})
for k in ("us-american-international", "us-chapman-international", "us-depaul-international", "us-drake-international", "us-ecu-international", "us-fau-international", "us-gonzaga-international", "us-luc-international", "us-marquette-international", "us-ndsu-international", "us-pdx-international", "us-pepperdine-international", "us-scu-international", "us-seattleu-international", "us-sjsu-international", "us-slu-international", "us-tulsa-international", "us-txstate-international", "us-uab-international", "us-udayton-international", "us-uic-international", "us-umbc-international", "us-umt-international", "us-uncc-international", "us-und-international", "us-utep-international", "us-uwm-international", "us-wfu-international", "us-wsu-international", "us-xavier-international"):
    X.setdefault(k, "list, home page, admissions page or several awards")
X["us-wsu-international"] = "several awards"
# batch 5 (US university pages)
P.update({
 "us-pugetsound-intl": dict(fields={"nationality": "not_stated", "levels": ["bachelor"], "deadlines": [], "cycle_status": "not_stated",
     "funding_class": "not_stated"},
     evidence={"funding_class": "Your Dean's Scholarship may only be applied towards Puget Sound tuition, not room, board or other expenses (amount not stated)"},
     ambiguous="terms page for recipients; a tuition award of unstated size"),
 "us-duq-intl": dict(fields={"nationality": "not_stated", "levels": ["bachelor"], "deadlines": [], "cycle_status": "not_stated",
     "components": {"tuition": "partial"}, "funding_class": "partially_funded"},
     evidence={"nationality": "International students who are accepted to Duquesne qualify for the Libermann Scholarship (status, not nationality)",
               "funding_class": "Students who receive the scholarship usually get between $10,000 to $30,000 per academic year ... Full scholarships and financial aid are not available to international students"}),
 "us-trinity-intl": dict(fields={"nationality": "not_stated", "levels": ["bachelor"], "deadlines": [], "cycle_status": "not_stated",
     "funding_class": "not_stated"},
     evidence={"nationality": "Who is eligible: Undergraduate, entering first-year and transfer international students. Who is not eligible: Continuing, domestic, or graduate students",
               "deadlines": "Feb 1 Application Deadline ... Deadline: Feb. 1 (no year)",
               "funding_class": "Need-based international scholarships replace FAFSA funding for international students"},
     ambiguous="'domestic' excluded without naming a country; a yearly deadline without a year; need-based"),
 "us-oberlin-intl": dict(fields={"nationality": "not_stated", "levels": ["bachelor"], "deadlines": [], "cycle_status": "not_stated",
     "funding_class": "not_stated"},
     evidence={"deadlines": "Financial Aid Deadline | November 1 | January 5 | November 1 | January 15 (no year)",
               "funding_class": "meet 100% of calculated financial need for all international students who apply for financial aid"},
     ambiguous="admission-round deadlines without a year; need-based"),
 "us-bentley-intl": dict(fields={"nationality": "not_stated", "levels": ["bachelor"], "deadlines": [D("2020-04-13")], "cycle_status": "closed",
     "funding_class": "not_stated"},
     evidence={"nationality": "Applicants must identify as one of these ethnic groups ... United States and Canada ... United Kingdom and Ireland ... South Africa ... Australia (ethnicity and country of study, not citizenship)",
               "deadlines": "Applications are due by April 13, 2020",
               "funding_class": "Scholarship award $5,000"},
     ambiguous="a career-centre repost of a 2020 call; countries name where the student is enrolled; a cash award"),
 "us-stthomas-intl": dict(fields={"nationality": "not_stated", "levels": ["bachelor"], "deadlines": [], "cycle_status": "not_stated",
     "components": {"tuition": "partial"}, "funding_class": "partially_funded"},
     evidence={"nationality": "International students with visas to study are eligible for merit-based scholarships (visa, not nationality)",
               "funding_class": "merit-based scholarships from 10-70% off tuition ... We do not offer full-ride scholarships ... a merit-based scholarship only applies to tuition"}),
 "us-miamioh-intl": dict(fields={"nationality": "not_stated", "levels": ["bachelor"], "deadlines": [], "cycle_status": "not_stated",
     "components": {"tuition": "partial"}, "funding_class": "partially_funded"},
     evidence={"deadlines": "priority consideration is given to students who submit their application by December 1 (no year; a priority date)",
               "funding_class": "Up to 50% of tuition ... Up to 40% of tuition ... Up to 30% of tuition ... Up to 20% of tuition"},
     ambiguous="a priority date without a year"),
 "us-wmich-intl": dict(fields={"nationality": "not_stated", "levels": ["bachelor", "master"], "deadlines": [], "cycle_status": "not_stated",
     "components": {"tuition": "partial"}, "funding_class": "partially_funded"},
     evidence={"nationality": "Merit scholarships are available only for degree-seeking students on F-1 or J-1 status (visa, not nationality)",
               "deadlines": "No additional application is necessary. Scholarships are awarded on a rolling basis to students while funds are available",
               "funding_class": "Global Education Merit Scholarship, valued up to $10,000 per academic year, can be applied to your WMU tuition"},
     ambiguous="undergraduate and graduate variants of one award on the same page"),
 "us-usm-intl": dict(fields={"nationality": "not_stated", "levels": ["bachelor"], "deadlines": [], "cycle_status": "not_stated",
     "funding_class": "not_stated"},
     evidence={"deadlines": "MARCH 1: Students must be fully admitted ... with final test scores, by this date to be automatically considered (no year)",
               "funding_class": "Annual Scholarship Amount $1,500 ... $2,500 ... $3,000 ... $4,500 ... Full tuition scholarships will increase as tuition rates increase"},
     ambiguous="a yearly date without a year; tiers from a cash award to full tuition"),
 "us-umkc-intl": dict(fields={"nationality": "not_stated", "levels": ["bachelor", "master"], "deadlines": [], "cycle_status": "not_stated",
     "components": {"tuition": "partial"}, "funding_class": "partially_funded"},
     evidence={"nationality": "bachelor's and master's F-1 students are eligible (visa, not nationality)",
               "funding_class": "Each scholarship waives a certain portion of the difference between non-resident tuition and resident tuition ... 100% ... 80% ... 60% ... 50% of Non-Resident Tuition differential"},
     ambiguous="four tiers of one waiver of the non-resident tuition differential"),
 "us-umassd-intl": dict(fields={"nationality": "not_stated", "levels": ["bachelor"], "deadlines": [], "cycle_status": "not_stated",
     "funding_class": "not_stated"},
     evidence={"funding_class": "International Freshmen $10,000-$15,500 with a high school GPA of 2.75 and above ... International Transfers $10,000 (what it pays for is not stated)"},
     ambiguous="a cash award"),
 "us-providence-intl": dict(fields={"nationality": {"mode": "exclude", "countries": ["US"]}, "levels": ["bachelor"], "deadlines": [],
     "cycle_status": "not_stated", "funding_class": "not_stated"},
     evidence={"nationality": "a limited amount of need-based aid to international students (non-US citizens)",
               "funding_class": "that support is capped at the cost of tuition ... Our need-based awards can cover up to the cost of full tuition, though these cases are extremely rare"},
     ambiguous="'non-US citizens' is a definition of international; need-based with a tuition cap"),
 "us-gustavus-intl": dict(fields={"nationality": {"mode": "exclude", "countries": ["US"]}, "levels": ["bachelor"], "deadlines": [],
     "cycle_status": "not_stated", "funding_class": "not_stated"},
     evidence={"nationality": "international students are automatically reviewed for the $43,000 Count Folke Bernadotte Scholarship ... Applicants who do not hold a United States Passport or have United States Permanent Residence status, are recognized as International Students",
               "funding_class": "the $43,000 Count Folke Bernadotte Scholarship (what it pays for is not stated)"},
     ambiguous="the exclusion comes from the definition of 'international'; a cash award"),
 "us-ucr-intl": dict(fields={"nationality": "not_stated", "levels": ["bachelor"], "deadlines": [], "cycle_status": "not_stated",
     "funding_class": "not_stated"},
     evidence={"nationality": "admitted students must be confirmed nonresidents (residency, not nationality)",
               "funding_class": "First-year students may receive up to $89,100 for four years, and transfers may receive up to $44,550 for two years (what it pays for is not stated)"},
     ambiguous="a cash award"),
 "us-hope-intl": dict(fields={"nationality": "not_stated", "levels": ["bachelor"], "deadlines": [], "cycle_status": "not_stated",
     "funding_class": "not_stated"},
     evidence={"funding_class": "automatically be considered for a merit-based scholarship of up to $30,000 (what it pays for is not stated)"},
     ambiguous="a cash award"),
})
AMB.update({"us-pugetsound-intl": ["funding_class"], "us-trinity-intl": ["nationality", "deadlines"], "us-oberlin-intl": ["deadlines", "funding_class"],
            "us-bentley-intl": ["nationality"], "us-miamioh-intl": ["deadlines"], "us-wmich-intl": ["levels"], "us-usm-intl": ["deadlines", "funding_class"],
            "us-umkc-intl": ["funding_class"], "us-umassd-intl": ["funding_class"], "us-providence-intl": ["nationality", "funding_class"],
            "us-gustavus-intl": ["nationality", "funding_class"], "us-ucr-intl": ["funding_class"], "us-hope-intl": ["funding_class"]})
for k in ("us-adelphi-intl", "us-agnesscott-intl", "us-alaska-intl", "us-babson-intl", "us-bard-intl", "us-beloit-intl", "us-bentley-intl", "us-bgsu-intl", "us-bradley-intl", "us-bryant-intl", "us-bucknell-intl", "us-butler-intl", "us-calpoly-intl", "us-caltech-intl", "us-calvin-intl", "us-campbell-intl", "us-carleton-intl", "us-centre-intl", "us-clarku-intl", "us-cmc-intl", "us-csulb-intl", "us-denison-intl", "us-depauw-intl", "us-dickinson-intl", "us-drew-intl", "us-duq-intl", "us-earlham-intl", "us-eckerd-intl", "us-elon-intl", "us-emerson-intl", "us-emich-intl", "us-fairfield-intl", "us-fandm-intl", "us-fit-intl", "us-furman-intl", "us-georgiasouthern-intl", "us-gettysburg-intl", "us-goucher-intl", "us-grinnell-intl", "us-gustavus-intl", "us-gvsu-intl", "us-hendrix-intl", "us-highpoint-intl", "us-hofstra-intl", "us-holycross-intl", "us-hope-intl", "us-ithaca-intl", "us-jhu-intl", "us-kean-intl", "us-kennesaw-intl", "us-kenyon-intl", "us-knox-intl", "us-kzoo-intl", "us-lafayette-intl", "us-lasalle-intl", "us-latech-intl", "us-lawrence-intl", "us-lclark-intl", "us-lmu-intl", "us-loyno-intl", "us-loyola-intl", "us-luther-intl", "us-mercer-intl", "us-miamioh-intl", "us-millsaps-intl", "us-mines-intl", "us-montclair-intl", "us-morehouse-intl", "us-niu-intl", "us-nova-intl", "us-oberlin-intl", "us-oru-intl", "us-pace-intl", "us-pitzer-intl", "us-pomona-intl", "us-pratt-intl", "us-providence-intl", "us-pugetsound-intl", "us-quinnipiac-intl", "us-redlands-intl", "us-reed-intl", "us-rider-intl", "us-rit-intl", "us-rollins-intl", "us-rowan-intl", "us-samford-intl", "us-scranton-intl", "us-shu-intl", "us-siena-intl", "us-simmons-intl", "us-siu-intl", "us-sju-intl", "us-skidmore-intl", "us-spelman-intl", "us-stedwards-intl", "us-stjohns-intl", "us-stolaf-intl", "us-stthomas-intl", "us-suffolk-intl", "us-towson-intl", "us-transy-intl", "us-trinity-intl", "us-ucdavis-intl", "us-ucr-intl", "us-ucsc-intl", "us-umassd-intl", "us-umkc-intl", "us-uncw-intl", "us-uni-intl", "us-union-intl", "us-unomaha-intl", "us-ursinus-intl", "us-usfca-intl", "us-usm-intl", "us-vassar-intl", "us-washington-intl", "us-wayne-intl", "us-whitman-intl", "us-whittier-intl", "us-willamette-intl", "us-wit-intl", "us-wmich-intl", "us-wofford-intl", "us-wooster-intl"):
    X.setdefault(k, "list, home page, admissions page or several awards")
for k in ("us-butler-intl", "us-adelphi-intl", "us-whitman-intl", "us-gvsu-intl", "us-niu-intl", "us-loyno-intl", "us-unomaha-intl", "us-towson-intl", "us-earlham-intl"):
    X[k] = "several awards"
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
(M / "labels.json").write_text(json.dumps({"today": "2026-10-19", "version": "P-1",
    "note": "programme decisions labelled by hand from the official pages before any extractor ran on them; quotes per field",
    "pages": pages}, indent=1, ensure_ascii=False) + "\n")
print(len(pages), "labelled (all test);", sum(1 for p in urls["pages"] if p["split"] == "excluded"), "excluded")
