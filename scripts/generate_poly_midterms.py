#!/usr/bin/env python3
"""
Generate a 2026 U.S. midterms dashboard from Polymarket multi-outcome markets.

Unlike the binary topic report, the midterms are priced as mutually-exclusive
multi-outcome markets (party-vs-party races, scenario splits, seat-count
distributions). This dashboard folds them into:
  - Control gauges (House / Senate, Dem vs Rep)
  - Balance-of-Power scenario breakdown
  - Republican House-seat distribution (with the 218 majority line)
  - Republican Senate-seat distribution derived from race markets
  - Competitive Senate races: Dem win% sorted, plus a Dem%-vs-volume bubble view

Usage:
    python3 generate_poly_midterms.py -o examples/midterms/midterms_dashboard.html
"""

import json
import re
import sys
from argparse import ArgumentParser
from datetime import datetime, timezone
from html import escape

from fetch_polymarket import fetch_event
from fetch_wiki_polls import race_polls

CONTROL = {
    "house": "which-party-will-win-the-house-in-2026",
    "senate": "which-party-will-win-the-senate-in-2026",
}
BALANCE = "balance-of-power-2026-midterms"
HOUSE_SEATS = "republican-house-seats-after-the-2026-midterm-elections"
# 31 Republican seats are not up in 2026. Seven Republican-held 2026 seats have
# no race market in RACE_SLUGS below, so this distribution holds them as R.
FIXED_REPUBLICAN_SENATE_SEATS = 38

RACE_SLUGS = [
    "maine", "texas", "alaska", "nebraska", "iowa", "michigan", "ohio",
    "montana", "north-carolina", "florida", "south-carolina", "colorado",
    "georgia", "kansas", "new-hampshire", "mississippi", "minnesota",
    "oklahoma", "wyoming", "virginia", "kentucky",
]
BATTLEGROUND_SLUGS = [
    "ohio", "texas", "iowa", "nebraska", "michigan", "alaska", "maine",
    "kansas", "new-hampshire",
]
# party for candidate markets that carry no (D)/(R) tag
NAME_PARTY = {"peltola": "D", "sullivan": "R"}

# Known 2026 general-election nominees / leading candidates per race (many race
# markets resolve by party only, so candidate names come from here). Source:
# Wikipedia "2026 United States Senate elections", checked September 13, 2026.
# NH nominees were confirmed September 8. South Carolina nominated Darline
# Graham in its August 25 special runoff; Nebraska's Burbank withdrew.
CANDIDATES_AS_OF = "2026-09-13"
CANDIDATE_SOURCES = {
    "overview": "https://en.wikipedia.org/wiki/2026_United_States_Senate_elections",
    "new-hampshire": "https://www.nhpr.org/politics/2026-09-08/pappas-sununu-win-senate-primaries-nh-newhampshire-elections-2026",
    "south-carolina": "https://www.washingtonpost.com/politics/2026/08/25/south-carolina-election-lindsey-graham/7cc61e26-a03a-11f1-8606-1d40ad00172e_story.html",
    "nebraska": "https://sos.nebraska.gov/secretary-evnen-issues-statement-cindy-burbank-declination-candidate-nomination",
}
CANDIDATES = {
    "maine": {"D": "Troy Jackson", "R": "Susan Collins"},
    "texas": {"D": "James Talarico", "R": "Ken Paxton"},
    "alaska": {"D": "Mary Peltola", "R": "Dan Sullivan"},
    "nebraska": {"I": "Dan Osborn", "R": "Pete Ricketts"},
    "iowa": {"D": "Josh Turek", "R": "Ashley Hinson"},
    "michigan": {"D": "Abdul El-Sayed", "R": "Mike Rogers"},
    "ohio": {"D": "Sherrod Brown", "R": "Jon Husted"},
    "montana": {"D": "Alani Bankhead", "R": "Kurt Alme", "I": "Seth Bodnar"},
    "north-carolina": {"D": "Roy Cooper", "R": "Michael Whatley"},
    "florida": {"D": "Angie Nixon", "R": "Ashley Moody"},
    "south-carolina": {"D": "Annie Andrews", "R": "Darline Graham"},
    "colorado": {"D": "John Hickenlooper", "R": "Mark Baisley"},
    "georgia": {"D": "Jon Ossoff", "R": "Mike Collins"},
    "kansas": {"D": "Adam Hamilton", "R": "Roger Marshall"},
    "new-hampshire": {"D": "Chris Pappas", "R": "John E. Sununu"},
    "mississippi": {"D": "Scott Colom", "R": "Cindy Hyde-Smith"},
    "minnesota": {"D": "Peggy Flanagan", "R": "Michele Tafoya"},
    "oklahoma": {"D": "N'Kiyla Jasmine Thomas", "R": "Kevin Hern"},
    "wyoming": {"D": "James Byrd", "R": "Harriet Hageman"},
    "virginia": {"D": "Mark Warner", "R": "Bert Mizusawa"},
    "kentucky": {"D": "Charles Booker", "R": "Andy Barr"},
}


def matchup(slug):
    c = CANDIDATES.get(slug, {})
    parts = [f"{c[p]} ({p})" for p in ("D", "I", "R") if c.get(p)]
    return " v ".join(parts) if parts else "—"


def party_of(label):
    l = label.lower()
    if "democrat" in l or "(d)" in l:
        return "D"
    if "republican" in l or "(r)" in l:
        return "R"
    for name, p in NAME_PARTY.items():
        if name in l:
            return p
    return None


def priced_outcomes(event):
    out = []
    for m in event["markets"]:
        op = m.get("outcomePrices")
        if not op:
            continue
        label = m.get("groupItemTitle") or m.get("question", "")
        out.append((label, float(json.loads(op)[0]) * 100))
    return out


def dem_pct(event):
    d = sum(p for label, p in priced_outcomes(event) if party_of(label) == "D")
    r = sum(p for label, p in priced_outcomes(event) if party_of(label) == "R")
    return d, r


def fmt_usd(v):
    v = float(v)
    if abs(v) >= 1_000_000:
        return f"${v/1_000_000:.1f}M"
    if abs(v) >= 1_000:
        return f"${v/1_000:.0f}k"
    return f"${v:.0f}"


def race_label(r):
    """State + matchup surnames. Known candidates whose party prices >= 5% are
    shown (so 3-way races surface the real contest, e.g. Osborn v Ricketts);
    if none clear that bar, fall back to every known candidate."""
    cand = CANDIDATES.get(r["slug"], {})
    share = {"D": r["dem"], "I": r.get("other", 0), "R": r["rep"]}
    names = [cand[p].split()[-1] for p in ("D", "I", "R") if cand.get(p) and share[p] >= 5]
    if not names:
        names = [cand[p].split()[-1] for p in ("D", "I", "R") if cand.get(p)]
    return f"{r['state']} · {' v '.join(names)}" if names else r["state"]


def poll_html(r):
    """Table cell: who leads the polls and by how much, or an em-dash."""
    p = r.get("poll")
    if not p:
        return '<span style="color:#475569">—</span>'
    cand = CANDIDATES.get(r["slug"], {})
    if p["margin"] >= 0:
        name, tag = cand.get("R", "Rep"), 'class="rep"'
    elif p["opp_party"] == "I":
        name, tag = cand.get("I", "Ind"), 'style="color:#a78bfa;font-weight:700"'
    else:
        name, tag = cand.get("D", "Dem"), 'class="dem"'
    src = "poll aggregates" if p["kind"] == "agg" else f'last {p["n"]} polls'
    lead = "Tied" if p["margin"] == 0 else f'{name.split()[-1]} +{abs(p["margin"]):.1f}'
    periods = list(dict.fromkeys(s["period"] for s in p.get("sources", []) if s["period"]))
    dates = "; ".join(periods) or p.get("latest", "Date unavailable")
    url = p.get("url", "https://en.wikipedia.org/wiki/2026_United_States_Senate_election_in_" + r["state"].replace(" ", "_"))
    return (f'<span {tag}>{escape(lead)}</span>'
            f' <span style="color:#64748b;font-size:11px">({src})</span>'
            f'<br><a class="poll-date" href="{escape(url, quote=True)}" title="{escape(dates, quote=True)}">'
            f'{escape(p.get("latest", "Polling source"))}</a>')


def senate_seat_distribution(races, fixed_seats=FIXED_REPUBLICAN_SENATE_SEATS):
    """Exact Republican Senate-seat distribution from independent race prices."""
    dist = {fixed_seats: 1.0}
    for race in races:
        p = max(0.0, min(1.0, race["rep"] / 100.0))
        nxt = {}
        for seats, prob in dist.items():
            nxt[seats] = nxt.get(seats, 0.0) + prob * (1.0 - p)
            nxt[seats + 1] = nxt.get(seats + 1, 0.0) + prob * p
        dist = nxt
    return [{"label": str(seats), "p": round(prob * 100.0, 1)}
            for seats, prob in sorted(dist.items()) if prob >= 0.05]


def battleground_races(races, key_slugs=BATTLEGROUND_SLUGS):
    """Races to show in the Senate battleground zoom."""
    key = set(key_slugs)
    picked = []
    for race in races:
        if race["slug"] in key or 25 <= race["rep"] <= 75:
            picked.append(race)
    return sorted(picked, key=lambda race: (race["rep"], race["state"]))


def collect():
    fetched_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    sys.stderr.write("Fetching control markets...\n")
    house = fetch_event(CONTROL["house"])
    senate = fetch_event(CONTROL["senate"])
    house_d, house_r = dem_pct(house)
    senate_d, senate_r = dem_pct(senate)

    sys.stderr.write("Fetching balance of power...\n")
    bop_ev = fetch_event(BALANCE)
    bop = sorted(priced_outcomes(bop_ev), key=lambda x: -x[1])

    sys.stderr.write("Fetching house-seat distribution...\n")
    seats_ev = fetch_event(HOUSE_SEATS)

    def bucket_low(label):
        nums = re.findall(r"\d+", label)
        return int(nums[0]) if nums else (0 if "below" in label.lower() else 999)
    seats = sorted(priced_outcomes(seats_ev), key=lambda x: bucket_low(x[0]))

    sys.stderr.write("Fetching Senate races...\n")
    races = []
    for st in RACE_SLUGS:
        try:
            ev = fetch_event(f"{st}-senate-election-winner")
        except Exception as exc:
            raise RuntimeError(f"Could not refresh {st}; keeping the previous dashboard") from exc
        d, r = dem_pct(ev)
        outs = priced_outcomes(ev)
        fav = max(outs, key=lambda x: x[1]) if outs else ("?", 0)
        races.append({
            "slug": st,
            "state": st.replace("-", " ").title(),
            "dem": round(d, 1),
            "rep": round(r, 1),
            "other": round(max(0.0, 100 - d - r), 1),
            "fav": f"{fav[0]} {fav[1]:.0f}%",
            "volume": round(float(ev.get("volume", 0))),
        })
    races.sort(key=lambda x: abs(x["rep"] - 50))  # most competitive first

    sys.stderr.write("Fetching Wikipedia polling...\n")
    for r in races:
        surnames = {p: n.split()[-1] for p, n in CANDIDATES.get(r["slug"], {}).items()}
        if r["slug"] == "south-carolina":
            surnames["R"] = "Darline Graham"  # Reject old Lindsey Graham matchups.
        r["poll"] = race_polls(r["state"].replace(" ", "_"), surnames) if surnames else None
        if r["poll"] is None:
            sys.stderr.write(f"  {r['state']}: no usable general-election polling\n")
    sys.stderr.write(f"  polling found for {sum(1 for r in races if r['poll'])}/{len(races)} races\n")

    return {
        "fetched_at": fetched_at,
        "candidates_as_of": CANDIDATES_AS_OF,
        "candidate_sources": CANDIDATE_SOURCES,
        "house": {"d": round(house_d, 1), "r": round(house_r, 1), "vol": float(house.get("volume", 0))},
        "senate": {"d": round(senate_d, 1), "r": round(senate_r, 1), "vol": float(senate.get("volume", 0))},
        "bop": [{"label": l, "p": round(p, 1)} for l, p in bop],
        "bop_vol": float(bop_ev.get("volume", 0)),
        "seats": [{"label": l, "p": round(p, 1)} for l, p in seats],
        "seats_vol": float(seats_ev.get("volume", 0)),
        "senate_seats": senate_seat_distribution(races),
        "fixed_republican_senate_seats": FIXED_REPUBLICAN_SENATE_SEATS,
        "races": races,
    }


def build_html(d, output_path):
    races = d["races"]
    for r in races:
        r["label"] = race_label(r)
    battleground = battleground_races(races)
    tossups = sum(1 for r in races if 40 <= r["rep"] <= 60)
    n_polled = sum(1 for r in races if r.get("poll"))
    total_vol = d["house"]["vol"] + d["senate"]["vol"] + d["bop_vol"] + d["seats_vol"] + sum(r["volume"] for r in races)
    fetched_at = escape(d.get("fetched_at", "Unknown — refresh required").replace("T", " ").replace("+00:00", " UTC"))

    races_rows = ""
    for r in races:
        ind = f' <span style="color:#a78bfa">· Ind {r["other"]:.0f}%</span>' if r["other"] >= 5 else ""
        races_rows += f"""<tr>
          <td class="name"><a href="https://polymarket.com/event/{r['slug']}-senate-election-winner">{r['state']}</a></td>
          <td style="color:#cbd5e1">{matchup(r['slug'])}</td>
          <td class="right"><span class="dem">{r['dem']:.0f}%</span></td>
          <td class="right"><span class="rep">{r['rep']:.0f}%</span>{ind}</td>
          <td class="right">{poll_html(r)}</td>
          <td class="right mono">{fmt_usd(r['volume'])}</td>
        </tr>"""

    html = f"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>2026 Midterms - Polymarket Dashboard</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
<style>
  *{{margin:0;padding:0;box-sizing:border-box}}
  body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;min-height:100vh;
       background:linear-gradient(135deg,#0f172a,#1e293b 50%,#0f172a);color:#fff;padding:32px}}
  .container{{max-width:1150px;margin:0 auto}}
  h1{{font-size:24px;margin-bottom:6px}}
  .subtitle{{color:#64748b;font-size:14px;margin-bottom:24px}}
  .stats-grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:16px;margin-bottom:24px}}
  .stat-card{{background:rgba(51,65,85,.3);border-radius:16px;padding:18px;border:1px solid rgba(71,85,105,.5)}}
  .stat-label{{font-size:11px;color:#64748b;text-transform:uppercase;margin-bottom:6px}}
  .stat-value{{font-size:22px;font-weight:700}}
  .chart-container{{background:rgba(51,65,85,.2);border-radius:20px;padding:24px;margin-bottom:24px;border:1px solid rgba(71,85,105,.3)}}
  .chart-title{{font-size:18px;font-weight:600;margin-bottom:4px}}
  .chart-title span{{font-size:13px;color:#64748b;font-weight:400;margin-left:8px}}
  .gauge{{margin:14px 0}}
  .gauge-label{{display:flex;justify-content:space-between;font-size:13px;margin-bottom:6px}}
  .bar{{display:flex;height:34px;border-radius:8px;overflow:hidden}}
  .bar .d{{background:#3b82f6;display:flex;align-items:center;padding-left:10px;font-size:12px;font-weight:600}}
  .bar .r{{background:#ef4444;display:flex;align-items:center;justify-content:flex-end;padding-right:10px;font-size:12px;font-weight:600}}
  .cols{{display:grid;grid-template-columns:1fr 1fr;gap:24px}}
  table{{width:100%;font-size:13px;border-collapse:collapse}}
  th{{text-align:left;padding:8px;color:#64748b;font-weight:500;border-bottom:1px solid rgba(71,85,105,.5)}}
  th.right,td.right{{text-align:right}}
  td{{padding:8px;border-bottom:1px solid rgba(71,85,105,.2)}}
  .name{{color:#e2e8f0;font-weight:500}}
  .dem{{color:#60a5fa;font-weight:700}} .rep{{color:#f87171;font-weight:700}}
  .mono{{font-family:monospace;color:#fbbf24}}
  a{{color:inherit}} .poll-date{{color:#94a3b8;font-size:11px}}
  .note{{color:#64748b;font-size:12px;margin-top:10px;line-height:1.5}}
  .footer{{margin-top:24px;text-align:center;color:#64748b;font-size:12px}}
  @media(max-width:768px){{.stats-grid{{grid-template-columns:repeat(2,1fr)}}.cols{{grid-template-columns:1fr}}}}
</style></head>
<body><div class="container">
  <h1>2026 U.S. Midterms — Polymarket Dashboard</h1>
  <p class="subtitle">Control, scenarios, seat distribution & {len(races)} Senate races · combined volume {fmt_usd(total_vol)} · data fetched {fetched_at}</p>

  <div class="stats-grid">
    <div class="stat-card"><div class="stat-label">House control</div><div class="stat-value"><span class="dem">D {d['house']['d']:.0f}%</span></div></div>
    <div class="stat-card"><div class="stat-label">Senate control</div><div class="stat-value"><span class="rep">R {d['senate']['r']:.0f}%</span></div></div>
    <div class="stat-card"><div class="stat-label">Top scenario</div><div class="stat-value" style="font-size:15px">{d['bop'][0]['label']}<br><span style="color:#94a3b8">{d['bop'][0]['p']:.0f}%</span></div></div>
    <div class="stat-card"><div class="stat-label">Toss-up Senate seats (40–60% R)</div><div class="stat-value">{tossups} / {len(races)}</div></div>
  </div>

  <div class="chart-container">
    <h2 class="chart-title">Chamber Control <span>(Dem vs Rep)</span></h2>
    <div class="gauge">
      <div class="gauge-label"><span class="dem">House — Democrats {d['house']['d']:.0f}%</span><span class="rep">Republicans {d['house']['r']:.0f}%</span></div>
      <div class="bar"><div class="d" style="width:{d['house']['d']:.0f}%">D</div><div class="r" style="width:{d['house']['r']:.0f}%">R</div></div>
    </div>
    <div class="gauge">
      <div class="gauge-label"><span class="dem">Senate — Democrats {d['senate']['d']:.0f}%</span><span class="rep">Republicans {d['senate']['r']:.0f}%</span></div>
      <div class="bar"><div class="d" style="width:{d['senate']['d']:.0f}%">D</div><div class="r" style="width:{d['senate']['r']:.0f}%">R</div></div>
    </div>
    <p class="note">Senate control means 51+ seats for Democrats: at 50–50 the Republican Vice President breaks ties, so Republicans keep control. These market prices resolve on that rule — the D% here is the chance Democrats reach 51, not 50.</p>
  </div>

  <div class="cols">
    <div class="chart-container">
      <h2 class="chart-title">Balance of Power <span>({fmt_usd(d['bop_vol'])})</span></h2>
      <div style="position:relative;height:240px"><canvas id="bopChart"></canvas></div>
    </div>
    <div class="chart-container">
      <h2 class="chart-title">Republican House Seats <span>({fmt_usd(d['seats_vol'])})</span></h2>
      <div style="position:relative;height:240px"><canvas id="seatsChart"></canvas></div>
      <p class="note">Amber dashed line = 218 (majority); green bars = buckets entirely above that threshold; the amber 215–219 bucket spans both outcomes.</p>
    </div>
    <div class="chart-container">
      <h2 class="chart-title">Republican Senate Seats <span>(derived from race markets)</span></h2>
      <div style="position:relative;height:240px"><canvas id="senateSeatsChart"></canvas></div>
      <p class="note">One-seat buckets from the listed Senate race markets, assuming independent outcomes and {d.get('fixed_republican_senate_seats', FIXED_REPUBLICAN_SENATE_SEATS)} fixed Republican seats from not-up seats plus unlisted Republican-held races. Amber line = 50, where Republicans control the Senate with the Vice President breaking ties.</p>
    </div>
  </div>

  <div class="chart-container">
    <h2 class="chart-title">Battleground Senate Zoom <span>(named battlegrounds plus any race with R between 25% and 75%)</span></h2>
    <div style="position:relative;height:360px"><canvas id="battlegroundChart"></canvas></div>
    <p class="note">Bars show distance from the 50% line using directly priced Republican win probability (bottom axis). Blue bars lean Democratic or independent; red bars lean Republican. Amber diamonds show the Republican polling margin over the top opponent (top axis, in points); a diamond on the dashed line is a tied poll, and a diamond on the far side of the line from its bar is a race where polls and money disagree. Races with no polling show no diamond. This view intentionally expands the middle of the map so Ohio, Texas, Iowa, Nebraska, Michigan, Alaska, Maine, Kansas, and New Hampshire are easier to compare.</p>
  </div>

  <div class="chart-container">
    <h2 class="chart-title">Senate Races — Republican win probability <span>(point size ∝ volume; below the 50% line = seat leans Dem/Ind)</span></h2>
    <div style="position:relative;height:440px"><canvas id="raceBubble"></canvas></div>
    <p class="note">Plotting Republican win % (directly priced) handles 3-way races: e.g. Nebraska is a Republican-vs-independent contest, so its Dem share is tiny but the seat is still competitive.</p>
  </div>

  <div class="chart-container">
    <h2 class="chart-title">Markets vs Polls <span>(where public polling exists: {n_polled} of {len(races)} races)</span></h2>
    <div style="position:relative;height:400px"><canvas id="mvpChart"></canvas></div>
    <p class="note">x = Republican polling margin over the top opponent (Wikipedia poll aggregates where available, otherwise the average of the newest head-to-head polls) · y = the market's Republican win probability. Dashed line = tied polls; the bold gridline = 50% odds. Points far from the natural S-shape are where money and polls disagree — polls measure vote share, markets price the chance of winning, so a small polled lead in a stable race can justify lopsided odds.</p>
  </div>

  <div class="chart-container">
    <h2 class="chart-title">Senate Races — detail <span>(most competitive first)</span></h2>
    <div style="overflow-x:auto"><table>
      <thead><tr><th>State</th><th>Matchup</th><th class="right">Dem</th><th class="right">Rep</th><th class="right">Poll avg</th><th class="right">Volume</th></tr></thead>
      <tbody>{races_rows}</tbody>
    </table></div>
    <p class="note">Polling dates describe the first listed source; hover to see all included fieldwork periods and click to inspect the table. Aggregates are averaged equally, excluding Wikipedia's summary row. Missing polling means no matching table was found. Candidate names checked {escape(d.get('candidates_as_of', 'date unavailable'))}.</p>
  </div>

  <div class="footer">Data: <a href="https://polymarket.com/event/{CONTROL['house']}">House</a> · <a href="https://polymarket.com/event/{CONTROL['senate']}">Senate</a> · <a href="https://polymarket.com/event/{BALANCE}">Balance of Power</a> · <a href="https://polymarket.com/event/{HOUSE_SEATS}">House seats</a> · polling from linked Wikipedia race pages · <a href="{CANDIDATE_SOURCES['overview']}">Candidates</a><br>Market prices are independently quoted and may not sum to 100%.</div>
</div>
<script>
(function init(){{
  // htmlpreview & similar proxies eval inline scripts before the CDN script
  // loads — poll until Chart.js is present instead of assuming order
  if(!window.Chart){{setTimeout(init,50);return;}}
  const bop={json.dumps(d['bop'])};
  const seats={json.dumps(d['seats'])};
  const senateSeats={json.dumps(d.get('senate_seats', []))};
  const races={json.dumps(races)};
  const battleground={json.dumps(battleground)};
  const fmtV=v=>Math.abs(v)>=1e6?'$'+(v/1e6).toFixed(1)+'M':Math.abs(v)>=1e3?'$'+(v/1e3).toFixed(0)+'k':'$'+v;

  new Chart(document.getElementById('bopChart'),{{type:'bar',
    data:{{labels:bop.map(b=>b.label),datasets:[{{data:bop.map(b=>b.p),
      backgroundColor:bop.map(b=>b.label.includes('Democrat')?'#3b82f6':b.label.includes('Republican')?'#ef4444':'#94a3b8')}}]}},
    options:{{indexAxis:'y',responsive:true,maintainAspectRatio:false,
      plugins:{{legend:{{display:false}},tooltip:{{callbacks:{{label:c=>c.raw+'%'}}}}}},
      scales:{{x:{{max:100,grid:{{color:'#334155'}},ticks:{{color:'#94a3b8',callback:v=>v+'%'}}}},y:{{grid:{{display:false}},ticks:{{color:'#cbd5e1',font:{{size:11}}}}}}}}}}}});

  const low=l=>{{const m=l.match(/\\d+/);return m?+m[0]:(l.toLowerCase().includes('below')?0:999);}};
  // dashed vertical line at 218 (majority), positioned within the 215-219 bucket
  const majLine={{id:'majLine',afterDatasetsDraw(chart){{
    const x=chart.scales.x,y=chart.scales.y,idx=seats.findIndex(s=>low(s.label)===215);
    if(idx<1)return;
    const step=x.getPixelForValue(idx)-x.getPixelForValue(idx-1);
    const px=x.getPixelForValue(idx)+0.2*step;           // 218 = 0.6 into the 215-219 bin, i.e. +0.1 bin past center... use +0.2*step
    const ctx=chart.ctx;ctx.save();
    ctx.strokeStyle='#fbbf24';ctx.lineWidth=2;ctx.setLineDash([6,4]);
    ctx.beginPath();ctx.moveTo(px,y.top);ctx.lineTo(px,y.bottom);ctx.stroke();
    ctx.setLineDash([]);ctx.fillStyle='#fbbf24';ctx.font='600 10px -apple-system,sans-serif';ctx.textAlign='left';
    ctx.fillText('218 = majority',px+4,y.top+10);ctx.restore();
  }}}};
  new Chart(document.getElementById('seatsChart'),{{type:'bar',
    data:{{labels:seats.map(s=>s.label),datasets:[{{data:seats.map(s=>s.p),
      backgroundColor:seats.map(s=>low(s.label)>=218?'#34d399':low(s.label)===215?'#fbbf24':'#a78bfa')}}]}},
    plugins:[majLine],
    options:{{responsive:true,maintainAspectRatio:false,
      plugins:{{legend:{{display:false}},tooltip:{{callbacks:{{label:c=>c.raw+'%'}}}}}},
      scales:{{x:{{grid:{{display:false}},ticks:{{color:'#94a3b8',font:{{size:9}},maxRotation:60,minRotation:45}}}},
        y:{{grid:{{color:'#334155'}},ticks:{{color:'#94a3b8',callback:v=>v+'%'}}}}}}}}}});

  const senateMajLine={{id:'senateMajLine',afterDatasetsDraw(chart){{
    const x=chart.scales.x,y=chart.scales.y,idx=senateSeats.findIndex(s=>+s.label===50);
    if(idx<0)return;
    const px=x.getPixelForValue(idx);
    const ctx=chart.ctx;ctx.save();
    ctx.strokeStyle='#fbbf24';ctx.lineWidth=2;ctx.setLineDash([6,4]);
    ctx.beginPath();ctx.moveTo(px,y.top);ctx.lineTo(px,y.bottom);ctx.stroke();
    ctx.setLineDash([]);ctx.fillStyle='#fbbf24';ctx.font='600 10px -apple-system,sans-serif';ctx.textAlign='left';
    ctx.fillText('50 = R control',px+4,y.top+10);ctx.restore();
  }}}};
  new Chart(document.getElementById('senateSeatsChart'),{{type:'bar',
    data:{{labels:senateSeats.map(s=>s.label),datasets:[{{data:senateSeats.map(s=>s.p),
      backgroundColor:senateSeats.map(s=>+s.label>50?'#34d399':+s.label===50?'#fbbf24':'#a78bfa')}}]}},
    plugins:[senateMajLine],
    options:{{responsive:true,maintainAspectRatio:false,
      plugins:{{legend:{{display:false}},tooltip:{{callbacks:{{label:c=>c.raw+'%'}}}}}},
      scales:{{x:{{grid:{{display:false}},ticks:{{color:'#94a3b8',font:{{size:9}},maxRotation:60,minRotation:45}}}},
        y:{{grid:{{color:'#334155'}},ticks:{{color:'#94a3b8',callback:v=>v+'%'}}}}}}}}}});

  const midLine={{id:'midLine',afterDatasetsDraw(chart){{
    const x=chart.scales.x,y=chart.scales.y,px=x.getPixelForValue(50),ctx=chart.ctx;
    ctx.save();ctx.strokeStyle='#fbbf24';ctx.lineWidth=2;ctx.setLineDash([6,4]);
    ctx.beginPath();ctx.moveTo(px,y.top);ctx.lineTo(px,y.bottom);ctx.stroke();
    ctx.setLineDash([]);ctx.fillStyle='#fbbf24';ctx.font='600 10px -apple-system,sans-serif';ctx.textAlign='left';
    ctx.fillText('50%',px+4,y.top+10);ctx.restore();
  }}}};
  // Poll-margin diamonds on the top axis (xPoll), which is centered on 0 so a
  // tied poll sits on the 50% line.
  const POLL_LIM=15;
  const pollDiamonds={{id:'pollDiamonds',afterDatasetsDraw(chart){{
    const xp=chart.scales.xPoll,y=chart.scales.y,ctx=chart.ctx;
    ctx.save();
    battleground.forEach((r,i)=>{{
      if(!r.poll)return;
      const m=Math.max(-POLL_LIM,Math.min(POLL_LIM,r.poll.margin));
      const px=xp.getPixelForValue(m),py=y.getPixelForValue(i),s=6;
      ctx.beginPath();ctx.moveTo(px,py-s);ctx.lineTo(px+s,py);ctx.lineTo(px,py+s);ctx.lineTo(px-s,py);ctx.closePath();
      ctx.fillStyle='#fbbf24';ctx.strokeStyle='#0f172a';ctx.lineWidth=1.5;ctx.fill();ctx.stroke();
    }});
    ctx.restore();
  }}}};
  const battlegroundBars=battleground.map(r=>({{
    x:[Math.min(r.rep,50),Math.max(r.rep,50)],
    y:r.label, rep:r.rep, dem:r.dem, other:r.other, volume:r.volume, poll:r.poll
  }}));
  new Chart(document.getElementById('battlegroundChart'),{{type:'bar',
    data:{{labels:battleground.map(r=>r.label),datasets:[{{data:battlegroundBars,
      backgroundColor:battleground.map(r=>r.rep>=50?'rgba(239,68,68,.72)':'rgba(59,130,246,.72)'),
      borderColor:battleground.map(r=>r.rep>=50?'#ef4444':'#3b82f6'),borderWidth:1}}]}},
    plugins:[midLine,pollDiamonds],
    options:{{indexAxis:'y',responsive:true,maintainAspectRatio:false,
      plugins:{{legend:{{display:false}},tooltip:{{callbacks:{{
        label:c=>{{const p=c.raw.poll;const poll=p?' · poll R '+(p.margin>0?'+':'')+p.margin+' ('+(p.kind==='agg'?'aggregates':'last '+p.n+' polls')+')':' · no polling';
          return c.raw.y+': R '+c.raw.rep+'% / D '+c.raw.dem+'%'+(c.raw.other>=5?' / other '+c.raw.other+'%':'')+poll+' · vol '+fmtV(c.raw.volume);}}}}}}}},
      scales:{{x:{{min:20,max:80,title:{{display:true,text:'Republican win probability (bars)',color:'#64748b'}},
          grid:{{color:c=>c.tick.value===50?'#64748b':'#334155'}},ticks:{{color:'#94a3b8',callback:v=>v+'%'}}}},
        xPoll:{{type:'linear',position:'top',min:-POLL_LIM,max:POLL_LIM,
          title:{{display:true,text:'◆ Republican polling margin, points (diamonds)',color:'#fbbf24'}},
          grid:{{display:false}},ticks:{{color:'#fbbf24',stepSize:5,callback:v=>(v>0?'R +':v<0?'D +':'')+Math.abs(v)}}}},
        y:{{grid:{{display:false}},ticks:{{color:'#cbd5e1',font:{{size:11}}}}}}}}}}}});

  const maxV=Math.max(...races.map(r=>r.volume),1);
  const bubble=races.map(r=>({{x:r.volume,y:r.rep,r:6+16*Math.sqrt(r.volume/maxV),state:r.state,dem:r.dem,label:r.label}}));
  // label-plugin factory: labels every point, greedily dodging collisions.
  // Each label tries above / below / right / left of its point, stepping
  // further out until it finds space free of other labels; boxes are clamped
  // to the chart area. Labels pushed far away get a connector line.
  const mkLabels=(id,data)=>({{id,afterDatasetsDraw(chart){{
    const ctx=chart.ctx, meta=chart.getDatasetMeta(0), area=chart.chartArea;
    ctx.save();ctx.font='600 10px -apple-system,BlinkMacSystemFont,sans-serif';ctx.textAlign='center';
    const placed=[], H=13;
    const hits=b=>placed.some(p=>b.x<p.x+p.w&&b.x+b.w>p.x&&b.y<p.y+p.h&&b.y+b.h>p.y);
    meta.data.forEach((pt,i)=>{{
      const t=data[i].label, w=ctx.measureText(t).width+6, r=pt.options.radius;
      const cands=[];
      for(let k=0;k<8;k++){{
        cands.push([pt.x,           pt.y-r-9-(H+2)*k]);   // above, stepping up
        cands.push([pt.x,           pt.y+r+14+(H+2)*k]);  // below, stepping down
        cands.push([pt.x+r+w/2+4,   pt.y+3+(H+2)*k]);     // right, drifting down
        cands.push([pt.x-r-w/2-4,   pt.y+3-(H+2)*k]);     // left, drifting up
      }}
      let box=null, tx=0, ty=0;
      for(const [cx,cy] of cands){{
        const bx=Math.min(Math.max(cx-w/2,area.left),area.right-w);
        const b={{x:bx,y:cy-9,w:w,h:H}};
        if(b.y<area.top||b.y+H>area.bottom)continue;
        if(!hits(b)){{box=b;tx=bx+w/2;ty=cy;break;}}
      }}
      if(!box){{  // fallback: directly above, clamped, even if it overlaps
        const bx=Math.min(Math.max(pt.x-w/2,area.left),area.right-w);
        box={{x:bx,y:pt.y-r-18,w:w,h:H}};tx=bx+w/2;ty=pt.y-r-9;
      }}
      placed.push(box);
      const dx=tx-pt.x, dy=ty-4-pt.y, dist=Math.hypot(dx,dy);
      if(dist>r+22){{  // connector from bubble edge to label box
        ctx.strokeStyle='rgba(148,163,184,.5)';ctx.lineWidth=1;
        ctx.beginPath();ctx.moveTo(pt.x+dx/dist*r,pt.y+dy/dist*r);ctx.lineTo(tx,ty-4);ctx.stroke();
      }}
      ctx.fillStyle='rgba(15,23,42,.88)';ctx.fillRect(box.x,box.y,w,H);
      ctx.fillStyle='#e2e8f0';ctx.fillText(t,tx,ty+1);
    }});
    ctx.restore();
  }}}});
  new Chart(document.getElementById('raceBubble'),{{type:'bubble',
    data:{{datasets:[{{data:bubble,
      backgroundColor:bubble.map(b=>b.y>50?'rgba(239,68,68,.55)':'rgba(59,130,246,.55)'),
      borderColor:bubble.map(b=>b.y>50?'#ef4444':'#3b82f6'),borderWidth:1}}]}},
    plugins:[mkLabels('raceLabels',bubble)],
    options:{{responsive:true,maintainAspectRatio:false,layout:{{padding:{{top:14,bottom:14,right:30}}}},
      plugins:{{legend:{{display:false}},tooltip:{{callbacks:{{
        label:c=>c.raw.label+': R '+c.raw.y+'% / D '+c.raw.dem+'%  ·  vol '+fmtV(c.raw.x)}}}}}},
      scales:{{x:{{type:'logarithmic',title:{{display:true,text:'Market volume (log)',color:'#64748b'}},
          grid:{{color:'#1e293b'}},ticks:{{color:'#94a3b8',callback:v=>fmtV(v)}}}},
        y:{{min:0,max:100,title:{{display:true,text:'Republican win probability',color:'#64748b'}},
          grid:{{color:c=>c.tick.value===50?'#64748b':'#334155'}},ticks:{{color:'#94a3b8',callback:v=>v+'%'}}}}}}}}}});
  // markets-vs-polls scatter: only races with polling; quadrant guides at 0 / 50%
  const polled=races.filter(r=>r.poll);
  const mvp=polled.map(r=>({{x:r.poll.margin,y:r.rep,r:6+10*Math.sqrt(r.volume/maxV),label:r.label}}));
  const mlo=Math.min(0,...mvp.map(p=>p.x))-6, mhi=Math.max(0,...mvp.map(p=>p.x))+6;
  const zeroLine={{id:'zeroLine',afterDatasetsDraw(chart){{
    const x=chart.scales.x,y=chart.scales.y,ctx=chart.ctx;
    if(x.min>=0||x.max<=0)return;
    const px=x.getPixelForValue(0);
    ctx.save();ctx.strokeStyle='#64748b';ctx.lineWidth=1;ctx.setLineDash([4,4]);
    ctx.beginPath();ctx.moveTo(px,y.top);ctx.lineTo(px,y.bottom);ctx.stroke();ctx.restore();
  }}}};
  new Chart(document.getElementById('mvpChart'),{{type:'bubble',
    data:{{datasets:[{{data:mvp,
      backgroundColor:mvp.map(b=>b.y>50?'rgba(239,68,68,.55)':'rgba(59,130,246,.55)'),
      borderColor:mvp.map(b=>b.y>50?'#ef4444':'#3b82f6'),borderWidth:1}}]}},
    plugins:[mkLabels('mvpLabels',mvp),zeroLine],
    options:{{responsive:true,maintainAspectRatio:false,layout:{{padding:{{top:14,bottom:6,right:24}}}},
      plugins:{{legend:{{display:false}},tooltip:{{callbacks:{{
        label:c=>c.raw.label+': polls R'+(c.raw.x>0?'+':'')+c.raw.x.toFixed(1)+' · market R '+c.raw.y+'%'}}}}}},
      scales:{{x:{{min:mlo,max:mhi,title:{{display:true,text:'Republican polling margin (points)',color:'#64748b'}},
          grid:{{color:'#1e293b'}},ticks:{{color:'#94a3b8',callback:v=>(v>0?'+':'')+v}}}},
        y:{{min:0,max:100,title:{{display:true,text:'Market: Republican win probability',color:'#64748b'}},
          grid:{{color:c=>c.tick.value===50?'#64748b':'#334155'}},ticks:{{color:'#94a3b8',callback:v=>v+'%'}}}}}}}}}});

}})();
</script></body></html>"""

    with open(output_path, "w") as f:
        f.write(html)
    print(f"Created {output_path}")


def main():
    parser = ArgumentParser(description="2026 midterms Polymarket dashboard")
    parser.add_argument("-o", "--output", required=True)
    args = parser.parse_args()
    data = collect()
    build_html(data, args.output)
    data_path = args.output.rsplit(".", 1)[0] + "_data.json"
    with open(data_path, "w") as f:
        json.dump(data, f, indent=2)
    sys.stderr.write(f"Wrote {data_path}\n")


if __name__ == "__main__":
    main()
