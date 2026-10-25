"""
Tests for the epiphany catalog: display names, the cost a card shows, and the Rossweisse variants from the real client.
"""

from __future__ import annotations

import pytest

from api.client_db import client_output_dir, have_client_db, have_client_text
from scripts.datagen.epiphany import Extra, card_cost, epiphany_name, variants
from scripts.datagen.runner import Context

REDUCE_COST = Extra("div_0098", "Nihilum", "Reduce Cost of this card by 1.")


def test_epiphany_name_prefers_a_distinct_game_name():
    assert epiphany_name("Flicker Blade", 5, "Flicker Blade (Unbound)") == "Flicker Blade (Unbound)"
    assert epiphany_name("Sword Resonance", 2, None) == "Sword Resonance II"
    assert epiphany_name("Sword Resonance", 2, "Sword Resonance") == "Sword Resonance II"


def test_card_cost_reduces_and_keeps_x():
    assert card_cost(1, REDUCE_COST) == 0
    assert card_cost(0, REDUCE_COST) == 0
    assert card_cost(-1, REDUCE_COST) == -1
    assert card_cost(2, None) == 2
    assert card_cost(2, Extra("com_0065", None, "Apply 1 Vulnerable to the target.")) == 2


@pytest.mark.skipif(not (have_client_db() and have_client_text()), reason="game client DB or its text catalogue not available")
def test_rossweisse_variants():
    ctx = Context(client_output_dir())
    assert [variant.cost for variant in variants(ctx, "c_30134_uni1")] == [1, 1, 1, 0, 1, 1]
    assert [variant.level for variant in variants(ctx, "c_30134_uni1")] == [0, 1, 2, 3, 4, 5]
    assert variants(ctx, "c_30134_uni1")[2].name == "Sword Resonance II"
    assert variants(ctx, "c_30134_srt4")[5].name == "Flicker Blade (Unbound)"
    assert variants(ctx, "c_30134_srt4_mut1")[5].name == "Shard:Light (Unbound)"
    assert variants(ctx, "c_30134_cre1") == []
    assert variants(ctx, "c_30134_uni1")[0].text
