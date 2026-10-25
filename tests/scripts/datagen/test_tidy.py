"""
Tests for the fixed cleanup pass every generated description goes through.
"""

from __future__ import annotations

from scripts.datagen.tidy import TidyRules, tidy

RULES = TidyRules(typos={"Rythmn": "Rhythm"}, casing={"Defense-based": "Defense-Based"}, soften={"shit": "bad", "shitty": "bad"})


def test_lines_become_sentences():
    assert tidy("120% Damage\n100% Shield\n1 Silver Veil", RULES) == "120% Damage. 100% Shield. 1 Silver Veil."


def test_existing_end_punctuation_is_kept():
    assert tidy("Dark Mist Stance:\nIncrease Damage Amount by 100%", RULES) == "Dark Mist Stance: Increase Damage Amount by 100%."


def test_a_comma_or_a_lower_case_start_continues_the_sentence():
    text = "Draw 2\nFor each Attack Card Drawn,\n100% Coordinated Attack\n+30% Damage\nfor each Lux Engraving"
    assert tidy(text, RULES) == "Draw 2. For each Attack Card Drawn, 100% Coordinated Attack. +30% Damage for each Lux Engraving."


def test_whitespace_and_space_before_punctuation_collapse():
    assert tidy("Increase Damage  by  20 %", RULES) == "Increase Damage by 20%."


def test_double_percent_collapses():
    assert tidy("100%% Coordinated Attack", RULES, sentences=False) == "100% Coordinated Attack"


def test_a_number_glued_to_a_word_is_separated():
    assert tidy("3Vulnerable for 1turn", RULES, sentences=False) == "3 Vulnerable for 1 turn"


def test_ordinals_and_ids_are_not_separated():
    assert tidy("the 2nd card, job_00533, HA-00", RULES, sentences=False) == "the 2nd card, job_00533, HA-00"


def test_a_dangling_hit_count_sign_is_dropped():
    assert tidy("120% Damage x\nAdd 1 Hit", RULES, sentences=False) == "120% Damage\nAdd 1 Hit"


def test_typos_and_casing_keep_a_leading_capital():
    assert tidy("rythmn and Rythmn deal Defense-based Damage", RULES) == "rhythm and Rhythm deal Defense-Based Damage."


def test_words_inside_other_words_are_not_replaced():
    assert tidy("Rythmns", RULES, sentences=False) == "Rythmns"


def test_softening_only_applies_when_asked():
    assert tidy("This is so shit", RULES) == "This is so shit."
    assert tidy("This is so shit, Shitty even", RULES, soften=True) == "This is so bad, Bad even."


def test_rules_file_loads():
    rules = TidyRules.load()
    assert rules.typos and rules.soften
