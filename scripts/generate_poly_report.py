#!/usr/bin/env python3
"""
Generate a multi-market topic report from Polymarket data.

Given several related event slugs, fetches each (metadata + price history) and
produces a single HTML report with:
  - Overlaid YES-probability curves for every market
  - A comparison table (current odds, volume, resolution date, weekly move)
  - Per-market resolution criteria

This is the "topic" view that complements the single-market deep dive in
generate_poly_viz.py.

Usage:
    python3 generate_poly_report.py \
        --slug will-the-iranian-regime-fall-by-june-30 \
        --slug strait-of-hormuz-traffic-returns-to-normal-by-end-of-june \
        --slug strait-of-hormuz-traffic-returns-to-normal-by-july-31 \
        --slug will-ships-transit-the-strait-of-hormuz-on-any-day-by-june-30 \
        --title "Iran / Strait of Hormuz Crisis" \
        -o examples/hormuz/iran_topic_report.html
"""

import json
import sys
from datetime import datetime, timezone
from argparse import ArgumentParser

from fetch_polymarket import fetch_event, fetch_price_history

PALETTE = ["#60a5fa", "#f59e0b", "#10b981", "#ef4444", "#a78bfa", "#ec4899", "#22d3ee"]


def fmt_usd(v):
    v = float(v)
    if abs(v) >= 1_000_000:
        return f"${v/1_000_000:.1f}M"
    if abs(v) >= 1_000:
        return f"${v/1_000:.0f}k"
    return f"${v:.0f}"


def collect(slug):
    event = fetch_event(slug)
    market = event["markets"][0]
    token = json.loads(market["clobTokenIds"])[0]  # YES token
    history = fetch_price_history(token)
    curve = [{"t": p["t"], "p": round(p["p"] * 100, 1)} for p in history]
    yes_price = float(json.loads(market["outcomePrices"])[0])
    return {
        "slug": slug,
        "title": event["title"],
        "yes": round(yes_price * 100, 1),
        "volume": float(event.get("volume", 0)),
        "liquidity": float(event.get("liquidity", 0)),
        "end_date": (event.get("endDate") or "")[:10],
        "wk_change": market.get("oneWeekPriceChange"),
        "day_change": market.get("oneDayPriceChange"),
        "description": market.get("description", "").split("\n")[0],
        "curve": curve,
    }


def build_report(markets, title, output_path):
    # Build a unified daily date axis across all markets
    all_days = set()
    series = []
    for m in markets:
        daily = {}
        for pt in m["curve"]:
            day = datetime.fromtimestamp(pt["t"], tz=timezone.utc).strftime("%Y-%m-%d")
            daily[day] = pt["p"]  # last value of the day wins
        all_days.update(daily.keys())
        series.append({"m": m, "daily": daily})
    days = sorted(all_days)

    datasets = []
    for i, sd in enumerate(series):
        daily = sd["daily"]
        last = None
        row = []
        for d in days:
            if d in daily:
                last = daily[d]
            row.append(last)  # forward-fill so lines stay continuous
        datasets.append({
            "label": sd["m"]["title"],
            "data": row,
            "color": PALETTE[i % len(PALETTE)],
        })

    rows_html = ""
    for i, m in enumerate(markets):
        wk = m["wk_change"]
        wk_str = f"{wk*100:+.0f} pts" if isinstance(wk, (int, float)) else "—"
        wk_class = "up" if isinstance(wk, (int, float)) and wk > 0 else ("down" if isinstance(wk, (int, float)) and wk < 0 else "")
        rows_html += f"""<tr>
          <td><span class="dot" style="background:{PALETTE[i%len(PALETTE)]}"></span></td>
          <td class="name"><a href="https://polymarket.com/event/{m['slug']}" target="_blank">{m['title']}</a>
              <div class="crit">{m['description']}</div></td>
          <td class="right big">{m['yes']:.0f}%</td>
          <td class="right {wk_class}">{wk_str}</td>
          <td class="right mono">{fmt_usd(m['volume'])}</td>
          <td class="right">{m['end_date']}</td>
        </tr>"""

    html = f"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title} - Polymarket Topic Report</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
<style>
  *{{margin:0;padding:0;box-sizing:border-box}}
  body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;min-height:100vh;
       background:linear-gradient(135deg,#0f172a,#1e293b 50%,#0f172a);color:#fff;padding:32px}}
  .container{{max-width:1100px;margin:0 auto}}
  h1{{font-size:24px;margin-bottom:6px}}
  .subtitle{{color:#64748b;font-size:14px;margin-bottom:28px}}
  .chart-container{{background:rgba(51,65,85,.2);border-radius:20px;padding:24px;margin-bottom:24px;border:1px solid rgba(71,85,105,.3)}}
  .chart-title{{font-size:18px;font-weight:600;margin-bottom:18px}}
  table{{width:100%;font-size:13px;border-collapse:collapse}}
  th{{text-align:left;padding:10px 8px;color:#64748b;font-weight:500;border-bottom:1px solid rgba(71,85,105,.5)}}
  th.right,td.right{{text-align:right}}
  td{{padding:12px 8px;border-bottom:1px solid rgba(71,85,105,.2);vertical-align:top}}
  .name a{{color:#e2e8f0;font-weight:600;text-decoration:none}}
  .name a:hover{{color:#60a5fa}}
  .crit{{color:#64748b;font-size:11px;margin-top:4px;max-width:520px;line-height:1.4}}
  .big{{font-size:18px;font-weight:700}}
  .mono{{font-family:monospace;color:#fbbf24}}
  .up{{color:#10b981}} .down{{color:#ef4444}}
  .dot{{display:inline-block;width:12px;height:12px;border-radius:50%}}
  .footer{{margin-top:28px;text-align:center;color:#64748b;font-size:12px}}
</style></head>
<body><div class="container">
  <h1>{title}</h1>
  <p class="subtitle">{len(markets)} related Polymarket markets · combined volume {fmt_usd(sum(m['volume'] for m in markets))} · generated <span id="date"></span></p>

  <div class="chart-container">
    <h2 class="chart-title">YES Probability — all markets</h2>
    <div style="position:relative;height:380px;width:100%"><canvas id="chart"></canvas></div>
  </div>

  <div class="chart-container">
    <h2 class="chart-title">Market Comparison</h2>
    <table>
      <thead><tr><th></th><th>Market</th><th class="right">YES now</th><th class="right">1wk</th><th class="right">Volume</th><th class="right">Resolves</th></tr></thead>
      <tbody>{rows_html}</tbody>
    </table>
  </div>
  <div class="footer">Data: Polymarket Gamma / CLOB · forward-filled daily closes</div>
</div>
<script>
  const labels={json.dumps(days)};
  const datasets={json.dumps(datasets)}.map(d=>({{label:d.label,data:d.data,borderColor:d.color,
     backgroundColor:'transparent',tension:.3,pointRadius:0,borderWidth:2,spanGaps:true}}));
  new Chart(document.getElementById('chart'),{{type:'line',data:{{labels,datasets}},
    options:{{responsive:true,maintainAspectRatio:false,interaction:{{mode:'index',intersect:false}},
      plugins:{{legend:{{labels:{{color:'#cbd5e1',boxWidth:12,font:{{size:11}}}}}},
        tooltip:{{backgroundColor:'rgba(15,23,42,.95)',callbacks:{{label:c=>c.dataset.label+': '+(c.raw==null?'—':c.raw+'%')}}}}}},
      scales:{{x:{{grid:{{color:'#1e293b'}},ticks:{{color:'#94a3b8',maxTicksLimit:10}}}},
        y:{{min:0,max:100,grid:{{color:'#334155'}},ticks:{{color:'#94a3b8',callback:v=>v+'%'}}}}}}}}}});
  document.getElementById('date').textContent=new Date().toLocaleDateString();
</script></body></html>"""

    with open(output_path, "w") as f:
        f.write(html)
    print(f"Created {output_path}")


def main():
    parser = ArgumentParser(description="Multi-market Polymarket topic report")
    parser.add_argument("--slug", action="append", required=True, help="Event slug (repeatable)")
    parser.add_argument("--title", default="Polymarket Topic Report")
    parser.add_argument("-o", "--output", required=True)
    args = parser.parse_args()

    markets = []
    for slug in args.slug:
        sys.stderr.write(f"Fetching {slug}...\n")
        markets.append(collect(slug))
    markets.sort(key=lambda m: -m["volume"])
    build_report(markets, args.title, args.output)

    # also dump the raw comparison data next to the report
    data_path = args.output.rsplit(".", 1)[0] + "_data.json"
    with open(data_path, "w") as f:
        json.dump([{k: v for k, v in m.items() if k != "curve"} for m in markets], f, indent=2)
    sys.stderr.write(f"Wrote {data_path}\n")


if __name__ == "__main__":
    main()
