#!/usr/bin/env python3
"""
Deep trader analysis for Manifold Markets data.

Analyzes:
- Estimated P&L based on entry prices vs current probability
- Timing patterns (early vs late, buying dips)
- Position changes over time
- Market impact (price movement caused)
- Trader classification (whale, retail, flipper, etc.)

Usage:
    python3 analyze_traders.py market_data.json [--current-prob 0.95]
"""

import json
import sys
from collections import defaultdict
from datetime import datetime
from argparse import ArgumentParser


def load_data(filepath):
    with open(filepath) as f:
        return json.load(f)


def estimate_pnl(trades, current_prob):
    """
    Estimate P&L for each trader based on their positions.

    For YES shares: profit if prob goes up, loss if down
    For NO shares: profit if prob goes down, loss if up

    Simplified model: assumes shares bought at probBefore price
    """
    trader_positions = defaultdict(lambda: {
        'yes_shares': 0,
        'no_shares': 0,
        'yes_cost': 0,
        'no_cost': 0,
        'trades': []
    })

    for t in trades:
        if t.get('is_redemption'):
            continue

        user = t['user']
        amount = t['amount']
        prob = t['prob_before'] / 100  # Convert to decimal

        # Approximate shares purchased (simplified AMM model)
        # In reality Manifold uses a more complex CPMM
        if t['outcome'] == 'YES':
            shares = amount / prob if prob > 0 else 0
            trader_positions[user]['yes_shares'] += shares
            trader_positions[user]['yes_cost'] += amount
        else:
            shares = amount / (1 - prob) if prob < 1 else 0
            trader_positions[user]['no_shares'] += shares
            trader_positions[user]['no_cost'] += amount

        trader_positions[user]['trades'].append(t)

    # Calculate estimated P&L
    results = []
    for user, pos in trader_positions.items():
        # YES shares worth: shares * current_prob
        yes_value = pos['yes_shares'] * current_prob
        yes_pnl = yes_value - pos['yes_cost']

        # NO shares worth: shares * (1 - current_prob)
        no_value = pos['no_shares'] * (1 - current_prob)
        no_pnl = no_value - pos['no_cost']

        total_pnl = yes_pnl + no_pnl
        total_cost = pos['yes_cost'] + pos['no_cost']
        roi = (total_pnl / total_cost * 100) if total_cost > 0 else 0

        results.append({
            'user': user,
            'yes_cost': round(pos['yes_cost'], 2),
            'no_cost': round(pos['no_cost'], 2),
            'total_cost': round(total_cost, 2),
            'yes_value': round(yes_value, 2),
            'no_value': round(no_value, 2),
            'estimated_pnl': round(total_pnl, 2),
            'roi_pct': round(roi, 1),
            'trade_count': len(pos['trades']),
            'position': 'LONG' if pos['yes_cost'] > pos['no_cost'] else 'SHORT'
        })

    return sorted(results, key=lambda x: x['estimated_pnl'], reverse=True)


def analyze_timing(trades):
    """Analyze when traders entered the market."""
    if not trades:
        return {}

    # Sort by timestamp
    sorted_trades = sorted(trades, key=lambda x: x['timestamp'])
    total_trades = len(sorted_trades)

    # Divide into quartiles
    q1_cutoff = total_trades // 4
    q2_cutoff = total_trades // 2
    q3_cutoff = (total_trades * 3) // 4

    trader_timing = defaultdict(lambda: {
        'first_trade_idx': float('inf'),
        'last_trade_idx': 0,
        'early_trades': 0,  # Q1
        'mid_trades': 0,    # Q2-Q3
        'late_trades': 0,   # Q4
        'total': 0
    })

    for idx, t in enumerate(sorted_trades):
        if t.get('is_redemption'):
            continue
        user = t['user']
        trader_timing[user]['total'] += 1
        trader_timing[user]['first_trade_idx'] = min(trader_timing[user]['first_trade_idx'], idx)
        trader_timing[user]['last_trade_idx'] = max(trader_timing[user]['last_trade_idx'], idx)

        if idx < q1_cutoff:
            trader_timing[user]['early_trades'] += 1
        elif idx < q3_cutoff:
            trader_timing[user]['mid_trades'] += 1
        else:
            trader_timing[user]['late_trades'] += 1

    results = []
    for user, data in trader_timing.items():
        timing_type = 'EARLY' if data['early_trades'] > data['late_trades'] else (
            'LATE' if data['late_trades'] > data['early_trades'] else 'SPREAD'
        )
        results.append({
            'user': user,
            'timing_type': timing_type,
            'first_trade_pct': round(data['first_trade_idx'] / total_trades * 100, 1),
            'early_trades': data['early_trades'],
            'mid_trades': data['mid_trades'],
            'late_trades': data['late_trades'],
        })

    return results


def analyze_position_changes(trades):
    """Track if traders flipped their positions over time."""
    trader_history = defaultdict(list)

    for t in sorted(trades, key=lambda x: x['timestamp']):
        if t.get('is_redemption'):
            continue
        trader_history[t['user']].append({
            'outcome': t['outcome'],
            'amount': t['amount'],
            'date': t['date'],
            'prob': t['prob_before']
        })

    results = []
    for user, history in trader_history.items():
        if len(history) < 2:
            continue

        # Check for position flips
        flips = 0
        last_direction = history[0]['outcome']
        for trade in history[1:]:
            if trade['outcome'] != last_direction:
                flips += 1
                last_direction = trade['outcome']

        # Calculate average entry price
        yes_volume = sum(t['amount'] for t in history if t['outcome'] == 'YES')
        no_volume = sum(t['amount'] for t in history if t['outcome'] == 'NO')

        if yes_volume > 0:
            avg_yes_entry = sum(t['prob'] * t['amount'] for t in history if t['outcome'] == 'YES') / yes_volume
        else:
            avg_yes_entry = 0

        if no_volume > 0:
            avg_no_entry = sum(t['prob'] * t['amount'] for t in history if t['outcome'] == 'NO') / no_volume
        else:
            avg_no_entry = 0

        results.append({
            'user': user,
            'trade_count': len(history),
            'flips': flips,
            'is_flipper': flips >= 2,
            'avg_yes_entry_prob': round(avg_yes_entry, 1),
            'avg_no_entry_prob': round(avg_no_entry, 1),
            'first_position': history[0]['outcome'],
            'final_position': history[-1]['outcome'],
        })

    return sorted(results, key=lambda x: x['flips'], reverse=True)


def analyze_market_impact(trades):
    """Analyze how much each trader moved the market."""
    trader_impact = defaultdict(lambda: {
        'total_price_impact': 0,
        'trades': 0,
        'biggest_move': 0
    })

    for t in trades:
        if t.get('is_redemption'):
            continue

        impact = abs(t['prob_after'] - t['prob_before'])
        user = t['user']

        trader_impact[user]['total_price_impact'] += impact
        trader_impact[user]['trades'] += 1
        trader_impact[user]['biggest_move'] = max(trader_impact[user]['biggest_move'], impact)

    results = []
    for user, data in trader_impact.items():
        avg_impact = data['total_price_impact'] / data['trades'] if data['trades'] > 0 else 0
        results.append({
            'user': user,
            'total_impact_pct': round(data['total_price_impact'], 2),
            'avg_impact_pct': round(avg_impact, 2),
            'biggest_move_pct': round(data['biggest_move'], 2),
            'trade_count': data['trades']
        })

    return sorted(results, key=lambda x: x['total_impact_pct'], reverse=True)


def classify_traders(trades, pnl_data):
    """Classify traders into categories."""
    # Build lookup
    pnl_lookup = {p['user']: p for p in pnl_data}

    trader_stats = defaultdict(lambda: {
        'volume': 0,
        'trades': 0,
        'yes_pct': 0
    })

    for t in trades:
        if t.get('is_redemption'):
            continue
        user = t['user']
        trader_stats[user]['volume'] += t['amount']
        trader_stats[user]['trades'] += 1

    # Calculate yes percentage
    for user in trader_stats:
        pnl = pnl_lookup.get(user, {})
        yes_cost = pnl.get('yes_cost', 0)
        total = pnl.get('total_cost', 1)
        trader_stats[user]['yes_pct'] = (yes_cost / total * 100) if total > 0 else 50

    # Classify
    volumes = [s['volume'] for s in trader_stats.values()]
    whale_threshold = sorted(volumes, reverse=True)[min(10, len(volumes)-1)] if volumes else 0

    results = []
    for user, stats in trader_stats.items():
        pnl = pnl_lookup.get(user, {})

        # Determine type
        types = []
        if stats['volume'] >= whale_threshold:
            types.append('WHALE')
        if stats['trades'] >= 20:
            types.append('ACTIVE')
        if stats['yes_pct'] >= 80:
            types.append('BULL')
        elif stats['yes_pct'] <= 20:
            types.append('BEAR')
        if pnl.get('roi_pct', 0) > 50:
            types.append('WINNER')
        elif pnl.get('roi_pct', 0) < -30:
            types.append('LOSER')

        if not types:
            types.append('RETAIL')

        results.append({
            'user': user,
            'types': types,
            'volume': round(stats['volume'], 2),
            'trades': stats['trades'],
            'yes_pct': round(stats['yes_pct'], 1),
            'estimated_pnl': pnl.get('estimated_pnl', 0),
            'roi_pct': pnl.get('roi_pct', 0)
        })

    return sorted(results, key=lambda x: x['volume'], reverse=True)


def main():
    parser = ArgumentParser(description='Deep trader analysis')
    parser.add_argument('input', help='Market data JSON file')
    parser.add_argument('--current-prob', '-p', type=float, default=None,
                       help='Current probability (0-1). If not set, uses last trade prob.')
    parser.add_argument('--output', '-o', choices=['all', 'pnl', 'timing', 'impact', 'classify'],
                       default='all')
    parser.add_argument('--top', '-n', type=int, default=20, help='Show top N traders')
    args = parser.parse_args()

    data = load_data(args.input)
    trades = data['trades']

    # Get current probability
    if args.current_prob is not None:
        current_prob = args.current_prob
    else:
        current_prob = data['summary'].get('current_probability', 50) / 100

    print(f"Market: {data['summary']['market_title']}", file=sys.stderr)
    print(f"Current probability: {current_prob*100:.1f}%", file=sys.stderr)
    print(f"Analyzing {len(trades)} trades...", file=sys.stderr)
    print(file=sys.stderr)

    # Run analyses
    pnl = estimate_pnl(trades, current_prob)
    timing = analyze_timing(trades)
    impact = analyze_market_impact(trades)
    positions = analyze_position_changes(trades)
    classifications = classify_traders(trades, pnl)

    if args.output == 'all':
        output = {
            'summary': {
                'market': data['summary']['market_title'],
                'current_prob': current_prob,
                'total_traders': len(pnl),
                'total_trades': len([t for t in trades if not t.get('is_redemption')])
            },
            'pnl_leaderboard': pnl[:args.top],
            'biggest_losers': sorted(pnl, key=lambda x: x['estimated_pnl'])[:args.top],
            'market_movers': impact[:args.top],
            'position_flippers': [p for p in positions if p['is_flipper']][:args.top],
            'trader_classifications': classifications[:args.top]
        }
    elif args.output == 'pnl':
        output = pnl[:args.top]
    elif args.output == 'timing':
        output = timing[:args.top]
    elif args.output == 'impact':
        output = impact[:args.top]
    elif args.output == 'classify':
        output = classifications[:args.top]

    print(json.dumps(output, indent=2))


if __name__ == '__main__':
    main()
