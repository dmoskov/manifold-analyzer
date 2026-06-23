#!/usr/bin/env python3
"""
Render a market-implied price-range "ladder" from a Polymarket multi-outcome
threshold event (e.g. "What will WTI Crude Oil hit in June 2026?").

These events bundle many binary barrier markets: "hit (HIGH) $X" (price rises to
touch $X) and "hit (LOW) $X" (price falls to touch $X). Plotting touch
probability vs price level folds ~30 markets into one chart and a single
market-implied trading range.

Usage:
    python3 generate_poly_ladder.py --slug what-price-will-wti-hit-in-june-2026 \
        -o examples/hormuz/wti_june_ladder.html
"""

import json
import re
import sys
from argparse import ArgumentParser

from fetch_polymarket import fetch_event


def parse_ladder(event):
    rows = []
    for m in event["markets"]:
        g = m.get("groupItemTitle", "") or ""
        q = m.get("question", "")
        if "↑" in g or "(HIGH)" in q:
            direction = "up"
        elif "↓" in g or "(LOW)" in q:
            direction = "down"
        else:
            continue
        match = re.search(r"\$?([\d,]+(?:\.\d+)?)", g) or re.search(r"\$?([\d,]+(?:\.\d+)?)", q)
        if not match:
            continue
        price = float(match.group(1).replace(",", ""))
        prob = round(float(json.loads(m["outcomePrices"])[0]) * 100, 1)
        rows.append({"price": price, "dir": direction, "prob": prob})
    return rows


def cross_50(points):
    """Interpolate the price level where touch probability passes 50%.
    points: list of (price, prob) sorted by price."""
    pts = sorted(points)
    for (p0, q0), (p1, q1) in zip(pts, pts[1:]):
        if (q0 - 50) * (q1 - 50) <= 0 and q0 != q1:
            frac = (50 - q0) / (q1 - q0)
            return round(p0 + frac * (p1 - p0), 1)
    return None


def build(event, output_path):
    rows = parse_ladder(event)
    up = sorted([(r["price"], r["prob"]) for r in rows if r["dir"] == "up"])
    down = sorted([(r["price"], r["prob"]) for r in rows if r["dir"] == "down"])

    up_50 = cross_50(up)      # price the market gives ~50% odds of reaching on the upside
    down_50 = cross_50(down)  # price the market gives ~50% odds of reaching on the downside

    # "almost-certain" realized/expected range: highest up price still >=90%, lowest down price still >=90%
    up_90 = max([p for p, q in up if q >= 90], default=None)
    down_90 = min([p for p, q in down if q >= 90], default=None)

    title = event["title"]
    range_bits = []
    if down_90 is not None and up_90 is not None:
        range_bits.append(f"≥90% touch range: ${down_90:.0f} – ${up_90:.0f}")
    if down_50 is not None:
        range_bits.append(f"~50% downside reach: ${down_50:.0f}")
    if up_50 is not None:
        range_bits.append(f"~50% upside reach: ${up_50:.0f}")
    range_summary = " · ".join(range_bits) if range_bits else "insufficient data"

    html = f"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title} - Price Ladder</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
<style>
  *{{margin:0;padding:0;box-sizing:border-box}}
  body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;min-height:100vh;
       background:linear-gradient(135deg,#0f172a,#1e293b 50%,#0f172a);color:#fff;padding:32px}}
  .container{{max-width:1000px;margin:0 auto}}
  h1{{font-size:22px;margin-bottom:6px}}
  .subtitle{{color:#64748b;font-size:14px;margin-bottom:8px}}
  .range{{display:inline-block;background:rgba(59,130,246,.15);border:1px solid rgba(59,130,246,.4);
         border-radius:12px;padding:10px 16px;font-size:14px;margin-bottom:24px}}
  .chart-container{{background:rgba(51,65,85,.2);border-radius:20px;padding:24px;border:1px solid rgba(71,85,105,.3)}}
  .chart-title{{font-size:18px;font-weight:600;margin-bottom:6px}}
  .note{{color:#64748b;font-size:12px;margin:10px 0 18px;line-height:1.5}}
  .footer{{margin-top:24px;text-align:center;color:#64748b;font-size:12px}}
</style></head>
<body><div class="container">
  <h1>{title}</h1>
  <p class="subtitle">Market-implied price range · {len(rows)} barrier markets folded into one curve · <span id="date"></span></p>
  <div class="range">📏 {range_summary}</div>
  <div class="chart-container">
    <h2 class="chart-title">Touch Probability by Price Level</h2>
    <p class="note">Red = probability price <b>rises</b> to touch a high level (falls as level increases).
       Blue = probability price <b>falls</b> to touch a low level (falls as level decreases).
       Where each curve crosses 50% is the market's even-odds reach in that direction.</p>
    <div style="position:relative;height:420px;width:100%"><canvas id="ladder"></canvas></div>
  </div>
  <div class="footer">Data: Polymarket Gamma · barrier-touch markets</div>
</div>
<script>
  const up={json.dumps([{ 'x': p, 'y': q } for p, q in up])};
  const down={json.dumps([{ 'x': p, 'y': q } for p, q in down])};
  new Chart(document.getElementById('ladder'),{{type:'line',
    data:{{datasets:[
      {{label:'Upside touch (price rises to $X)',data:up,borderColor:'#ef4444',backgroundColor:'rgba(239,68,68,.12)',tension:.2,pointRadius:4,borderWidth:2,fill:true}},
      {{label:'Downside touch (price falls to $X)',data:down,borderColor:'#60a5fa',backgroundColor:'rgba(96,165,250,.12)',tension:.2,pointRadius:4,borderWidth:2,fill:true}}
    ]}},
    options:{{responsive:true,maintainAspectRatio:false,interaction:{{mode:'nearest',intersect:false}},
      plugins:{{legend:{{labels:{{color:'#cbd5e1',boxWidth:12,font:{{size:11}}}}}},
        tooltip:{{backgroundColor:'rgba(15,23,42,.95)',callbacks:{{label:c=>c.dataset.label+': '+c.raw.y+'% @ $'+c.raw.x}}}}}},
      scales:{{x:{{type:'linear',title:{{display:true,text:'Price level ($)',color:'#64748b'}},grid:{{color:'#1e293b'}},ticks:{{color:'#94a3b8',callback:v=>'$'+v}}}},
        y:{{min:0,max:100,title:{{display:true,text:'Touch probability',color:'#64748b'}},grid:{{color:'#334155'}},ticks:{{color:'#94a3b8',callback:v=>v+'%'}}}}}}}}}});
  document.getElementById('date').textContent=new Date().toLocaleDateString();
</script></body></html>"""

    with open(output_path, "w") as f:
        f.write(html)
    print(f"Created {output_path}")
    sys.stderr.write(f"Range: {range_summary}\n")


def main():
    parser = ArgumentParser(description="Polymarket price-range ladder")
    g = parser.add_mutually_exclusive_group(required=True)
    g.add_argument("--slug")
    g.add_argument("--url")
    parser.add_argument("-o", "--output", required=True)
    args = parser.parse_args()
    from fetch_polymarket import slug_from_url
    slug = args.slug or slug_from_url(args.url)
    event = fetch_event(slug)
    build(event, args.output)


if __name__ == "__main__":
    main()
