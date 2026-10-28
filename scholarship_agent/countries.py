"""ISO 3166-1 countries with UN M49 regions, plus name lookup.

Used for nationality rules, destination coverage, and the coverage-gap report.
The coverage report walks this whole table, which is how "supports global
search" is kept apart from "has sources for": every country without a
registered source is listed as a gap.
"""

from __future__ import annotations

import re

_RAW = """
AF|Afghanistan|Asia AX|Aland Islands|Europe AL|Albania|Europe DZ|Algeria|Africa AS|American Samoa|Oceania
AD|Andorra|Europe AO|Angola|Africa AI|Anguilla|Americas AG|Antigua and Barbuda|Americas AR|Argentina|Americas
AM|Armenia|Asia AW|Aruba|Americas AU|Australia|Oceania AT|Austria|Europe AZ|Azerbaijan|Asia BS|Bahamas|Americas
BH|Bahrain|Asia BD|Bangladesh|Asia BB|Barbados|Americas BY|Belarus|Europe BE|Belgium|Europe BZ|Belize|Americas
BJ|Benin|Africa BM|Bermuda|Americas BT|Bhutan|Asia BO|Bolivia|Americas BA|Bosnia and Herzegovina|Europe
BW|Botswana|Africa BR|Brazil|Americas BN|Brunei|Asia BG|Bulgaria|Europe BF|Burkina Faso|Africa BI|Burundi|Africa
CV|Cabo Verde|Africa KH|Cambodia|Asia CM|Cameroon|Africa CA|Canada|Americas KY|Cayman Islands|Americas
CF|Central African Republic|Africa TD|Chad|Africa CL|Chile|Americas CN|China|Asia CO|Colombia|Americas
KM|Comoros|Africa CG|Congo|Africa CD|Democratic Republic of the Congo|Africa CK|Cook Islands|Oceania
CR|Costa Rica|Americas CI|Cote d'Ivoire|Africa HR|Croatia|Europe CU|Cuba|Americas CW|Curacao|Americas
CY|Cyprus|Asia CZ|Czechia|Europe DK|Denmark|Europe DJ|Djibouti|Africa DM|Dominica|Americas
DO|Dominican Republic|Americas EC|Ecuador|Americas EG|Egypt|Africa SV|El Salvador|Americas
GQ|Equatorial Guinea|Africa ER|Eritrea|Africa EE|Estonia|Europe SZ|Eswatini|Africa ET|Ethiopia|Africa
FK|Falkland Islands|Americas FO|Faroe Islands|Europe FJ|Fiji|Oceania FI|Finland|Europe FR|France|Europe
GF|French Guiana|Americas PF|French Polynesia|Oceania GA|Gabon|Africa GM|Gambia|Africa GE|Georgia|Asia
DE|Germany|Europe GH|Ghana|Africa GI|Gibraltar|Europe GR|Greece|Europe GL|Greenland|Americas GD|Grenada|Americas
GP|Guadeloupe|Americas GU|Guam|Oceania GT|Guatemala|Americas GG|Guernsey|Europe GN|Guinea|Africa
GW|Guinea-Bissau|Africa GY|Guyana|Americas HT|Haiti|Americas VA|Holy See|Europe HN|Honduras|Americas
HK|Hong Kong|Asia HU|Hungary|Europe IS|Iceland|Europe IN|India|Asia ID|Indonesia|Asia IR|Iran|Asia IQ|Iraq|Asia
IE|Ireland|Europe IM|Isle of Man|Europe IL|Israel|Asia IT|Italy|Europe JM|Jamaica|Americas JP|Japan|Asia
JE|Jersey|Europe JO|Jordan|Asia KZ|Kazakhstan|Asia KE|Kenya|Africa KI|Kiribati|Oceania KP|North Korea|Asia
KR|South Korea|Asia XK|Kosovo|Europe KW|Kuwait|Asia KG|Kyrgyzstan|Asia LA|Laos|Asia LV|Latvia|Europe
LB|Lebanon|Asia LS|Lesotho|Africa LR|Liberia|Africa LY|Libya|Africa LI|Liechtenstein|Europe LT|Lithuania|Europe
LU|Luxembourg|Europe MO|Macao|Asia MG|Madagascar|Africa MW|Malawi|Africa MY|Malaysia|Asia MV|Maldives|Asia
ML|Mali|Africa MT|Malta|Europe MH|Marshall Islands|Oceania MQ|Martinique|Americas MR|Mauritania|Africa
MU|Mauritius|Africa YT|Mayotte|Africa MX|Mexico|Americas FM|Micronesia|Oceania MD|Moldova|Europe MC|Monaco|Europe
MN|Mongolia|Asia ME|Montenegro|Europe MS|Montserrat|Americas MA|Morocco|Africa MZ|Mozambique|Africa
MM|Myanmar|Asia NA|Namibia|Africa NR|Nauru|Oceania NP|Nepal|Asia NL|Netherlands|Europe NC|New Caledonia|Oceania
NZ|New Zealand|Oceania NI|Nicaragua|Americas NE|Niger|Africa NG|Nigeria|Africa NU|Niue|Oceania
MK|North Macedonia|Europe NO|Norway|Europe OM|Oman|Asia PK|Pakistan|Asia PW|Palau|Oceania PS|Palestine|Asia
PA|Panama|Americas PG|Papua New Guinea|Oceania PY|Paraguay|Americas PE|Peru|Americas PH|Philippines|Asia
PL|Poland|Europe PT|Portugal|Europe PR|Puerto Rico|Americas QA|Qatar|Asia RE|Reunion|Africa RO|Romania|Europe
RU|Russia|Europe RW|Rwanda|Africa KN|Saint Kitts and Nevis|Americas LC|Saint Lucia|Americas
VC|Saint Vincent and the Grenadines|Americas WS|Samoa|Oceania SM|San Marino|Europe ST|Sao Tome and Principe|Africa
SA|Saudi Arabia|Asia SN|Senegal|Africa RS|Serbia|Europe SC|Seychelles|Africa SL|Sierra Leone|Africa
SG|Singapore|Asia SX|Sint Maarten|Americas SK|Slovakia|Europe SI|Slovenia|Europe SB|Solomon Islands|Oceania
SO|Somalia|Africa ZA|South Africa|Africa SS|South Sudan|Africa ES|Spain|Europe LK|Sri Lanka|Asia SD|Sudan|Africa
SR|Suriname|Americas SE|Sweden|Europe CH|Switzerland|Europe SY|Syria|Asia TW|Taiwan|Asia TJ|Tajikistan|Asia
TZ|Tanzania|Africa TH|Thailand|Asia TL|Timor-Leste|Asia TG|Togo|Africa TK|Tokelau|Oceania TO|Tonga|Oceania
TT|Trinidad and Tobago|Americas TN|Tunisia|Africa TR|Turkiye|Asia TM|Turkmenistan|Asia TC|Turks and Caicos Islands|Americas
TV|Tuvalu|Oceania UG|Uganda|Africa UA|Ukraine|Europe AE|United Arab Emirates|Asia GB|United Kingdom|Europe
US|United States|Americas UY|Uruguay|Americas UZ|Uzbekistan|Asia VU|Vanuatu|Oceania VE|Venezuela|Americas
VN|Vietnam|Asia VG|British Virgin Islands|Americas VI|U.S. Virgin Islands|Americas EH|Western Sahara|Africa
YE|Yemen|Asia ZM|Zambia|Africa ZW|Zimbabwe|Africa
"""

COUNTRIES: dict[str, tuple[str, str]] = {}
for _tok in re.findall(r"([A-Z]{2})\|([^|]+?)\|(Africa|Americas|Asia|Europe|Oceania)", _RAW):
    COUNTRIES[_tok[0]] = (_tok[1].strip(), _tok[2])

ALIASES = {
    "usa": "US", "u.s.": "US", "u.s.a.": "US", "united states of america": "US", "america": "US", "uk": "GB", "great britain": "GB",
    "britain": "GB", "england": "GB", "scotland": "GB", "wales": "GB", "korea": "KR", "republic of korea": "KR",
    "turkey": "TR", "türkiye": "TR", "czech republic": "CZ", "viet nam": "VN", "ivory coast": "CI",
    "côte d'ivoire": "CI", "drc": "CD", "dr congo": "CD", "uae": "AE", "russian federation": "RU",
    "swaziland": "SZ", "burma": "MM", "east timor": "TL", "lao pdr": "LA", "macedonia": "MK", "holland": "NL",
    "deutschland": "DE", "nippon": "JP", "brasil": "BR", "méxico": "MX", "españa": "ES", "italia": "IT",
}
# Country names as written on German, French, Spanish/Portuguese and Indonesian pages (where they differ).
_LOCAL = {
    "ID": "indonesien indonésie", "KE": "kenia", "VN": "viêt nam", "BR": "brasilien brésil", "MX": "mexiko mexique",
    "EG": "ägypten égypte egipto egito mesir", "IN": "indien inde", "CN": "chine", "JP": "japon jepang",
    "ZA": "südafrika afrique du sud sudáfrica áfrica do sul afrika selatan", "DE": "allemagne alemania alemanha jerman",
    "FR": "frankreich francia frança prancis", "ES": "spanien espagne espanha spanyol", "CO": "kolumbien colombie",
    "PE": "perú pérou", "MA": "marokko maroc marruecos marrocos maroko", "TR": "türkei turquie turquía",
    "PH": "philippinen filipinas filipina", "ET": "äthiopien éthiopie etiopía", "BD": "bangladesch",
    "GB": "vereinigtes königreich royaume-uni reino unido inggris", "US": "vereinigte staaten états-unis estados unidos amerika serikat",
    "IT": "italien italie", "NL": "niederlande pays-bas países bajos belanda", "SN": "sénégal", "TN": "tunesien tunisie túnez",
    "DZ": "algerien algérie argelia", "CM": "kamerun cameroun camerún", "CI": "elfenbeinküste", "TZ": "tansania tanzanie",
    "NG": "nigéria", "PK": "pakistán", "AF": "afghanistán", "IR": "irán", "IQ": "irak", "SY": "syrien syrie siria",
    "JO": "jordanien jordanie jordania", "LB": "libanon liban líbano", "SA": "saudi-arabien arabie saoudite arabia saudita arab saudi",
    "KR": "südkorea corée du sud corea del sur korea selatan", "MY": "malaisie malasia", "TH": "thaïlande tailandia",
    "NP": "népal", "LK": "sri lanka", "MM": "birmanie", "KH": "kambodscha cambodge camboya kamboja",
    "CL": "chili", "AR": "argentinien argentine", "EC": "équateur", "BO": "bolivien bolivie", "VE": "venezuela",
    "GT": "guatemala", "CU": "kuba", "HT": "haïti", "RU": "russland russie rusia rusia", "UA": "ukraine ucrania",
    "PL": "polen pologne polonia", "GR": "griechenland grèce grecia yunani", "AU": "australien australie",
    "NZ": "neuseeland nouvelle-zélande nueva zelanda selandia baru", "CA": "kanada", "CH": "schweiz suisse suiza swiss",
    "AT": "österreich autriche", "BE": "belgien belgique bélgica", "SE": "schweden suède suecia swedia",
    "NO": "norwegen norvège noruega norwegia", "DK": "dänemark danemark dinamarca denmark", "FI": "finnland finlande finlandia",
}
# Tokens that only make sense inside a multi-word name ("corea del sur"); those names are added whole below.
_PARTS = set("corée sud del sur du de united states reino unido arabie saoudite arabia saudita afrique nouvelle zélande "
             "nueva zelanda selatan korea afrika amerika serikat royaume uni vereinigtes königreich vereinigte staaten "
             "états unis estados unidos países bajos pays bas saudi sri lanka côte d'ivoire baru selandia inggris "
             "áfrica do sul viêt nam "   # round 27: "do" alone matched every English "do" as South Africa
             "".split())
for _c, _names in _LOCAL.items():
    for _n in _names.split():
        if _n not in _PARTS:
            ALIASES.setdefault(_n, _c)
# names official lists write with accents or in "name (qualifier)" form
ALIASES.update({"áfrica do sul": "ZA", "viêt nam": "VN"})
ALIASES.update({"bosnia-herzegovina": "BA", "bosnia & herzegovina": "BA", "bosnia herzegovina": "BA", "bosnia-hercegovina": "BA"})   # round 42
ALIASES.update({"são tomé and príncipe": "ST", "sao tomé and príncipe": "ST", "são tomé e príncipe": "ST",
                "congo (democratic republic)": "CD", "congo (democratic republic of the)": "CD", "dr congo": "CD",
                "d.r. congo": "CD", "drc": "CD", "democratic republic of congo": "CD", "rd congo": "CD",
                "congo (republic)": "CG", "republic of the congo": "CG", "congo-brazzaville": "CG", "congo-kinshasa": "CD"})
ALIASES.update({"afrique du sud": "ZA", "royaume-uni": "GB", "états-unis": "US", "estados unidos": "US",
                "reino unido": "GB", "corée du sud": "KR", "corea del sur": "KR", "arabie saoudite": "SA",
                "amerika serikat": "US", "korea selatan": "KR", "nouvelle-zélande": "NZ", "nueva zelanda": "NZ",
                "sri lanka": "LK", "países bajos": "NL", "surinam": "SR", "afrika selatan": "ZA", "vereinigte staaten": "US",
                "vereinigtes königreich": "GB", "selandia baru": "NZ", "arab saudi": "SA", "côte d'ivoire": "CI"})
DEMONYMS = {
    # round 31: European and other demonyms the pages use ("Spanish or Portuguese nationality"); "polish" and
    # "georgian" are left out because the match is case-insensitive and they are also an English verb / a US state
    "portuguese": "PT", "dutch": "NL", "swedish": "SE", "norwegian": "NO", "danish": "DK", "finnish": "FI",
    "czech": "CZ", "hungarian": "HU", "romanian": "RO", "bulgarian": "BG", "greek": "GR", "irish": "IE",
    "austrian": "AT", "swiss": "CH", "belgian": "BE", "luxembourgish": "LU", "croatian": "HR", "slovenian": "SI",
    "slovene": "SI", "slovak": "SK", "estonian": "EE", "latvian": "LV", "lithuanian": "LT", "maltese": "MT",
    "cypriot": "CY", "icelandic": "IS", "new zealander": "NZ", "emirati": "AE", "saudi": "SA", "qatari": "QA",
    "kuwaiti": "KW", "omani": "OM", "israeli": "IL", "libyan": "LY", "singaporean": "SG", "taiwanese": "TW",
    "kazakh": "KZ", "uzbek": "UZ", "kyrgyz": "KG", "tajik": "TJ", "turkmen": "TM", "azerbaijani": "AZ",
    "armenian": "AM", "moldovan": "MD", "serbian": "RS", "bosnian": "BA", "macedonian": "MK", "albanian": "AL",
    "montenegrin": "ME", "kosovar": "XK", "mongolian": "MN", "burmese": "MM", "laotian": "LA",
    "indonesian": "ID", "indian": "IN", "pakistani": "PK", "bangladeshi": "BD", "nigerian": "NG", "kenyan": "KE",
    "ghanaian": "GH", "egyptian": "EG", "filipino": "PH", "vietnamese": "VN", "thai": "TH", "malaysian": "MY",
    "chinese": "CN", "japanese": "JP", "korean": "KR", "brazilian": "BR", "mexican": "MX", "american": "US",
    "canadian": "CA", "british": "GB", "german": "DE", "french": "FR", "italian": "IT", "spanish": "ES",
    "turkish": "TR", "ethiopian": "ET", "ugandan": "UG", "tanzanian": "TZ", "rwandan": "RW", "nepalese": "NP",
    "nepali": "NP", "sri lankan": "LK", "afghan": "AF", "iranian": "IR", "iraqi": "IQ", "jordanian": "JO",
    "moroccan": "MA", "tunisian": "TN", "algerian": "DZ", "south african": "ZA", "zimbabwean": "ZW",
    "colombian": "CO", "peruvian": "PE", "chilean": "CL", "argentine": "AR", "australian": "AU",
    "russian": "RU", "belarusian": "BY", "ukrainian": "UA", "syrian": "SY", "sudanese": "SD", "yemeni": "YE",
    "somali": "SO", "palestinian": "PS", "lebanese": "LB",
}
for _stem, _c in (("colombian", "CO"), ("peruan", "PE"), ("mexican", "MX"), ("chilen", "CL"), ("argentin", "AR"),
                  ("ecuatorian", "EC"), ("bolivian", "BO"), ("venezolan", "VE"), ("paraguay", "PY"), ("uruguay", "UY"),
                  ("guatemaltec", "GT"), ("hondureñ", "HN"), ("salvadoreñ", "SV"), ("costarricens", "CR"),
                  ("dominican", "DO"), ("cuban", "CU"), ("nicaragüens", "NI"), ("panameñ", "PA")):
    for _suf in ("o", "a", "os", "as"):
        DEMONYMS.setdefault(_stem + _suf, _c)
# French nationality adjectives ("de nationalité palestinienne", "ressortissants marocains")
for _stem, _c in (("palestinien", "PS"), ("marocain", "MA"), ("algérien", "DZ"), ("tunisien", "TN"), ("sénégalais", "SN"),
                  ("camerounais", "CM"), ("ivoirien", "CI"), ("malien", "ML"), ("béninois", "BJ"), ("rwandais", "RW"),
                  ("burundais", "BI"), ("haïtien", "HT"), ("indonésien", "ID"), ("vietnamien", "VN"), ("cambodgien", "KH"),
                  ("népalais", "NP"), ("philippin", "PH"), ("bolivien", "BO"), ("péruvien", "PE"), ("équatorien", "EC"),
                  ("cubain", "CU"), ("mexicain", "MX"), ("brésilien", "BR"), ("égyptien", "EG"), ("éthiopien", "ET")):
    for _suf in ("", "e", "s", "es", "ne", "nes"):
        if not (_suf.startswith("n") and not _stem.endswith("ien")):
            DEMONYMS.setdefault(_stem + _suf, _c)

_BY_NAME = {name.lower(): code for code, (name, _) in COUNTRIES.items()}
_BY_NAME.update(ALIASES)


def _trie(words: list[str]) -> str:
    """One pattern for many names, sharing their prefixes ("niger(?:ia(?:n)?)?"). Python tries an alternation one
    branch at a time; the shared-prefix form fails at the first letter that fits no name, about twenty times faster on
    long pages. Optional tails are greedy, so the longest name is tried first, as in a longest-first alternation."""
    root: dict = {}
    for w in words:
        node = root
        for ch in w:
            node = node.setdefault(ch, {})
        node[""] = {}

    def build(node: dict) -> str:
        alts = [re.escape(ch) + build(child) for ch, child in sorted(node.items()) if ch]
        if not alts:
            return ""
        body = alts[0] if len(alts) == 1 else "(?:" + "|".join(alts) + ")"
        return f"(?:{body})?" if "" in node else body

    return build(root)


# Longest names first so "South Sudan" wins over "Sudan", "Niger" does not eat "Nigeria".
_NAME_RX = re.compile(r"\b(" + _trie(sorted({n.lower() for n in list(_BY_NAME) + list(DEMONYMS)})) + r")(?!\w)", re.I)

REGIONS = sorted({r for _, r in COUNTRIES.values()})


def code(text: str) -> str | None:
    t = (text or "").strip()
    if len(t) == 2 and t.upper() in COUNTRIES:
        return t.upper()
    return _BY_NAME.get(t.lower()) or DEMONYMS.get(t.lower())


def name(c: str) -> str:
    return COUNTRIES.get(c.upper(), (c, ""))[0]


def region(c: str) -> str:
    return COUNTRIES.get(c.upper(), ("", "Unknown"))[1]


def mentions(text: str) -> list[str]:
    """Country codes named in text, in order of first appearance."""
    seen: list[str] = []
    for m in _NAME_RX.finditer(text or ""):
        k = m.group(1).lower()
        c = _BY_NAME.get(k) or DEMONYMS.get(k)
        if c and k not in _BY_NAME and _ADJ_NOUN_RX.match(text, m.end()):
            continue   # "Dutch student visa", "Finnish Student Health Service", "Austrian national health plan": not a person
        if c and c not in seen:
            seen.append(c)
    return seen


# a demonym used as an adjective of a thing, not of the applicant
_ADJ_NOUN_RX = re.compile(r"\s+(?:students?'?\s+)?(?:visas?|health|services?|union|fees?|plans?|universit(?:y|ies)|language|"
                          r"government|embassy|embassies|consulates?|institutions?|residence|bank|law|degrees?|qualifications?|"
                          r"system|authorit(?:y|ies)|culture|society|labou?r|market|tax|insurance|national (?:health|insurance|"
                          r"law|system|government|register|id)|academic|higher education|school|colleges?|public|state|border|"
                          r"grading|credits?|economy|history|literature|studies|politics|society|media|art|cuisine|krone|crowns?|"
                          r"francs?|dollars?|pounds?|euros?)\b", re.I)

# Member lists for groups an eligibility sentence names without listing ("outside the EU/EEA"). Source: the EU's
# member list (european-union.europa.eu, 27 states since 2020) and the EEA Agreement (EU + Iceland, Liechtenstein,
# Norway). Switzerland is in neither and is added only when a page names it.
EU = ["AT", "BE", "BG", "HR", "CY", "CZ", "DK", "EE", "FI", "FR", "DE", "GR", "HU", "IE", "IT", "LV", "LT", "LU", "MT",
      "NL", "PL", "PT", "RO", "SK", "SI", "ES", "SE"]
EEA = EU + ["IS", "LI", "NO"]
EFTA = ["IS", "LI", "NO", "CH"]    # the EFTA Convention (efta.int)
_GROUP_RX = re.compile(r"\b(EU\s*/\s*EEA|EEA|European Economic Area|EFTA|European Free Trade Association|EU|European Union)\b")


def group_members(text: str) -> list[str]:
    """Codes of the EU/EEA named in text plus any countries named beside them ("EU/EEA, Switzerland or Surinam")."""
    out: list[str] = []
    for m in _GROUP_RX.finditer(text or ""):
        g = m.group(1)
        out += EU if g in ("EU", "European Union") else EFTA if g in ("EFTA", "European Free Trade Association") else EEA
    out += mentions(text)
    return list(dict.fromkeys(out))
