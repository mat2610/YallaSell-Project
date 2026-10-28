"""The external service is replaced by a Mock of requests.get: no network, no real waits."""

from __future__ import annotations

from datetime import date
from unittest.mock import Mock, patch

import pytest
import requests

from yallasell.api_client import ExchangeRateClient, RatesConnectionError, RatesDataError, RatesHTTPError

URL = "https://api.example.test/latest"
GOOD_BODY = {"amount": 1.0, "base": "ILS", "date": "2026-10-27", "rates": {"USD": 0.27, "EUR": 0.25}}


def ok_response(body=GOOD_BODY):
    response = Mock(status_code=200)
    response.raise_for_status.return_value = None
    response.json.return_value = body
    return response


@pytest.fixture
def client():
    return ExchangeRateClient(URL, timeout=2, max_attempts=3, retry_wait=1)


@patch("yallasell.api_client.requests.get")
def test_success_returns_checked_rates(mock_get, client):
    mock_get.return_value = ok_response()

    rates = client.get_rates("ILS", ["USD", "EUR"])

    assert rates.rates == {"USD": 0.27, "EUR": 0.25}
    assert rates.rates_date == date(2026, 10, 27)
    mock_get.assert_called_once_with(URL, params={"base": "ILS", "symbols": "USD,EUR"}, timeout=2)


@patch("yallasell.api_client.time.sleep")
@patch("yallasell.api_client.requests.get")
def test_timeout_is_retried_then_reported(mock_get, mock_sleep, client):
    mock_get.side_effect = requests.Timeout()

    with pytest.raises(RatesConnectionError, match="after 3 attempts"):
        client.get_rates("ILS", ["USD"])

    assert mock_get.call_count == 3              # 3 attempts in total, not more
    assert mock_sleep.call_count == 2            # a wait between attempts, none after the last


@patch("yallasell.api_client.time.sleep")
@patch("yallasell.api_client.requests.get")
def test_success_after_a_temporary_failure(mock_get, mock_sleep, client):
    mock_get.side_effect = [requests.ConnectionError(), ok_response()]

    rates = client.get_rates("ILS", ["USD", "EUR"])

    assert rates.rates["USD"] == 0.27
    assert mock_get.call_count == 2


@patch("yallasell.api_client.requests.get")
def test_http_error_is_not_retried(mock_get, client):
    response = Mock(status_code=500)
    response.raise_for_status.side_effect = requests.HTTPError("500")
    mock_get.return_value = response

    with pytest.raises(RatesHTTPError):
        client.get_rates("ILS", ["USD"])
    assert mock_get.call_count == 1


@patch("yallasell.api_client.requests.get")
def test_missing_rate_is_refused_without_retry(mock_get, client):
    mock_get.return_value = ok_response({"base": "ILS", "date": "2026-10-27", "rates": {"EUR": 0.25}})

    with pytest.raises(RatesDataError, match="missing rate for USD"):
        client.get_rates("ILS", ["USD"])
    assert mock_get.call_count == 1
