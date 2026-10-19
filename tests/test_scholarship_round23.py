"""Round 23: catalogue pages (many different programmes named, none dominant) are scholarship_catalog, not
programmes and not irrelevant; a programme title on such a page makes the call uncertain (review). Offline."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scholarship_agent.extract import Page, classify_page  # noqa: E402
from scholarship_agent.identity import catalogue_evidence, named_programmes  # noqa: E402

NAMES = ["Beasiswa KIP Kuliah", "Beasiswa Bank Indonesia", "Beasiswa Djarum Plus", "Beasiswa Tanoto Foundation",
         "Beasiswa BAZNAS Cendekia", "Beasiswa Pemprov Kaltim", "Beasiswa Pertamina Sobat Bumi", "Beasiswa Karya Salemba"]
BODY = "".join(f"<p>{n}</p><p>Persyaratan: IPK minimal 3,0. Pendaftaran ditutup 30 November 2026.</p>" for n in NAMES)


def page(url, title, body):
    return Page(url, f"<html><head><title>{title}</title></head><body><h1>{title}</h1>{body}</body></html>")


class TestCatalogue(unittest.TestCase):
    def test_list_of_named_programmes_is_a_catalogue(self):
        c = classify_page(page("https://kemahasiswaan.example.ac.id/beasiswa", "Daftar Beasiswa", BODY))
        self.assertEqual((c["kind"], c["confidence"]), ("listing", "high"))

    def test_programme_repeating_its_own_name_is_not_a_catalogue(self):
        body = "".join(f"<p>Beasiswa Djarum Plus {x}: persyaratan, manfaat dan pendaftaran.</p>"
                       for x in ("2026", "angkatan 41", "untuk mahasiswa S1", "tahap 1"))
        body += "<p>Beasiswa Bank Indonesia dan Beasiswa KIP Kuliah tidak dapat digabung.</p>"
        self.assertFalse(catalogue_evidence(page("https://x.example.ac.id/djarum", "Beasiswa Djarum Plus", body).text,
                                            "Beasiswa Djarum Plus")[0])

    def test_programme_title_on_a_catalogue_page_is_uncertain(self):
        c = classify_page(page("https://x.example.ac.id/b", "Lovelace Programme", BODY))
        self.assertEqual((c["kind"], c["confidence"]), ("listing", "low"))

    def test_sentence_starts_are_not_programme_names(self):
        self.assertNotIn(("this",), named_programmes("This scholarship is open. This Scholarship covers fees."))


if __name__ == "__main__":
    unittest.main()
