---
name: midterms-refresh
description: "Refresh the 2026 midterms Polymarket dashboard with live prices and polling, then report what moved. Use when asked to 'update the midterms dashboard', 'refresh midterms', 'rerun midterms numbers', or 'what moved in the midterms markets'."
---

# Midterms Dashboard Refresh

Regenerate the 2026 U.S. midterms dashboard from live Polymarket markets and Wikipedia polling, then summarize the changes for the user.

## Files (relative to the repo root)

```
scripts/refresh_midterms.py                      # the refresh wrapper
scripts/generate_poly_midterms.py                # generator + candidate roster
examples/midterms/midterms_dashboard.html        # output page
examples/midterms/midterms_dashboard_data.json   # output data
examples/midterms/history/<date>.json            # one archive per refresh
```

## Steps

1. Run the refresh. It snapshots the previous data, regenerates the dashboard, prints a movers diff, and archives `history/<date>.json`:
   ```bash
   python3 scripts/refresh_midterms.py
   ```
   Add `--commit` only if the user asked to commit. The script fails loudly if any race market cannot be fetched; do not hand-edit the output files to work around that.

2. Verify the page renders: open the dashboard in the browser, confirm `Object.keys(Chart.instances).length` is 6, the race table has 21 rows, and the console has no errors.

3. Report to the user from the diff output, in this order:
   - Senate control and House control (Dem %), before and after.
   - Top scenario (Balance of Power) change.
   - Race movers of 2+ points, and whether polling moved with the market or the shift is money-only.
   - Anything the run flagged: races missing polling, candidate-name check date.

4. If the user asks what a Senate result means, the rule is: Democrats need 51 seats (the Republican VP breaks a 50-50 tie). Baseline is 53 R / 47 D. The main Dem path is hold everything + North Carolina + Maine + Alaska (= 50), then one of Texas / Ohio / Iowa.

## Candidate roster changes

Nominee names live in `CANDIDATES` in `scripts/generate_poly_midterms.py` with `CANDIDATES_AS_OF` and `CANDIDATE_SOURCES`. When a nominee changes (withdrawal, runoff), update those three together and cite the source URL, then rerun.

## Known quirks

- The derived "Republican Senate Seats" chart assumes independent races and hides buckets under 5%; it understates wave tails versus Polymarket's own seat-count market (`republican-senate-seats-after-the-2026-midterm-elections-927`).
- Polling date strings come from Wikipedia verbatim, typos included.
