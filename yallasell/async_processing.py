"""Asynchronous collection: the status of our ads on several platforms (SIMULATED).

Every morning YallaSell checks each published ad: still active? how many views?
Each check is independent (it does not need the result of another one), so they can
wait in parallel instead of one after the other.

The platforms are simulated: `await asyncio.sleep(delay)` stands for the network wait
and the answer comes from local data. No real network call is made in this module.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass


@dataclass(frozen=True)
class StatusRequest:
    channel: str
    item_id: int


@dataclass(frozen=True)
class PlatformStatus:
    channel: str
    item_id: int
    status: str        # "active" / "sold" / "removed"
    views: int


class SimulatedPlatforms:
    """Local answers: (channel, item_id) -> (delay in seconds, status, views)."""

    def __init__(self, answers: dict[tuple[str, int], tuple[float, str, int]]):
        self.answers = answers
        self.finish_order: list[tuple[str, int]] = []      # to show that finish order != input order

    async def fetch_status(self, request: StatusRequest) -> PlatformStatus:
        key = (request.channel, request.item_id)
        if key not in self.answers:
            raise KeyError(f"No ad of item {request.item_id} on {request.channel}")
        delay, status, views = self.answers[key]
        await asyncio.sleep(delay)                         # non-blocking wait (never time.sleep here)
        self.finish_order.append(key)
        return PlatformStatus(request.channel, request.item_id, status, views)


async def collect_sequential(platforms: SimulatedPlatforms,
                             requests: list[StatusRequest]) -> list[PlatformStatus]:
    """One after the other: each check starts only when the previous one is finished."""
    results = []
    for request in requests:
        results.append(await platforms.fetch_status(request))
    return results


async def collect_concurrent(platforms: SimulatedPlatforms,
                             requests: list[StatusRequest]) -> list[PlatformStatus]:
    """All checks are scheduled first, then collected. gather keeps the INPUT order."""
    return list(await asyncio.gather(*(platforms.fetch_status(r) for r in requests)))


def ads_needing_attention(statuses: list[PlatformStatus], min_views: int) -> list[PlatformStatus]:
    """Business use of the collected data: active ads with few views -> candidates for a
    price drop or another channel."""
    return [s for s in statuses if s.status == "active" and s.views < min_views]
