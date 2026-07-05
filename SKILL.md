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

- `code_execution` toolset must be available
- `file` toolset must be available (to persist the helper script below on first use)
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

### Step 1: Ensure the helper script exists

Using the `file` toolset, check whether `finviz_stock_price.py` already exists
in this skill's working directory. If it does not, write the exact contents
from the "Helper Script" section below to `finviz_stock_price.py` in that
directory. Do this once; reuse the file on subsequent runs rather than
rewriting it every time.

### Step 2: Parse the request

Identify the ticker(s), and whether the user wants daily or intraday data.
Map casual language to timeframe codes:
- "price today" / "current price" / no timeframe mentioned → `d` (daily)
- "1 minute" / "minute bars" → `i1`
- "5 minute" → `i5`
- "15 minute" → `i15`
- "30 minute" → `i30`
- "hourly" / "1 hour" → `i60`

### Step 3: Run the script via code_execution

```
python3 finviz_stock_price.py <TICKER>
```

Or, if executing Python inline in the same process:
```python
from finviz_stock_price import get_stock_data
rows = get_stock_data(ticker="AAPL", timeframe="d")
```

### Step 4: Handle errors

- If the script raises a config error about `FINVIZ_API_TOKEN` missing, tell
  the user the token isn't configured on this host — do not ask them to paste
  the token into chat.
- If Finviz returns HTML instead of CSV (invalid ticker, bad auth, or plan
  limit), surface a clear message rather than raw HTML.

### Step 5: Present the result

Summarize the relevant fields for the user's question (e.g. latest close
price, day's range) rather than dumping the full raw row list, unless they
asked for the full data.

## Notes

- Never log, print, or echo the `FINVIZ_API_TOKEN` value anywhere in output,
  cron logs, or messages sent via the messaging toolset.
- This skill only reads market data — it does not place trades or interact
  with any brokerage account.

## Helper Script

Save this exact content as `finviz_stock_price.py` (Step 1 above):

```python
"""
Hermes skill: get_stock_data
Fetches stock/price data from the Finviz Elite export API.

SECURITY:
- The Finviz Elite API token is read from the FINVIZ_API_TOKEN environment
  variable. It is never hardcoded, never logged, and never included in
  exception messages or return values.
"""

import os
import csv
import io
import logging
from typing import Optional

import requests

logger = logging.getLogger("hermes.skills.finviz")

FINVIZ_EXPORT_URL = "https://elite.finviz.com/export/stock"
REQUEST_TIMEOUT_SECONDS = 15


class FinvizConfigError(RuntimeError):
    """Raised when the Finviz API token is missing or misconfigured."""


class FinvizRequestError(RuntimeError):
    """Raised when the Finviz API request fails or returns unexpected data."""


def _get_api_token() -> str:
    token = os.environ.get("FINVIZ_API_TOKEN")
    if not token:
        raise FinvizConfigError(
            "FINVIZ_API_TOKEN environment variable is not set. "
            "Configure it on the host — never hardcode it in source."
        )
    return token


def get_stock_data(
    ticker: str,
    timeframe: str = "d",
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
) -> list[dict]:
    """
    Fetch stock price/export data for a ticker from Finviz Elite.

    Args:
        ticker: Stock ticker symbol, e.g. "AAPL". Comma-separate for multiple.
        timeframe: "d" (daily, default), "i1"/"i5"/"i15"/"i30"/"i60" (intraday).
        date_from: Optional start date "YYYY-MM-DD" (intraday timeframes only).
        date_to: Optional end date "YYYY-MM-DD".

    Returns:
        A list of dicts, one per CSV row Finviz returns.

    Raises:
        FinvizConfigError: if the API token isn't configured.
        FinvizRequestError: if the request fails or the response isn't parseable CSV.
    """
    if not ticker or not ticker.strip():
        raise ValueError("ticker is required")

    token = _get_api_token()

    params = {
        "t": ticker.strip().upper(),
        "p": timeframe,
    }
    if date_from:
        params["f"] = date_from
    if date_to:
        params["to"] = date_to
    params["auth"] = token  # only ever placed in the request, never logged

    try:
        response = requests.get(
            FINVIZ_EXPORT_URL,
            params=params,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
    except requests.exceptions.RequestException as exc:
        logger.error("Finviz request failed for ticker=%s: %s", ticker, type(exc).__name__)
        raise FinvizRequestError(
            f"Failed to fetch data from Finviz for {ticker!r}: {type(exc).__name__}"
        ) from exc

    content_type = response.headers.get("Content-Type", "")
    text = response.text

    if "text/csv" not in content_type and text.lstrip().startswith(("<", "<!DOCTYPE")):
        raise FinvizRequestError(
            "Finviz did not return CSV data — likely an invalid token, "
            "invalid ticker, or a plan/permission limit. Response was HTML, not data."
        )

    try:
        reader = csv.DictReader(io.StringIO(text))
        rows = list(reader)
    except csv.Error as exc:
        raise FinvizRequestError(f"Could not parse Finviz response as CSV: {exc}") from exc

    if not rows:
        raise FinvizRequestError(f"Finviz returned no rows for ticker {ticker!r}")

    return rows


if __name__ == "__main__":
    import json
    import sys

    test_ticker = sys.argv[1] if len(sys.argv) > 1 else "AAPL"
    try:
        data = get_stock_data(test_ticker)
        print(json.dumps(data[:5], indent=2))
        print(f"...{len(data)} rows total")
    except (FinvizConfigError, FinvizRequestError) as e:
        print(f"Error: {e}")
```
