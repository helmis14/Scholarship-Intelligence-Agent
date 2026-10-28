"""Round 51: backups of the catalogue and the private data, and their restore.

A backup is one compressed archive: consistent copies of `catalog.db` and `private/private.db` taken with SQLite's
backup interface (safe while the site or a crawl is running), the encryption keys (`private/keys.json`, without which
the private data cannot be read), and a manifest with checksums and record counts. Archives are written 0600 to
SCHOLAR_BACKUP_DIR (default ~/ScholarshipBackups, outside the repository and the data folder) and only the newest
`keep` are kept.

A restore checks every checksum first, saves the current data as a "pre-restore" archive, then copies the databases
back through the same SQLite interface (connections that are open see the restored data) and the keys file after them,
and finally counts the records again.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sqlite3
import tarfile
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Optional

FILES = ("catalog.db", "private/private.db", "private/keys.json")
NAME_RX = re.compile(r"^scholarship-backup-(\d{8}-\d{6})(?:-(?P<label>[a-z-]+))?\.tar\.gz$")


def backup_dir() -> Path:
    return Path(os.environ.get("SCHOLAR_BACKUP_DIR") or Path.home() / "ScholarshipBackups")


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def _count(db: Path, table: str) -> Optional[int]:
    if not Path(db).exists():   # connecting would create an empty file
        return None
    try:
        con = sqlite3.connect(str(db), timeout=60)   # not read-only: a WAL database copy has no -shm file to read with
        try:
            return con.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
        finally:
            con.close()
    except sqlite3.Error:
        return None


def _copy_db(src: Path, dst: Path) -> None:
    """A consistent copy of a live database (its WAL included)."""
    a, b = sqlite3.connect(str(src), timeout=60), sqlite3.connect(str(dst))
    try:
        a.backup(b)
    finally:
        b.close()
        a.close()


def create(data_dir: Path, out_dir: Optional[Path] = None, keep: int = 7, label: str = "") -> dict:
    data_dir, out_dir = Path(data_dir), Path(out_dir or backup_dir())
    out_dir.mkdir(parents=True, exist_ok=True)
    os.chmod(out_dir, 0o700)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    name = f"scholarship-backup-{stamp}{'-' + label if label else ''}.tar.gz"
    with tempfile.TemporaryDirectory(dir=out_dir) as tmp:
        tmp = Path(tmp)
        (tmp / "private").mkdir()
        files = {}
        for rel in FILES:
            src = data_dir / rel
            if not src.exists():
                continue
            dst = tmp / rel
            if rel.endswith(".db"):
                _copy_db(src, dst)
            else:
                shutil.copy2(src, dst)
            files[rel] = {"sha256": _sha256(dst), "bytes": dst.stat().st_size}
        if not files:
            raise FileNotFoundError(f"nothing to back up in {data_dir}")
        manifest = {"created": datetime.now().isoformat(timespec="seconds"), "data_dir": str(data_dir), "files": files,
                    "records": {"opportunities": _count(tmp / "catalog.db", "opportunities"),
                                "profiles": _count(tmp / "private/private.db", "profiles"),
                                "applications": _count(tmp / "private/private.db", "applications"),
                                "users": _count(tmp / "private/private.db", "users")}}
        (tmp / "manifest.json").write_text(json.dumps(manifest, indent=1))
        target, partial = out_dir / name, out_dir / (name + ".part")
        with tarfile.open(partial, "w:gz", compresslevel=6) as tar:
            for rel in ["manifest.json", *files]:
                tar.add(tmp / rel, arcname=rel)
        os.chmod(partial, 0o600)
        os.replace(partial, target)   # an archive is either complete or absent
    removed = prune(out_dir, keep) if keep else []
    return {"backup": str(target), "bytes": target.stat().st_size, "records": manifest["records"], "removed": removed}


def listing(out_dir: Optional[Path] = None) -> list[dict]:
    out_dir = Path(out_dir or backup_dir())
    rows = []
    for p in sorted(out_dir.glob("scholarship-backup-*.tar.gz"), reverse=True):
        if not NAME_RX.match(p.name):
            continue
        try:
            with tarfile.open(p, "r:gz") as tar:
                m = json.load(tar.extractfile("manifest.json"))
            rows.append({"backup": str(p), "created": m["created"], "bytes": p.stat().st_size, "records": m["records"]})
        except (tarfile.TarError, KeyError, OSError, ValueError):
            rows.append({"backup": str(p), "error": "unreadable archive"})
    return rows


def prune(out_dir: Path, keep: int) -> list[str]:
    """Keep the newest `keep` regular backups; pre-restore archives are never removed here."""
    regular = [p for p in sorted(Path(out_dir).glob("scholarship-backup-*.tar.gz"), reverse=True)
               if (m := NAME_RX.match(p.name)) and not m.group("label")]
    gone = []
    for p in regular[keep:]:
        p.unlink()
        gone.append(p.name)
    return gone


def restore(archive: Path, data_dir: Path, yes: bool = False, out_dir: Optional[Path] = None) -> dict:
    archive, data_dir = Path(archive), Path(data_dir)
    if not yes:
        raise ValueError("restore replaces the current catalogue and private data: run again with --yes")
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        with tarfile.open(archive, "r:gz") as tar:
            for member in tar.getmembers():   # only the files a backup writes: no links, no paths outside the folder
                if member.name not in ("manifest.json", "private", *FILES) or not (member.isfile() or member.isdir()):
                    raise ValueError(f"unexpected entry in archive: {member.name}")
            try:
                tar.extractall(tmp, filter="data")
            except TypeError:   # Python before 3.10.12 / 3.11.4: the entries were checked above
                tar.extractall(tmp)
        manifest = json.loads((tmp / "manifest.json").read_text())
        for rel, meta in manifest["files"].items():
            if _sha256(tmp / rel) != meta["sha256"]:
                raise ValueError(f"checksum mismatch for {rel}: the archive is damaged")
        safety = None   # the data being replaced, next to the archive (an empty, just-created folder is not kept)
        if any(_count(data_dir / db, table) for db, table in (("catalog.db", "opportunities"), ("private/private.db", "users"),
                                                               ("private/private.db", "profiles"))):
            safety = create(data_dir, out_dir or archive.parent, keep=0, label="pre-restore")["backup"]
        (data_dir / "private").mkdir(parents=True, exist_ok=True)
        os.chmod(data_dir / "private", 0o700)
        for rel in manifest["files"]:
            src, dst = tmp / rel, data_dir / rel
            if rel.endswith(".db"):
                _copy_db(src, dst)   # open connections of the site see the restored data
                if rel.startswith("private/"):
                    os.chmod(dst, 0o600)
            else:
                part = dst.with_suffix(dst.suffix + ".part")
                shutil.copy2(src, part)
                os.chmod(part, 0o600)
                os.replace(part, dst)
    now = {"opportunities": _count(data_dir / "catalog.db", "opportunities"),
           "profiles": _count(data_dir / "private/private.db", "profiles"),
           "applications": _count(data_dir / "private/private.db", "applications"),
           "users": _count(data_dir / "private/private.db", "users")}
    return {"restored_from": str(archive), "created": manifest["created"], "records": now,
            "matches_backup": now == manifest["records"], "previous_data_saved_as": safety}
