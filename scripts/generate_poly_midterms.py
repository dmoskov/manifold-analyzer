#!/usr/bin/env python3
"""
Generate a 2026 U.S. midterms dashboard from Polymarket multi-outcome markets.

Unlike the binary topic report, the midterms are priced as mutually-exclusive
multi-outcome markets (party-vs-party races, scenario splits, seat-count
distributions). This dashboard folds them into:
  - Control gauges (House / Senate, Dem vs Rep)
  - Balance-of-Power scenario breakdown
  - Republican House-seat distribution (with the 218 majority line)
  - Competitive Senate races: Dem win% sorted, plus a Dem%-vs-volume bubble view

Usage:
    python3 generate_poly_midterms.py -o examples/midterms/midterms_dashboard.html
"""

import json
import re
import sys
from argparse import ArgumentParser

from fetch_polymarket import fetch_event

CONTROL = {
    "house": "which-party-will-win-the-house-in-2026",
    "senate": "which-party-will-win-the-senate-in-2026",
}
BALANCE = "balance-of-power-2026-midterms"
HOUSE_SEATS = "republican-house-seats-after-the-2026-midterm-elections"

RACE_SLUGS = [
    "maine", "texas", "alaska", "nebraska", "iowa", "michigan", "ohio",
    "montana", "north-carolina", "florida", "south-carolina", "colorado",
    "georgia", "kansas", "new-hampshire", "mississippi", "minnesota",
    "oklahoma", "wyoming", "virginia", "kentucky",
]
# party for candidate markets that carry no (D)/(R) tag
NAME_PARTY = {"peltola": "D", "sullivan": "R"}

# Known 2026 general-election nominees / leading candidates per race (many race
# markets resolve by party only, so candidate names come from here). Source:
# Wikipedia "2026 United States Senate elections" + Ballotpedia, as of June 2026.
# "TBD" nominees are simply omitted.
CANDIDATES = {
    "maine": {"D": "Graham Platner", "R": "Susan Collins"},
    "texas": {"D": "James Talarico", "R": "Ken Paxton"},
    "alaska": {"D": "Mary Peltola", "R": "Dan Sullivan"},
    "nebraska": {"I": "Dan Osborn", "R": "Pete Ricketts"},
    "iowa": {"D": "Josh Turek", "R": "Ashley Hinson"},
    "michigan": {"R": "Mike Rogers"},
    "ohio": {"D": "Sherrod Brown", "R": "Jon Husted"},
    "montana": {"D": "Alani Bankhead"},
    "north-carolina": {"D": "Roy Cooper", "R": "Michael Whatley"},
    "florida": {"D": "Alexander Vindman", "R": "Ashley Moody"},
    "south-carolina": {"D": "Annie Andrews", "R": "Lindsey Graham"},
    "colorado": {"D": "John Hickenlooper", "R": "Mark Baisley"},
    "georgia": {"D": "Jon Ossoff", "R": "Mike Collins"},
    "kansas": {"R": "Roger Marshall"},
    "new-hampshire": {"R": "John E. Sununu"},
    "mississippi": {"D": "Scott Colom", "R": "Cindy Hyde-Smith"},
    "minnesota": {},
    "oklahoma": {"R": "Kevin Hern"},
    "wyoming": {"R": "Harriet Hageman"},
    "virginia": {},
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
    """State + the leading candidate's surname, from the known-candidate map."""
    cand = CANDIDATES.get(r["slug"], {})
    lead = max({"D": r["dem"], "R": r["rep"], "I": r.get("other", 0)}.items(), key=lambda x: x[1])[0]
    name = cand.get(lead)
    return f"{r['state']} · {name.split()[-1]}" if name else r["state"]


def collect():
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
        except Exception:
            continue
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

    return {
        "house": {"d": round(house_d, 1), "r": round(house_r, 1), "vol": float(house.get("volume", 0))},
        "senate": {"d": round(senate_d, 1), "r": round(senate_r, 1), "vol": float(senate.get("volume", 0))},
        "bop": [{"label": l, "p": round(p, 1)} for l, p in bop],
        "bop_vol": float(bop_ev.get("volume", 0)),
        "seats": [{"label": l, "p": round(p, 1)} for l, p in seats],
        "seats_vol": float(seats_ev.get("volume", 0)),
        "races": races,
    }


def build_html(d, output_path):
    races = d["races"]
    for r in races:
        r["label"] = race_label(r)
    tossups = sum(1 for r in races if 40 <= r["rep"] <= 60)
    total_vol = d["house"]["vol"] + d["senate"]["vol"] + d["bop_vol"] + d["seats_vol"] + sum(r["volume"] for r in races)

    races_rows = ""
    for r in races:
        ind = f' <span style="color:#a78bfa">· Ind {r["other"]:.0f}%</span>' if r["other"] >= 5 else ""
        races_rows += f"""<tr>
          <td class="name">{r['state']}</td>
          <td style="color:#cbd5e1">{matchup(r['slug'])}</td>
          <td class="right"><span class="dem">{r['dem']:.0f}%</span></td>
          <td class="right"><span class="rep">{r['rep']:.0f}%</span>{ind}</td>
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
  .note{{color:#64748b;font-size:12px;margin-top:10px;line-height:1.5}}
  .footer{{margin-top:24px;text-align:center;color:#64748b;font-size:12px}}
  @media(max-width:768px){{.stats-grid{{grid-template-columns:repeat(2,1fr)}}.cols{{grid-template-columns:1fr}}}}
</style></head>
<body><div class="container">
  <h1>2026 U.S. Midterms — Polymarket Dashboard</h1>
  <p class="subtitle">Control, scenarios, seat distribution & {len(races)} Senate races · combined volume {fmt_usd(total_vol)} · generated <span id="date"></span></p>

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
  </div>

  <div class="cols">
    <div class="chart-container">
      <h2 class="chart-title">Balance of Power <span>({fmt_usd(d['bop_vol'])})</span></h2>
      <div style="position:relative;height:240px"><canvas id="bopChart"></canvas></div>
    </div>
    <div class="chart-container">
      <h2 class="chart-title">Republican House Seats <span>({fmt_usd(d['seats_vol'])})</span></h2>
      <div style="position:relative;height:240px"><canvas id="seatsChart"></canvas></div>
      <p class="note">Amber dashed line = 218 (majority); green bars = outcomes where Republicans keep a majority. The mass sits left of the line → market expects GOP losses (and a likely lost majority).</p>
    </div>
  </div>

  <div class="chart-container">
    <h2 class="chart-title">Senate Races — Republican win probability <span>(point size ∝ volume; below the 50% line = seat leans Dem/Ind)</span></h2>
    <div style="position:relative;height:360px"><canvas id="raceBubble"></canvas></div>
    <p class="note">Plotting Republican win % (directly priced) handles 3-way races: e.g. Nebraska is a Republican-vs-independent contest, so its Dem share is tiny but the seat is still competitive.</p>
  </div>

  <div class="chart-container">
    <h2 class="chart-title">Senate Races — detail <span>(most competitive first)</span></h2>
    <table>
      <thead><tr><th>State</th><th>Matchup</th><th class="right">Dem</th><th class="right">Rep</th><th class="right">Volume</th></tr></thead>
      <tbody>{races_rows}</tbody>
    </table>
  </div>

  <div class="footer">Data: Polymarket Gamma · multi-outcome markets folded to party totals</div>
</div>
<script>
  const bop={json.dumps(d['bop'])};
  const seats={json.dumps(d['seats'])};
  const races={json.dumps(races)};
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
      backgroundColor:seats.map(s=>low(s.label)>=215?'#34d399':'#a78bfa')}}]}},
    plugins:[majLine],
    options:{{responsive:true,maintainAspectRatio:false,
      plugins:{{legend:{{display:false}},tooltip:{{callbacks:{{label:c=>c.raw+'%'}}}}}},
      scales:{{x:{{grid:{{display:false}},ticks:{{color:'#94a3b8',font:{{size:9}},maxRotation:60,minRotation:45}}}},
        y:{{grid:{{color:'#334155'}},ticks:{{color:'#94a3b8',callback:v=>v+'%'}}}}}}}}}});

  const maxV=Math.max(...races.map(r=>r.volume),1);
  const bubble=races.map(r=>({{x:r.volume,y:r.rep,r:6+16*Math.sqrt(r.volume/maxV),state:r.state,dem:r.dem,label:r.label}}));
  // inline plugin: draw each race's label, nudged up/down alternately to reduce overlap
  const raceLabels={{id:'raceLabels',afterDatasetsDraw(chart){{
    const ctx=chart.ctx, meta=chart.getDatasetMeta(0);
    ctx.save();ctx.font='600 10px -apple-system,BlinkMacSystemFont,sans-serif';ctx.textAlign='center';
    meta.data.forEach((pt,i)=>{{
      const above=bubble[i].y<=92;                 // put label below if point is near the top
      const off=pt.options.radius+(above?9:14);
      const y=above?pt.y-off:pt.y+off;
      ctx.fillStyle='rgba(15,23,42,.85)';
      const t=bubble[i].label, w=ctx.measureText(t).width;
      ctx.fillRect(pt.x-w/2-3,y-9,w+6,13);
      ctx.fillStyle='#e2e8f0';ctx.fillText(t,pt.x,y+1);
    }});
    ctx.restore();
  }}}};
  new Chart(document.getElementById('raceBubble'),{{type:'bubble',
    data:{{datasets:[{{data:bubble,
      backgroundColor:bubble.map(b=>b.y>50?'rgba(239,68,68,.55)':'rgba(59,130,246,.55)'),
      borderColor:bubble.map(b=>b.y>50?'#ef4444':'#3b82f6'),borderWidth:1}}]}},
    plugins:[raceLabels],
    options:{{responsive:true,maintainAspectRatio:false,layout:{{padding:{{top:14,bottom:14,right:30}}}},
      plugins:{{legend:{{display:false}},tooltip:{{callbacks:{{
        label:c=>c.raw.label+': R '+c.raw.y+'% / D '+c.raw.dem+'%  ·  vol '+fmtV(c.raw.x)}}}}}},
      scales:{{x:{{type:'logarithmic',title:{{display:true,text:'Market volume (log)',color:'#64748b'}},
          grid:{{color:'#1e293b'}},ticks:{{color:'#94a3b8',callback:v=>fmtV(v)}}}},
        y:{{min:0,max:100,title:{{display:true,text:'Republican win probability',color:'#64748b'}},
          grid:{{color:c=>c.tick.value===50?'#64748b':'#334155'}},ticks:{{color:'#94a3b8',callback:v=>v+'%'}}}}}}}}}});
  document.getElementById('date').textContent=new Date().toLocaleDateString();
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
