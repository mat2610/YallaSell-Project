"""Settings read from environment variables (optionally from a local .env file).

The exchange-rate service used by YallaSell (Frankfurter) needs no API key,
so there is no secret here. If a keyed service is added later, its key must be
read with os.getenv like the values below and never written in the code.
"""

from __future__ import annotations

import logging
import os
import sys
from dataclasses import dataclass

try:                                    # python-dotenv is optional: without it, only real env vars are used
    from dotenv import load_dotenv
except ImportError:                     # pragma: no cover
    load_dotenv = None


@dataclass(frozen=True)
class Settings:
    rates_api_url: str
    rates_timeout: float
    rates_max_attempts: int
    rates_retry_wait: float
    log_level: str


def load_settings() -> Settings:
    if load_dotenv is not None:
        load_dotenv()                   # reads .env if it exists, does not override real env vars
    return Settings(
        rates_api_url=os.getenv("RATES_API_URL", "https://api.frankfurter.dev/v1/latest"),
        rates_timeout=float(os.getenv("RATES_TIMEOUT_SECONDS", "5")),
        rates_max_attempts=int(os.getenv("RATES_MAX_ATTEMPTS", "3")),
        rates_retry_wait=float(os.getenv("RATES_RETRY_WAIT_SECONDS", "1")),
        log_level=os.getenv("YALLASELL_LOG_LEVEL", "WARNING"),
    )


def setup_logging(level: str) -> None:
    # stdout (not stderr): log lines appear in the same order as the demo output
    logging.basicConfig(level=level.upper(), stream=sys.stdout,
                        format="%(levelname)s %(name)s: %(message)s")
