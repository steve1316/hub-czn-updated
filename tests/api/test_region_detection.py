"""
Region detection reads the host the game connected to.

It used to look for a `world_id` field in the character payload. The server never sends one, so it
always returned None and the region was never detected - the user's manual pick was all there was.
"""

from types import SimpleNamespace

import pytest

from api.capture.addon import Addon, HOST_TO_REGION

GLOBAL_HOST = "live-g-czn-gamemjc2n1x.game.playstove.com"
ASIA_HOST = "live-czn-gamelksj2nmf.game.playstove.com"


@pytest.fixture
def addon(tmp_path):
    return Addon(tmp_path)


def test_both_regions_are_mapped():
    assert HOST_TO_REGION[GLOBAL_HOST] == "global"
    assert HOST_TO_REGION[ASIA_HOST] == "asia"


@pytest.mark.parametrize("host,expected", [(GLOBAL_HOST, "global"), (ASIA_HOST, "asia")])
def test_region_comes_from_the_host_that_was_seen(addon, host, expected):
    addon.seen_hosts.add(host)
    assert addon._detect_region() == expected


def test_no_region_before_anything_connects(addon):
    assert addon._detect_region() is None


def test_an_unrelated_host_does_not_produce_a_region(addon):
    addon.seen_hosts.add("cdn.example.com")
    assert addon._detect_region() is None


def test_world_id_is_no_longer_consulted(addon):
    # Regression: the old implementation keyed off character_data["user"]["world_id"], which does
    # not exist in a real capture. Setting it must not bring that behaviour back.
    addon.character_data = {"user": {"world_id": "world_live_asia"}}
    assert addon._detect_region() is None

    addon.seen_hosts.add(GLOBAL_HOST)
    assert addon._detect_region() == "global"
