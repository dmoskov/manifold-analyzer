#!/usr/bin/env python3
"""
Generate an HTML visualization for Polymarket data produced by fetch_polymarket.py.

Includes:
  - Full YES-probability price curve
  - Volume breakdown across time windows (Gamma aggregates)
  - Positions leaderboard: top YES holders (bulls) vs top NO holders (bears)
  - Recent order-flow summary

Usage:
    python3 generate_poly_viz.py examples/hormuz/hormuz_data.json -o examples/hormuz/hormuz_viz.html
"""

import json
from datetime import datetime, timezone
from argparse import ArgumentParser


def fmt_usd(v):
    v = float(v)
    if abs(v) >= 1_000_000:
        return f"${v/1_000_000:.2f}M"
    if abs(v) >= 1_000:
        return f"${v/1_000:.1f}k"
    return f"${v:.0f}"


def build_html(data, output_path):
    s = data["summary"]
    yes_token = data["tokens"]["yes"]
    no_token = data["tokens"]["no"]

    # --- price curve (YES probability) ---
    curve = [
        {"t": datetime.fromtimestamp(p["t"], tz=timezone.utc).strftime("%Y-%m-%d"),
         "p": round(p["p"] * 100, 1)}
        for p in data["price_history"]
    ]

    # --- volume breakdown across windows ---
    total, mo, wk, day = s["volume_total"], s["volume_1mo"], s["volume_1wk"], s["volume_24hr"]
    vol_windows = [
        {"label": "Opening (>1mo ago)", "value": max(total - mo, 0)},
        {"label": "Mid (1mo → 1wk)", "value": max(mo - wk, 0)},
        {"label": "Past week (1wk → 24h)", "value": max(wk - day, 0)},
        {"label": "Last 24h", "value": day},
    ]

    # --- positions leaderboards ---
    def top(token, n=15):
        rows = sorted(data["holders"].get(token, []), key=lambda h: -h["amount"])[:n]
        return [{"name": (h.get("name") or h.get("pseudonym") or h["proxyWallet"][:10]),
                 "amount": round(h["amount"])} for h in rows]

    yes_holders = top(yes_token)
    no_holders = top(no_token)
    yes_top_sum = sum(h["amount"] for h in yes_holders)
    no_top_sum = sum(h["amount"] for h in no_holders)

    # --- recent flow ---
    flow = data.get("recent_flow", {})
    yes_bull = flow.get("BUY_Yes", 0) + flow.get("SELL_No", 0)
    yes_bear = flow.get("BUY_No", 0) + flow.get("SELL_Yes", 0)
    span = data.get("recent_trades_span", [None, None])

    yes_pct = s["yes_price"] * 100

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{s['title']} - Polymarket Analysis</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
<style>
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{ font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif; min-height:100vh;
         background:linear-gradient(135deg,#0f172a 0%,#1e293b 50%,#0f172a 100%); color:#fff; padding:32px; }}
  .container {{ max-width:1200px; margin:0 auto; }}
  h1 {{ font-size:22px; font-weight:700; margin-bottom:8px; line-height:1.3; }}
  .subtitle {{ color:#64748b; font-size:14px; margin-bottom:24px; }}
  .subtitle a {{ color:#60a5fa; text-decoration:none; }}
  .stats-grid {{ display:grid; grid-template-columns:repeat(5,1fr); gap:16px; margin-bottom:24px; }}
  .stat-card {{ background:rgba(51,65,85,0.3); border-radius:16px; padding:18px; border:1px solid rgba(71,85,105,0.5); }}
  .stat-label {{ font-size:11px; color:#64748b; text-transform:uppercase; margin-bottom:6px; }}
  .stat-value {{ font-size:22px; font-weight:700; }}
  .chart-container {{ background:rgba(51,65,85,0.2); border-radius:20px; padding:24px; margin-bottom:24px; border:1px solid rgba(71,85,105,0.3); }}
  .chart-title {{ font-size:18px; font-weight:600; margin-bottom:18px; }}
  .chart-title span {{ font-size:13px; color:#64748b; font-weight:400; margin-left:10px; }}
  .cols {{ display:grid; grid-template-columns:1fr 1fr; gap:24px; }}
  table {{ width:100%; font-size:13px; border-collapse:collapse; }}
  th {{ text-align:left; padding:8px; color:#64748b; font-weight:500; border-bottom:1px solid rgba(71,85,105,0.5); }}
  th.right, td.right {{ text-align:right; }}
  td {{ padding:8px; border-bottom:1px solid rgba(71,85,105,0.2); }}
  .rank {{ color:#94a3b8; }}
  .name {{ color:#e2e8f0; font-weight:500; }}
  .yes {{ color:#10b981; }}
  .no {{ color:#ef4444; }}
  .mono {{ font-family:monospace; }}
  .flow-bar {{ display:flex; height:36px; border-radius:8px; overflow:hidden; margin:12px 0 6px; }}
  .flow-yes {{ background:#10b981; display:flex; align-items:center; justify-content:center; font-size:12px; font-weight:600; }}
  .flow-no {{ background:#ef4444; display:flex; align-items:center; justify-content:center; font-size:12px; font-weight:600; }}
  .note {{ color:#64748b; font-size:12px; line-height:1.5; }}
  .footer {{ margin-top:28px; text-align:center; color:#64748b; font-size:12px; }}
  @media (max-width:768px) {{ .stats-grid {{ grid-template-columns:repeat(2,1fr); }} .cols {{ grid-template-columns:1fr; }} }}
</style>
</head>
<body>
<div class="container">
  <h1>{s['title']}</h1>
  <p class="subtitle"><a href="https://polymarket.com/event/{s['slug']}" target="_blank">polymarket.com/event/{s['slug']}</a>
     &nbsp;·&nbsp; resolves {s['end_date'][:10] if s.get('end_date') else 'TBD'}</p>

  <div class="stats-grid">
    <div class="stat-card"><div class="stat-label">YES chance</div><div class="stat-value yes">{yes_pct:.0f}%</div></div>
    <div class="stat-card"><div class="stat-label">Total volume</div><div class="stat-value">{fmt_usd(total)}</div></div>
    <div class="stat-card"><div class="stat-label">Open interest</div><div class="stat-value">{fmt_usd(s['open_interest'])}</div></div>
    <div class="stat-card"><div class="stat-label">Liquidity</div><div class="stat-value">{fmt_usd(s['liquidity'])}</div></div>
    <div class="stat-card"><div class="stat-label">Holders shown</div><div class="stat-value">{len(data['holders'].get(yes_token,[]))+len(data['holders'].get(no_token,[]))}</div></div>
  </div>

  <div class="chart-container">
    <h2 class="chart-title">YES Probability <span>(full history)</span></h2>
    <div style="position:relative; height:340px; width:100%;"><canvas id="priceChart"></canvas></div>
  </div>

  <div class="chart-container">
    <h2 class="chart-title">Volume by Period <span>(from Polymarket aggregates)</span></h2>
    <div style="position:relative; height:220px; width:100%;"><canvas id="volChart"></canvas></div>
  </div>

  <div class="chart-container">
    <h2 class="chart-title">Recent Order Flow <span>({span[0]} → {span[1]} UTC · {data['recent_trade_count']} trades)</span></h2>
    <div class="flow-bar">
      <div class="flow-yes" style="width:{(yes_bull/(yes_bull+yes_bear)*100) if (yes_bull+yes_bear) else 50:.0f}%">YES-side {fmt_usd(yes_bull)}</div>
      <div class="flow-no" style="width:{(yes_bear/(yes_bull+yes_bear)*100) if (yes_bull+yes_bear) else 50:.0f}%">NO-side {fmt_usd(yes_bear)}</div>
    </div>
    <p class="note">YES-side = buys of YES + sells of NO. NO-side = buys of NO + sells of YES.</p>
  </div>

  <div class="chart-container">
    <h2 class="chart-title">Positions Leaderboard <span>(current top holders per outcome)</span></h2>
    <div class="cols">
      <div>
        <table>
          <thead><tr><th>#</th><th>YES holder (bull)</th><th class="right">Shares</th></tr></thead>
          <tbody id="yesT"></tbody>
        </table>
        <p class="note" style="margin-top:8px">Top {len(yes_holders)} YES holders: {fmt_usd(yes_top_sum)} shares</p>
      </div>
      <div>
        <table>
          <thead><tr><th>#</th><th>NO holder (bear)</th><th class="right">Shares</th></tr></thead>
          <tbody id="noT"></tbody>
        </table>
        <p class="note" style="margin-top:8px">Top {len(no_holders)} NO holders: {fmt_usd(no_top_sum)} shares</p>
      </div>
    </div>
  </div>

  <div class="footer">Data: Polymarket Gamma / CLOB / data-api · Generated <span id="date"></span></div>
</div>

<script>
  const curve = {json.dumps(curve)};
  const vols = {json.dumps(vol_windows)};
  const yesH = {json.dumps(yes_holders)};
  const noH = {json.dumps(no_holders)};
  const fmt = v => Math.abs(v)>=1e6 ? '$'+(v/1e6).toFixed(2)+'M' : Math.abs(v)>=1e3 ? '$'+(v/1e3).toFixed(1)+'k' : '$'+Math.round(v);
  const fmtShares = v => v>=1e6 ? (v/1e6).toFixed(2)+'M' : v>=1e3 ? (v/1e3).toFixed(1)+'k' : Math.round(v);

  new Chart(document.getElementById('priceChart'), {{
    type:'line',
    data:{{ labels:curve.map(d=>d.t), datasets:[{{ label:'YES %', data:curve.map(d=>d.p),
            borderColor:'#60a5fa', backgroundColor:'rgba(96,165,250,0.15)', fill:true, tension:0.3, pointRadius:0, borderWidth:2 }}]}},
    options:{{ responsive:true, maintainAspectRatio:false, interaction:{{mode:'index',intersect:false}},
      plugins:{{ legend:{{display:false}}, tooltip:{{ backgroundColor:'rgba(15,23,42,0.95)', callbacks:{{ label:c=>'YES: '+c.raw+'%' }} }} }},
      scales:{{ x:{{ grid:{{color:'#1e293b'}}, ticks:{{color:'#94a3b8', maxTicksLimit:10}} }},
                y:{{ min:0, max:100, grid:{{color:'#334155'}}, ticks:{{color:'#94a3b8', callback:v=>v+'%'}} }} }} }}
  }});

  new Chart(document.getElementById('volChart'), {{
    type:'bar',
    data:{{ labels:vols.map(d=>d.label), datasets:[{{ data:vols.map(d=>d.value),
            backgroundColor:['#475569','#3b82f6','#60a5fa','#93c5fd'] }}]}},
    options:{{ responsive:true, maintainAspectRatio:false, indexAxis:'y',
      plugins:{{ legend:{{display:false}}, tooltip:{{ callbacks:{{ label:c=>fmt(c.raw) }} }} }},
      scales:{{ x:{{ grid:{{color:'#334155'}}, ticks:{{color:'#94a3b8', callback:v=>fmt(v)}} }},
                y:{{ grid:{{display:false}}, ticks:{{color:'#94a3b8'}} }} }} }}
  }});

  const yesT=document.getElementById('yesT'), noT=document.getElementById('noT');
  yesH.forEach((h,i)=>{{ yesT.innerHTML+=`<tr><td class="rank">${{i+1}}</td><td class="name">${{h.name}}</td><td class="right mono yes">${{fmtShares(h.amount)}}</td></tr>`; }});
  noH.forEach((h,i)=>{{ noT.innerHTML+=`<tr><td class="rank">${{i+1}}</td><td class="name">${{h.name}}</td><td class="right mono no">${{fmtShares(h.amount)}}</td></tr>`; }});
  document.getElementById('date').textContent=new Date().toLocaleDateString();
</script>
</body>
</html>"""

    with open(output_path, "w") as f:
        f.write(html)
    print(f"Created {output_path}")


def main():
    parser = ArgumentParser(description="Generate Polymarket HTML visualization")
    parser.add_argument("data", help="JSON file from fetch_polymarket.py")
    parser.add_argument("-o", "--output", required=True, help="Output HTML file")
    args = parser.parse_args()
    with open(args.data) as f:
        data = json.load(f)
    build_html(data, args.output)


if __name__ == "__main__":
    main()
