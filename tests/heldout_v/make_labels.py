"""Set V labels (round 43), written by hand from the official pages in pages/ before any extractor ran on set V.

Set V is the fourth fresh test set and the first built from the pages the agent itself reads: every source in
scholarship_agent/sources.json was fetched and the links on it that name an award were followed (tests/heldout_v/collect.py;
hosts of labelled pages in sets T and U left out). 501 pages were fetched on 2026-10-21 after the round-42 code was finished;
86 single-programme pages were labelled and the rest are excluded without a per-page reason (lists, several programmes on
one page, news, staff or research grants, forms, near-empty pages, or not reviewed). Labels follow the reading of sets L to
U: fee status, residence, enrolment, membership and region or group names without a list are "not_stated" nationality; a
cash award whose use is not stated is "not_stated" funding (paid per month or year: "stipend_only", marked as a close call);
a stated share, cap or fixed amount towards tuition is "partially_funded"; deadlines are applicant dates with a year;
cycle_status as of 2026-10-21. Close calls are recorded per decision in AMB ("ambiguous_fields"); results are reported with
and without them. Run once to write labels.json; manifest.json then freezes it."""
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
 "v-br-cnpq-2": dict(fields=L(NS, ["postdoc"], [D("2027-01-07", "current")], "open", "stipend_only"),
     evidence={"deadlines": "Estão abertas até 07 de janeiro de 2027 as inscrições", "funding_class": "PQ-Sr | 5 anos | R$ 1.500 (monthly research grant)"},
     ambiguous="researchers holding a doctorate read as postdoc level; a monthly research grant read as stipend_only"),
 "v-c-anu-edu-au-au-1": dict(fields=L(NS, ["bachelor", "master"], funding="partially_funded"),
     evidence={"nationality": "holds residential status in one of the following Countries or Regions (residence)", "funding_class": "20% off your first-year tuition fees."}),
 "v-c-aus-edu-ae": dict(fields=L(NS, ["bachelor"], [D("2025-04-17")], "closed", "fully_funded", ST),
     evidence={"deadlines": "The deadline to apply is Thursday, April 17, 2025.", "funding_class": "100% tuition and lab fees; Monthly stipend"}),
 "v-c-concordia-ca-ca-1": dict(fields=L(NS, ["master", "phd"], [D("2026-09-30")], "closed"),
     evidence={"deadlines": "Applicants should send an email to sjc@concordia.ca by Sept 30, 2026", "funding_class": "bursaries of 7,000$ each (use not stated)"}),
 "v-c-cuhk-edu-hk-hk-2": dict(fields=L(NS, ["master"]), evidence={"nationality": "scholarships for local students (status)"}),
 "v-c-dal-ca-ca-2": dict(fields=L(INC("CA"), ["bachelor"], [], "closed", "partially_funded"),
     evidence={"nationality": "Be a Canadian citizen or permanent resident.", "cycle_status": "Note: Applications are now closed. Check back in fall 2026",
               "funding_class": "Up to $30,000 ... Travel stipend ($3,500) Living stipend (up to $12,000) ..."},
     ambiguous="permanent residents also eligible; capped amounts read as partial funding"),
 "v-c-fu-berlin-de-de": dict(fields=L(NS, ["phd", "postdoc"]),
     evidence={"nationality": "doctoral students and postdoctoral researchers from outstanding Chinese universities (institution)"},
     ambiguous="CSC rules (on another site) require Chinese citizenship; the page names universities only"),
 "v-c-imperial-ac-uk-gb-1": dict(fields=L(NS, ["master"], [D("2025-03-27")], "closed"),
     evidence={"deadlines": "Application deadline 27/03/2025 Closed", "funding_class": "GBP 10,000 cash bursary (use not stated)",
               "nationality": "available for Home and Overseas students (fee status)"}),
 "v-c-imperial-ac-uk-gb-2": dict(fields=L(INC("GB"), ["master"], [D("2026-05-01")], "closed", "tuition_funded", TF),
     evidence={"nationality": "be a UK national and eligible for Home fee status", "deadlines": "Application deadline 01/05/2026 Closed",
               "funding_class": "Full Home tuition fee scholarship"}),
 "v-c-mun-ca-ca-2": dict(fields=L(NS, ["bachelor"], [], "closed"),
     evidence={"cycle_status": "The application period for the 2026-27 academic year is complete. Check back in January 2027",
               "funding_class": "Valued at $5,000 each (use not stated)", "nationality": "students graduating from a Newfoundland and Labrador high school ... living in the area (residence)"}),
 "v-c-nawa-gov-pl-pl": dict(fields=L(NS, ["master"], funding="fully_funded", comp=ST),
     evidence={"nationality": "open to citizens of 36 countries covered by Polish Aid ... The full list ... is available in the call announcement.",
               "funding_class": "monthly scholarship of PLN 2,500; exemption from tuition fees at public universities"},
     ambiguous="the 36 countries are not listed on this page"),
 "v-c-nyu-edu-ae-1": dict(fields=L(INC("US"), ["bachelor", "master"], [D("2023-02-01")], "closed"),
     evidence={"nationality": "Be a citizen of the United States at the time of application", "deadlines": "All applications are due by February 1st, 2023."}),
 "v-c-pku-edu-cn-cn-1": dict(fields=L(NS, ["bachelor", "master", "phd"], [], "closed"),
     evidence={"nationality": "full-time foreign undergraduate, master's and doctoral student ... from Peking University (status)",
               "cycle_status": "Open now until Beijing time at 9:00 a.m. on September 11th (notice of September 3, 2025)"},
     ambiguous="the closing date has no year; the notice date makes it 2025"),
 "v-c-qatar-vcu-edu-qa-1": dict(fields=L(NS, ["bachelor"], [], "open", "tuition_funded", TF),
     evidence={"cycle_status": "ADMISSIONS FOR FALL 2027 NOW OPEN + NEW MERIT SCHOLARSHIP AVAILABLE",
               "funding_class": "up to $40,000/year, which can cover annual tuition as well as on-campus student housing"},
     ambiguous="the scholarship has no own application; tuition plus possibly housing"),
 "v-c-sorbonne-universite-fr-fr-1": dict(fields=L(EXC("FR"), ["master"]),
     evidence={"nationality": "All countries outside France are eligible.", "cycle_status": "Applications are evaluated on an ongoing basis."},
     ambiguous="'countries outside France' may describe the university of origin, not citizenship"),
 "v-c-sutd-edu-sg-sg-1": dict(fields=L(INC("SG"), ["bachelor"], funding="partially_funded"),
     evidence={"nationality": "Singapore Citizen or Singapore Permanent Resident",
               "funding_class": "valued at S$15,000 per academic year ... applied towards the payment of tuition fees and study-related expenses"},
     ambiguous="permanent residents also eligible"),
 "v-c-sutd-edu-sg-sg-2": dict(fields=L(INC("SG"), ["bachelor"], funding="tuition_funded", comp=TF),
     evidence={"nationality": "The Scholarship is open to Singapore Citizens",
               "funding_class": "the subsidised tuition fees (after Tuition Grant) ... travel award of up to S$5,000 ... hostel award that fully covers the compulsory Freshmore hostel stay"},
     ambiguous="tuition plus a first-year hostel and a travel award, no living allowance"),
 "v-c-tudelft-nl-nl-1": dict(fields=L(), evidence={"nationality": "awarded each year to talented female alumni from Delft University of Technology ... (alumni status)"}),
 "v-c-uaeu-ac-ae-ae-1": dict(fields=L(INC("AE"), ["master", "phd"], funding="fully_funded", comp=ST),
     evidence={"nationality": "Full – Ride Scholarship for Master to PhD (UAE nationals) ... recruit high achieving Emirati undergraduate students",
               "funding_class": "Full tuition waiver. Monthly Stipend."}),
 "v-c-uaeu-ac-ae-ae-2": dict(fields=L({"mode": "any", "countries": []}, ["phd"], funding="fully_funded", comp=ST),
     evidence={"nationality": "PhD Fellowship (All Nationalities)", "funding_class": "a) Full Package Full tuition waiver. Monthly Stipend. ... b) Basic Package Full tuition waiver."},
     ambiguous="'all nationalities' is only in the title; a full and a basic (tuition-only) package"),
 "v-c-ucalgary-ca-ca-1": dict(fields=L(INC("CA"), [], funding="partially_funded"),
     evidence={"nationality": "Be a Canadian citizen or permanent resident.", "funding_class": "Value: Up to $1,000 toward tuition fees", "deadlines": "Application Deadline: August 1 (no year)"},
     ambiguous="permanent residents also eligible; continuing education, no degree level"),
 "v-c-ucalgary-ca-ca-2": dict(fields=L(INC("CA")),
     evidence={"nationality": "Canadian citizen or permanent resident", "funding_class": "Value: $1,200 for OHS Diploma; $600 ... per year (use not stated)"},
     ambiguous="permanent residents also eligible"),
 "v-c-udst-edu-qa-qa": dict(fields=L({"mode": "any", "countries": []}, ["bachelor"], [D("2027-03-31", "current")], "upcoming", "fully_funded", ST, openings=["2027-01-10"]),
     evidence={"nationality": "awarded to eligible students residing in Qatar, and to international students from all over the world",
               "deadlines": "FALL 2027 APPLICATIONS 10 January – 31 March 2027", "funding_class": "Tuition fees waiver for obtaining a bachelor's degree; Monthly stipend"},
     ambiguous="'residing in Qatar and international students from all over the world' read as any nationality"),
 "v-c-unpad-ac-id-id-1": dict(fields=L(INC("BN", "KH", "LA", "MY", "MM", "PH", "SG", "TH", "VN", "TL"), ["master"], funding="fully_funded", comp=ST),
     evidence={"nationality": "Pendaftar harus memiliki kewarganegaraan di negara-negara ASEAN (kecuali Indonesia) atau Timor-Leste.",
               "funding_class": "Pengurangan Biaya Penuh ... Biaya Hidup: tunjangan hidup tahunan sebesar IDR 30.000.000"}),
 "v-c-unpad-ac-id-id-2": dict(fields=L(NS, ["master"], [D("2026-07-13")], "closed"),
     evidence={"deadlines": "membuka pendaftaran Program Beasiswa Guru ... hingga 13 Juli 2026"}),
 "v-c-uoguelph-ca-ca-2": dict(fields=L(NS, ["master", "phd"], [D("2026-02-06")], "closed"),
     evidence={"nationality": "129 OGS awarded to Canadian citizens, Permanent Residents, or Protected Persons ... 4 OGS awarded to international students",
               "deadlines": "The deadline to apply for 2026-27 OGS funding at Guelph is February 6, 2026.", "funding_class": "valued at $15,000 for one year (use not stated)"}),
 "v-c-uottawa-ca-ca-2": dict(fields=L(NS, ["bachelor", "master"], funding="partially_funded"),
     evidence={"nationality": "international Francophone and Francophile students ... who pay international tuition fees (fee status)",
               "funding_class": "Differential Tuition Fee Exemption ... Value of the scholarship per eligible term $12,500 - $18,000"}),
 "v-c-uq-edu-au-au-2": dict(fields=L(NS, ["phd"], funding="stipend_only"),
     evidence={"nationality": "Aboriginal and Torres Strait Islander persons (status)", "funding_class": "$20,000 per annum; $5000 per annum research support funds (a top-up)"},
     ambiguous="a yearly top-up read as stipend_only"),
 "v-c-urfu-ru-ru-2": dict(fields=L(NS, ["bachelor", "master", "phd", "postdoc"], funding="tuition_funded", comp=TF),
     evidence={"nationality": "Foreign citizens;", "funding_class": "early admission to a tuition-free program"},
     ambiguous="'foreign citizens' read as status, not an exclusion of Russia"),
 "v-c-uwa-edu-au-au-2": dict(fields=L(NS, ["phd"], [D("2027-06-30", "current")], "open", "stipend_only", openings=["2026-10-19"]),
     evidence={"deadlines": "Open date | 19 Oct 2026 Close date | 30 Jun 2027", "funding_class": "Stipend top up scholarship ... AUD $10,000pa"},
     ambiguous="a yearly top-up read as stipend_only"),
 "v-c-waikato-ac-nz-nz-2": dict(fields=L(NS, ["bachelor"]), evidence={"levels": "If you're a school leaver ..."}),
 "v-c-warwick-ac-uk-gb": dict(fields=L(NS, ["bachelor"], funding="partially_funded"),
     evidence={"funding_class": "a bursary of up to GBP 2,000 per year ... a 50% tuition fee discount", "cycle_status": "Applications for the Warwick Scholars programme will open in March 2026."},
     ambiguous="the only cycle statement names a past opening month"),
 "v-cl-chileatiende-becas-1": dict(fields=L(INC("CL"), ["postdoc"], [D("2025-07-04")], "closed", "stipend_only", {"stipend": "covered"}),
     evidence={"nationality": "Ser chileno o extranjero con permanencia definitiva en Chile vigente.", "deadlines": "Postula al concurso en el sitio web de ANID hasta el 4 de julio de 2025",
               "funding_class": "Asignación de manutención mensual para el becario ... Pasajes ida y vuelta ... seguro médico"},
     ambiguous="foreigners with permanent residence also eligible; a postdoc maintenance allowance read as stipend_only"),
 "v-eu-erasmus-mundus-1": dict(fields=L(INC(*AFRICA), ["master", "phd"]),
     evidence={"nationality": "Students who reside in Africa and are nationals of an African country, can apply"},
     ambiguous="also requires residence in Africa; 'African country' read as the 54 African states"),
 "v-g-education-gov-bb": dict(fields=L(INC("BB"), ["bachelor", "master"], [D("2026-06-17")], "closed", "fully_funded", ST),
     evidence={"nationality": "be citizens of Barbados", "deadlines": "All forms must be completed and submitted no later than June 17, 2026.",
               "funding_class": "full tuition fees ... USA. $6,300.00 per annum (maintenance)"}),
 "v-g-go-psecu-com": dict(fields=L(NS, ["bachelor"], [], "upcoming", "stipend_only"),
     evidence={"cycle_status": "2026's program is officially closed but we will be opening applications for 2027's program in November 2026.",
               "funding_class": "Winners receive a $2,000 scholarship every year over the next four years"},
     ambiguous="closed for 2026 and upcoming for 2027; a yearly cash award read as stipend_only"),
 "v-g-mes-demarches-gov-pf": dict(fields=L(NS, [], [D("2026-10-09")], "closed", openings=["2026-09-09"]),
     evidence={"deadlines": "La campagne d'inscription est ouverte du mercredi 9 septembre 2026 au vendredi 9 octobre 2026 à minuit"}),
 "v-g-pso-gov-ki-1": dict(fields=L(INC("KI"), ["bachelor", "master", "phd"], [D("2026-10-07")], "closed"),
     evidence={"nationality": "invite suitably qualified I-Kiribati", "deadlines": "no later than the 7th October 2026"}),
 "v-g-sitesa-gov-sb-1": dict(fields=L(INC("SB"), ["bachelor", "master", "phd"]), evidence={"nationality": "Be a Solomon Islands Citizen"}),
 "v-g-sitesa-gov-sb-2": dict(fields=L(NS, ["master", "phd"], [D("2025-10-25")], "closed", openings=["2025-09-25"]),
     evidence={"nationality": "Be a citizen of or have been granted refugee status by an eligible Commonwealth country (countries not listed)",
               "deadlines": "The CSC is open for applications between 25 September 2025 and 25 October 2025."},
     ambiguous="eligible Commonwealth countries are not listed on the page"),
 "v-g-tsap-moey-gov-jm-1": dict(fields=L(INC("JM"), ["bachelor"]), evidence={"nationality": "Jamaican citizen, domiciled in Jamaica during the last five years."}),
 "v-g-tsap-moey-gov-jm-2": dict(fields=L(INC("JM"), ["bachelor"]), evidence={"nationality": "Jamaican citizens, domiciled in Jamaica during the last five (5) years"}),
 "v-gb-edinburgh-1": dict(fields=L(INC("TR"), ["bachelor"], [], "closed", "partially_funded"),
     evidence={"nationality": "be a Turkish national domiciled in Turkey.", "cycle_status": "The deadline to apply for this scholarship has now passed.",
               "funding_class": "GBP 100,000 in total towards the tuition fee cost ... GBP 25,000 per year towards these costs"},
     ambiguous="a fixed yearly amount towards tuition; whether it covers the whole fee is not stated"),
 "v-gb-edinburgh-2": dict(fields=L(NS, ["bachelor"], [D("2026-05-31")], "closed", "stipend_only"),
     evidence={"nationality": "classified as UK Graduate or International for fee purposes (fee status)", "deadlines": "The deadline for applying is 31st May 2026.",
               "funding_class": "Each scholarship is worth GBP 5,000 per year"},
     ambiguous="a yearly cash amount read as stipend_only"),
 "v-gh-gsa-2": dict(fields=L(INC("GH"), [], [D("2026-10-28", "current")], "open"),
     evidence={"nationality": "Be Ghanaian citizens resident in Ghana", "deadlines": "Deadline October 28, 2026"},
     ambiguous="cycle read as open from a future deadline"),
 "v-int-jjwbgsp-1": dict(fields=L(NS, [], [], "closed"),
     evidence={"cycle_status": "The RSMFP program is no longer receiving applications", "nationality": "researchers from developing countries (not listed)"}),
 "v-int-mo-ibrahim-1": dict(fields=L(INC(*AFRICA), [], [], "open"),
     evidence={"nationality": "open annually to young professionals, mid-career and new executives from Africa", "cycle_status": "The application process for the 2027 Fellowships is now open."},
     ambiguous="'from Africa' read as the 54 African states"),
 "v-no-forskningsradet-calls-1": dict(fields=L(NS, ["phd", "postdoc"]),
     evidence={"nationality": "doktorgrads- og postdoktorstipendiater som er helt eller delvis finansiert av Forskningsrådet (status)"}),
 "v-pk-nust-scholarships-1": dict(fields=L(NS, ["bachelor", "master"]),
     evidence={"cycle_status": "Institutions are informed as and when the scholarships are available. Tentatively in October / September."}),
 "v-pl-nawa-1": dict(fields=L(INC("AO", "CO", "ET", "IN", "ID", "KE", "LB", "MX", "MM", "NG", "PS", "PE", "ZA", "PH", "SN", "TZ", "UG", "VN"), ["master"], funding="tuition_funded", comp=TF),
     evidence={"nationality": "Scholarship holders will be first recruited from the following countries: Angola, Colombia, ... Uganda and Vietnam.",
               "funding_class": "tuition-free 2nd cycle studies ... preparatory course ... also covered by the scholarship"},
     ambiguous="'first recruited from' the listed countries within developing countries in general; a stipend is not mentioned on this page"),
 "v-tr-turkiye-burslari-1": dict(fields=L(NS, ["bachelor", "master", "phd"], [D("2026-02-20")], "closed", "fully_funded", ST, openings=["2026-01-10"]),
     evidence={"nationality": "open to successful international students from IsDB member countries as well as Muslim communities around the world (not listed)",
               "deadlines": "Application Dates: 10 January – 20 February 2026", "funding_class": "a monthly stipend, accommodation support, tuition fees, health insurance"}),
 "v-uk-chevening-2": dict(fields=L(INC("BN", "KH", "ID", "LA", "MY", "MM", "PH", "SG", "TH", "VN", "TL"), ["master"]),
     evidence={"nationality": "outstanding individuals from ASEAN member states or Timor-Leste"},
     ambiguous="ASEAN read as its ten member states"),
 "v-uk-clarendon": dict(fields=L({"mode": "any", "countries": []}, ["master", "phd"], funding="fully_funded", comp=ST),
     evidence={"nationality": "There are no restrictions on nationality, ordinary residence or field of study.",
               "funding_class": "Clarendon scholarships cover course fees and provide a grant for living expenses",
               "deadlines": "if you apply by the December or January deadline (no year)"}),
 "v-uk-gates-cambridge-1": dict(fields=L(EXC("GB"), ["master", "phd"], funding="fully_funded", comp=ST),
     evidence={"nationality": "outstanding applicants from countries outside the UK", "funding_class": "covers the full cost of studying at Cambridge ... University Composition Fee ... a maintenance allowance"},
     ambiguous="'applicants from countries outside the UK' read as excluding UK nationals"),
 "v-uk-rhodes-1": dict(fields=L(NS, ["master", "phd"], funding="fully_funded", comp=ST),
     evidence={"nationality": "Students from around the world can apply (through constituencies, not listed here)", "funding_class": "The Scholarship covers all fees and a stipend"},
     ambiguous="'from around the world' but awards are by constituency; postgraduate read as master and doctorate"),
 "v-us-knight-hennessy": dict(fields=L({"mode": "any", "countries": []}, ["master", "phd"], funding="fully_funded", comp=ST),
     evidence={"nationality": "Scholars, who come from around the globe", "funding_class": "a fellowship for up to three years of tuition ... a stipend for living and academic expenses"},
     ambiguous="'from around the globe' read as any nationality"),
 "v-x-admissions-uc-edu-2": dict(fields=L(NS, ["bachelor"], funding="tuition_funded", comp=TF),
     evidence={"funding_class": "scholarships for undergraduate tuition and supplemental educational experiences", "cycle_status": "Applications ... open each fall"},
     ambiguous="the tuition amount is not stated"),
 "v-x-admissions-unl-edu-1": dict(fields=L(NS, ["bachelor"], funding="partially_funded"),
     evidence={"funding_class": "up to $1,000 (up to $500/semester) toward University of Nebraska–Lincoln undergraduate tuition", "deadlines": "Apply for admission by March 1 (fall) (no year)"}),
 "v-x-admissions-unl-edu-2": dict(fields=L(NS, ["bachelor"], funding="partially_funded"),
     evidence={"nationality": "Awarded to Nebraska residents (residence)", "funding_class": "$2,000 ($1,000/semester) toward ... undergraduate tuition"}),
 "v-x-engagedlearning-web-baylor-edu-2": dict(fields=L(NS, ["bachelor"], [D("2026-03-01")], "closed"),
     evidence={"deadlines": "Applications have closed as of March 1, 2026."}),
 "v-x-financialaid-ucla-edu-1": dict(fields=L(NS, [], [], "closed"),
     evidence={"cycle_status": "all funding allocated to the Presidential Fellowship for Experiential Learning has been fully exhausted",
               "nationality": "non-DACA, AB 540 undocumented students (status)"},
     ambiguous="funds exhausted rather than an application closing"),
 "v-x-marquette-edu-2": dict(fields=L(NS, ["bachelor"], funding="fully_funded", comp=ST),
     evidence={"funding_class": "Full Ride – tuition, fees, housing and food"}),
 "v-x-oia-nchu-edu-tw-2": dict(fields=L(INC("TW")), evidence={"nationality": "Only Taiwanese students can apply those scholarships."},
     ambiguous="several MOE internship scholarships described in one sentence"),
 "v-x-pnca-willamette-edu-2": dict(fields=L(NS, ["bachelor"], [D("2026-12-01", "current")], "open", "tuition_funded", TF),
     evidence={"nationality": "Be a resident of the state of Oregon. (residence)", "deadlines": "Application Deadline: December 1st, 2026",
               "funding_class": "a full-tuition scholarship ... coverage of remaining tuition costs after ... federal and state grants"},
     ambiguous="cycle read as open from a future deadline"),
 "v-x-unisa-ac-za-1": dict(fields=L(INC("ZA"), ["bachelor"], [D("2026-11-30", "current")], "open", "tuition_funded", TF, openings=["2026-09-21"]),
     evidence={"nationality": "South African (citizens)", "deadlines": "The 2027 UNISA Postgraduate Bursary Application open 21 September 2026 to 30 November 2026",
               "funding_class": "assist qualifying South African Unisa alumni students with their Unisa tuition fees"},
     ambiguous="honours / postgraduate diploma read as bachelor level; 'assist with tuition' read as tuition only"),
 "v-x-uta-edu-1": dict(fields=L(NS, ["bachelor"], funding="stipend_only"),
     evidence={"funding_class": "a $13,000 award annually; up to $52,000 over four years"}, ambiguous="a yearly cash award read as stipend_only"),
 "v-x-uta-edu-2": dict(fields=L(NS, ["bachelor"], funding="stipend_only"),
     evidence={"funding_class": "range from $1,000 to $8,000 per year"}, ambiguous="a yearly cash award read as stipend_only"),
 "v-x-whittier-edu-1": dict(fields=L(NS, ["bachelor"]),
     evidence={"nationality": "be a United States resident and graduate from a U.S. high school (residence)", "deadlines": "Wednesday, April 10 (no year)",
               "funding_class": "a scholarship of an additional $5,000 (use not stated)"}),
 "v-de-boell": dict(fields=L(NS, ["master", "phd"], [D("2027-03-01", "current"), D("2027-09-01", "current")], "upcoming", openings=["2027-01-15", "2027-07-15"]),
     evidence={"nationality": "Priority is given to applicants from DAC countries (a preference, countries not listed)",
               "deadlines": "Spring 2027: 15 January 2027 until 1 March 2027 Fall 2027: 15 July 2027 until 1 September 2027"},
     ambiguous="two application rounds a year"),
 "v-c-adelaide-edu-au-au-1": dict(fields=L(INC("AU"), [], [D("2026-06-30")], "closed", "fully_funded", ST),
     evidence={"nationality": "All applicants must be either Australian citizens or have permanent resident status in Australia.",
               "deadlines": "submit the online application form prior to midnight 30 June 2026",
               "funding_class": "covers reasonable costs for twelve months overseas, including institutional fees ... a generous tax-exempt stipend of $75,000"},
     ambiguous="permanent residents also eligible; artists, not a degree level"),
 "v-c-uwo-ca-ca-1": dict(fields=L(NS, ["phd"], [D("2026-09-18")], "closed", "stipend_only"),
     evidence={"nationality": "Include eligible domestic and international PhD students", "deadlines": "Application Deadline September 18, 2026", "funding_class": "Value $40,000 per year"},
     ambiguous="the date is the university's own submission date; a yearly amount read as stipend_only"),
 "v-c-uq-edu-au-au-1": dict(fields=L(NS, ["master", "phd"], funding="stipend_only", comp={"stipend": "covered"}),
     evidence={"funding_class": "Living stipend of $39,220 per annum tax free ... Single Overseas Student Health Cover", "cycle_status": "EOIs are accepted year-round ... scholarship round dates"},
     ambiguous="domestic applicants may also get a tuition fee scholarship"),
 "v-c-uwa-edu-au-au-1": dict(fields=L(NS, ["phd"], [D("2026-11-02", "current")], "open"),
     evidence={"nationality": "We encourage domestic and international students to apply", "deadlines": "Close date | 02 Nov 2026"},
     ambiguous="cycle read as open from a future close date"),
 "v-tr-turkiye-burslari-2": dict(fields=L(NS, ["bachelor", "master", "phd"]),
     evidence={"nationality": "students and scholars from lsDB member countries (not listed)", "funding_class": "For associate and bachelor's degrees, the scholarship is an interest-free loan (Qard-Hasan)"}),
 "v-gh-gsa-1": dict(fields=L(INC("GH")),
     evidence={"nationality": "supports academically qualified Ghanaian students pursuing accredited tertiary education in Ghana"},
     ambiguous="'Ghanaian students' read as Ghanaian nationals"),
 "v-c-lpdp-kemenkeu-go-id-id": dict(fields=L(INC("ID"), ["master", "phd"], [D("2026-07-31")], "closed", openings=["2026-06-30"]),
     evidence={"nationality": "program beasiswa magister/doktor untuk putra-putri (Indonesia)", "deadlines": "Jadwal dan Tahapan Seleksi Beasiswa LPDP 2026 ... 30 Juni – 31 Juli 2026"},
     ambiguous="the stage names of the schedule table are not in the extracted text; the first row read as registration"),
 "v-uk-csc-2": dict(fields=L(NS, [], [], "closed"),
     evidence={"cycle_status": "Applications for Commonwealth Startup Fellowships are currently closed.",
               "nationality": "a citizen of ... an eligible low or middle income Commonwealth country (not listed)"}),
 "v-c-uj-edu-pl-pl-1": dict(fields=L(NS, ["master"], [D("2026-06-15")], "closed", "fully_funded", ST, openings=["2026-04-15"]),
     evidence={"nationality": "the best candidates from V4, EaP and the Western Balkans (group names)", "deadlines": "Starting date: April 15, 2026 Closing date: June 15, 2026 (noon)",
               "funding_class": "Scholarships cover mobility costs (3500 EUR per semester) and the tuition fee for the programme."},
     ambiguous="the region sentence is about another IVF call; 'mobility costs' read as living costs"),
 "v-g-education-gov-ck": dict(fields=L(INC("CK"), ["bachelor"], [D("2025-11-28")], "closed"),
     evidence={"nationality": "enabling Cook Islanders to pursue tertiary studies", "deadlines": "Scholarship Application Form 2026 (closes 28 November 2025 )"},
     ambiguous="several funding streams of one programme on the page"),
 "v-c-ju-edu-sa-sa": dict(fields=L(NS, [], [D("2026-05-21")], "closed"),
     evidence={"deadlines": "the application deadline is Thursday, May 21, 2026", "nationality": "scholarships for international students (status)"}),
 "v-c-udst-edu-qa-qa-1": dict(fields=L(NS, ["master", "phd"], [D("2025-04-21")], "closed", "tuition_funded", TF),
     evidence={"deadlines": "Deadline to submit application: 21 April 2025, noon (Doha Time).", "funding_class": "Tuition fees: Fully covered. Conference allowance ... Health insurance and settlement allowance for international awardees"},
     ambiguous="tuition plus allowances; no monthly living stipend on the page"),
 "v-g-dmuc-edu-kh-1": dict(fields=L(NS, [], funding="partially_funded"),
     evidence={"funding_class": "automatically qualify for a 25%. School Partnership Award, reducing tuition to just USD 7,500 per year"}),
 "v-g-gov-gg-1": dict(fields=L(NS, [], [], "closed", "fully_funded"),
     evidence={"cycle_status": "Brock University has discontinued its annual scholarship for a student from the islands.",
               "funding_class": "Brock University has offered a fully funded academic opportunity to a local student"},
     ambiguous="a discontinued programme read as closed; 'fully funded' without detail"),
 "v-x-fau-edu-2": dict(fields=L(NS, ["bachelor", "master"], [D("2026-09-19")], "closed"),
     evidence={"deadlines": "Applications will be accepted through September 19th, 2026 in Scholarship Universe."},
     ambiguous="one application for several College of Education awards"),
 "v-x-go-okstate-edu-1": dict(fields=L(NS, ["bachelor"], funding="partially_funded"),
     evidence={"funding_class": "A four-year partial out-of-state tuition waiver ... $15,000 ($60,000 four-year total)", "nationality": "out-of-state students (residence)"}),
 "v-c-mcgill-ca-ca-2": dict(fields=L(NS, ["bachelor", "master", "phd"]),
     evidence={"nationality": "Self-identify as a member of the 2SLGBTQIA+ community (not nationality)", "funding_class": "emergency, medical and administrative costs (need-based amounts not stated)"}),
})
AMB.update({'v-br-cnpq-2': ['levels', 'funding_class'], 'v-c-dal-ca-ca-2': ['nationality', 'funding_class'], 'v-c-fu-berlin-de-de': ['nationality'], 'v-c-nawa-gov-pl-pl': ['nationality'], 'v-c-pku-edu-cn-cn-1': ['cycle_status'], 'v-c-qatar-vcu-edu-qa-1': ['cycle_status', 'funding_class'], 'v-c-sorbonne-universite-fr-fr-1': ['nationality', 'cycle_status'], 'v-c-sutd-edu-sg-sg-1': ['nationality'], 'v-c-sutd-edu-sg-sg-2': ['funding_class'], 'v-c-uaeu-ac-ae-ae-2': ['nationality', 'funding_class'], 'v-c-ucalgary-ca-ca-1': ['nationality'], 'v-c-ucalgary-ca-ca-2': ['nationality'], 'v-c-udst-edu-qa-qa': ['nationality'], 'v-c-uq-edu-au-au-2': ['funding_class'], 'v-c-urfu-ru-ru-2': ['nationality'], 'v-c-uwa-edu-au-au-2': ['funding_class'], 'v-c-warwick-ac-uk-gb': ['cycle_status'], 'v-cl-chileatiende-becas-1': ['nationality', 'funding_class'], 'v-eu-erasmus-mundus-1': ['nationality'], 'v-g-go-psecu-com': ['cycle_status', 'funding_class'], 'v-g-sitesa-gov-sb-2': ['nationality'], 'v-gb-edinburgh-1': ['funding_class'], 'v-gb-edinburgh-2': ['funding_class'], 'v-gh-gsa-2': ['cycle_status'], 'v-int-mo-ibrahim-1': ['nationality'], 'v-pl-nawa-1': ['nationality', 'funding_class'], 'v-uk-chevening-2': ['nationality'], 'v-uk-gates-cambridge-1': ['nationality'], 'v-uk-rhodes-1': ['nationality', 'levels'], 'v-us-knight-hennessy': ['nationality'], 'v-x-admissions-uc-edu-2': ['funding_class'], 'v-x-financialaid-ucla-edu-1': ['cycle_status'], 'v-x-oia-nchu-edu-tw-2': ['nationality'], 'v-x-pnca-willamette-edu-2': ['cycle_status'], 'v-x-unisa-ac-za-1': ['levels', 'funding_class'], 'v-x-uta-edu-1': ['funding_class'], 'v-x-uta-edu-2': ['funding_class'], 'v-de-boell': ['deadlines'], 'v-c-adelaide-edu-au-au-1': ['nationality'], 'v-c-uwo-ca-ca-1': ['deadlines', 'funding_class'], 'v-c-uq-edu-au-au-1': ['funding_class'], 'v-c-uwa-edu-au-au-1': ['cycle_status'], 'v-gh-gsa-1': ['nationality'], 'v-c-lpdp-kemenkeu-go-id-id': ['nationality', 'deadlines'], 'v-c-uj-edu-pl-pl-1': ['nationality', 'funding_class'], 'v-g-education-gov-ck': ['levels'], 'v-c-udst-edu-qa-qa-1': ['funding_class'], 'v-g-gov-gg-1': ['cycle_status', 'funding_class'], 'v-x-fau-edu-2': ['levels']})

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
(M / "labels.json").write_text(json.dumps({"today": "2026-10-21", "version": "V-1",
    "note": "programme decisions labelled by hand from the official pages before any extractor ran on them; quotes per field",
    "pages": pages}, indent=1, ensure_ascii=False) + "\n")
print(len(pages), "labelled (all test);", sum(1 for p in urls["pages"] if p["split"] == "excluded"), "excluded")
