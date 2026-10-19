"""Benchmark for the application-document side (round 31): does the reviewer catch what the rules forbid, and do the
documents the code assembles stay inside the confirmed facts?

The agent never invents prose: voice documents (essays, statements) come from the orchestrating model or the applicant,
so what the code owns is (1) the fact-only CV and skeletons, and (2) review.review(), the gate every draft passes
before it is saved. This benchmark plants known faults into otherwise clean drafts and measures:
  recall     planted faults the reviewer flags (by fault kind)
  false alarms   issues of severity error/warning raised on the clean draft (it has none)
  cv_invention   numbers, years and organisation names in the assembled CV that are not confirmed facts (must be 0)
  skeleton       placeholders for every required topic, no prose claims
Synthetic profile and opportunities only; no network, no model. Usage: docs_bench.py [--json]
"""
import json, re, sys
from pathlib import Path
REPO = Path(__file__).resolve().parents[1]
sys.path.append(str(REPO))

from scholarship_agent import documents as D, review as R  # noqa: E402
from scholarship_agent.models import Education, Experience, Opportunity, Profile, RequiredDocument, TestScore  # noqa: E402

PROFILE = Profile(
    id="bench", name="Ayu Lestari", citizenships=["ID"], residence_country="ID", target_levels=["master"],
    target_intake="2027-09", disciplines=["public health"], research_interests=["maternal health", "health systems"],
    education=[Education(degree="bachelor", field="Public Health", institution="Universitas Gadjah Mada", country="ID",
                         start="2019-08", end="2023-07", gpa=3.62, gpa_scale=4.0)],
    tests=[TestScore(test="IELTS", score=7.0, date="2026-03")],
    experience=[Experience(kind="work", title="Programme Officer", organization="Yayasan Sehat Bersama", start="2023-09",
                           end="", description="Coordinated a community midwife training programme in Yogyakarta.")],
    achievements=["Best graduate of the Faculty of Medicine, Public Health and Nursing, 2023"],
    languages={"Indonesian": "native", "English": "C1"},
)
PROFILE.inferred = {"publications"}

OPPS = [
    Opportunity(id="o1", title="Global Health Leaders Scholarship", provider_name="Example University", info_url="https://x.org/ghl",
                study_levels=["master"], selection_criteria=["academic excellence", "leadership potential", "commitment to health equity"],
                required_documents=[RequiredDocument(name="Motivation letter", word_limit=500,
                                                     prompt="Describe your leadership experience and how the programme will help you improve health equity in your country.")]),
    Opportunity(id="o2", title="Research Master Fellowship", provider_name="Example Institute", info_url="https://x.org/rmf",
                study_levels=["master"], selection_criteria=["research quality", "feasibility"],
                required_documents=[RequiredDocument(name="Research proposal", word_limit=1000,
                                                     prompt="Outline your research question, methods and expected impact.")]),
    Opportunity(id="o3", title="Equity Scholarship", provider_name="Example Foundation", info_url="https://x.org/eq",
                study_levels=["master"], selection_criteria=["financial need", "community service"],
                required_documents=[RequiredDocument(name="Personal statement", char_limit=3000,
                                                     prompt="Tell us about your community service and your goals.")]),
]

CLEAN = {
    "o1": ("I graduated in Public Health from Universitas Gadjah Mada in 2023 and now work as a Programme Officer at "
           "Yayasan Sehat Bersama, where I coordinate a community midwife training programme in Yogyakarta. That work is "
           "my leadership experience: I plan sessions, support midwives and follow up on what changes in the villages. "
           "The programme would give me the health systems knowledge to improve health equity for mothers in Indonesia, "
           "and I would return to extend the training to more districts."),
    "o2": ("My research question is how community midwife training changes maternal health outcomes in rural districts. "
           "The methods are a before-and-after comparison of records from the training programme I coordinate at Yayasan "
           "Sehat Bersama, with interviews. The expected impact is practical guidance for health systems in Indonesia. "
           "The study is feasible within the master's year because the records already exist."),
    "o3": ("My community service is the midwife training programme I coordinate at Yayasan Sehat Bersama in Yogyakarta. "
           "My goals are to study health systems and return to work on maternal health in Indonesia."),
}

# (fault kind, reviewer issue type expected, how the fault is planted)
FAULTS = [
    ("invented_gpa", "unsupported_claim", lambda t: t + " I graduated with a GPA of 3.9."),
    ("invented_organisation", "unsupported_claim", lambda t: t + " I also interned at the World Health Organization Jakarta Office."),
    ("invented_year", "unsupported_claim", lambda t: t + " In 2021 I led the national student congress."),
    ("invented_publication", "missing_evidence", lambda t: t + " I published two papers on maternal health."),
    ("invented_award", "missing_evidence", lambda t: t + " I won the national public health innovation award."),
    ("placeholder_left", "placeholder", lambda t: t + " [YOU WRITE: a specific example]"),
    ("over_word_limit", "word_limit", lambda t: t + (" This sentence pads the essay beyond the limit." * 160)),
    ("missing_topic", "required_topic", lambda t: re.sub(r"leadership|health equity|methods|community service", "work", t, flags=re.I)),
    ("over_char_limit", "char_limit", lambda t: t + (" More words to pass the character limit." * 90)),
]


def _facts_text():
    return D.fact_text(PROFILE).lower()


def cv_invention() -> dict:
    """Numbers, years and capitalised names in the assembled CV that are not confirmed facts."""
    cv = D.academic_cv(PROFILE, OPPS[0])
    facts = _facts_text() + " " + OPPS[0].title.lower() + " " + OPPS[0].provider_name.lower()
    bad = []
    for m in re.finditer(r"\b(\d{4}|\d\.\d{1,2})\b", cv):
        if m.group(1) not in facts and m.group(1).split("-")[0] not in facts:
            bad.append(m.group(1))
    for m in D.re.finditer(r"\b([A-Z][a-z]+(?: [A-Z][a-z]+){1,4})\b", cv):
        name = m.group(1)
        if name.lower() not in facts and not all(w.lower() in facts for w in name.split() if len(w) > 3) \
                and name not in ("Research and", "Professional", "Awards and", "Research interests", "Public Health"):
            bad.append(name)
    return {"invented": sorted(set(bad)), "has_education": "## Education" in cv,
            "uses_inferred": any(k in cv.lower() for k in PROFILE.inferred)}


def skeleton_check() -> dict:
    out = {}
    for o in OPPS:
        kind = D.writing_tasks(o)[0]["kind"]
        b = D.brief(kind, o, PROFILE)
        sk = D.skeleton(kind, b)
        topics = b["required_topics"][:6]
        out[o.id] = {"kind": kind, "placeholders": len(R.PLACEHOLDER.findall(sk)),
                     "topics_with_placeholder": sum(1 for t in topics if f"'{t}'" in sk), "topics": len(topics),
                     "prose_claims": len(R.CLAIM_VERBS.findall(sk))}
    return out


def reviewer_bench() -> dict:
    hits = {}
    false_alarms = []
    for o in OPPS:
        task = D.writing_tasks(o)[0]
        b = D.brief(task["kind"], o, PROFILE, task)
        clean = CLEAN[o.id]
        rv = R.review(clean, b, PROFILE)
        false_alarms += [f"{o.id}: {i['type']}: {i['detail'][:80]}" for i in rv["issues"] if i["severity"] in ("error", "warning")]
        for name, expect, plant in FAULTS:
            if (expect == "char_limit") != bool(b.get("char_limit")) and expect in ("word_limit", "char_limit"):
                continue   # a limit kind the brief does not have
            text = plant(clean)
            if text == clean:
                continue
            found = [i["type"] for i in R.review(text, b, PROFILE)["issues"]]
            hits.setdefault(name, []).append(expect in found)
    recall = {k: f"{sum(v)}/{len(v)}" for k, v in hits.items()}
    # cross-document consistency: a GPA that differs between two drafts
    b = D.brief("motivation_letter", OPPS[0], PROFILE)
    rv = R.review(CLEAN["o1"] + " My GPA of 3.62 reflects steady work.", b, PROFILE,
                  other_docs={"cv": "## Education\n- GPA 3.9/4.0"})
    recall["gpa_inconsistency"] = f"{int(any(i['type'] == 'consistency' for i in rv['issues']))}/1"
    return {"recall_by_fault": recall, "false_alarms_on_clean_drafts": false_alarms,
            "planted": sum(len(v) for v in hits.values()), "caught": sum(sum(v) for v in hits.values())}


def main():
    out = {"reviewer": reviewer_bench(), "cv": cv_invention(), "skeletons": skeleton_check()}
    print(json.dumps(out, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
