#!/usr/bin/env python3
"""
One-shot refresh of the 2026 midterms dashboard.

Steps:
  1. Snapshot the current data JSON (so the run can be diffed).
  2. Run generate_poly_midterms.py (live Polymarket prices + Wikipedia polling).
  3. Print what moved: control markets, scenarios, and the biggest race movers.
  4. Archive the new data JSON under examples/midterms/history/<date>.json.
  5. Optionally commit the refreshed files with a summary message.

Usage:
    python3 scripts/refresh_midterms.py              # refresh + diff + archive
    python3 scripts/refresh_midterms.py --commit     # ...and git commit
    python3 scripts/refresh_midterms.py --diff-only PREV.json   # diff current output vs a file
"""

import json
import os
import shutil
import subprocess
import sys
from argparse import ArgumentParser
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUT_HTML = os.path.join(ROOT, "examples", "midterms", "midterms_dashboard.html")
OUT_JSON = os.path.join(ROOT, "examples", "midterms", "midterms_dashboard_data.json")
HISTORY = os.path.join(ROOT, "examples", "midterms", "history")
MOVER_THRESHOLD = 2.0  # points of Dem win probability


def load(path):
    with open(path) as f:
        return json.load(f)


def fmt_date(iso):
    return iso.replace("T", " ").replace("+00:00", " UTC") if iso else "unknown"


def diff(old, new):
    """Return a plain-text summary of what moved between two data files."""
    lines = [f"Data: {fmt_date(old.get('fetched_at'))} -> {fmt_date(new.get('fetched_at'))}", ""]
    lines.append(f"{'Market':28} {'Before':>8} {'After':>8} {'Change':>8}")
    for key, label in (("senate", "Senate control, Dem"), ("house", "House control, Dem")):
        a, b = old[key]["d"], new[key]["d"]
        lines.append(f"{label:28} {a:7.1f}% {b:7.1f}% {b - a:+7.1f}")
    old_bop = {x["label"]: x["p"] for x in old["bop"]}
    for x in new["bop"]:
        a = old_bop.get(x["label"])
        if a is None:
            continue
        lines.append(f"{x['label']:28} {a:7.1f}% {x['p']:7.1f}% {x['p'] - a:+7.1f}")

    old_races = {r["slug"]: r for r in old["races"]}
    movers = []
    for r in new["races"]:
        a = old_races.get(r["slug"])
        if a is None:
            movers.append((99, r["state"], None, r["dem"], None, None))
            continue
        delta = r["dem"] - a["dem"]
        pa = (a.get("poll") or {}).get("margin")
        pb = (r.get("poll") or {}).get("margin")
        movers.append((abs(delta), r["state"], a["dem"], r["dem"], pa, pb))
    movers.sort(reverse=True)
    lines += ["", f"Race movers (Dem win %, |change| >= {MOVER_THRESHOLD:.0f} pts):"]
    shown = 0
    for mag, state, a, b, pa, pb in movers:
        if a is not None and mag < MOVER_THRESHOLD:
            continue
        poll = "" if pa is None and pb is None else f"   poll R-margin {pa} -> {pb}"
        before = "new" if a is None else f"{a:5.1f}%"
        lines.append(f"  {state:16} {before:>6} -> {b:5.1f}%{poll}")
        shown += 1
    if not shown:
        lines.append("  (no race moved more than the threshold)")
    n_polled = sum(1 for r in new["races"] if r.get("poll"))
    lines += ["", f"Polling found for {n_polled}/{len(new['races'])} races; "
                  f"candidates checked {new.get('candidates_as_of', '?')}."]
    return "\n".join(lines)


def commit_message(old, new):
    d = new["senate"]["d"] - old["senate"]["d"]
    date = (new.get("fetched_at") or "")[:10]
    return (f"Refresh midterms dashboard: {date} market data\n\n"
            f"Senate control (Dem) {old['senate']['d']:.1f}% -> {new['senate']['d']:.1f}% ({d:+.1f}); "
            f"House control (Dem) {old['house']['d']:.1f}% -> {new['house']['d']:.1f}%.\n\n"
            "Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>\n")


def main():
    p = ArgumentParser(description="Refresh the 2026 midterms dashboard and report what moved")
    p.add_argument("--commit", action="store_true", help="git commit the refreshed dashboard files")
    p.add_argument("--no-archive", action="store_true", help="skip writing history/<date>.json")
    p.add_argument("--diff-only", metavar="PREV_JSON", help="skip fetching; diff current output against PREV_JSON")
    args = p.parse_args()

    if args.diff_only:
        print(diff(load(args.diff_only), load(OUT_JSON)))
        return

    old = load(OUT_JSON) if os.path.exists(OUT_JSON) else None
    subprocess.run([sys.executable, os.path.join(HERE, "generate_poly_midterms.py"), "-o", OUT_HTML],
                   check=True, cwd=HERE)
    new = load(OUT_JSON)

    if not args.no_archive:
        os.makedirs(HISTORY, exist_ok=True)
        stamp = (new.get("fetched_at") or datetime.now(timezone.utc).isoformat())[:10]
        shutil.copy(OUT_JSON, os.path.join(HISTORY, f"{stamp}.json"))

    if old is None:
        print("No previous data to diff against.")
        return
    print()
    print(diff(old, new))

    if args.commit:
        paths = [OUT_HTML, OUT_JSON] + ([] if args.no_archive else [HISTORY])
        subprocess.run(["git", "add", *paths], check=True, cwd=ROOT)
        subprocess.run(["git", "commit", "-q", "-m", commit_message(old, new)], check=True, cwd=ROOT)
        print("\nCommitted.")


if __name__ == "__main__":
    main()
