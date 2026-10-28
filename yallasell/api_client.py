"""Communication with the external exchange-rate service (Frankfurter, ECB rates).

This module only talks to the service and checks the answer.
What YallaSell DOES with the rates (prices on foreign platforms, what to do on a failure)
is decided in services.py.

Docs: https://frankfurter.dev
Request:  GET https://api.frankfurter.dev/v1/latest?base=ILS&symbols=USD,EUR
Answer:   {"amount": 1.0, "base": "ILS", "date": "2026-10-27", "rates": {"EUR": 0.25, "USD": 0.27}}
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import requests

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------- errors
# One class per kind of failure, so the caller can react differently to each one.

class RatesError(Exception):
    """Base class: the rates could not be obtained."""


class RatesConnectionError(RatesError):
    """Timeout or connection failure, still failing after every attempt."""


class RatesHTTPError(RatesError):
    """The service answered with an error code (4xx / 5xx). Not retried."""

    def __init__(self, status_code: int | None, message: str):
        super().__init__(message)
        self.status_code = status_code


class RatesInvalidJSONError(RatesError):
    """The body is not valid JSON. Not retried."""


class RatesDataError(RatesError):
    """Valid JSON, but not the structure / values we need. Not retried."""


# ---------------------------------------------------------------- result object

@dataclass(frozen=True)
class ExchangeRates:
    base: str
    rates_date: date
    rates: dict[str, float]          # currency code -> how much of it for 1 unit of base
    source: str                      # "live" or "simulated": shown in every output

    def convert(self, amount: float, currency: str) -> float:
        if currency == self.base:
            return round(amount, 2)
        if currency not in self.rates:
            raise KeyError(f"No rate for {currency}")
        return round(amount * self.rates[currency], 2)


def parse_rates(data: object, base: str, symbols: list[str], source: str) -> ExchangeRates:
    """Check the decoded JSON and turn it into an ExchangeRates object."""
    if not isinstance(data, dict):
        raise RatesDataError("answer is not a JSON object")
    for field in ("base", "date", "rates"):
        if field not in data:
            raise RatesDataError(f"missing field {field!r}")
    if data["base"] != base:
        raise RatesDataError(f"expected base {base}, got {data['base']!r}")
    try:
        rates_date = date.fromisoformat(data["date"])
    except (TypeError, ValueError):
        raise RatesDataError(f"invalid date {data['date']!r}") from None
    rates = data["rates"]
    if not isinstance(rates, dict):
        raise RatesDataError("'rates' is not an object")
    clean: dict[str, float] = {}
    for code in symbols:
        value = rates.get(code)
        if value is None:
            raise RatesDataError(f"missing rate for {code}")
        if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
            raise RatesDataError(f"invalid rate for {code}: {value!r}")
        clean[code] = float(value)
    return ExchangeRates(base, rates_date, clean, source)


# ---------------------------------------------------------------- real client

class ExchangeRateClient:
    """Gets exchange rates from the real service, with timeout and retry."""

    def __init__(self, base_url: str, timeout: float = 5.0,
                 max_attempts: int = 3, retry_wait: float = 1.0):
        if max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")
        self.base_url = base_url
        self.timeout = timeout
        self.max_attempts = max_attempts
        self.retry_wait = retry_wait

    def get_rates(self, base: str, symbols: list[str]) -> ExchangeRates:
        params = {"base": base, "symbols": ",".join(symbols)}
        response = self._get_with_retry(params)

        try:
            response.raise_for_status()
        except requests.HTTPError as error:
            # 4xx / 5xx: repeating the same request will not fix it (bad currency, no permission...)
            status = response.status_code
            logger.error("Rates service answered HTTP %s", status)
            raise RatesHTTPError(status, f"rates service returned HTTP {status}") from error

        try:
            data = response.json()
        except ValueError as error:          # requests raises a ValueError subclass for bad JSON
            logger.error("Rates service returned a body that is not JSON")
            raise RatesInvalidJSONError("rates service returned invalid JSON") from error

        rates = parse_rates(data, base, symbols, source="live")
        logger.info("Got %d rates for %s, dated %s", len(rates.rates), base, rates.rates_date)
        return rates

    def _get_with_retry(self, params: dict) -> requests.Response:
        """Retry ONLY on Timeout / ConnectionError, at most max_attempts in total."""
        for attempt in range(1, self.max_attempts + 1):
            try:
                return requests.get(self.base_url, params=params, timeout=self.timeout)
            except (requests.Timeout, requests.ConnectionError) as error:
                logger.warning("Attempt %d/%d failed: %s", attempt, self.max_attempts,
                               type(error).__name__)
                if attempt == self.max_attempts:
                    logger.error("Rates service unreachable after %d attempts", self.max_attempts)
                    raise RatesConnectionError(
                        f"rates service unreachable after {self.max_attempts} attempts "
                        f"({type(error).__name__})") from error
                time.sleep(self.retry_wait * attempt)      # wait a bit longer each time
        raise AssertionError("unreachable")                # pragma: no cover


# ---------------------------------------------------------------- offline client

class FileRatesClient:
    """Offline replacement with the same get_rates() contract.

    Reads rates saved in a local JSON file (same structure as the real answer).
    Used by the default run of main.py so the demo works without network.
    Its results are marked source="simulated" so they are never shown as real.
    """

    def __init__(self, path: str | Path):
        self.path = Path(path)

    def get_rates(self, base: str, symbols: list[str]) -> ExchangeRates:
        try:
            with open(self.path, encoding="utf-8") as file:
                data = json.load(file)
        except json.JSONDecodeError as error:
            raise RatesInvalidJSONError(f"{self.path.name} is not valid JSON") from error
        return parse_rates(data, base, symbols, source="simulated")
