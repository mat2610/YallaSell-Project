from __future__ import annotations

import asyncio
import time

import pytest

from yallasell.async_processing import (PlatformStatus, SimulatedPlatforms, StatusRequest,
                                        ads_needing_attention, collect_concurrent, collect_sequential)

REQUESTS = [StatusRequest("GlobalMarket", 1), StatusRequest("EuroBay", 2), StatusRequest("Marketplace A", 3)]


@pytest.fixture
def answers():
    # the FIRST request is the slowest, so the finish order differs from the input order
    return {("GlobalMarket", 1): (0.20, "active", 4),
            ("EuroBay", 2): (0.10, "sold", 40),
            ("Marketplace A", 3): (0.05, "active", 25)}


def test_both_versions_give_same_results_in_input_order(answers):
    sequential = asyncio.run(collect_sequential(SimulatedPlatforms(answers), REQUESTS))
    platforms = SimulatedPlatforms(answers)
    concurrent = asyncio.run(collect_concurrent(platforms, REQUESTS))

    assert concurrent == sequential
    assert [s.item_id for s in concurrent] == [1, 2, 3]               # one result per id, input order
    assert [key[1] for key in platforms.finish_order] == [3, 2, 1]    # but they finished in reverse


def test_concurrent_waits_overlap(answers):
    start = time.perf_counter()
    asyncio.run(collect_sequential(SimulatedPlatforms(answers), REQUESTS))
    sequential_time = time.perf_counter() - start

    start = time.perf_counter()
    asyncio.run(collect_concurrent(SimulatedPlatforms(answers), REQUESTS))
    concurrent_time = time.perf_counter() - start

    assert sequential_time >= 0.35          # 0.20 + 0.10 + 0.05
    assert concurrent_time < 0.30           # about the slowest one (0.20)


def test_ads_needing_attention():
    statuses = [PlatformStatus("GlobalMarket", 1, "active", 4),
                PlatformStatus("EuroBay", 2, "sold", 0),          # sold: no action needed
                PlatformStatus("Marketplace A", 3, "active", 25)]
    assert ads_needing_attention(statuses, min_views=10) == [statuses[0]]
