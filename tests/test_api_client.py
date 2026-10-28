"""The external service is replaced by a Mock of requests.get: no network, no real waits."""

from __future__ import annotations

import json
from datetime import date
from unittest.mock import Mock, patch

import pytest
import requests

from yallasell.api_client import (ExchangeRateClient, FileRatesClient, RatesConnectionError,
                                  RatesDataError, RatesHTTPError, RatesInvalidJSONError)

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
    assert rates.source == "live"
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
    mock_sleep.assert_called_once_with(1)


@pytest.mark.parametrize("status_code", [401, 404, 500])
@patch("yallasell.api_client.time.sleep")
@patch("yallasell.api_client.requests.get")
def test_http_error_is_not_retried(mock_get, mock_sleep, client, status_code):
    response = Mock(status_code=status_code)
    response.raise_for_status.side_effect = requests.HTTPError(f"{status_code}")
    mock_get.return_value = response

    with pytest.raises(RatesHTTPError) as error:
        client.get_rates("ILS", ["USD"])

    assert error.value.status_code == status_code
    assert mock_get.call_count == 1
    mock_sleep.assert_not_called()


@pytest.mark.parametrize("body, reason", [
    ({"base": "ILS", "date": "2026-10-27"}, "missing field 'rates'"),
    ({"base": "ILS", "date": "2026-10-27", "rates": {"EUR": 0.25}}, "missing rate for USD"),
    ({"base": "ILS", "date": "2026-10-27", "rates": {"USD": -1}}, "invalid rate for USD"),
    ({"base": "EUR", "date": "2026-10-27", "rates": {"USD": 1.1}}, "expected base ILS"),
])
@patch("yallasell.api_client.requests.get")
def test_invalid_data_is_refused_without_retry(mock_get, client, body, reason):
    mock_get.return_value = ok_response(body)

    with pytest.raises(RatesDataError, match=reason):
        client.get_rates("ILS", ["USD"])
    assert mock_get.call_count == 1


@patch("yallasell.api_client.requests.get")
def test_body_that_is_not_json(mock_get, client):
    response = ok_response()
    response.json.side_effect = ValueError("Expecting value")
    mock_get.return_value = response

    with pytest.raises(RatesInvalidJSONError):
        client.get_rates("ILS", ["USD"])


def test_offline_client_reads_file_and_marks_it_simulated(tmp_path):
    path = tmp_path / "rates.json"
    path.write_text(json.dumps(GOOD_BODY), encoding="utf-8")

    rates = FileRatesClient(path).get_rates("ILS", ["USD"])

    assert rates.rates == {"USD": 0.27}
    assert rates.source == "simulated"
