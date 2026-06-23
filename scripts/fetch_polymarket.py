#!/usr/bin/env python3
"""
Fetch market data for a Polymarket event.

Polymarket's public APIs (no auth required):
  - Gamma API        market/event metadata + aggregate volume windows
  - CLOB prices-history   full price (probability) curve
  - data-api /holders     current top holders per outcome token (positions)
  - data-api /trades      recent trades (offset-capped ~3500, ~last days on busy markets)

Note: there is no public endpoint for the *full* trade-by-trade history of a
busy market (the trades endpoint caps pagination and the on-chain subgraph is
stale), so daily volume is reconstructed from recent trades + Gamma's windowed
aggregates rather than every fill.

Usage:
    python3 fetch_polymarket.py --slug strait-of-hormuz-traffic-returns-to-normal-by-july-31 -o hormuz.json
    python3 fetch_polymarket.py --url https://polymarket.com/event/<slug> -o out.json
"""

import json
import sys
import time
from datetime import datetime, timezone
from collections import defaultdict
from urllib.parse import urlparse
from urllib.request import urlopen, Request
from urllib.error import HTTPError
from argparse import ArgumentParser

GAMMA = "https://gamma-api.polymarket.com"
CLOB = "https://clob.polymarket.com"
DATA = "https://data-api.polymarket.com"


def fetch_json(url, method="GET", body=None):
    headers = {"User-Agent": "PolymarketAnalysis/1.0", "Accept": "application/json"}
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    req = Request(url, data=data, headers=headers, method=method)
    with urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode())


def slug_from_url(url):
    path = urlparse(url).path.strip("/").split("/")
    return path[-1] if path else url


def fetch_event(slug):
    events = fetch_json(f"{GAMMA}/events?slug={slug}")
    if not events:
        raise SystemExit(f"No Polymarket event found for slug: {slug}")
    return events[0]


def fetch_price_history(token_id, fidelity=60):
    url = f"{CLOB}/prices-history?market={token_id}&interval=all&fidelity={fidelity}"
    return fetch_json(url).get("history", [])


def fetch_holders(condition_id, limit=100):
    """Top holders per outcome token. Returns {token_id: [holder, ...]}."""
    data = fetch_json(f"{DATA}/holders?market={condition_id}&limit={limit}")
    return {entry["token"]: entry["holders"] for entry in data}


def fetch_recent_trades(condition_id, max_offset=3000, page=500):
    """Recent taker trades (newest first). Offset-capped by the API."""
    trades = []
    for off in range(0, max_offset + 1, page):
        url = f"{DATA}/trades?market={condition_id}&limit={page}&offset={off}"
        try:
            batch = fetch_json(url)
        except HTTPError:
            break  # hit the offset cap
        if not batch:
            break
        trades.extend(batch)
        if len(batch) < page:
            break
        time.sleep(0.1)
    return trades


def build(slug):
    event = fetch_event(slug)
    market = event["markets"][0]
    outcomes = json.loads(market["outcomes"])           # ["Yes", "No"]
    prices = [float(p) for p in json.loads(market["outcomePrices"])]
    token_ids = json.loads(market["clobTokenIds"])      # [yes_token, no_token]
    yes_token, no_token = token_ids[0], token_ids[1]
    condition_id = market["conditionId"]

    sys.stderr.write("Fetching price history...\n")
    price_history = fetch_price_history(yes_token)

    sys.stderr.write("Fetching holders...\n")
    holders = fetch_holders(condition_id)

    sys.stderr.write("Fetching recent trades...\n")
    trades = fetch_recent_trades(condition_id)

    # Recent daily volume + flow from the trades we can see
    daily = defaultdict(lambda: {"notional": 0.0, "count": 0})
    flow = defaultdict(float)
    per_wallet = defaultdict(lambda: {"name": "", "notional": 0.0, "trades": 0})
    for t in trades:
        notional = float(t["size"]) * float(t["price"])
        day = datetime.fromtimestamp(t["timestamp"], tz=timezone.utc).strftime("%Y-%m-%d")
        daily[day]["notional"] += notional
        daily[day]["count"] += 1
        flow[f'{t["side"]}_{t["outcome"]}'] += notional
        w = per_wallet[t["proxyWallet"]]
        w["name"] = t.get("name") or t.get("pseudonym") or t["proxyWallet"][:10]
        w["notional"] += notional
        w["trades"] += 1

    return {
        "summary": {
            "title": event["title"],
            "slug": slug,
            "condition_id": condition_id,
            "description": market.get("description", ""),
            "outcomes": outcomes,
            "yes_price": prices[0],
            "no_price": prices[1],
            "start_date": event.get("startDate"),
            "end_date": event.get("endDate"),
            "closed": event.get("closed"),
            "volume_total": float(event.get("volume", 0)),
            "volume_1mo": float(event.get("volume1mo", 0)),
            "volume_1wk": float(event.get("volume1wk", 0)),
            "volume_24hr": float(event.get("volume24hr", 0)),
            "liquidity": float(event.get("liquidity", 0)),
            "open_interest": float(event.get("openInterest", 0)),
            "best_bid": market.get("bestBid"),
            "best_ask": market.get("bestAsk"),
            "spread": market.get("spread"),
            "one_day_change": market.get("oneDayPriceChange"),
            "one_week_change": market.get("oneWeekPriceChange"),
            "one_month_change": market.get("oneMonthPriceChange"),
        },
        "tokens": {"yes": yes_token, "no": no_token},
        "price_history": price_history,
        "holders": holders,
        "recent_daily_volume": {d: daily[d] for d in sorted(daily)},
        "recent_flow": dict(flow),
        "recent_trade_count": len(trades),
        "recent_trades_span": [
            datetime.fromtimestamp(min(t["timestamp"] for t in trades), tz=timezone.utc).strftime("%Y-%m-%d %H:%M") if trades else None,
            datetime.fromtimestamp(max(t["timestamp"] for t in trades), tz=timezone.utc).strftime("%Y-%m-%d %H:%M") if trades else None,
        ],
        "top_wallets_recent": sorted(per_wallet.values(), key=lambda x: -x["notional"])[:25],
    }


def main():
    parser = ArgumentParser(description="Fetch Polymarket market data")
    g = parser.add_mutually_exclusive_group(required=True)
    g.add_argument("--slug", help="Event slug")
    g.add_argument("--url", help="Full polymarket.com event URL")
    parser.add_argument("-o", "--output", help="Output JSON file (default: stdout)")
    args = parser.parse_args()

    slug = args.slug or slug_from_url(args.url)
    data = build(slug)
    out = json.dumps(data, indent=2)
    if args.output:
        with open(args.output, "w") as f:
            f.write(out)
        sys.stderr.write(f"Wrote {args.output}\n")
    else:
        print(out)


if __name__ == "__main__":
    main()
