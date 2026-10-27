"""
Tests for the per-character art target's choice of cards.
"""

from __future__ import annotations

import io
from pathlib import Path
from types import SimpleNamespace

from PIL import Image

from scripts.datagen.targets import card_art


def test_extra_cards_lists_created_mutated_and_collapse_but_not_shards():
    cards = {card_id: {} for card_id in ("c_30134_cre1", "c_30134_srt4_mut1", "c_30134_srt4_rsp1_mut1", "c_30134_srt4", "c_30135_cre1", "c_30134_col")}
    ctx = SimpleNamespace(client=SimpleNamespace(cards=cards))
    assert card_art.extra_cards(ctx, 30134) == ["c_30134_col", "c_30134_cre1", "c_30134_srt4_mut1"]


def _shipped_icons(tmp_path: Path, monkeypatch, shipped: tuple[str, ...], in_client: tuple[str, ...], refresh_art: bool) -> SimpleNamespace:
    """
    Ship small simulator icons in a temp repo, and give a temp client full-size illustrations for some of them.

    Args:
        tmp_path: The temp folder.
        monkeypatch: Points `card_art` at the temp repo.
        shipped: The icon stems the repo ships.
        in_client: The stems the client has an illustration for.
        refresh_art: Whether the run refreshes art.

    Returns:
        A run context over the temp client.
    """
    icons = tmp_path / "repo" / card_art.ICONS_DIR
    icons.mkdir(parents=True)
    for stem in shipped:
        Image.new("RGBA", (12, 18)).save(icons / f"{stem}.webp")
    art = tmp_path / "client" / "card_illustration"
    art.mkdir(parents=True)
    for stem in in_client:
        Image.new("RGBA", (42, 63)).save(art / f"{stem}.png")
    monkeypatch.setattr(card_art, "REPO_ROOT", tmp_path / "repo")
    return SimpleNamespace(client=SimpleNamespace(root=tmp_path / "client"), refresh_art=refresh_art)


def test_a_refresh_re_encodes_every_shipped_icon_with_a_client_source(tmp_path, monkeypatch):
    ctx = _shipped_icons(tmp_path, monkeypatch, ("job_00001", "potion_00001", "not_in_client"), ("job_00001", "potion_00001"), refresh_art=True)
    # An icon this run already encodes is left as it is.
    new_files = {card_art.ICONS_DIR / "potion_00001.webp": b"combatant"}
    card_art.refresh_shipped_icons(ctx, new_files)
    assert set(new_files) == {card_art.ICONS_DIR / "job_00001.webp", card_art.ICONS_DIR / "potion_00001.webp"}
    assert new_files[card_art.ICONS_DIR / "potion_00001.webp"] == b"combatant"
    assert Image.open(io.BytesIO(new_files[card_art.ICONS_DIR / "job_00001.webp"])).size == (42, 63)


def test_shipped_icons_are_left_alone_without_a_refresh(tmp_path, monkeypatch):
    ctx = _shipped_icons(tmp_path, monkeypatch, ("job_00001",), ("job_00001",), refresh_art=False)
    new_files = {}
    card_art.refresh_shipped_icons(ctx, new_files)
    assert new_files == {}
