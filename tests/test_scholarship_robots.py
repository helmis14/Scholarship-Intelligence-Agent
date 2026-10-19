"""scholarship_agent.robots: the robots.txt reading the fetcher relies on. Every case here is a way a careless parser
fails open (reads "allowed" where the site said no or said nothing readable)."""
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from scholarship_agent.robots import allowed, has_undecodable_rule, is_robots_body  # noqa: E402

AGENT = "ScholarshipIntelligenceAgent"


class TestAllowed(unittest.TestCase):
    def test_longest_match_wins_whatever_the_order(self):
        t = "User-agent: *\nDisallow: /\nAllow: /scholarships/"
        self.assertTrue(allowed(t, AGENT, "/scholarships/x"))
        self.assertFalse(allowed(t, AGENT, "/admin"))
        t = "User-agent: *\nAllow: /scholarships/\nDisallow: /scholarships/private/"
        self.assertFalse(allowed(t, AGENT, "/scholarships/private/a"))

    def test_equal_specificity_goes_to_disallow(self):
        for t in ("User-agent: *\nAllow: /a\nDisallow: /a", "User-agent: *\nDisallow: /a\nAllow: /a"):
            self.assertFalse(allowed(t, AGENT, "/a/b"), t)

    def test_blank_lines_inside_a_group_do_not_end_it(self):
        t = "User-agent: *\n\nDisallow: /secret/\n\nAllow: /"
        self.assertFalse(allowed(t, AGENT, "/secret/x"))
        self.assertTrue(allowed(t, AGENT, "/open"))

    def test_own_agent_group_beats_star(self):
        t = f"User-agent: *\nDisallow: /\n\nUser-agent: {AGENT}\nAllow: /"
        self.assertTrue(allowed(t, AGENT, "/anything"))
        t = f"User-agent: *\nAllow: /\n\nUser-agent: {AGENT.lower()}\nDisallow: /"
        self.assertFalse(allowed(t, AGENT, "/anything"))

    def test_several_agents_share_one_group(self):
        t = "User-agent: a\nUser-agent: b\nDisallow: /x"
        self.assertFalse(allowed(t, "B", "/x/1"))
        self.assertTrue(allowed(t, "c", "/x/1"))

    def test_wildcards_and_end_anchor(self):
        t = "User-agent: *\nDisallow: /*.pdf$\nDisallow: /tmp*"
        self.assertFalse(allowed(t, AGENT, "/files/a.pdf"))
        self.assertTrue(allowed(t, AGENT, "/files/a.pdf?download=1"))
        self.assertFalse(allowed(t, AGENT, "/tmp-old/x"))

    def test_dollar_in_the_middle_is_literal(self):
        t = "User-agent: *\nDisallow: /a$b"
        self.assertFalse(allowed(t, AGENT, "/a$b/c"))
        self.assertTrue(allowed(t, AGENT, "/a"))

    def test_percent_encoded_rule_matches_the_decoded_path(self):
        t = "User-agent: *\nDisallow: /foo%20bar"
        self.assertFalse(allowed(t, AGENT, "/foo bar/x"))
        self.assertTrue(allowed(t, AGENT, "/foobar"))

    def test_empty_disallow_and_comments(self):
        self.assertTrue(allowed("User-agent: *\nDisallow:", AGENT, "/x"))
        self.assertTrue(allowed("# nothing here\nUser-agent: *\nDisallow: /x # not this\n", AGENT, "/y"))
        self.assertFalse(allowed("User-agent: *\nDisallow: /x # comment", AGENT, "/x"))

    def test_bom_does_not_hide_the_first_group(self):
        self.assertFalse(allowed("﻿User-agent: *\nDisallow: /", AGENT, "/"))

    def test_no_rules_means_allowed(self):
        self.assertTrue(allowed("", AGENT, "/"))
        self.assertTrue(allowed("Sitemap: https://x.org/sitemap.xml", AGENT, "/"))


class TestBodyChecks(unittest.TestCase):
    def test_html_or_json_error_page_is_not_a_robots_file(self):
        self.assertFalse(is_robots_body("<html><body>Not found</body></html>"))
        self.assertFalse(is_robots_body('{"error": "not found"}'))

    def test_empty_body_is_an_allow_all_robots_file(self):
        self.assertTrue(is_robots_body(""))
        self.assertTrue(is_robots_body("﻿  \n"))

    def test_any_directive_counts(self):
        self.assertTrue(is_robots_body("Sitemap: https://x.org/s.xml"))
        self.assertTrue(is_robots_body("﻿User-agent: *\nDisallow: /"))

    def test_undecodable_rule_lines_make_the_file_unreadable(self):
        self.assertTrue(has_undecodable_rule("User-agent: *\nDisallow: /caf�/"))
        self.assertTrue(has_undecodable_rule("�Disallow: /x"))
        self.assertTrue(has_undecodable_rule("User-agent: �\nDisallow: /"))

    def test_undecodable_bytes_elsewhere_are_harmless(self):
        self.assertFalse(has_undecodable_rule("# caf�\nUser-agent: *\nDisallow: /x"))
        self.assertFalse(has_undecodable_rule("Sitemap: https://x.org/�\nUser-agent: *\nAllow: /"))
        self.assertFalse(has_undecodable_rule("User-agent: *\nDisallow: /café/"))


if __name__ == "__main__":
    unittest.main()
