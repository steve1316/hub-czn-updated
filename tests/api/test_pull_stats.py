"""Pull tracker stats: 50/50 wins and losses, pity per banner, luck against the published rates, and the stale marker."""

import json

from api.routes.rescue import _luck_percentile, _process_records, _ssr_rate

# A real 5-star combatant id.
FIVE = 1004
COMBATANT_POOL = "gacha_pickup_combatant_30115"
PARTNER_POOL = "gacha_pickup_supporter_30116"
STANDARD_POOL = "gacha_general"


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


def test_fifty_fifty_skips_the_guaranteed_five_star_after_a_loss():
    raw = [_rec(1, [FIVE, FIVE, FIVE], prisms=[0, 1, 1])]
    stats = _banner(raw)["stats"]
    assert stats["losses_50_50"] == 1
    assert stats["wins_50_50"] == 1
    assert stats["win_rate_50_50"] == 0.5


def test_partner_and_standard_banners_have_no_fifty_fifty():
    for pool, prisms in ((PARTNER_POOL, [1, 1]), (STANDARD_POOL, [0, 0])):
        stats = _banner([_rec(1, [FIVE, FIVE], prisms=prisms, gacha_id=pool)])["stats"]
        assert stats["five_star"] == 2
        assert stats["wins_50_50"] == 0
        assert stats["losses_50_50"] == 0


def test_pity_curve_matches_the_published_combined_rate():
    assert round(_ssr_rate() * 100, 5) == 2.14343


def test_luck_percentile_follows_the_pity_curve():
    # Pity guarantees a 5-star by the 70th pull, so none in 100 pulls is impossible.
    assert _luck_percentile(0, 100) == 0.0
    assert _luck_percentile(6, 100) > 95
    assert 45 < _luck_percentile(21, 1000) < 60
    assert _luck_percentile(0, 0) is None


def test_banner_reports_luck_and_the_rate_it_used():
    stats = _banner([_rec(1, [FIVE] + [99999] * 9)])["stats"]
    assert stats["luck_percentile"] is not None
    assert stats["ssr_rate"] == round(_ssr_rate(), 7)


def test_banner_lists_every_pool_it_covers():
    raw = [_rec(1, [99999], gacha_id="gacha_pickup_combatant_30115"), _rec(2, [99999], gacha_id="gacha_pickup_combatant_30120")]
    assert _banner(raw)["pool_ids"] == ["gacha_pickup_combatant_30115", "gacha_pickup_combatant_30120"]


def test_banners_use_the_in_game_category_names():
    pools = {
        "gacha_pickup_combatant_30115": "Seasonal Combatant Rescue Rate-Up",
        "gacha_pickup_supporter_30116": "Seasonal Partner Rescue Rate-Up",
        "gacha_pickup_combatant_1062_1": "Normal Combatant Rescue Rate-Up",
        "gacha_pickup_supporter_30045_1": "Normal Partner Rescue Rate-Up",
        "gacha_general": "Normal Combatant Rescue",
        "gacha_general_supporter": "Normal Partner Rescue",
        "gacha_card_factor": "Observe Prism Module",
    }
    raw = [_rec(i, [99999], gacha_id=pool) for i, pool in enumerate(pools)]
    names = {banner["pool_ids"][0]: banner["banner_name"] for banner in _process_records(raw)}
    assert names == pools


def test_an_older_rate_up_shares_the_seasonal_category_and_its_pity():
    # Pre-seasonal rate-up pools count toward the same server pity, so they are one category.
    raw = [_rec(1, [99999], gacha_id="gacha_pickup_combatant_1062"), _rec(2, [99999], gacha_id=COMBATANT_POOL, ts=2000)]
    banners = _process_records(raw, {"pity": {"gacha_pity_pickup_combatant": {"pity_ssr_count": 7}}})
    assert len(banners) == 1
    assert banners[0]["banner_name"] == "Seasonal Combatant Rescue Rate-Up"
    assert banners[0]["pity_current"] == 7


def test_normal_combatant_rate_up_has_its_own_pity_and_a_fifty_fifty():
    raw = [_rec(1, [FIVE, 99999, FIVE], prisms=[1, 0, 0], gacha_id="gacha_pickup_combatant_1062_1")]
    banner = _banner(raw, {"pity": {"gacha_pity_genal_p_combatant": {"pity_ssr_count": 4}}})
    assert banner["pity_current"] == 4
    assert banner["stats"]["wins_50_50"] == 1
    assert banner["stats"]["losses_50_50"] == 1


def test_a_pool_newer_than_the_shipped_table_borrows_the_category_of_a_pool_shaped_like_it():
    seasonal = _banner([_rec(1, [FIVE, 99999], prisms=[0, 0], gacha_id="gacha_pickup_combatant_99999")])
    assert seasonal["banner_name"] == "Seasonal Combatant Rescue Rate-Up"
    assert seasonal["stats"]["losses_50_50"] == 1
    assert _banner([_rec(1, [99999], gacha_id="gacha_pickup_supporter_99999_1")])["banner_name"] == "Normal Partner Rescue Rate-Up"
    assert _banner([_rec(1, [99999], gacha_id="gacha_mystery_pool")])["banner_name"] == "Gacha Mystery Pool"
