#!/usr/bin/env python3
"""
Scrape general-election polling from Wikipedia's per-race Senate pages.

For a "2026 United States Senate election in <State>" page this pulls polling
for the actual general-election matchup:
  1. the poll-aggregation table (RCP / Race to the WH / 270toWin averages)
     when the page has one, averaging the aggregate rows;
  2. otherwise the newest head-to-head polls (up to POLL_LIMIT), averaged.

Tables are matched by the known nominees' surnames in the candidate header,
which skips hypothetical-matchup and primary tables. Returns None when the
page has no polling for the real matchup ("where available").
"""

import re
import sys
import urllib.request

WIKI = "https://en.wikipedia.org/wiki/2026_United_States_Senate_election_in_{}"
POLL_LIMIT = 5  # newest head-to-head polls averaged when no aggregate exists


def _fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "manifold-analysis/1.0 (midterms dashboard)"})
    return urllib.request.urlopen(req, timeout=30).read().decode("utf-8", "replace")


def _text(html):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html)).strip()


def _cells(row_html):
    return [_text(c) for c in re.findall(r"<t[dh][^>]*>(.*?)(?=<t[dh][^>]*>|$)", row_html, re.S)]


def _pct(cell):
    m = re.search(r"(\d+(?:\.\d+)?)\s*%", cell or "")
    return float(m.group(1)) if m else None


def _party_cols(head, surnames):
    """Column index per party; a column only counts if the known nominee's
    surname appears in its header cell (rejects hypothetical matchups)."""
    cols = {}
    for i, c in enumerate(head):
        cl = c.lower()
        for p in ("R", "D", "I"):
            sn = surnames.get(p)
            if f"({p.lower()})" in cl and sn and sn.lower() in cl and p not in cols:
                cols[p] = i
    return cols


def race_polls(state_title, surnames):
    """Average polling for the real matchup, or None if unavailable.

    state_title: e.g. "North_Carolina"; surnames: {"R": "Husted", "D": "Brown"}.
    Returns {"kind": "agg"|"raw", "n", "rep", "opp", "opp_party", "margin",
    "latest"} where margin = R minus the strongest-polling opponent.
    """
    try:
        html = _fetch(WIKI.format(state_title))
    except Exception as e:
        sys.stderr.write(f"  polls fetch failed ({state_title}): {e}\n")
        return None

    agg = raw = None
    for t in re.findall(r'<table class="wikitable.*?</table>', html, re.S):
        rows = [r for r in (_cells(x) for x in re.split(r"<tr[^>]*>", t)[1:]) if r]
        if len(rows) < 2:
            continue
        first = rows[0][0].lower()
        kind = "agg" if "aggregation" in first else "raw" if "poll source" in first else None
        if kind is None:
            continue
        cols = _party_cols(rows[0], surnames)
        if "R" not in cols or len(cols) < 2:
            continue
        if kind == "agg" and agg is None:
            agg = (rows[1:], cols)
        elif kind == "raw" and raw is None:
            raw = (rows[1:], cols)

    for kind, table in (("agg", agg), ("raw", raw)):
        if not table:
            continue
        rows, cols = table
        sums = {p: 0.0 for p in cols}
        counts = {p: 0 for p in cols}
        n, latest = 0, ""
        for row in rows:
            vals = {p: _pct(row[i]) if i < len(row) else None for p, i in cols.items()}
            if vals.get("R") is None or all(vals[p] is None for p in cols if p != "R"):
                continue
            n += 1
            latest = latest or (row[1] if len(row) > 1 else "")
            for p, v in vals.items():
                if v is not None:
                    sums[p] += v
                    counts[p] += 1
            if kind == "raw" and n >= POLL_LIMIT:
                break
        if n == 0:
            continue
        avg = {p: sums[p] / counts[p] for p in cols if counts[p]}
        opp = max((p for p in avg if p != "R"), key=lambda p: avg[p], default=None)
        if opp is None:
            continue
        return {
            "kind": kind,
            "n": n,
            "rep": round(avg["R"], 1),
            "opp": round(avg[opp], 1),
            "opp_party": opp,
            "margin": round(avg["R"] - avg[opp], 1),
            "latest": latest[:40],
        }
    return None
