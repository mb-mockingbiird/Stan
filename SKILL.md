---
name: finviz-stock-data
description: "Fetch stock price/export data (daily OHLC or intraday) for one or more tickers from Finviz Elite."
version: 1.0.0
platforms:
metadata:
  hermes:
    tags:
      - finance
      - stocks
      - market-data
      - finviz
    related_skills: []
---

# Finviz Stock Data: Fetch Ticker Price/Export Data

## Overview

This skill fetches stock price and export data (daily OHLC or intraday bars)
for one or more tickers from the Finviz Elite export API. Use it whenever the
user asks for a stock's current price, recent price history, or intraday data.

## Prerequisites

- `code_execution` toolset must be available (to run the bundled Python script)
- `file` toolset must be available (to read the script from this skill's directory)
- Environment variable `FINVIZ_API_TOKEN` must be set on the host (Finviz Elite
  API token). If it is not set, tell the user to configure it rather than
  asking them for the raw token value in chat.
- `requests` Python package must be installed (`pip3 install requests --break-system-packages`
  if missing)

## Inputs

The user provides, directly or inferred from their request:
1. **Ticker(s)** — e.g. "AAPL" or "AAPL,MSFT,TSLA"
2. **Timeframe** (optional) — daily by default; intraday if the user asks for
   minute-level data (1/5/15/30/60-min)
3. **Date range** (optional) — only meaningful for intraday timeframes

## Workflow

### Step 1: Parse the request
Identify the ticker(s), and whether the user wants daily or intraday data.
Map casual language to timeframe codes:
- "price today" / "current price" / no timeframe mentioned → `d` (daily)
- "1 minute" / "minute bars" → `i1`
- "5 minute" → `i5`
- "15 minute" → `i15`
- "30 minute" → `i30`
- "hourly" / "1 hour" → `i60`

### Step 2: Run the script via code_execution
Invoke `finviz_stock_price.py` (located alongside this SKILL.md in the skill's
install directory) as a subprocess, or import and call `get_stock_data()`
directly if running in the same Python process:

```
python3 finviz_stock_price.py <TICKER>
```

Or programmatically:
```python
from finviz_stock_price import get_stock_data
rows = get_stock_data(ticker="AAPL", timeframe="d")
```

### Step 3: Handle errors
- If the script raises a config error about `FINVIZ_API_TOKEN` missing, tell
  the user the token isn't configured on this host — do not ask them to paste
  the token into chat.
- If Finviz returns HTML instead of CSV (invalid ticker, bad auth, or plan
  limit), surface a clear message rather than raw HTML.

### Step 4: Present the result
Summarize the relevant fields for the user's question (e.g. latest close price,
day's range) rather than dumping the full raw row list, unless they asked for
the full data.

## Notes

- Never log, print, or echo the `FINVIZ_API_TOKEN` value anywhere in output,
  cron logs, or messages sent via the messaging toolset.
- This skill only reads market data — it does not place trades or interact
  with any brokerage account.
