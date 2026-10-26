"""
Tests for reading a guide card picture: which epiphany its text matches, the OCR read itself and the god emblem.
"""

from __future__ import annotations

import io

import pytest
from PIL import Image, ImageDraw, ImageFont

from scripts.datagen import card_text
from scripts.datagen.card_text import Match, match_epiphany, match_god, read_card_text
from scripts.datagen.epiphany import Extra, Variant

BRAND_4 = Variant(0, "c_1_uni3", "Blade of the Cycle", 1, "Deal 240% damage. Apply 4 Brand of the Cycle")
BRAND_1 = Variant(1, "c_1_uni3_rsp1", "Blade of the Cycle I", 1, "Deal 300% damage. Apply 1 Brand of the Cycle")
VULNERABLE = Extra("com_0065", None, "Apply 1 Vulnerable to the target.")


def _png(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, "PNG")
    return buffer.getvalue()


def test_match_epiphany_picks_the_level_and_extra():
    # As read off the real C11 picture. Letters alone tie with level 1, the numbers settle it.
    text = "240% Damage 4 Brand of the Cycle Apply 1 Vulnerable to the target"
    assert match_epiphany(text, [BRAND_4, BRAND_1], [VULNERABLE]) == Match(0, VULNERABLE)


def test_match_epiphany_refuses_a_close_call():
    twin = Variant(1, "c_1_uni3_rsp1", "Blade of the Cycle I", 1, BRAND_4.text)
    assert match_epiphany("Deal 240% damage. Apply 4 Brand of the Cycle", [BRAND_4, twin], []) is None


def test_match_epiphany_refuses_a_close_call_on_the_added_line():
    # The digit that tells these two lines apart was not read.
    weaken_2, weaken_1 = Extra("com_0050", None, "Apply 2 Weaken"), Extra("com_0055", None, "Apply 1 Weaken")
    assert match_epiphany(f"{BRAND_4.text} Apply Weaken", [BRAND_4], [weaken_2, weaken_1]) is None
    # Lines with the same text are one line, so they are no reason to refuse.
    twin = Extra("com_0099", None, VULNERABLE.text)
    assert match_epiphany(f"{BRAND_4.text} {VULNERABLE.text}", [BRAND_4], [VULNERABLE, twin]) == Match(0, VULNERABLE)


def test_match_epiphany_refuses_garbage():
    assert match_epiphany("zzzz", [BRAND_4, BRAND_1], [VULNERABLE]) is None


def test_match_epiphany_falls_back_on_the_percentages():
    # An older picture of Opening Found V, worded before a patch. Only level V has exactly these percentages.
    found = [
        Variant(0, "c_1040_srt4", "Opening Found", 1, "[Retain] 160% Damage. Retain: Add 1 Hit(s) for 1 turn."),
        Variant(3, "c_1040_srt4_rsp3", "Opening Found III", 1, "[Retain] 110% Damage. Retain: Add 2 Hit(s) for 1 turn."),
        Variant(5, "c_1040_srt4_rsp5", "Opening Found V", 1, "When a card of this unit is Retained, 150% Extra Attack to random enemies."),
    ]
    text = "When Retain owned cards, 150%6 Extra Attack to random cnemies"
    assert match_epiphany(text, found, [VULNERABLE]) == Match(5, None)
    # A god's emblem means a divine line the percentages cannot place.
    assert match_epiphany(text, found, [Extra("div_0098", "Nihilum", "Reduce Cost of this card by 1.")]) is None


def test_match_epiphany_percentages_must_pick_one_level():
    shield = [
        Variant(1, "c_1_uni3_rsp1", "Firepower I", 1, "150% Shield. +120% Damage Amount to the next Attack Card."),
        Variant(4, "c_1_uni3_rsp4", "Firepower IV", 1, "150% Shield. +120% Damage Amount to the next Attack Card activated."),
    ]
    assert match_epiphany("+150% Shicld +120% Attack Damage of next own card", shield, []) is None
    assert match_epiphany("Draw 2 cards", [BRAND_4, BRAND_1], []) is None
    # Far more text than the level means an added line the percentages cannot place.
    assert match_epiphany("+150% Shicld +120% Attack Damage of next own card used. For 1 turn, gain 2 Morale. Reduce Cost of this card by 1", shield[:1], []) is None


def test_read_card_text_reads_and_caches(monkeypatch):
    pytest.importorskip("rapidocr_onnxruntime")
    image = Image.new("RGB", (246, 364), (0, 0, 0))
    ImageDraw.Draw(image).text((12, 260), "Deal 120% damage", fill=(255, 255, 255), font=ImageFont.load_default(size=24))
    data = _png(image)
    cache: dict[str, str] = {}
    assert "deal" in read_card_text(data, cache).lower()

    def fail():
        raise AssertionError("a cached picture should not be read again")

    monkeypatch.setattr(card_text, "_ocr", fail)
    assert "deal" in read_card_text(data, cache).lower()


def test_match_god_ignores_the_regular_emblem():
    plain = Image.new("RGB", card_text.RENDER_SIZE, (90, 90, 90))
    assert match_god(plain) is None
    icon = Image.open(card_text.GOD_ICON_DIR / "nihilum.webp").convert("RGBA").resize((22, 22))
    marked = plain.copy()
    marked.paste(icon, (4, 30), icon)
    assert match_god(marked) == "Nihilum"


FRACTURE_TEXT = "[Unique] When Fracture or Agony is activated through a Targeting Card, 2 Fracture and 3 Agony to the target ({} time(s) per turn)."
CRAVINGS = [
    Variant(0, "c_30117_uni3", "Insatiable Cravings", 1, FRACTURE_TEXT.format(3)),
    Variant(1, "c_30117_uni3_rsp1", "Insatiable Cravings I", 1, FRACTURE_TEXT.format(3).replace("[Unique]", "[Unique] [Initiation]")),
    Variant(2, "c_30117_uni3_rsp2", "Insatiable Cravings II", 1, FRACTURE_TEXT.format(4)),
]


def test_match_epiphany_reads_one_changed_number_on_a_long_text():
    # Levels 0 and 2 differ only by "3" against "4 time(s) per turn". The second read has the circled 3 (u2462) the picture shows.
    read = "WhenFractureor Agony is activated through a Targeting Card,2Fracture and3 Agony to the target {} time(s) per tum)"
    assert match_epiphany(read.format("4"), CRAVINGS, []) == Match(2, None)
    assert match_epiphany(read.format("\u2462"), CRAVINGS, []) == Match(0, None)


def test_match_epiphany_mends_a_zero_read_as_an_o():
    # An older picture, worded "until used", with the "400%" read as "40o%". Level 1 shares every word and only says 600%.
    brand = [
        Variant(0, "c_1064_uni1", "Brand of Annihilation", 3, "400% Damage to all enemies. When a card is Exhausted, decrease Cost of this card by 1 for 1 turn until activated."),
        Variant(1, "c_1064_uni1_rsp1", "Brand of Annihilation I", 3, "600% Damage to all enemies. When a card is Exhausted, decrease Cost of this card by 1 for 1 turn until activated."),
    ]
    morale = Extra("com_0070", None, "For 1 turn, gain 4 Morale")
    read = "40o%Damagetoallenemles WnenacsrdsExosusteo dacrcareCostorthlsoardby1for 1tumurkused For1trn9an4Mole"
    assert match_epiphany(read, brand, [morale, Extra("com_0071", None, "Draw 1 Common Card(s)")]) == Match(0, None)


def test_match_epiphany_reads_a_picture_worded_common_for_neutral():
    # Quantum Seed with a divine line. The picture says "Common Card" where the client text says "Neutral Card".
    seed = [
        Variant(0, "c_30084_srt4", "Quantum Seed", 1, "Heal 100%. Create 2 Archetype card(s) in Draw Pile. Draw 1 of them."),
        Variant(1, "c_30084_srt4_rsp1", "Quantum Seed I", 1, "Heal 150%. Create 3 Archetype card(s) in Draw Pile. Draw 1 of them."),
    ]
    neutral = Extra("div_0015", "Caligo", "Treated as a Neutral Card. Draw 1 Neutral Card(s).")
    read = "[Duplicated] He81180% Create 3 Archetype card(s) in DrawPia Draw 1ofthcm TreatedasaCommonCard Drew 1 Common Card(s)"
    assert match_epiphany(read, seed, [neutral, Extra("div_0008", "Caligo", "Reduce Cost of this card by 1.")]) == Match(1, neutral)
