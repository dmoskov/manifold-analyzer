#!/usr/bin/env python3
"""
Generate enhanced HTML visualization for Manifold Markets data.

Includes:
- Cumulative volume chart
- Trader leaderboard with P&L estimates
- Market movers analysis
- Trader classification badges

Usage:
    python3 generate_viz.py market_data.json usernames.json -o output.html
"""

import json
from collections import defaultdict
from datetime import datetime
from argparse import ArgumentParser


def load_json(filepath):
    with open(filepath) as f:
        return json.load(f)


def estimate_pnl(trades, current_prob):
    """Estimate P&L for each trader."""
    trader_positions = defaultdict(lambda: {
        'yes_shares': 0, 'no_shares': 0,
        'yes_cost': 0, 'no_cost': 0
    })

    for t in trades:
        if t.get('is_redemption'):
            continue
        user = t['user']
        amount = t['amount']
        prob = t['prob_before'] / 100

        if t['outcome'] == 'YES':
            shares = amount / prob if prob > 0 else 0
            trader_positions[user]['yes_shares'] += shares
            trader_positions[user]['yes_cost'] += amount
        else:
            shares = amount / (1 - prob) if prob < 1 else 0
            trader_positions[user]['no_shares'] += shares
            trader_positions[user]['no_cost'] += amount

    results = {}
    for user, pos in trader_positions.items():
        yes_value = pos['yes_shares'] * current_prob
        no_value = pos['no_shares'] * (1 - current_prob)
        total_cost = pos['yes_cost'] + pos['no_cost']
        total_pnl = (yes_value - pos['yes_cost']) + (no_value - pos['no_cost'])
        roi = (total_pnl / total_cost * 100) if total_cost > 0 else 0

        results[user] = {
            'pnl': round(total_pnl, 0),
            'roi': round(roi, 1),
            'cost': round(total_cost, 0)
        }
    return results


def analyze_market_impact(trades):
    """Calculate price impact per trader."""
    impact = defaultdict(lambda: {'total': 0, 'biggest': 0})
    for t in trades:
        if t.get('is_redemption'):
            continue
        move = abs(t['prob_after'] - t['prob_before'])
        impact[t['user']]['total'] += move
        impact[t['user']]['biggest'] = max(impact[t['user']]['biggest'], move)
    return {u: {'total': round(d['total'], 1), 'biggest': round(d['biggest'], 1)}
            for u, d in impact.items()}


def classify_trader(volume, trades, yes_pct, roi, whale_threshold):
    """Return list of trader type badges."""
    types = []
    if volume >= whale_threshold:
        types.append('WHALE')
    if trades >= 15:
        types.append('ACTIVE')
    if yes_pct >= 80:
        types.append('BULL')
    elif yes_pct <= 20:
        types.append('BEAR')
    if roi > 50:
        types.append('WINNER')
    elif roi < -30:
        types.append('LOSER')
    return types if types else ['RETAIL']


def fmt_vol(v):
    if v >= 1000000:
        return f"Ṁ{v/1000000:.2f}M"
    if v >= 1000:
        return f"Ṁ{v/1000:.1f}k"
    return f"Ṁ{v:.0f}"


def generate_html(data, users, output_path, url_slug=None):
    """Generate the HTML visualization."""
    trades = data['trades']
    s = data['summary']
    current_prob = s.get('current_probability', 50) / 100

    # Calculate cumulative monthly data
    monthly = defaultdict(lambda: {'yes': 0, 'no': 0})
    for t in trades:
        if t.get('is_redemption'):
            continue
        month = t['month']
        if t['outcome'] == 'YES':
            monthly[month]['yes'] += t['amount']
        else:
            monthly[month]['no'] += t['amount']

    def month_sort_key(m):
        try:
            return datetime.strptime(m, '%b %Y')
        except:
            return datetime.min

    months = sorted(monthly.keys(), key=month_sort_key)
    cumulative = []
    yes_cum, no_cum = 0, 0
    for m in months:
        yes_cum += monthly[m]['yes']
        no_cum += monthly[m]['no']
        cumulative.append({'month': m, 'YES': round(yes_cum), 'NO': round(no_cum)})

    # Run analyses
    pnl_data = estimate_pnl(trades, current_prob)
    impact_data = analyze_market_impact(trades)

    # Build trader list
    volumes = [t['total_volume'] for t in data['traders']]
    whale_threshold = sorted(volumes, reverse=True)[min(9, len(volumes)-1)] if volumes else 0

    traders_enhanced = []
    for t in data['traders'][:25]:
        u = users.get(t['username'], {})
        username = u.get('username', t['username'][:12])
        pnl = pnl_data.get(t['username'], {'pnl': 0, 'roi': 0, 'cost': 0})
        impact = impact_data.get(t['username'], {'total': 0, 'biggest': 0})

        types = classify_trader(
            t['total_volume'], t['trade_count'], t['yes_pct'],
            pnl['roi'], whale_threshold
        )

        traders_enhanced.append({
            'name': f"@{username}",
            'volume': round(t['total_volume']),
            'trades': t['trade_count'],
            'yesPct': round(t['yes_pct'], 1),
            'yes': round(t['yes_volume']),
            'no': round(t['no_volume']),
            'pnl': pnl['pnl'],
            'roi': pnl['roi'],
            'impact': impact['total'],
            'types': types
        })

    total_yes = round(sum(t['yes_volume'] for t in data['traders']))
    total_no = round(sum(t['no_volume'] for t in data['traders']))
    yes_pct = round(total_yes / (total_yes + total_no) * 100, 1) if (total_yes + total_no) > 0 else 0

    title = s['market_title']
    if not url_slug:
        url_slug = "market"

    # Generate HTML
    html = f'''<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title} - Analysis</title>
  <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
  <style>
    * {{ margin: 0; padding: 0; box-sizing: border-box; }}
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; min-height: 100vh; background: linear-gradient(135deg, #0f172a 0%, #1e293b 50%, #0f172a 100%); color: white; padding: 32px; }}
    .container {{ max-width: 1200px; margin: 0 auto; }}
    h1 {{ font-size: 22px; font-weight: 700; margin-bottom: 8px; line-height: 1.3; }}
    .subtitle {{ color: #64748b; font-size: 14px; margin-bottom: 32px; }}
    .subtitle a {{ color: #60a5fa; text-decoration: none; }}
    .stats-grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; margin-bottom: 32px; }}
    .stat-card {{ background: rgba(51, 65, 85, 0.3); border-radius: 16px; padding: 20px; border: 1px solid rgba(71, 85, 105, 0.5); }}
    .stat-label {{ display: flex; align-items: center; gap: 8px; margin-bottom: 8px; font-size: 12px; color: #64748b; text-transform: uppercase; }}
    .stat-value {{ font-size: 24px; font-weight: 700; }}
    .chart-container {{ background: rgba(51, 65, 85, 0.2); border-radius: 20px; padding: 24px; margin-bottom: 32px; border: 1px solid rgba(71, 85, 105, 0.3); }}
    .chart-title {{ font-size: 20px; font-weight: 600; margin-bottom: 24px; }}
    .chart-title span {{ font-size: 14px; color: #64748b; font-weight: 400; margin-left: 12px; }}
    .legend {{ display: flex; justify-content: center; gap: 32px; margin-top: 16px; flex-wrap: wrap; }}
    .legend-item {{ display: flex; align-items: center; gap: 8px; }}
    .legend-dot {{ width: 12px; height: 12px; border-radius: 50%; }}
    table {{ width: 100%; font-size: 13px; border-collapse: collapse; }}
    th {{ text-align: left; padding: 10px 8px; color: #64748b; font-weight: 500; border-bottom: 1px solid rgba(71, 85, 105, 0.5); }}
    th.right {{ text-align: right; }}
    th.center {{ text-align: center; }}
    td {{ padding: 10px 8px; border-bottom: 1px solid rgba(71, 85, 105, 0.2); }}
    td.right {{ text-align: right; }}
    td.center {{ text-align: center; }}
    .rank {{ color: #94a3b8; }}
    .rank.gold {{ color: #fbbf24; font-weight: 600; }}
    .trader-name {{ color: #e2e8f0; font-weight: 500; }}
    .volume {{ font-family: monospace; color: #fbbf24; }}
    .yes-vol {{ font-family: monospace; color: #10b981; }}
    .no-vol {{ font-family: monospace; color: #ef4444; }}
    .pnl-pos {{ font-family: monospace; color: #10b981; }}
    .pnl-neg {{ font-family: monospace; color: #ef4444; }}
    .badge {{ display: inline-block; padding: 2px 8px; border-radius: 12px; font-size: 10px; font-weight: 600; margin-right: 4px; }}
    .badge.whale {{ background: rgba(251, 191, 36, 0.2); color: #fbbf24; }}
    .badge.bull {{ background: rgba(16, 185, 129, 0.2); color: #10b981; }}
    .badge.bear {{ background: rgba(239, 68, 68, 0.2); color: #ef4444; }}
    .badge.active {{ background: rgba(96, 165, 250, 0.2); color: #60a5fa; }}
    .badge.winner {{ background: rgba(34, 197, 94, 0.2); color: #22c55e; }}
    .badge.loser {{ background: rgba(239, 68, 68, 0.2); color: #ef4444; }}
    .badge.retail {{ background: rgba(148, 163, 184, 0.2); color: #94a3b8; }}
    .footer {{ margin-top: 32px; text-align: center; color: #64748b; font-size: 12px; }}
    @media (max-width: 768px) {{ .stats-grid {{ grid-template-columns: repeat(2, 1fr); }} }}
  </style>
</head>
<body>
  <div class="container">
    <h1>{title}</h1>
    <p class="subtitle"><a href="https://manifold.markets/{url_slug}" target="_blank">manifold.markets/{url_slug}</a></p>
    <div class="stats-grid">
      <div class="stat-card"><div class="stat-label"><span>🎯</span> Probability</div><div class="stat-value">{s["current_probability"]:.0f}%</div></div>
      <div class="stat-card"><div class="stat-label"><span>📊</span> Volume</div><div class="stat-value">{fmt_vol(s["total_volume"])}</div></div>
      <div class="stat-card"><div class="stat-label"><span>🔄</span> Trades</div><div class="stat-value">{s["total_trades"]:,}</div></div>
      <div class="stat-card"><div class="stat-label"><span>👥</span> Traders</div><div class="stat-value">{s["unique_traders"]:,}</div></div>
    </div>
    <div class="chart-container">
      <h2 class="chart-title">Cumulative Volume Over Time <span>(Stacked by Position)</span></h2>
      <div style="position: relative; height: 350px; width: 100%;"><canvas id="volumeChart"></canvas></div>
      <div class="legend">
        <div class="legend-item"><div class="legend-dot" style="background: #10b981;"></div><span style="color:#94a3b8">YES</span><span class="yes-vol">{fmt_vol(total_yes)} ({yes_pct}%)</span></div>
        <div class="legend-item"><div class="legend-dot" style="background: #ef4444;"></div><span style="color:#94a3b8">NO</span><span class="no-vol">{fmt_vol(total_no)} ({100-yes_pct:.1f}%)</span></div>
      </div>
    </div>
    <div class="chart-container">
      <h2 class="chart-title">Trader Leaderboard <span>(with estimated P&L)</span></h2>
      <table>
        <thead><tr>
          <th>#</th><th>Trader</th><th>Types</th>
          <th class="right">Volume</th><th class="right">Trades</th>
          <th class="right">YES</th><th class="right">NO</th>
          <th class="right">Est. P&L</th><th class="right">ROI</th>
          <th class="right">Impact</th>
        </tr></thead>
        <tbody id="traderTable"></tbody>
      </table>
    </div>
    <div class="footer">Data from Manifold Markets API • Enhanced analysis • Generated <span id="date"></span></div>
  </div>
  <script>
    const dailyData = {json.dumps(cumulative)};
    const traders = {json.dumps(traders_enhanced)};
    function fmt(v) {{ if (v >= 1000000) return `Ṁ${{(v/1000000).toFixed(2)}}M`; if (v >= 1000) return `Ṁ${{(v/1000).toFixed(1)}}k`; return `Ṁ${{Math.round(v)}}`; }}
    const ctx = document.getElementById('volumeChart').getContext('2d');
    new Chart(ctx, {{
      type: 'line',
      data: {{ labels: dailyData.map(d => d.month), datasets: [
        {{ label: 'YES', data: dailyData.map(d => d.YES), borderColor: '#10b981', backgroundColor: 'rgba(16,185,129,0.3)', fill: true, tension: 0.4, pointRadius: 3, order: 2 }},
        {{ label: 'NO', data: dailyData.map(d => d.NO), borderColor: '#ef4444', backgroundColor: 'rgba(239,68,68,0.3)', fill: true, tension: 0.4, pointRadius: 3, order: 1 }}
      ]}},
      options: {{ responsive: true, maintainAspectRatio: false, interaction: {{ mode: 'index', intersect: false }},
        plugins: {{ legend: {{ display: false }}, tooltip: {{ backgroundColor: 'rgba(15,23,42,0.95)', callbacks: {{ label: ctx => `${{ctx.dataset.label}}: ${{fmt(ctx.raw)}}`, footer: items => `Total: ${{fmt(items.reduce((s,i) => s+i.raw, 0))}}` }} }} }},
        scales: {{ x: {{ grid: {{ color: '#334155' }}, ticks: {{ color: '#94a3b8' }} }}, y: {{ stacked: true, grid: {{ color: '#334155' }}, ticks: {{ color: '#94a3b8', callback: v => fmt(v) }} }} }}
      }}
    }});
    const tb = document.getElementById('traderTable');
    traders.forEach((t, i) => {{
      const badges = t.types.map(type => `<span class="badge ${{type.toLowerCase()}}">${{type}}</span>`).join('');
      const pnlClass = t.pnl >= 0 ? 'pnl-pos' : 'pnl-neg';
      const pnlSign = t.pnl >= 0 ? '+' : '';
      tb.innerHTML += `<tr>
        <td class="${{i<3?'rank gold':'rank'}}">${{i===0?'🥇':i===1?'🥈':i===2?'🥉':i+1}}</td>
        <td class="trader-name">${{t.name}}</td>
        <td>${{badges}}</td>
        <td class="right volume">${{fmt(t.volume)}}</td>
        <td class="right" style="color:#94a3b8">${{t.trades}}</td>
        <td class="right yes-vol">${{fmt(t.yes)}}</td>
        <td class="right no-vol">${{fmt(t.no)}}</td>
        <td class="right ${{pnlClass}}">${{pnlSign}}${{fmt(Math.abs(t.pnl))}}</td>
        <td class="right ${{pnlClass}}">${{pnlSign}}${{t.roi.toFixed(0)}}%</td>
        <td class="right" style="color:#94a3b8">${{t.impact.toFixed(1)}}%</td>
      </tr>`;
    }});
    document.getElementById('date').textContent = new Date().toLocaleDateString();
  </script>
</body>
</html>'''

    with open(output_path, 'w') as f:
        f.write(html)
    print(f"Created {output_path}")


def main():
    parser = ArgumentParser(description='Generate enhanced Manifold visualization')
    parser.add_argument('data', help='Market data JSON file')
    parser.add_argument('usernames', help='Resolved usernames JSON file')
    parser.add_argument('-o', '--output', required=True, help='Output HTML file')
    parser.add_argument('--url', help='URL slug for market link')
    args = parser.parse_args()

    data = load_json(args.data)
    users = load_json(args.usernames)
    generate_html(data, users, args.output, args.url)


if __name__ == '__main__':
    main()
