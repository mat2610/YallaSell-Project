"""Communication with the external Jewish calendar service (Hebcal), Israel schedule.

This module only talks to the service and checks the answer.
What YallaSell DOES with the holidays (moving an agreement's end date, what to do
on a failure) is decided in services.py.

Docs: https://www.hebcal.com/home/195/jewish-calendar-rest-api
Request:  GET https://www.hebcal.com/hebcal?v=1&cfg=json&maj=on&i=on&start=2027-04-15&end=2027-05-19
Answer:   {"title": "...", "range": {...}, "items": [
              {"title": "Pesach I", "date": "2027-04-22", "category": "holiday",
               "subcat": "major", "hebrew": "פסח א׳", "yomtov": true}, ...]}
Only items with "yomtov": true are days when businesses are closed.
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

class CalendarError(Exception):
    """Base class: the holidays could not be obtained."""


class CalendarConnectionError(CalendarError):
    """Timeout or connection failure, still failing after every attempt."""


class CalendarHTTPError(CalendarError):
    """The service answered with an error code (4xx / 5xx). Not retried."""

    def __init__(self, status_code: int | None, message: str):
        super().__init__(message)
        self.status_code = status_code


class CalendarInvalidJSONError(CalendarError):
    """The body is not valid JSON. Not retried."""


class CalendarDataError(CalendarError):
    """Valid JSON, but not the structure / values we need. Not retried."""


# ---------------------------------------------------------------- result objects

@dataclass(frozen=True)
class Holiday:
    day: date
    title: str
    hebrew: str


@dataclass(frozen=True)
class HolidayCalendar:
    """The Yom Tov days (businesses closed) between start and end."""
    start: date
    end: date
    holidays: dict[date, Holiday]
    source: str                       # "live" or "simulated": shown in every output

    def holiday_on(self, day: date) -> Holiday | None:
        return self.holidays.get(day)


def parse_holidays(data: object, start: date, end: date, source: str) -> HolidayCalendar:
    """Check the decoded JSON and keep only the Yom Tov days."""
    if not isinstance(data, dict):
        raise CalendarDataError("answer is not a JSON object")
    if "items" not in data:
        raise CalendarDataError("missing field 'items'")
    items = data["items"]
    if not isinstance(items, list):
        raise CalendarDataError("'items' is not a list")

    holidays: dict[date, Holiday] = {}
    for item in items:
        if not isinstance(item, dict):
            raise CalendarDataError("an item is not an object")
        for field in ("title", "date"):
            if field not in item:
                raise CalendarDataError(f"item without {field!r}")
        try:
            day = date.fromisoformat(str(item["date"])[:10])   # timed items carry "T18:00..."
        except ValueError:
            raise CalendarDataError(f"invalid date {item['date']!r}") from None
        if item.get("yomtov") is True:                          # only closed days matter
            holidays[day] = Holiday(day, item["title"], item.get("hebrew", item["title"]))
    return HolidayCalendar(start, end, holidays, source)


# ---------------------------------------------------------------- real client

class HebcalClient:
    """Gets the Israeli holidays from the real service, with timeout and retry."""

    def __init__(self, base_url: str, timeout: float = 5.0,
                 max_attempts: int = 3, retry_wait: float = 1.0):
        if max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")
        self.base_url = base_url
        self.timeout = timeout
        self.max_attempts = max_attempts
        self.retry_wait = retry_wait

    def get_holidays(self, start: date, end: date) -> HolidayCalendar:
        if end < start:
            raise ValueError("end must not be before start")
        params = {"v": 1, "cfg": "json", "maj": "on", "i": "on",       # i=on: Israel schedule
                  "start": start.isoformat(), "end": end.isoformat()}
        response = self._get_with_retry(params)

        try:
            response.raise_for_status()
        except requests.HTTPError as error:
            # 4xx / 5xx: repeating the same request will not fix it (bad parameters, no permission...)
            status = response.status_code
            logger.error("Calendar service answered HTTP %s", status)
            raise CalendarHTTPError(status, f"calendar service returned HTTP {status}") from error

        try:
            data = response.json()
        except ValueError as error:          # requests raises a ValueError subclass for bad JSON
            logger.error("Calendar service returned a body that is not JSON")
            raise CalendarInvalidJSONError("calendar service returned invalid JSON") from error

        calendar = parse_holidays(data, start, end, source="live")
        logger.info("Got %d Yom Tov days between %s and %s", len(calendar.holidays), start, end)
        return calendar

    def _get_with_retry(self, params: dict) -> requests.Response:
        """Retry ONLY on Timeout / ConnectionError, at most max_attempts in total."""
        for attempt in range(1, self.max_attempts + 1):
            try:
                return requests.get(self.base_url, params=params, timeout=self.timeout)
            except (requests.Timeout, requests.ConnectionError) as error:
                logger.warning("Attempt %d/%d failed: %s", attempt, self.max_attempts,
                               type(error).__name__)
                if attempt == self.max_attempts:
                    logger.error("Calendar service unreachable after %d attempts", self.max_attempts)
                    raise CalendarConnectionError(
                        f"calendar service unreachable after {self.max_attempts} attempts "
                        f"({type(error).__name__})") from error
                time.sleep(self.retry_wait * attempt)      # wait a bit longer each time
        raise AssertionError("unreachable")                # pragma: no cover


# ---------------------------------------------------------------- offline client

class FileCalendarClient:
    """Offline replacement with the same get_holidays() contract.

    Reads a saved answer (same structure as the real one) from a local JSON file.
    Used by the default run of main.py so the demo works without network.
    Its results are marked source="simulated" so they are never shown as real.
    """

    def __init__(self, path: str | Path):
        self.path = Path(path)

    def get_holidays(self, start: date, end: date) -> HolidayCalendar:
        try:
            with open(self.path, encoding="utf-8") as file:
                data = json.load(file)
        except json.JSONDecodeError as error:
            raise CalendarInvalidJSONError(f"{self.path.name} is not valid JSON") from error
        calendar = parse_holidays(data, start, end, source="simulated")
        kept = {d: h for d, h in calendar.holidays.items() if start <= d <= end}
        return HolidayCalendar(start, end, kept, "simulated")
