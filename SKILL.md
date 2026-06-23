---
name: manifold-analysis
description: Analyze prediction market data from Manifold Markets and Polymarket. Use when processing HTML exports or trade history to create visualizations of trading volume, trader leaderboards, probability movements, position holders, and market dynamics. Also handles multi-market "topic" reports. Triggers on requests involving Manifold Markets or Polymarket data, prediction market analysis, or when user uploads market HTML files or pastes a polymarket.com / manifold.markets URL.
---

# Prediction Market Analysis

Analyze prediction market data from Manifold Markets and Polymarket to create interactive visualizations and trader analytics.

> Two platforms are supported. Manifold is play-money (see notes below); Polymarket is real-money USDC. Pick the section that matches the source. For Polymarket, jump to [Polymarket](#polymarket).

## Overview

Manifold Markets is a play-money prediction market platform. Key concepts:
- **Mana (Ṁ)** - Play-money currency (not convertible to cash, ~Ṁ100 = $1 purchase price)
- **Markets** - Questions with multiple answer buckets (e.g., "$5-10B", ">$25B")
- **Trading** - Users buy YES/NO shares on answers; prices reflect probability

## Data Sources

### Manifold API (Preferred)
Fetch data directly from the Manifold Markets API:

1. **Find market ID** via search:
```bash
curl "https://api.manifold.markets/v0/search-markets?term=your+search+term"
```

2. **Fetch all bets** with pagination:
```bash
curl "https://api.manifold.markets/v0/bets?contractId=MARKET_ID&limit=1000"
# Use &before=LAST_BET_ID for pagination
```

3. **Resolve usernames** for top traders:
```bash
curl "https://api.manifold.markets/v0/user/by-id/USER_ID"
```

**Rate Limiting**: Be conservative - 1 second between paginated requests, longer for user lookups. Skip bulk user lookups if possible.

Use `scripts/fetch_market_data.py` for automated fetching:
```bash
python3 scripts/fetch_market_data.py --market-id MARKET_ID --output all > market_data.json
```

### HTML Export
Users may upload saved HTML from manifold.markets pages. Extract data from:
- Market title and metadata in page header
- Trade history in comments/activity sections (look for patterns like "bought Ṁ50 of YES")
- Current probabilities displayed for each answer

### Trade History Text
Users may paste trade history directly. Common format:
```
Username,action,amount,answer,outcome,time_ago
JoshYou,bought,350,>$25B,YES,1y
Bayesian,sold,100,$5-10B,NO,3mo
```

Time formats: `23d` (days), `1mo`/`3mo` (months), `1y` (year ago)

## Analysis Workflow

### 1. Parse Trade Data
Use `scripts/parse_trades.py` to extract trades from text:
```bash
python3 scripts/parse_trades.py < trades.txt > trades.json
```

### 2. Aggregate by Trader
For each trader compute:
- Total volume (sum of all trade amounts)
- Trade count
- Buy/sell ratio
- YES vs NO volume breakdown
- Top answer buckets traded

### 3. Aggregate by Time
Convert relative timestamps to approximate dates:
- Reference: current date or market close date
- Map "1y" → ~12 months ago, "3mo" → ~3 months ago, etc.
- Group by month for time series

### 4. Create Visualization
Build an HTML visualization with Chart.js (preferred for reliability):

```html
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
```

Include:
- Cumulative stacked area chart by answer over time
- Trader leaderboard table with volume, trades, YES/NO breakdown
- Answer breakdown legend with colors
- Stats cards showing probability, total volume, trades, unique traders

See `references/visualization_template.md` for React/Recharts approach (less reliable CDN loading).

**Example output**: `iran_market_viz_chartjs.html` - full standalone visualization

## Polymarket

Polymarket is a real-money (USDC) prediction market. No API key is required for
the public read endpoints. Unlike Manifold, there is **no public full trade-by-trade
history** for busy markets (the trades endpoint caps pagination at ~3,500 rows and
the on-chain subgraph is stale), so analysis leans on **current holders** (positions)
plus **aggregate volume windows** rather than every fill.

### Data Sources (no auth)
- **Gamma** `https://gamma-api.polymarket.com/events?slug=<slug>` — market metadata,
  outcomes/prices, and `volume`, `volume1mo`, `volume1wk`, `volume24hr` aggregates.
- **CLOB** `https://clob.polymarket.com/prices-history?market=<tokenId>&interval=all&fidelity=60`
  — full probability curve (use the YES `clobTokenIds[0]`).
- **data-api holders** `https://data-api.polymarket.com/holders?market=<conditionId>&limit=100`
  — top holders per outcome token (the cleanest "puts and takes" / bull-vs-bear view).
- **data-api trades** `https://data-api.polymarket.com/trades?market=<conditionId>&limit=500&offset=N`
  — recent trades only; `offset` caps near 3,500 (≈ last days on busy markets). Use for
  recent order flow, not full history.

Outcome ordering is `["Yes", "No"]` with YES = index 0 (verify per market before
trusting derived numbers).

### Single-market workflow
```bash
# 1. Fetch everything into one JSON (slug from the polymarket.com/event/<slug> URL)
python3 scripts/fetch_polymarket.py --slug <slug> -o examples/<name>/data.json
# or: --url https://polymarket.com/event/<slug>

# 2. Render the deep-dive viz (price curve, volume-by-period, order flow, holders leaderboard)
python3 scripts/generate_poly_viz.py examples/<name>/data.json -o examples/<name>/viz.html
```

### Multi-market topic report
For a topic spanning several related markets, fetch each and overlay them:
```bash
python3 scripts/generate_poly_report.py \
  --slug will-the-iranian-regime-fall-by-june-30 \
  --slug strait-of-hormuz-traffic-returns-to-normal-by-end-of-june \
  --slug strait-of-hormuz-traffic-returns-to-normal-by-july-31 \
  --title "Iran / Strait of Hormuz Crisis" \
  -o examples/hormuz/iran_topic_report.html
```
Produces overlaid YES-probability curves + a comparison table (current odds, weekly
move, volume, resolution date) and a `_data.json` sidecar. Find related slugs via the
Gamma `events` endpoint. **Read each market's resolution criteria** — markets that look
contradictory are usually pricing different bars (a one-touch threshold, a single-day
count, a 7-day moving average, an end-of-period level). Worked example lives in
`examples/hormuz/`.

### Polymarket interpretation notes
- Positions ≈ 50/50 in size is consistent with a price near 50%; large lopsided holder
  sums on one side signal conviction.
- Wallets appearing in *both* outcome top-100 lists are likely hedgers/market-makers;
  their absence means the leaders are committed directional traders.
- Recent flow can diverge from price when a *realized* data print (the resolution
  source) moves the odds independent of order flow.

## Color Scheme for Answers

### Binary Markets (YES/NO)
```javascript
const colors = {
  YES: '#10b981',  // Green - teal
  NO: '#ef4444'    // Red
};
```

### Multi-Answer Markets
Use consistent colors across visualizations:
```javascript
const colors = {
  "<$5B": "#99DDFF",
  "$5-10B": "#FFDD99",
  "$10.1-12.5B": "#FFAABB",
  "$12.6-15B": "#77F299",
  "$15.1-17.5B": "#CD46EA",
  "$17.6-20B": "#F23542",
  "$20.1-25B": "#FF8C00",
  ">$25B": "#44BB99"
};
```

Adapt color keys to match actual answer labels in the market.

## Key Metrics to Surface

### Market Level
- Total volume traded
- Number of unique traders
- Peak trading month
- Current leading answer and probability

### Trader Level
- Rank by total volume ("whales")
- Rank by trade count ("most active")
- YES vs NO ratio (bullish/bearish tendency)
- Top 2-3 answers traded per user

### Insights to Highlight
- **Biggest whale** - Highest total volume
- **Most active** - Highest trade count
- **Top bull** - Highest % YES volume
- **Top bear** - Highest % NO volume

## Context Notes

When presenting analysis, note:
1. Mana is play money with no cash value
2. Large positions may represent accumulated winnings, not money invested
3. New users get Ṁ1,000 free; active traders earn daily bonuses
4. Someone with Ṁ40k may have spent $0-400 actual dollars
