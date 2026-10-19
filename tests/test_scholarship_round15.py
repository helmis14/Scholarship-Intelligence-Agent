"""Round 15: SearXNG engine health (choice, cooldowns, pacing, pause), durable official sources (URL patterns,
explicit sitemaps, feeds, newest calls first) and the browser-need check on visible text. Offline."""

import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from scholarship_agent.discovery import Discovery, feed_links, newest_first  # noqa: E402
from scholarship_agent.extract import Page  # noqa: E402
from scholarship_agent.net import Fetcher, Response  # noqa: E402
from scholarship_agent.registry import Source  # noqa: E402
from scholarship_agent.retrieval import needs_browser  # noqa: E402
from scholarship_agent.search import SearxngSearch  # noqa: E402
from scholarship_agent.search_health import EnginePool, EnginesUnavailable, classify  # noqa: E402
from scholarship_agent.store import Store  # noqa: E402
from scholarship_agent.strategy import StrategyConfig, StrategyRunner  # noqa: E402


class Clock:
    def __init__(self):
        self.t = 1_000_000.0

    def __call__(self):
        return self.t


class TestEngineHealth(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name))

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def test_classification_respects_blocks(self):
        self.assertEqual(classify("Suspended: too many requests"), (3600, "rate_limited"))
        self.assertEqual(classify("access denied")[1], "access_denied")
        self.assertEqual(classify("SSL error: certificate validation has failed")[1], "network_blocked")
        self.assertEqual(classify("HTTP connection error")[1], "unreachable")

    def test_rotation_cooldown_pacing_and_persistence(self):
        clock = Clock()
        pool = EnginePool(["google cse", "bing", "yahoo", "naver"], per_query=2, store=self.store, clock=clock)
        first, second = pool.pick("en"), pool.pick("en")
        self.assertEqual(len(first), 2)
        self.assertNotEqual(first, second)                       # no engine gets every query
        self.assertEqual(pool.pick("ko")[0], "naver")            # a language's own index first
        pool.record(["google cse", "bing"], {"bing"}, [["google cse", "Suspended: too many requests"]])
        self.assertNotIn("google cse", pool.healthy())
        self.assertEqual(pool.interval, 6.0)                     # throttled: slow down
        pool.record(["bing", "yahoo"], {"bing", "yahoo"}, [])
        self.assertLess(pool.interval, 6.0)                      # clean answer: recover slowly
        again = EnginePool(["google cse", "bing", "yahoo", "naver"], store=self.store, clock=clock)
        self.assertNotIn("google cse", again.healthy())          # cooldown survives a restart
        clock.t += 3601
        self.assertIn("google cse", again.healthy())

    def test_all_engines_cooling_pauses_the_run_for_resume(self):
        clock = Clock()
        pool = EnginePool(["bing"], clock=clock)
        pool.record(["bing"], set(), [["bing", "access denied"]])
        with self.assertRaises(EnginesUnavailable) as e:
            pool.pick("en")
        self.assertAlmostEqual(e.exception.ready_at, clock.t + 86400)
        s = SearxngSearch(base="http://localhost:8080", get=lambda u, h: {"results": []}, pool=pool)
        d = Discovery(self.store, Fetcher(lambda u, h: Response(u, 404, "text/plain", ""), min_interval=0,
                                          sleep=lambda x: None), None, date(2026, 10, 18), [])
        rep = StrategyRunner(self.store, d, s, StrategyConfig(countries=["NO"], queries_per_country=2),
                             sleep=lambda x: None, today=date(2026, 10, 18)).run()
        self.assertTrue(rep["paused"])
        self.assertEqual(rep["queries_executed"], 0)
        self.assertIsNone(self.store.get_checkpoint(rep["job_id"]))   # the first query is still to do on resume
        self.assertEqual(self.store.job(rep["job_id"])["status"], "paused")

    def test_engines_parameter_is_sent(self):
        seen = []
        pool = EnginePool(["bing", "yahoo"], clock=Clock())
        s = SearxngSearch(base="http://localhost:8080", pool=pool,
                          get=lambda u, h: seen.append(u) or {"results": [{"url": "https://a.example", "engines": ["bing"]}]})
        s.search("stipend Norge", 10, "no", 0)
        self.assertIn("engines=", seen[0])
        self.assertEqual(pool.state["bing"]["ok"], 1)


class TestDurableSources(unittest.TestCase):
    def test_newest_calls_first_and_feeds(self):
        urls = ["https://f.example/utlysninger/2024/a/", "https://f.example/utlysninger/2027/b/",
                "https://f.example/utlysninger/2026/c/", "https://f.example/om-oss/"]
        self.assertEqual(newest_first(urls, date(2026, 10, 18)),
                         ["https://f.example/utlysninger/2027/b/", "https://f.example/utlysninger/2026/c/",
                          "https://f.example/om-oss/"])
        rss = "<rss><channel><item><title>x</title><link>https://f.example/a</link></item></channel></rss>"
        atom = "<feed><entry><link href='https://f.example/b'/></entry></feed>"
        self.assertEqual(feed_links(rss + atom), ["https://f.example/a", "https://f.example/b"])

    def test_pattern_source_reads_its_sitemap_and_keeps_programmes_apart(self):
        listing = "<a href='/utlysninger/2026/a/'>A</a><a href='/om-oss/'>About</a>"
        sitemap = ("<urlset><url><loc>https://www.f.example/utlysninger/2027/b/</loc></url>"
                   "<url><loc>https://www.f.example/utlysninger/2023/old/</loc></url></urlset>")
        call = ("<html><head><title>{t}</title></head><body><h1>{t}</h1><p>Utlysning: stipendiat for ph.d. "
                "Søknadsfrist: 1. mars 2027. Stipendet dekker lønn.</p><p>Hvem kan søke? Søknad sendes elektronisk.</p>"
                "</body></html>")
        pages = {"https://www.f.example/utlysninger/": listing, "https://www.f.example/map.xml": sitemap,
                 "https://www.f.example/utlysninger/2026/a/": call.format(t="Ensomhet og sosial ulikhet i helse"),
                 "https://www.f.example/utlysninger/2027/b/": call.format(t="Grønn plattform hovedutlysning")}
        fetched = []

        def transport(url, headers):
            fetched.append(url)
            if url.endswith("/robots.txt"):
                return Response(url, 404, "text/plain", "")
            body = pages.get(url)
            return Response(url, 200, "text/xml" if url.endswith(".xml") else "text/html", body) if body \
                else Response(url, 404, "text/html", "")
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp))
            src = Source(id="f", name="F calls", url="https://www.f.example/utlysninger/", provider="F",
                         official_domains=["f.example"], countries=["NO"], url_pattern=r"/utlysninger/20\d\d/",
                         sitemap="https://www.f.example/map.xml")
            d = Discovery(store, Fetcher(transport, min_interval=0, sleep=lambda x: None), None, date(2026, 10, 18), [src])
            res = d.run(use_search=False)
            titles = sorted(o.title for o in store.list_opportunities())
            store.close()
        self.assertEqual(titles, ["Ensomhet og sosial ulikhet i helse", "Grønn plattform hovedutlysning"])   # not merged under the source name
        self.assertNotIn("https://www.f.example/utlysninger/2023/old/", fetched)  # past calls are not fetched
        self.assertNotIn("https://www.f.example/om-oss/", fetched)
        self.assertEqual(res.sitemap_urls, 2)   # both listed in the sitemap; only the current one fetched


class TestBrowserNeedOnVisibleText(unittest.TestCase):
    def test_captcha_library_in_scripts_is_not_an_access_block(self):
        html = ("<html><head><script src='https://www.google.com/recaptcha/api.js'></script></head><body>"
                + "<p>Scholarship for master's students. Application deadline 1 March 2027.</p>" * 40 + "</body></html>")
        need, why = needs_browser(Response("https://x.example", 200, "text/html", html), Page("https://x.example", html))
        self.assertFalse(need)
        self.assertEqual(why, "HTTP text is sufficient")


if __name__ == "__main__":
    unittest.main()
