"""robots.txt reading for the fetcher (RFC 9309), on the cautious side.

The fetcher asks two questions before it reads a page: does the body the server sent actually look like a robots.txt
(`is_robots_body`), and can every rule in it be trusted (`has_undecodable_rule`)? Only then does `allowed` decide
the path. Anything that cannot be read with confidence is treated as "permission unconfirmed", never as permission.

Decisions:
  * the most specific (longest) matching rule wins; when an Allow and a Disallow match equally, Disallow wins
  * a group is the User-agent lines followed by their rules; blank lines inside a group do not end it
  * one leading byte-order mark is ignored, so a file saved with a BOM does not hide its first group
  * "$" at the end of a pattern anchors the end of the path; anywhere else it is a literal character
  * patterns are percent-decoded before matching, so "Disallow: /a%20b" applies to "/a b"
  * an empty body allows everything; a non-empty body with no robots directive is not a robots.txt
  * a User-agent, Allow or Disallow line containing U+FFFD (a byte that was not UTF-8) makes the file unreadable
"""
from __future__ import annotations

import re
from urllib.parse import unquote

_DIRECTIVES = ("user-agent", "allow", "disallow", "sitemap", "crawl-delay", "host")
_RULE_FIELDS = ("user-agent", "allow", "disallow")


def _lines(text: str):
    """(field, value) for every directive line, comments and the leading BOM removed."""
    for raw in (text or "").removeprefix("﻿").splitlines():
        line = raw.split("#", 1)[0]
        if ":" not in line:
            continue
        field, _, value = line.partition(":")
        yield field.strip().lower(), value.strip()


def is_robots_body(text: str) -> bool:
    """True for an empty body (allow-all) or one holding at least one robots directive; False for an HTML or JSON
    page served with status 200 in place of robots.txt."""
    if not (text or "").removeprefix("﻿").strip():
        return True
    return any(field in _DIRECTIVES for field, _ in _lines(text))


def has_undecodable_rule(text: str) -> bool:
    """True when a rule line holds U+FFFD: the pattern can never match, so the rule would be silently lost."""
    for raw in (text or "").removeprefix("﻿").splitlines():
        line = raw.split("#", 1)[0]
        if "�" in line and ":" in line:
            field = line.partition(":")[0].replace("�", "").strip().lower()
            if field in _RULE_FIELDS:
                return True
    return False


def _rules_by_agent(text: str) -> dict[str, list[tuple[bool, str]]]:
    groups: dict[str, list[tuple[bool, str]]] = {}
    current: list[str] = []
    in_rules = False
    for field, value in _lines(text):
        if field == "user-agent":
            if in_rules:          # a User-agent after rules starts a new group
                current, in_rules = [], False
            agent = value.lower()
            current.append(agent)
            groups.setdefault(agent, [])
        elif field in ("allow", "disallow") and current:
            in_rules = True
            for agent in current:
                groups[agent].append((field == "allow", value))
    return groups


def _match_length(pattern: str, path: str) -> int:
    """Length of the pattern when it matches the path, else -1."""
    if not pattern:
        return -1
    pattern = unquote(pattern)
    anchored = pattern.endswith("$")
    body = pattern[:-1] if anchored else pattern
    regex = "".join(".*" if ch == "*" else re.escape(ch) for ch in body)
    if re.match(regex + ("$" if anchored else ""), path):
        return len(pattern)
    return -1


def allowed(text: str, agent: str, path: str) -> bool:
    """May `agent` fetch `path` under this robots.txt? The agent's own group applies, else the "*" group."""
    groups = _rules_by_agent(text)
    rules = groups.get(agent.lower()) or groups.get("*") or []
    best = (-1, True)   # (match length, is_allow)
    for is_allow, pattern in rules:
        n = _match_length(pattern, path)
        if n < 0:
            continue
        if n > best[0] or (n == best[0] and not is_allow):
            best = (n, is_allow)
    return best[1]
