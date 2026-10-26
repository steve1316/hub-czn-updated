"""Pull tracker stats: 50/50 wins and losses, pity per banner, luck against the assumed rate, and the stale marker."""

import json

from api.routes.rescue import _luck_percentile, _process_records

# A real 5-star combatant id.
FIVE = 1004
COMBATANT_POOL = "gacha_pickup_combatant_30115"


def _rec(rid, rewards, prisms=None, gacha_id=COMBATANT_POOL, ts=1000):
    return {
        "id": str(rid),
        "gacha_id": gacha_id,
        "reward": json.dumps(rewards),
        "prism": json.dumps(prisms if prisms is not None else [0] * len(rewards)),
        "createAt": str(ts),
    }


def _banner(raw, meta=None):
    return _process_records(raw, meta)[0]


def test_fifty_fifty_counts_wins_and_losses():
    raw = [_rec(1, [FIVE, 99999, FIVE], prisms=[1, 0, 0])]
    stats = _banner(raw)["stats"]
    assert stats["five_star"] == 2
    assert stats["wins_50_50"] == 1
    assert stats["losses_50_50"] == 1


def test_current_pity_is_counted_since_the_last_five_star_when_the_server_gave_none():
    raw = [_rec(1, [FIVE, 99999, 99999, 99999])]
    banner = _banner(raw)
    assert banner["pity_current"] == 3
    assert banner["pity_source"] == "computed"


def test_current_pity_prefers_the_server_value_for_the_matching_pity_group():
    meta = {"pity": {"gacha_pity_pickup_combatant": {"pity_ssr_count": 6}}}
    banner = _banner([_rec(1, [FIVE, 99999])], meta)
    assert banner["pity_current"] == 6
    assert banner["pity_source"] == "server"


def test_banner_is_stale_unless_one_of_its_pools_was_fetched_this_session():
    raw = [_rec(1, [99999])]
    assert _banner(raw)["stale"] is True
    old = {"session_start": 5000, "pool_fetches": {COMBATANT_POOL: 4000}}
    assert _banner(raw, old)["stale"] is True
    fresh = {"session_start": 5000, "pool_fetches": {COMBATANT_POOL: 5100}}
    banner = _banner(raw, fresh)
    assert banner["stale"] is False
    assert banner["last_refreshed"] == 5100


def test_luck_percentile_is_high_when_far_above_expected_and_low_when_below():
    assert _luck_percentile(0, 100, 0.015) < 25
    assert _luck_percentile(6, 100, 0.015) > 95
    assert 40 < _luck_percentile(1, 67, 0.015) < 80
    assert _luck_percentile(0, 0, 0.015) is None


def test_banner_reports_luck_against_an_assumed_rate():
    stats = _banner([_rec(1, [FIVE] + [99999] * 9)])["stats"]
    assert stats["luck_percentile"] is not None
    assert stats["rate_assumed"] is True


def test_banner_lists_every_pool_it_covers():
    raw = [_rec(1, [99999], gacha_id="gacha_pickup_combatant_30115"), _rec(2, [99999], gacha_id="gacha_pickup_combatant_30120")]
    assert _banner(raw)["pool_ids"] == ["gacha_pickup_combatant_30115", "gacha_pickup_combatant_30120"]
