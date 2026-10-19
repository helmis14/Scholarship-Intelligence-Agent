"""Round 24: an official catalogue met in search is a lead whose programme links are read, so the catalogue rule
does not drop the programmes it lists. Offline."""

import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tests"))

from scholarship_agent.discovery import Discovery, DiscoveryResult  # noqa: E402
from scholarship_agent.models import SourceType  # noqa: E402
from scholarship_agent.net import Fetcher  # noqa: E402
from scholarship_agent.store import Store  # noqa: E402
from test_scholarship_agent import FakeTransport  # noqa: E402

BASE = "https://www.example.ac.id"
NAMES = ["KIP Kuliah", "Bank Indonesia", "Djarum Plus", "Tanoto Foundation", "BAZNAS Cendekia", "Pemprov Kaltim",
         "Pertamina Sobat Bumi", "Karya Salemba"]
CATALOGUE = ("<html><head><title>Daftar Beasiswa</title></head><body><h1>Daftar Beasiswa</h1>" +
             "".join(f"<p><a href='{BASE}/beasiswa/{i}'>Beasiswa {n}</a></p><p>Persyaratan: IPK minimal 3,0.</p>"
                     for i, n in enumerate(NAMES)) + "</body></html>")


def programme(n):
    return (f"<html><head><title>Beasiswa {n}</title></head><body><h1>Beasiswa {n}</h1><p>Beasiswa {n} diberikan "
            f"kepada mahasiswa S1. Persyaratan: IPK minimal 3,0. Manfaat: biaya kuliah dan uang saku bulanan.</p>"
            f"<p>Pendaftaran ditutup 30 November 2026. Cara mendaftar: isi formulir pendaftaran beasiswa {n}.</p>"
            "</body></html>")


class TestCatalogueLeads(unittest.TestCase):
    def test_programmes_linked_from_a_search_catalogue_are_read(self):
        pages = {f"{BASE}/beasiswa": CATALOGUE} | {f"{BASE}/beasiswa/{i}": programme(n) for i, n in enumerate(NAMES)}
        with tempfile.TemporaryDirectory() as d:
            st = Store(Path(d))
            disc = Discovery(st, Fetcher(FakeTransport(pages), min_interval=0, sleep=lambda s: None), None,
                             date(2026, 10, 18), [])
            res = DiscoveryResult(job_id=1)
            out = disc.ingest_url(st.start_job("t", {}), f"{BASE}/beasiswa", provider="example.ac.id",
                                  provider_type="other", source_type=SourceType.SEARCH_RESULT, countries_hint=["ID"],
                                  result=res, discovered_via="search:test")
            self.assertIsNone(out)                      # the catalogue itself is not a record
            self.assertEqual(res.catalogue_links_followed, disc.links_per_catalogue)
            titles = sorted(o.title for o in st.list_opportunities())
            self.assertEqual(len(titles), disc.links_per_catalogue)
            self.assertTrue(all(t.startswith("Beasiswa ") for t in titles))
            self.assertTrue(all(o.discovered_via.endswith(":via-catalogue") for o in st.list_opportunities()))
            st.close()


if __name__ == "__main__":
    unittest.main()
