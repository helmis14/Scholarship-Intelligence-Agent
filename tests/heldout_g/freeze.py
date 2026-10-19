"""Freeze set G before evaluation: page snapshot hashes, the labels hash and the classifier files' hashes.
Writes tests/heldout_g/manifest.json; evaluate.py refuses to run when any of these changed."""
import hashlib, json, sys
from pathlib import Path
REPO = Path(__file__).resolve().parents[2]
G = REPO / "tests" / "heldout_g"
CODE = ["extract.py", "identity.py", "evidence.py", "countries.py", "audit.py", "verify.py", "discovery.py"]
sha = lambda b: hashlib.sha256(b).hexdigest()  # noqa: E731


def current() -> dict:
    pages = []
    for p in json.loads((G / "urls.json").read_text())["pages"]:
        f = next((G / "pages").glob(p["id"] + ".*"))
        pages.append({"id": p["id"], "url": p["url"], "file": f.name, "sha256": sha(f.read_bytes())})
    return {"set": "G", "fetched": "2026-10-18", "labels_sha256": sha((G / "labels.json").read_bytes()),
            "code_sha256": {c: sha((REPO / "scholarship_agent" / c).read_bytes()) for c in CODE}, "pages": pages}


if __name__ == "__main__":
    (G / "manifest.json").write_text(json.dumps(current(), indent=1) + "\n")
    print("frozen", len(current()["pages"]), "pages")
