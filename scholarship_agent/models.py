"""Scholarship domain model.

Plain dataclasses with a stable to_dict()/from_dict() shape. Every dict that
leaves the service layer carries SCHEMA_VERSION so a future web backend can
detect drift. Nested structures persist as JSON inside the store; the fields
the engine filters on (country, deadlines, status) also get their own columns.
"""

from __future__ import annotations

import dataclasses
import functools
import hashlib
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

SCHEMA_VERSION = "1.0"


class StrEnum(str, Enum):
    def __str__(self) -> str:  # json.dumps and f-strings show the value
        return self.value


class VerificationStatus(StrEnum):
    CONFIRMED = "officially_confirmed"
    EXTRACTED = "extracted_unverified"
    HISTORICAL = "historical"
    ESTIMATED = "estimated"
    CONFLICTING = "conflicting"
    UNKNOWN = "unknown"
    SOURCE_UNAVAILABLE = "source_unavailable"


class SourceType(StrEnum):
    OFFICIAL = "official"          # the provider's own site or its government portal
    AGGREGATOR = "aggregator"      # discovery aid only; never the authority
    SEARCH_RESULT = "search_result"
    USER_SUPPLIED = "user_supplied"


class SourceAuthority(StrEnum):
    """How much a page can be trusted for a fact, strongest first. Levels 1-4 are official; 5-7 never confirm."""
    PROGRAMME_PAGE = "1_official_programme_page"      # the scholarship's own page on the provider's site
    PROVIDER_PAGE = "2_official_provider_page"        # other pages of the university / funder
    GOVERNMENT = "3_official_government_agency"       # ministry, embassy, public agency portal
    OFFICIAL_FEED = "4_official_catalogue_feed"       # provider's structured dataset, catalogue or RSS
    TRUSTED_SECONDARY = "5_trusted_secondary"         # e.g. another university's page relaying an external award
    AGGREGATOR = "6_aggregator_or_search_result"      # listing sites, blogs, search hits
    LEAD = "7_unverified_lead"                        # a URL nobody has read yet

    @property
    def official(self) -> bool:
        return self.value[0] in "1234"


class ProviderType(StrEnum):
    UNIVERSITY = "university"
    GOVERNMENT = "government"
    PUBLIC_AGENCY = "public_agency"
    FOUNDATION = "foundation"
    INTERNATIONAL_ORG = "international_org"
    RESEARCH_INSTITUTE = "research_institute"
    COMPANY = "company"
    AGGREGATOR = "aggregator"
    OTHER = "other"


class EligibilityStatus(StrEnum):
    ELIGIBLE = "ELIGIBLE"
    LIKELY_ELIGIBLE = "LIKELY_ELIGIBLE"
    UNCERTAIN = "UNCERTAIN"
    INELIGIBLE = "INELIGIBLE"
    INSUFFICIENT_INFORMATION = "INSUFFICIENT_INFORMATION"


class FundingClass(StrEnum):
    FULLY_FUNDED = "fully_funded"
    TUITION_FUNDED = "tuition_funded"
    PARTIALLY_FUNDED = "partially_funded"
    STIPEND_ONLY = "stipend_only"
    ASSISTANTSHIP = "assistantship"
    FEE_WAIVER = "fee_waiver"
    UNCLEAR = "funding_unclear"


class DeadlineKind(StrEnum):
    SCHOLARSHIP = "scholarship"
    ADMISSION = "admission"
    TEST = "test"
    RECOMMENDATION = "recommendation"
    DOCUMENT = "document"
    OPENING = "opening"
    ROLLING = "rolling"                # applications reviewed as they arrive; no closing date
    INSTITUTIONAL = "institutional"    # a date for universities, nominating bodies or officials, not applicants
    EVENT = "event"                    # results, interviews, open days, announcements
    NOMINATION = "nomination"          # round 28: a school's, supervisor's or coordinator's nomination or selection date
    REFERENCE = "reference"            # round 28: a date quoted from an earlier cycle (an FAQ, "this year's deadline" years ago)
    OTHER_PROGRAMME = "other_programme"   # round 29: a date the page gives for another award or a partner's own window
    OTHER = "other"


class DeadlineCertainty(StrEnum):
    CONFIRMED = "confirmed"            # stated by an official source for the current cycle
    EXPECTED = "expected_unconfirmed"  # approximate ("usually in November"); never a precise date
    HISTORICAL = "historical"          # a past cycle's date
    UNKNOWN = "unknown"


class AppStatus(StrEnum):
    DISCOVERED = "discovered"
    AWAITING_VERIFICATION = "awaiting_verification"
    ELIGIBILITY_REVIEW = "eligibility_review"
    SHORTLISTED = "shortlisted"
    PREPARING = "preparing_documents"
    WAITING_RECOMMENDATIONS = "waiting_for_recommendations"
    READY_FOR_REVIEW = "ready_for_review"
    SUBMITTED = "submitted"
    ASSESSMENT = "assessment_or_interview"
    AWAITING_DECISION = "awaiting_decision"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    WITHDRAWN = "withdrawn"
    EXPIRED = "expired"


TERMINAL_STATUSES = {AppStatus.ACCEPTED, AppStatus.REJECTED, AppStatus.WITHDRAWN, AppStatus.EXPIRED}

# Forward flow plus the always-available exits. Going back one planning step is
# allowed (documents get reworked); un-submitting is not.
_PRE_SUBMIT = [AppStatus.DISCOVERED, AppStatus.AWAITING_VERIFICATION, AppStatus.ELIGIBILITY_REVIEW,
               AppStatus.SHORTLISTED, AppStatus.PREPARING, AppStatus.WAITING_RECOMMENDATIONS,
               AppStatus.READY_FOR_REVIEW]
ALLOWED_TRANSITIONS: dict[AppStatus, set[AppStatus]] = {}
for i, s in enumerate(_PRE_SUBMIT):
    ALLOWED_TRANSITIONS[s] = set(_PRE_SUBMIT[max(0, i - 1):]) | {AppStatus.SUBMITTED, AppStatus.WITHDRAWN, AppStatus.EXPIRED}
    ALLOWED_TRANSITIONS[s].discard(s)
ALLOWED_TRANSITIONS[AppStatus.DISCOVERED] -= {AppStatus.SUBMITTED}
ALLOWED_TRANSITIONS[AppStatus.SUBMITTED] = {AppStatus.ASSESSMENT, AppStatus.AWAITING_DECISION, AppStatus.ACCEPTED,
                                            AppStatus.REJECTED, AppStatus.WITHDRAWN}
ALLOWED_TRANSITIONS[AppStatus.ASSESSMENT] = {AppStatus.AWAITING_DECISION, AppStatus.ACCEPTED, AppStatus.REJECTED,
                                             AppStatus.WITHDRAWN}
ALLOWED_TRANSITIONS[AppStatus.AWAITING_DECISION] = {AppStatus.ASSESSMENT, AppStatus.ACCEPTED, AppStatus.REJECTED,
                                                    AppStatus.WITHDRAWN}
for s in TERMINAL_STATUSES:
    ALLOWED_TRANSITIONS[s] = set()


def stable_id(*parts: str, prefix: str = "sch") -> str:
    h = hashlib.sha256("\x1f".join(p.strip().lower() for p in parts).encode()).hexdigest()[:12]
    return f"{prefix}_{h}"


# ---------------------------------------------------------------- dataclasses

class Model:
    """to_dict/from_dict for nested dataclasses and enums."""

    def to_dict(self) -> dict:
        return _plain(self)

    @classmethod
    def from_dict(cls, d: dict):
        return _build(cls, d)


def _plain(v):
    if dataclasses.is_dataclass(v):
        return {f.name: _plain(getattr(v, f.name)) for f in dataclasses.fields(v)}
    if isinstance(v, Enum):
        return v.value
    if isinstance(v, list):
        return [_plain(x) for x in v]
    if isinstance(v, dict):
        return {k: _plain(x) for k, x in v.items()}
    return v


@functools.lru_cache(maxsize=None)
def _hints(cls) -> dict:
    """A dataclass's resolved field types, worked out once (get_type_hints evaluates the annotations each call)."""
    import typing
    return typing.get_type_hints(cls)


def _build(cls, d):
    hints = _hints(cls)
    kwargs = {}
    for f in dataclasses.fields(cls):
        if f.name not in d:
            continue
        kwargs[f.name] = _coerce(hints[f.name], d[f.name])
    return cls(**kwargs)


def _coerce(tp, v):
    import typing
    if v is None:
        return None
    origin = typing.get_origin(tp)
    args = typing.get_args(tp)
    if origin is typing.Union:
        inner = [a for a in args if a is not type(None)]
        return _coerce(inner[0], v) if inner else v
    if origin is list:
        return [_coerce(args[0], x) for x in v]
    if origin is dict:
        return {k: _coerce(args[1], x) for k, x in v.items()}
    if isinstance(tp, type) and issubclass(tp, Enum):
        return tp(v)
    if isinstance(tp, type) and dataclasses.is_dataclass(tp):
        return _build(tp, v)
    return v


@dataclass
class Evidence(Model):
    """One claim about one field, tied to where it came from."""
    field: str
    value: Any
    source_url: str
    source_type: SourceType = SourceType.OFFICIAL
    snippet: str = ""
    retrieved_at: str = ""
    verified_at: Optional[str] = None
    status: VerificationStatus = VerificationStatus.EXTRACTED
    confidence: float = 0.5
    note: str = ""
    authority: str = ""                 # SourceAuthority of source_url
    method: str = "rules"               # rules | ollama | anthropic | openai_compat | structured
    cycle: Optional[str] = None         # scholarship cycle the claim applies to, when stated
    warnings: list[str] = field(default_factory=list)   # why the quote may not substantiate the value
    original: str = ""                  # the value as written on the page ("15. mars 2027"), when it differs from value
    final_url: str = ""                 # address after redirects / rendering
    programme: str = ""                 # programme the claim belongs to
    applicant_category: str = ""        # who it applies to ("US citizens", "new students"), when the page limits it
    method_version: str = ""            # rules-r14, extract-v2, targeted-v1 ...
    verdict: str = "accepted"           # accepted | needs_review (a person decides; never applied to the record)

    def decision(self) -> str:
        """accepted | needs_review | confirmed (accepted and confirmed on an official page)."""
        if self.verdict == "needs_review":
            return "needs_review"
        return "confirmed" if self.status == VerificationStatus.CONFIRMED else "accepted"


@dataclass
class Deadline(Model):
    kind: DeadlineKind
    certainty: DeadlineCertainty
    date: Optional[str] = None          # ISO date; only set when the source states one
    time: Optional[str] = None          # "23:59" when stated
    timezone: Optional[str] = None      # "CET", "UTC+9" ... when stated
    cycle: Optional[str] = None         # "2026/2027"
    approximate: Optional[str] = None   # "usually early November" - EXPECTED deadlines live here
    recurs: Optional[str] = None        # "03-01" when the source says the date recurs every year (EXPECTED, no year)
    label: str = ""                     # verbatim evidence quotation
    source_url: str = ""
    scope: str = "general"              # general | country | applicant_group | institution | programme
    applies_to: list[str] = field(default_factory=list)   # ISO countries, institution or programme names
    retrieved_at: str = ""
    warnings: list[str] = field(default_factory=list)


@dataclass
class FundingComponent(Model):
    kind: str                           # tuition | stipend | living_allowance | travel | insurance | relocation | research | fee_waiver | other
    covered: Optional[bool] = True      # None = mentioned but unclear
    amount: Optional[float] = None
    currency: Optional[str] = None
    period: Optional[str] = None        # month | semester | year | total | one_off
    full: Optional[bool] = None         # "full tuition" vs a partial amount
    note: str = ""


@dataclass
class LanguageRequirement(Model):
    test: str                           # IELTS | TOEFL_IBT | PTE | DUOLINGO | CAMBRIDGE | MOI | OTHER
    minimum: Optional[float] = None
    language: str = "English"
    mandatory: bool = True
    note: str = ""


@dataclass
class NationalityRule(Model):
    mode: str = "unknown"               # any | include | exclude | unknown
    countries: list[str] = field(default_factory=list)   # ISO alpha-2
    residency_required: list[str] = field(default_factory=list)
    note: str = ""
    # what the countries are: citizenship | origin ("students from X") | "" when the page does not say.
    # Residence lives in residency_required; mode stays "unknown" unless the page states a nationality rule.
    basis: str = ""
    # round 27: "international" | "domestic_and_international" | "" - who may apply by fee status. "Open to
    # international students" is not "open to all nationalities", so it never sets mode to "any".
    applicant_scope: str = ""


@dataclass
class RequiredDocument(Model):
    name: str
    category: str = "scholarship"       # admission | scholarship | visa | enrollment
    mandatory: Optional[bool] = True
    format: str = ""
    word_limit: Optional[int] = None
    char_limit: Optional[int] = None
    prompt: str = ""                    # the actual essay question, when given
    translation: str = ""
    certification: str = ""
    source_url: str = ""


@dataclass
class Opportunity(Model):
    id: str
    title: str
    provider_name: str
    provider_type: ProviderType = ProviderType.OTHER
    info_url: str = ""
    application_url: str = ""
    destination_countries: list[str] = field(default_factory=list)
    institution: str = ""
    programs: list[str] = field(default_factory=list)
    study_levels: list[str] = field(default_factory=list)   # bachelor | master | phd | postdoc | short_course | exchange
    disciplines: list[str] = field(default_factory=list)
    nationality: NationalityRule = field(default_factory=NationalityRule)
    min_gpa: Optional[float] = None
    gpa_scale: Optional[float] = None
    max_age: Optional[int] = None
    min_age: Optional[int] = None
    # level-specific limits [{"level": "bachelor", "max": 35, "min": 19}, ...]; max_age/min_age stay None then
    age_limits: list[dict] = field(default_factory=list)
    min_work_years: Optional[float] = None
    requires_supervisor: Optional[bool] = None
    requires_research_proposal: Optional[bool] = None
    language_requirements: list[LanguageRequirement] = field(default_factory=list)
    moi_policy: str = ""                # only when officially documented
    funding: list[FundingComponent] = field(default_factory=list)
    funding_duration: str = ""
    renewal_conditions: str = ""
    deadlines: list[Deadline] = field(default_factory=list)
    current_cycle: Optional[str] = None
    required_documents: list[RequiredDocument] = field(default_factory=list)
    selection_criteria: list[str] = field(default_factory=list)
    evidence: list[Evidence] = field(default_factory=list)
    verification_status: VerificationStatus = VerificationStatus.EXTRACTED
    verification_reason: str = ""       # plain-language why the record has its status
    source_authority: str = ""          # SourceAuthority of info_url
    discovered_authority: str = ""      # authority of the page it was first found on (aggregator origin tracking)
    last_verified_at: Optional[str] = None
    uncertainties: list[str] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)
    # funder / provider / host / administrator / partner, each with the sentence that states the role
    funding_parties: list[dict] = field(default_factory=list)
    # what the page the record rests on is (identity.PAGE_TYPES), kept apart from source_authority (who published it)
    page_type: str = "unknown"
    page_language: str = ""             # round 47: <html lang>, else detected from the whole page text
    # {"state": confirmed | needs_review | rejected, "name", "reasons"} from identity.identity() on the fetched page
    programme_identity: dict = field(default_factory=dict)
    # round 29: distinctive words of the award this page is about (its title plus the award name it repeats); used to
    # tell this programme's dates and quotations from those of other awards named on the same page
    own_programme_words: list[str] = field(default_factory=list)
    # per key field: {"state": present | not_stated | not_applicable | ..., "detail": ...}; see audit.py
    field_status: dict[str, dict] = field(default_factory=dict)
    # round 43: an independent model's own reading of the four decisions (ai_check.py); answers it reads differently are
    # held for review, never replaced
    second_reading: dict[str, str] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)
    # scholarship_programme | research_position | funded_project | admission_programme | fellowship | grant | unknown
    opportunity_type: str = "unknown"
    provider_metadata: dict[str, Any] = field(default_factory=dict)   # adapter-specific fields, kept verbatim
    discovered_via: str = ""
    created_at: str = ""
    updated_at: str = ""


@dataclass
class Fact(Model):
    value: Any
    confirmed: bool = True              # False = inferred, never used as proof of eligibility
    source: str = "user"                # user | document:<name> | inferred


@dataclass
class Education(Model):
    degree: str                         # bachelor | master | phd | diploma ...
    field: str = ""
    institution: str = ""
    country: str = ""
    start: str = ""
    end: str = ""                       # graduation date; "" = in progress / unknown
    gpa: Optional[float] = None
    gpa_scale: Optional[float] = None
    completed: Optional[bool] = None
    language_of_instruction: str = ""
    confirmed: bool = True


@dataclass
class TestScore(Model):
    test: str
    score: float
    date: str = ""
    confirmed: bool = True


@dataclass
class Experience(Model):
    kind: str                           # work | research | teaching | volunteer
    title: str
    organization: str = ""
    start: str = ""
    end: str = ""
    description: str = ""
    confirmed: bool = True


@dataclass
class Profile(Model):
    id: str = "default"
    name: str = ""
    email: str = ""
    citizenships: list[str] = field(default_factory=list)       # ISO alpha-2
    residence_country: str = ""
    date_of_birth: str = ""
    education: list[Education] = field(default_factory=list)
    target_levels: list[str] = field(default_factory=list)
    target_intake: str = ""
    preferred_countries: list[str] = field(default_factory=list)
    disciplines: list[str] = field(default_factory=list)
    research_interests: list[str] = field(default_factory=list)
    languages: dict[str, str] = field(default_factory=dict)     # language -> level
    tests: list[TestScore] = field(default_factory=list)
    experience: list[Experience] = field(default_factory=list)
    projects: list[str] = field(default_factory=list)
    publications: list[str] = field(default_factory=list)
    achievements: list[str] = field(default_factory=list)
    funding_need: str = "full"                                  # full | tuition | partial | any
    passport_valid_until: str = ""
    documents_ready: list[str] = field(default_factory=list)    # names of docs the applicant already holds
    inferred: dict[str, Fact] = field(default_factory=dict)     # anything not confirmed by the applicant
    updated_at: str = ""
