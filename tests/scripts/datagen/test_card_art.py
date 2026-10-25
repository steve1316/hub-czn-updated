"""
Tests for the per-character art target's choice of cards.
"""

from __future__ import annotations

from types import SimpleNamespace

from scripts.datagen.targets import card_art


def test_extra_cards_lists_created_mutated_and_collapse_but_not_shards():
    cards = {card_id: {} for card_id in ("c_30134_cre1", "c_30134_srt4_mut1", "c_30134_srt4_rsp1_mut1", "c_30134_srt4", "c_30135_cre1", "c_30134_col")}
    ctx = SimpleNamespace(client=SimpleNamespace(cards=cards))
    assert card_art.extra_cards(ctx, 30134) == ["c_30134_col", "c_30134_cre1", "c_30134_srt4_mut1"]
