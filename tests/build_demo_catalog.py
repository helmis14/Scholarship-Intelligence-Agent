"""Fill a scratch catalog from the saved pages of evaluation sets, for trying the web front end without a live crawl.

    python3 tests/build_demo_catalog.py /tmp/demo-data heldout_x heldout_w [--readings ~/.scholar_check/reading_haiku.json]
    SCHOLAR_DATA_DIR=/tmp/demo-data python3 -m scholarship_agent serve

Only the labelled single-programme pages are read; every record goes through the same extraction and checks as a live
run. The destination hint is the country a first-round page was searched for (urls.json "parent": "search:XX"; those
searches asked for study in that country), as discovery passes it. --readings attaches second readings saved by tests/decisions_check.py (keyed by model, address and page
text; no model is called), so the catalogue shows what the public setting shows: rules, second reading, strict gate.
The pages are copies kept for evaluation; a public catalogue is built from live pages.
"""
import hashlib
import json
import sys
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))


def main():
    import os
    if not os.environ.get("SCHOLAR_RISK_GATE"):
        os.environ["SCHOLAR_RISK_GATE"] = "strict"
    from scholarship_agent.audit import field_status
    from scholarship_agent.extract import classify_page, extract_opportunity
    from scholarship_agent.heldout import load_page
    from scholarship_agent.identity import page_type
    from scholarship_agent.models import ProviderType, SourceType
    from scholarship_agent.normalize import dedup_key, normalize_url
    from scholarship_agent.store import Store
    args = sys.argv[1:]
    readings = {}
    while "--readings" in args:
        i = args.index("--readings")
        readings.update(json.loads(Path(args[i + 1]).expanduser().read_text()))
        del args[i:i + 2]
    out, sets = Path(args[0]), args[1:] or ["heldout_x"]
    model = os.environ.get("SCHOLAR_READING_MODEL", "claude-haiku-5-5")
    store = Store(out)
    n = read = 0
    for s in sets:
        root = REPO / "tests" / s
        labels = json.loads((root / "labels.json").read_text())
        today = date.fromisoformat(labels["today"])
        urls = {p["id"]: p for p in json.loads((root / "urls.json").read_text())["pages"]}
        for pid in labels["pages"]:
            meta = urls[pid]
            pg = load_page(pid, meta["url"], root)
            parent = meta.get("parent", "")
            # first-round searches asked for study in a country; second-round ones ("x2-", "w2-") for its citizens
            hint = [parent.split(":", 1)[1].upper()] if parent.startswith("search:") and len(parent) == 9 \
                and not pid.split("-")[0].endswith("2") else []
            opp, _ = extract_opportunity(pg, provider_name=meta.get("domain", ""), provider_type=ProviderType.OTHER,
                                         source_type=SourceType.OFFICIAL, country_hint=hint, retrieved_at=today.isoformat(),
                                         today=today)
            cls = classify_page(pg)
            opp.page_type = "unknown" if cls["confidence"] == "low" else page_type(cls["kind"])
            key = hashlib.sha256(f"{model}\n{pg.url}\n{pg.text}".encode()).hexdigest()
            if key in readings:
                opp.second_reading = readings[key]
                read += 1
            opp.field_status = field_status(opp, today)
            store.save_opportunity(opp, dedup_key(opp.title, opp.provider_name), normalize_url(opp.info_url))
            n += 1
    print(json.dumps({"records": n, "second_readings": read, "data_dir": str(out)}))


if __name__ == "__main__":
    main()
