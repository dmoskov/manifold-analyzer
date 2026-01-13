#!/usr/bin/env python3
"""
Parse Manifold Markets trade history from text format.

Input: Trade history text (stdin or file), one trade per line
Output: JSON array of parsed trades with computed dates

Usage:
    python3 parse_trades.py < trades.txt > trades.json
    python3 parse_trades.py trades.txt --reference-date 2025-01-11
"""

import sys
import json
import re
from datetime import datetime, timedelta
from collections import defaultdict
from argparse import ArgumentParser


def parse_time_ago(time_str: str, reference_date: datetime) -> datetime:
    """Convert relative time string to approximate date."""
    time_str = time_str.strip().lower()
    
    # Parse days: "23d", "5d"
    if match := re.match(r'(\d+)d', time_str):
        days = int(match.group(1))
        return reference_date - timedelta(days=days)
    
    # Parse months: "1mo", "3mo", "11mo"
    if match := re.match(r'(\d+)mo?', time_str):
        months = int(match.group(1))
        return reference_date - timedelta(days=months * 30)
    
    # Parse years: "1y", "2y"
    if match := re.match(r'(\d+)y', time_str):
        years = int(match.group(1))
        return reference_date - timedelta(days=years * 365)
    
    # Default to reference date if unparseable
    return reference_date


def parse_trade_line(line: str, reference_date: datetime) -> dict | None:
    """Parse a single trade line into structured data."""
    line = line.strip()
    if not line:
        return None
    
    # Try CSV format: user,action,amount,answer,outcome,time_ago
    parts = line.split(',')
    if len(parts) >= 6:
        user, action, amount, answer, outcome, time_ago = parts[:6]
        try:
            trade_date = parse_time_ago(time_ago, reference_date)
            return {
                'user': user.strip(),
                'action': action.strip().lower(),
                'amount': int(amount.strip()),
                'answer': answer.strip(),
                'outcome': outcome.strip().upper(),
                'time_ago': time_ago.strip(),
                'date': trade_date.strftime('%Y-%m-%d'),
                'month': trade_date.strftime('%b %Y')
            }
        except (ValueError, AttributeError):
            pass
    
    # Try natural language: "JoshYou bought Ṁ350 of >$25B YES"
    pattern = r'(\w+)\s+(bought|sold)\s+[ṀM]?(\d+)\s+(?:of\s+)?(.+?)\s+(YES|NO)'
    if match := re.match(pattern, line, re.IGNORECASE):
        user, action, amount, answer, outcome = match.groups()
        return {
            'user': user,
            'action': action.lower(),
            'amount': int(amount),
            'answer': answer.strip(),
            'outcome': outcome.upper(),
            'time_ago': 'unknown',
            'date': reference_date.strftime('%Y-%m-%d'),
            'month': reference_date.strftime('%b %Y')
        }
    
    return None


def aggregate_by_trader(trades: list) -> list:
    """Aggregate trades by trader for leaderboard."""
    traders = defaultdict(lambda: {
        'total_volume': 0,
        'trade_count': 0,
        'buys': 0,
        'sells': 0,
        'yes_volume': 0,
        'no_volume': 0,
        'answers': defaultdict(float)
    })
    
    for t in trades:
        user = t['user']
        amount = t['amount']
        
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
        
        traders[user]['answers'][t['answer']] += amount
    
    # Convert to sorted list
    result = []
    for name, data in sorted(traders.items(), key=lambda x: x[1]['total_volume'], reverse=True):
        top_answers = sorted(data['answers'].items(), key=lambda x: x[1], reverse=True)[:3]
        result.append({
            'name': name,
            'total_volume': data['total_volume'],
            'trade_count': data['trade_count'],
            'buys': data['buys'],
            'sells': data['sells'],
            'yes_volume': data['yes_volume'],
            'no_volume': data['no_volume'],
            'top_answers': [{'answer': a, 'volume': v} for a, v in top_answers]
        })
    
    return result


def aggregate_by_month(trades: list) -> list:
    """Aggregate trades by month and answer for time series."""
    monthly = defaultdict(lambda: defaultdict(float))
    
    for t in trades:
        monthly[t['month']][t['answer']] += t['amount']
    
    # Sort by date and convert to list
    def month_sort_key(month_str):
        try:
            return datetime.strptime(month_str, '%b %Y')
        except ValueError:
            return datetime.min
    
    result = []
    for month in sorted(monthly.keys(), key=month_sort_key):
        entry = {'month': month}
        entry.update(monthly[month])
        result.append(entry)
    
    return result


def main():
    parser = ArgumentParser(description='Parse Manifold Markets trade history')
    parser.add_argument('input', nargs='?', help='Input file (default: stdin)')
    parser.add_argument('--reference-date', '-r', default=None,
                       help='Reference date for relative timestamps (YYYY-MM-DD)')
    parser.add_argument('--output', '-o', choices=['trades', 'traders', 'monthly', 'all'],
                       default='all', help='Output format')
    args = parser.parse_args()
    
    # Set reference date
    if args.reference_date:
        reference_date = datetime.strptime(args.reference_date, '%Y-%m-%d')
    else:
        reference_date = datetime.now()
    
    # Read input
    if args.input:
        with open(args.input) as f:
            lines = f.readlines()
    else:
        lines = sys.stdin.readlines()
    
    # Parse trades
    trades = []
    for line in lines:
        if trade := parse_trade_line(line, reference_date):
            trades.append(trade)
    
    # Generate output
    if args.output == 'trades':
        output = trades
    elif args.output == 'traders':
        output = aggregate_by_trader(trades)
    elif args.output == 'monthly':
        output = aggregate_by_month(trades)
    else:  # all
        output = {
            'trades': trades,
            'traders': aggregate_by_trader(trades),
            'monthly': aggregate_by_month(trades),
            'summary': {
                'total_trades': len(trades),
                'total_volume': sum(t['amount'] for t in trades),
                'unique_traders': len(set(t['user'] for t in trades)),
                'reference_date': reference_date.strftime('%Y-%m-%d')
            }
        }
    
    print(json.dumps(output, indent=2))


if __name__ == '__main__':
    main()
