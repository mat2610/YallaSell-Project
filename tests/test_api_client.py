"""The external service is replaced by a Mock of requests.get: no network, no real waits."""

from __future__ import annotations

from datetime import date
from unittest.mock import Mock, patch

import pytest
import requests

from yallasell.api_client import (CalendarConnectionError, CalendarDataError, CalendarHTTPError,
                                  HebcalClient)

URL = "https://api.example.test/hebcal"
START, END = date(2027, 4, 15), date(2027, 5, 19)
GOOD_BODY = {"title": "Hebcal Israel", "items": [
    {"title": "Erev Pesach", "date": "2027-04-21", "category": "holiday"},                 # not Yom Tov
    {"title": "Pesach I", "date": "2027-04-22", "hebrew": "פסח א׳", "yomtov": True},
    {"title": "Pesach II (CH''M)", "date": "2027-04-23", "category": "holiday"},           # not Yom Tov
    {"title": "Pesach VII", "date": "2027-04-28", "hebrew": "פסח ז׳", "yomtov": True},
]}


def ok_response(body=GOOD_BODY):
    response = Mock(status_code=200)
    response.raise_for_status.return_value = None
    response.json.return_value = body
    return response


@pytest.fixture
def client():
    return HebcalClient(URL, timeout=2, max_attempts=3, retry_wait=1)


@patch("yallasell.api_client.requests.get")
def test_success_keeps_only_yom_tov_days(mock_get, client):
    mock_get.return_value = ok_response()

    calendar = client.get_holidays(START, END)

    assert sorted(calendar.holidays) == [date(2027, 4, 22), date(2027, 4, 28)]   # 2 of the 4 items
    assert calendar.holiday_on(date(2027, 4, 22)).hebrew == "פסח א׳"
    assert calendar.source == "live"
    mock_get.assert_called_once_with(URL, params={"v": 1, "cfg": "json", "maj": "on", "i": "on",
                                                  "start": "2027-04-15", "end": "2027-05-19"}, timeout=2)


@patch("yallasell.api_client.time.sleep")
@patch("yallasell.api_client.requests.get")
def test_timeout_is_retried_then_reported(mock_get, mock_sleep, client):
    mock_get.side_effect = requests.Timeout()

    with pytest.raises(CalendarConnectionError, match="after 3 attempts"):
        client.get_holidays(START, END)

    assert mock_get.call_count == 3              # 3 attempts in total, not more
    assert mock_sleep.call_count == 2            # a wait between attempts, none after the last


@patch("yallasell.api_client.time.sleep")
@patch("yallasell.api_client.requests.get")
def test_success_after_a_temporary_failure(mock_get, mock_sleep, client):
    mock_get.side_effect = [requests.ConnectionError(), ok_response()]

    calendar = client.get_holidays(START, END)

    assert len(calendar.holidays) == 2
    assert mock_get.call_count == 2


@patch("yallasell.api_client.requests.get")
def test_http_error_is_not_retried(mock_get, client):
    response = Mock(status_code=500)
    response.raise_for_status.side_effect = requests.HTTPError("500")
    mock_get.return_value = response

    with pytest.raises(CalendarHTTPError):
        client.get_holidays(START, END)
    assert mock_get.call_count == 1


@patch("yallasell.api_client.requests.get")
def test_missing_field_is_refused_without_retry(mock_get, client):
    mock_get.return_value = ok_response({"title": "Hebcal Israel"})          # no "items"

    with pytest.raises(CalendarDataError, match="missing field 'items'"):
        client.get_holidays(START, END)
    assert mock_get.call_count == 1
