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


def test_match_epiphany_refuses_garbage():
    assert match_epiphany("zzzz", [BRAND_4, BRAND_1], [VULNERABLE]) is None


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
