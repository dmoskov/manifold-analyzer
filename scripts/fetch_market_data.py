#!/usr/bin/env python3
"""
Fetch all bets and user data for a Manifold Markets market.

Usage:
    python3 fetch_market_data.py --market-id tt0Uy260hp
"""

import json
import sys
import time
from datetime import datetime
from urllib.request import urlopen, Request
from urllib.error import HTTPError
from collections import defaultdict
from argparse import ArgumentParser


BASE_URL = "https://api.manifold.markets/v0"


def fetch_json(url: str) -> dict | list:
    """Fetch JSON from URL with basic error handling."""
    req = Request(url, headers={'User-Agent': 'ManifoldAnalysis/1.0'})
    try:
        with urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode())
    except HTTPError as e:
        print(f"Error fetching {url}: {e}", file=sys.stderr)
        return None


def fetch_all_bets(contract_id: str, limit_per_page: int = 1000) -> list:
    """Fetch all bets for a contract with pagination."""
    all_bets = []
    before = None

    while True:
        url = f"{BASE_URL}/bets?contractId={contract_id}&limit={limit_per_page}"
        if before:
            url += f"&before={before}"

        print(f"Fetching bets... (got {len(all_bets)} so far)", file=sys.stderr)
        bets = fetch_json(url)

        if not bets:
            break

        all_bets.extend(bets)

        if len(bets) < limit_per_page:
            break

        # Use the oldest bet's ID for pagination
        before = bets[-1]['id']
        time.sleep(1.0)  # Be nice to the API - 1 second between pages

    return all_bets


def fetch_user(user_id: str) -> dict:
    """Fetch user details by ID."""
    url = f"{BASE_URL}/user/by-id/{user_id}"
    return fetch_json(url)


def fetch_users_batch(user_ids: set, skip_fetch: bool = True) -> dict:
    """Fetch multiple users and return id->name mapping.

    If skip_fetch=True, just use truncated IDs to avoid hammering API.
    """
    user_map = {}

    if skip_fetch:
        # Just use truncated IDs - avoid API calls
        for uid in user_ids:
            user_map[uid] = {'name': uid[:12], 'username': uid[:12]}
        return user_map

    total = len(user_ids)

    for i, uid in enumerate(user_ids):
        if (i + 1) % 10 == 0:
            print(f"Fetching users... {i+1}/{total}", file=sys.stderr)

        user = fetch_user(uid)
        if user:
            user_map[uid] = {
                'name': user.get('name', 'Unknown'),
                'username': user.get('username', uid),
            }
        else:
            user_map[uid] = {'name': uid[:12], 'username': uid[:12]}

        time.sleep(0.5)  # Much longer delay to be nice

    return user_map


def fetch_market(market_id: str) -> dict:
    """Fetch market details."""
    url = f"{BASE_URL}/market/{market_id}"
    return fetch_json(url)


def process_bets(bets: list, user_map: dict) -> list:
    """Process bets into structured trade records."""
    trades = []

    for bet in bets:
        user_id = bet.get('userId', 'unknown')
        user_info = user_map.get(user_id, {'name': user_id[:8], 'username': user_id[:8]})

        # Convert timestamp
        created_time = bet.get('createdTime', 0)
        dt = datetime.fromtimestamp(created_time / 1000)

        # Handle both regular bets and limit orders
        amount = abs(bet.get('amount', 0))
        outcome = bet.get('outcome', 'YES')

        # Determine action type
        is_redemption = bet.get('isRedemption', False)
        is_sell = amount < 0 or bet.get('isSold', False)

        if is_redemption:
            action = 'redeemed'
        elif bet.get('amount', 0) < 0:
            action = 'sold'
        else:
            action = 'bought'

        trades.append({
            'user': user_info['name'],
            'username': user_info['username'],
            'user_id': user_id,
            'action': action,
            'amount': round(abs(bet.get('amount', 0)), 2),
            'outcome': outcome,
            'prob_before': round(bet.get('probBefore', 0) * 100, 1),
            'prob_after': round(bet.get('probAfter', 0) * 100, 1),
            'date': dt.strftime('%Y-%m-%d'),
            'month': dt.strftime('%b %Y'),
            'timestamp': created_time,
            'is_limit_order': bet.get('limitProb') is not None,
            'is_redemption': is_redemption,
        })

    return sorted(trades, key=lambda x: x['timestamp'])


def aggregate_by_trader(trades: list) -> list:
    """Aggregate trades by trader for leaderboard."""
    traders = defaultdict(lambda: {
        'total_volume': 0,
        'trade_count': 0,
        'buys': 0,
        'sells': 0,
        'yes_volume': 0,
        'no_volume': 0,
        'username': '',
    })

    for t in trades:
        if t['is_redemption']:
            continue

        user = t['user']
        amount = t['amount']

        traders[user]['username'] = t['username']
        traders[user]['total_volume'] += amount
        traders[user]['trade_count'] += 1

        if t['action'] == 'bought':
            traders[user]['buys'] += 1
        else:
            traders[user]['sells'] += 1

        if t['outcome'] == 'YES':
            traders[user]['yes_volume'] += amount
        else:
            traders[user]['no_volume'] += amount

    # Convert to sorted list
    result = []
    for name, data in sorted(traders.items(), key=lambda x: x[1]['total_volume'], reverse=True):
        yes_pct = (data['yes_volume'] / data['total_volume'] * 100) if data['total_volume'] > 0 else 0
        result.append({
            'name': name,
            'username': data['username'],
            'total_volume': round(data['total_volume'], 2),
            'trade_count': data['trade_count'],
            'buys': data['buys'],
            'sells': data['sells'],
            'yes_volume': round(data['yes_volume'], 2),
            'no_volume': round(data['no_volume'], 2),
            'yes_pct': round(yes_pct, 1),
        })

    return result


def aggregate_by_month(trades: list) -> list:
    """Aggregate trades by month for time series."""
    monthly = defaultdict(lambda: {'yes': 0, 'no': 0, 'total': 0, 'count': 0})

    for t in trades:
        if t['is_redemption']:
            continue

        month = t['month']
        monthly[month]['total'] += t['amount']
        monthly[month]['count'] += 1

        if t['outcome'] == 'YES':
            monthly[month]['yes'] += t['amount']
        else:
            monthly[month]['no'] += t['amount']

    # Sort by date
    def month_sort_key(month_str):
        try:
            return datetime.strptime(month_str, '%b %Y')
        except ValueError:
            return datetime.min

    result = []
    for month in sorted(monthly.keys(), key=month_sort_key):
        data = monthly[month]
        result.append({
            'month': month,
            'yes_volume': round(data['yes'], 2),
            'no_volume': round(data['no'], 2),
            'total_volume': round(data['total'], 2),
            'trade_count': data['count'],
        })

    return result


def main():
    parser = ArgumentParser(description='Fetch and analyze Manifold Markets data')
    parser.add_argument('--market-id', '-m', required=True, help='Market ID')
    parser.add_argument('--output', '-o', default='all',
                       choices=['trades', 'traders', 'monthly', 'all', 'json'])
    args = parser.parse_args()

    # Fetch market info
    print(f"Fetching market {args.market_id}...", file=sys.stderr)
    market = fetch_market(args.market_id)

    if not market:
        print("Failed to fetch market", file=sys.stderr)
        sys.exit(1)

    # Fetch all bets
    bets = fetch_all_bets(args.market_id)
    print(f"Fetched {len(bets)} bets", file=sys.stderr)

    if not bets:
        print("No bets found", file=sys.stderr)
        sys.exit(1)

    # Get unique user IDs and fetch user info
    user_ids = set(bet.get('userId') for bet in bets if bet.get('userId'))
    print(f"Fetching {len(user_ids)} unique users...", file=sys.stderr)
    user_map = fetch_users_batch(user_ids)

    # Process bets into trades
    trades = process_bets(bets, user_map)
    traders = aggregate_by_trader(trades)
    monthly = aggregate_by_month(trades)

    # Summary stats
    summary = {
        'market_title': market.get('question', 'Unknown'),
        'market_id': args.market_id,
        'current_probability': round(market.get('probability', 0) * 100, 1),
        'total_trades': len([t for t in trades if not t['is_redemption']]),
        'total_volume': round(sum(t['amount'] for t in trades if not t['is_redemption']), 2),
        'unique_traders': len(traders),
        'date_range': f"{trades[0]['date']} to {trades[-1]['date']}" if trades else 'N/A',
    }

    # Output
    if args.output == 'json' or args.output == 'all':
        output = {
            'summary': summary,
            'traders': traders,
            'monthly': monthly,
            'trades': trades if args.output == 'json' else trades[-100:],  # Last 100 for 'all'
        }
        print(json.dumps(output, indent=2))
    elif args.output == 'trades':
        print(json.dumps(trades, indent=2))
    elif args.output == 'traders':
        print(json.dumps(traders, indent=2))
    elif args.output == 'monthly':
        print(json.dumps(monthly, indent=2))


if __name__ == '__main__':
    main()
