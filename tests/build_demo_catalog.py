"""Fill a scratch catalog from the saved pages of evaluation sets, for trying the web front end without a live crawl.

    python3 tests/build_demo_catalog.py /tmp/demo-data heldout_x heldout_w
    SCHOLAR_DATA_DIR=/tmp/demo-data python3 -m scholarship_agent serve

Only the labelled single-programme pages are read; every record goes through the same extraction and checks as a live
run (no second reading here). The pages are copies kept for evaluation; a public catalogue is built from live pages.
"""
import json
import sys
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))


def main():
    from scholarship_agent.audit import field_status
    from scholarship_agent.extract import classify_page, extract_opportunity
    from scholarship_agent.heldout import load_page
    from scholarship_agent.identity import page_type
    from scholarship_agent.models import ProviderType, SourceType
    from scholarship_agent.normalize import dedup_key, normalize_url
    from scholarship_agent.store import Store
    out, sets = Path(sys.argv[1]), sys.argv[2:] or ["heldout_x"]
    store = Store(out)
    n = 0
    for s in sets:
        root = REPO / "tests" / s
        labels = json.loads((root / "labels.json").read_text())
        today = date.fromisoformat(labels["today"])
        urls = {p["id"]: p for p in json.loads((root / "urls.json").read_text())["pages"]}
        for pid in labels["pages"]:
            pg = load_page(pid, urls[pid]["url"], root)
            opp, _ = extract_opportunity(pg, provider_name=urls[pid].get("domain", ""), provider_type=ProviderType.OTHER,
                                         source_type=SourceType.OFFICIAL, country_hint=[], retrieved_at=today.isoformat(),
                                         today=today)
            cls = classify_page(pg)
            opp.page_type = "unknown" if cls["confidence"] == "low" else page_type(cls["kind"])
            opp.field_status = field_status(opp, today)
            store.save_opportunity(opp, dedup_key(opp.title, opp.provider_name), normalize_url(opp.info_url))
            n += 1
    print(json.dumps({"records": n, "data_dir": str(out)}))


if __name__ == "__main__":
    main()
