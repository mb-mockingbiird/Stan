"""
Hermes skill: get_stock_data
Fetches stock/price data from the Finviz Elite export API.

SECURITY:
- The Finviz Elite API token is read from the FINVIZ_API_TOKEN environment
  variable. It is never hardcoded, never logged, and never included in
  exception messages or return values.
- Set it on the VPS via systemd EnvironmentFile or a chmod 600 .env file
  (see: /etc/finviz/finviz.env, loaded by the hermes.service unit).

USAGE (as a Hermes tool):
  Register `get_stock_data` as the callable. Hermes should populate
  `ticker` (and optionally `timeframe`/date range) from the user's request.

Example:
    get_stock_data(ticker="AAPL", timeframe="d")
    get_stock_data(ticker="MSFT", timeframe="i1", date_from="2026-06-01", date_to="2026-07-01")
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
            "Configure it in /etc/finviz/finviz.env (chmod 600) or your "
            "systemd EnvironmentFile — never hardcode it in source."
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
        ticker: Stock ticker symbol, e.g. "AAPL". Comma-separate for multiple,
            e.g. "AAPL,MSFT,TSLA".
        timeframe: Finviz timeframe code. Common values: "d" (daily),
            "i1" (1-min intraday), "i5" (5-min), "i15", "i30", "i60".
            Defaults to daily.
        date_from: Optional start date "YYYY-MM-DD" (only used for
            timeframes that support a date range, e.g. intraday).
        date_to: Optional end date "YYYY-MM-DD".

    Returns:
        A list of dicts, one per row of the CSV Finviz returns
        (e.g. [{"Date": "...", "Open": "...", "High": "...", ...}, ...]).

    Raises:
        FinvizConfigError: if the API token isn't configured.
        FinvizRequestError: if the request fails, times out, or the
            response isn't parseable CSV.
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
        # Strip any query string (which contains the token) before logging/raising
        safe_url = FINVIZ_EXPORT_URL
        logger.error("Finviz request failed for ticker=%s: %s", ticker, type(exc).__name__)
        raise FinvizRequestError(
            f"Failed to fetch data from Finviz for {ticker!r} ({safe_url}): {type(exc).__name__}"
        ) from exc

    content_type = response.headers.get("Content-Type", "")
    text = response.text

    # Finviz returns an HTML error page (not CSV) on bad auth/params
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


# --- Hermes tool schema (for skill registration) -----------------------------
TOOL_SCHEMA = {
    "name": "get_stock_data",
    "description": (
        "Get stock price/export data (OHLC or intraday) for one or more "
        "tickers from Finviz Elite."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "ticker": {
                "type": "string",
                "description": "Ticker symbol, e.g. 'AAPL'. Comma-separate for multiple.",
            },
            "timeframe": {
                "type": "string",
                "description": "d=daily, i1/i5/i15/i30/i60=intraday minutes. Default 'd'.",
                "default": "d",
            },
            "date_from": {
                "type": "string",
                "description": "Optional start date YYYY-MM-DD (intraday timeframes only).",
            },
            "date_to": {
                "type": "string",
                "description": "Optional end date YYYY-MM-DD.",
            },
        },
        "required": ["ticker"],
    },
}


if __name__ == "__main__":
    # Quick manual smoke test — requires FINVIZ_API_TOKEN to be set in env.
    import json
    import sys

    test_ticker = sys.argv[1] if len(sys.argv) > 1 else "AAPL"
    try:
        data = get_stock_data(test_ticker)
        print(json.dumps(data[:5], indent=2))
        print(f"...{len(data)} rows total")
    except (FinvizConfigError, FinvizRequestError) as e:
        print(f"Error: {e}")
