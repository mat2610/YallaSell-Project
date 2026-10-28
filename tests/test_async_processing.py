from __future__ import annotations

import asyncio

from yallasell.async_processing import SimulatedPlatforms, StatusRequest, collect_concurrent, collect_sequential


def test_both_versions_give_same_results_in_input_order():
    # the FIRST request is the slowest, so the finish order differs from the input order
    answers = {("GlobalMarket", 1): (0.20, "active", 4),
               ("EuroBay", 2): (0.10, "sold", 40),
               ("Marketplace A", 3): (0.05, "active", 25)}
    requests = [StatusRequest("GlobalMarket", 1), StatusRequest("EuroBay", 2), StatusRequest("Marketplace A", 3)]

    sequential = asyncio.run(collect_sequential(SimulatedPlatforms(answers), requests))
    platforms = SimulatedPlatforms(answers)
    concurrent = asyncio.run(collect_concurrent(platforms, requests))

    assert concurrent == sequential
    assert [s.item_id for s in concurrent] == [1, 2, 3]               # one result per id, input order
    assert [key[1] for key in platforms.finish_order] == [3, 2, 1]    # but they finished in reverse
