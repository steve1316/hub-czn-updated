"""
Tests for the `items` datagen target, on a tiny fixture client written to a temp folder.

The relic-only value tokens are checked on their own, then a whole build checks the row filter, the slot and rarity
mapping, the output order and how overrides land.
"""

from __future__ import annotations

import json
from pathlib import Path

from scripts.datagen.overrides import Overrides
from scripts.datagen.runner import Context
from scripts.datagen.targets import items

# An image the app already ships, so the missing-image check passes for it.
SHIPPED_IMAGE = "itens/item_0001.webp"

TEXT = {
    "relic@name@eq_pub_001": "Second Method",
    "relic@s1_description@eq_pub_001": "+<cc>#rev_0_0#</>% Damage Amount to $Extra Attack$s",
    "relic@name@eq_pub_042": "Sphere of Randomness",
    "relic@s1_description@eq_pub_042": "+<cc>#nbev_0#</>% max HP<br>At the start of battle, +<cc>1</> $AP$",
    "relic@name@eq_dpt_test_001": "Test Sword",
    "relic@s1_description@eq_dpt_test_001": "Test",
    "relic@name@relic_001": "Not Equipment",
    "relic@s1_description@relic_001": "Test",
    "relic@name@eq_ds02_004": "Vine Camouflage",
    "relic@s1_description@eq_ds02_004": "1 $Evasion$ (#rev_0_0# times per battle)<br>#rev_1_0# more",
}


# //////////////////////////////////////////////////////////////////////////////////////////////////
# //////////////////////////////////////////////////////////////////////////////////////////////////
# Helpers


def _relic(relic_id: str, relic_type: str, rarity: str = "RARITY_RARE", cs_values: str = "[]", nb_values: str = "[]") -> dict:
    """
    One relic row with only the columns the target reads.

    Args:
        relic_id: The row id.
        relic_type: Such as "EQUIP_WEAPON".
        rarity: Such as "RARITY_LEGEND".
        cs_values: The `s1_cs_value` cell.
        nb_values: The `s1_nb_eff_value` cell.

    Returns:
        The row.
    """
    return {
        "id": relic_id,
        "relic_type": relic_type,
        "rarity": rarity,
        "name": f"relic@name@{relic_id}",
        "s1_description": f"relic@s1_description@{relic_id}",
        "s1_cs_value": cs_values,
        "s1_nb_eff_value": nb_values,
    }


def _context(root: Path, overrides: Overrides) -> Context:
    """
    A run context over a fixture client.

    Args:
        root: The temp folder to write the client into.
        overrides: The `items` overrides to use instead of the real file.

    Returns:
        The context.
    """
    (root / "db").mkdir()
    (root / "text" / "en").mkdir(parents=True)
    public = [
        _relic("eq_pub_001", "EQUIP_WEAPON", "RARITY_LEGEND", cs_values="[35]"),
        _relic("relic_001", "RELIC"),
        _relic("eq_dpt_test_001", "EQUIP_WEAPON"),
        _relic("eq_pub_042", "EQUIP_ACC", "RARITY_UNIQUE", nb_values="[10]"),
    ]
    disaster = [_relic("eq_ds02_004", "EQUIP_ARMOR", cs_values="[2]")]
    (root / "db" / "relic@relic.json").write_text(json.dumps(public), encoding="utf-8")
    (root / "db" / "relic(disaster)@relic.json").write_text(json.dumps(disaster), encoding="utf-8")
    (root / "text" / "en" / "text.json").write_text(json.dumps([{"id": key, "text": text} for key, text in TEXT.items()]), encoding="utf-8")
    ctx = Context(root)
    ctx._overrides[items.NAME] = overrides
    return ctx


def _built(ctx: Context) -> tuple[list[dict], list[str]]:
    """
    Run the target and read its output back.

    Args:
        ctx: The run context.

    Returns:
        The items in file order, and the issue messages.
    """
    result = items.build(ctx)
    return json.loads(result.files[items.ITEMS_PATH]), [issue.message for issue in result.issues]


# //////////////////////////////////////////////////////////////////////////////////////////////////
# //////////////////////////////////////////////////////////////////////////////////////////////////
# Relic value tokens


def test_status_value_reads_the_nth_status_term_value():
    row = {"s1_cs_value": "[3,80]"}
    assert items.fill_relic_values("#rev_0_0#% HP and #rev_1_0#% Shield", row) == "3% HP and 80% Shield"


def test_status_value_ignores_the_effect_index():
    assert items.fill_relic_values("#rev_0_1#", {"s1_cs_value": "[1]"}) == "1"


def test_passive_value_reads_the_nth_passive_value():
    row = {"s1_nb_eff_value": "[1,10]"}
    assert items.fill_relic_values("+15% Attack, +#nbev_1#% Max HP", row) == "+15% Attack, +10% Max HP"


def test_out_of_range_token_is_left_for_the_resolver_to_report():
    assert items.fill_relic_values("#rev_2_0# and #nbev_0#", {"s1_cs_value": "[5]"}) == "#rev_2_0# and #nbev_0#"


def test_other_tokens_are_untouched():
    assert items.fill_relic_values("#result_ev_0#", {"s1_cs_value": "[5]"}) == "#result_ev_0#"


# //////////////////////////////////////////////////////////////////////////////////////////////////
# //////////////////////////////////////////////////////////////////////////////////////////////////
# Whole build


def test_build_keeps_equipment_in_table_order(tmp_path):
    output, issues = _built(_context(tmp_path, Overrides(items.NAME, exclude=["eq_dpt_test_*"])))
    assert [item["id"] for item in output] == ["eq_pub_001", "eq_pub_042", "eq_ds02_004"]


def test_build_maps_fields_and_resolves_text(tmp_path):
    output, _ = _built(_context(tmp_path, Overrides(items.NAME, exclude=["eq_dpt_test_*"])))
    first, second = output[0], output[1]
    assert first == {
        "id": "eq_pub_001",
        "name": "Second Method",
        "rarity": "Legendary",
        "slot": "Weapon",
        "tags": [],
        "description": {"en": "+35% Damage Amount to Extra Attacks."},
        "image_path": "",
    }
    assert (second["slot"], second["rarity"]) == ("Accessory", "Unique")
    assert second["description"] == {"en": "+10% max HP. At the start of battle, +1 AP."}


def test_build_reports_unresolved_tokens(tmp_path):
    output, issues = _built(_context(tmp_path, Overrides(items.NAME, exclude=["eq_dpt_test_*"])))
    assert output[2]["description"] == {"en": "1 Evasion (2 times per battle). #rev_1_0# more."}
    assert issues == ["items: eq_ds02_004 has unresolved placeholders ['rev_1_0']"]


def test_an_override_silences_unresolved_tokens(tmp_path):
    fixed = {"en": "1 Evasion (2 times per battle)."}
    overrides = Overrides(items.NAME, entries={"eq_ds02_004": {"description": fixed, "_why": "test"}}, exclude=["eq_dpt_test_*"])
    output, issues = _built(_context(tmp_path, overrides))
    assert output[2]["description"] == fixed
    assert issues == []


def test_build_applies_overrides_and_checks_images(tmp_path):
    overrides = Overrides(
        items.NAME,
        entries={
            "eq_pub_001": {"image_path": SHIPPED_IMAGE, "_why": "test"},
            "eq_pub_042": {"image_path": "itens/no_such_image.webp", "_why": "test"},
        },
        exclude=["eq_dpt_test_*"],
    )
    output, issues = _built(_context(tmp_path, overrides))
    assert output[0]["image_path"] == SHIPPED_IMAGE
    assert "items: eq_pub_042 points at a missing image itens/no_such_image.webp" in issues
    assert not any("eq_pub_001" in issue for issue in issues)
