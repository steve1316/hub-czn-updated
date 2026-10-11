"""
Fill in the game client's text templates.

Card and effect descriptions in the client are templates such as `#result_coeff_ev_0# $Defense-Based Damage$`, where each
`#...#` placeholder reads a value from the card's linked effect rows. This module resolves them into plain text, the one
implementation every generator shares.

The values come from the effect ids a card lists in `link_skill_eff_id`, in order, so `ev_1` means the second linked
effect. Placeholders for values that only exist mid-battle (a running stack count, the current X) are dropped, along
with any brackets or `{cal}` expression they leave empty.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from scripts.datagen.client import Client, parse_list

# Effect kinds whose value is a percentage of a stat, so the plain number reads as a percent.
_PERCENT_EFFECTS = ("SKILL_EFF_DMG", "SKILL_EFF_SHIELD", "SKILL_EFF_CURE")

# An effect with a fixed-damage attribute deals a flat amount, so its value is not a percent.
_FLAT_ATTR = "DMG_ATTR_FIX"

# What the client calls the assigned combatant on partner cards.
_ASSIGNED_COMBATANT = "the assigned Combatant"

# Placeholders for values that only exist during a battle. They are removed rather than reported.
_BATTLE_ONLY = re.compile(r"^(n_.*|.*_stack_.*|.*vt_mul.*|.*vt_add.*|cs_tv_(?!max_).*|xvalue|hand_count.*|hand_connect.*|.*during_turn.*)$")

_TOKEN = re.compile(r"#([A-Za-z0-9_]+)#")
_CAL = re.compile(r"\{cal\}(.*?)\{/\}", re.DOTALL)
_TRIGGER = re.compile(r"\^(TRIGGER_[A-Za-z0-9_]+)\^")
_CARD_REF = re.compile(r"\^card@([A-Za-z0-9_]+)\^")
_KEYWORD = re.compile(r"\$([^$]*?)(?:#\d+)?\$")
_COLOR_MARKERS = re.compile(r"\[/?(?:fc|nfc|cfc|reverse_color)\]|\[/\]")
_TAGS = re.compile(r"<[^>]*>")
_EMPTY_BRACKETS = re.compile(r"\(\s*[%x×]?\s*\)")
_ARITHMETIC = re.compile(r"^[\d.\s*/+\-()]+$")
_TALENT_COUNT = re.compile(r"^(TALENT_[A-Z_]+?)_(\d+)$")

# Placeholder name -> (handler name, pattern). Checked in order, so the specific forms come before the general ones.
_HANDLERS: list[tuple[str, re.Pattern]] = [
    ("raw", re.compile(r"^(?:result_coeff_pct_off_ev|result_damage_pct_off)_(\d+)$")),
    ("percent", re.compile(r"^(?:result_coeff_ev|result_damage|result_damage_noecv|coeff_ev)_(\d+)$")),
    ("raw", re.compile(r"^(?:result_|final_|basic_|nrd_result_)?ev_(\d+)$")),
    ("raw", re.compile(r"^result_value_(\d+)$")),
    ("count", re.compile(r"^(?:result_|final_)?ecv_(\d+)$")),
    ("target_count", re.compile(r"^(?:result_|final_)?ectc_(\d+)$")),
    ("condition_percent", re.compile(r"^result_coeff_ecdv(\d)_(\d+)$")),
    ("condition", re.compile(r"^(?:basic_|result_)?ecdv(\d)_(\d+)$")),
    ("condition_count", re.compile(r"^ecdcv(\d)_(\d+)$")),
    ("run_pct", re.compile(r"^run_pct_(\d+)$")),
    ("status_value", re.compile(r"^cs_ev_(\d+)_(\d+)$")),
    ("status_count", re.compile(r"^cs_ecv_(\d+)_(\d+)$")),
    ("status_target_count", re.compile(r"^cs_ectc_(\d+)_(\d+)$")),
    ("status_condition", re.compile(r"^cs_ecdv(\d)_(\d+)_(\d+)$")),
    ("status_run_pct", re.compile(r"^cs_run_pct_(\d+)_(\d+)$")),
    ("status_max", re.compile(r"^cs_tv_max_(.+)$")),
    ("during_status_value", re.compile(r"^during_cs_ev_(\d+)_(\d+)$")),
    ("during_target_count", re.compile(r"^during_result_ectc_(\d+)_(\d+)$")),
    ("during_count", re.compile(r"^during_result_ecv_(\d+)_(\d+)$")),
    ("during_percent", re.compile(r"^during_result_coeff_ev_(\d+)_(\d+)$")),
    ("during_raw", re.compile(r"^during_(?:result_)?ev_(\d+)_(\d+)$")),
    ("leech", re.compile(r"^dmg_attr_leech_(shield|hp)_(\d+)$")),
    ("damage_kind", re.compile(r"^dmg_attr_class_(\d+)$")),
    ("effect_by_id", re.compile(r"^skill_eff_ev_(.+)$")),
    ("assigned", re.compile(r"^(?:match_comb_char|own_char)$")),
]


@dataclass
class Resolution:
    """A resolved description and anything in it that could not be resolved."""

    # The text with every resolvable placeholder filled in and the client markup removed. Lines are separated by "\n".
    text: str
    # Placeholders that had no value to read, still written into `text` as `#name#`.
    unresolved: list[str] = field(default_factory=list)


def format_number(value: str | float | int) -> str:
    """
    Render a client number the way the game does, without a trailing ".0".

    Args:
        value: A number, or the string the client stored it as.

    Returns:
        The number as text, or the input unchanged when it is not numeric (such as "MAX").
    """
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    return str(int(number)) if number.is_integer() else f"{number:g}"


class TemplateResolver:
    """Resolves client text templates against one extracted client."""

    def __init__(self, client: Client, talent_titles: dict[str, str] | None = None):
        """
        Args:
            client: The extracted game client.
            talent_titles: Titles for card traits the client has no title text for, keyed by talent id. Comes from the
                overrides file.
        """
        self.client = client
        self.talent_titles = talent_titles or {}

    # //////////////////////////////////////////////////////////////////////////////////////////////////
    # //////////////////////////////////////////////////////////////////////////////////////////////////
    # Cards

    def card_name(self, card_id: str) -> str | None:
        """
        A card's display name.

        Args:
            card_id: The card id, such as "c_1008_srt4".

        Returns:
            The English name, or None when the card or its name is unknown.
        """
        card = self.client.cards.get(card_id)
        return self.client.text(card.get("name")) if card else None

    def card_description(self, card_id: str, *, base_card_id: str | None = None) -> Resolution:
        """
        A card's description with its trait tags in front, such as "[Exhaust 2] Apply Blessing to 2 ...".

        Args:
            card_id: The card id.
            base_card_id: For an epiphany variant whose own description is "none", the card whose template it shares. The
                values still come from `card_id`'s own effects.

        Returns:
            The resolved description. Empty text when the card has no description at all.
        """
        card = self.client.cards.get(card_id, {})
        template = self.client.text(card.get("desc"))
        if template is None and base_card_id:
            template = self.client.text(self.client.cards.get(base_card_id, {}).get("desc"))
        if template is None:
            return Resolution("")
        resolution = self.resolve(template, parse_list(card.get("link_skill_eff_id")))
        tags = self.talent_tags(card)
        if tags:
            resolution.text = " ".join(f"[{tag}]" for tag in tags) + " " + resolution.text
        return resolution

    def talent_tags(self, card: dict) -> list[str]:
        """
        A card's traits as the game names them, such as ["Exhaust 2", "Retain"].

        Args:
            card: The card row.

        Returns:
            One title per trait, in the card's order. Traits with no known title are left out.
        """
        tags = []
        for talent in parse_list(card.get("talent")):
            talent = talent.strip("[")
            if talent == "TALENT_NONE":
                continue
            title = self.talent_title(talent)
            if title:
                tags.append(title)
        return tags

    def talent_title(self, talent: str) -> str | None:
        """
        The title of one card trait, with its count filled in for numbered traits like TALENT_EXHAUST_2.

        Args:
            talent: The talent id.

        Returns:
            The title, or None when neither the client nor the overrides name it.
        """
        if talent in self.talent_titles:
            return self.talent_titles[talent]
        title = self._tooltip_title(talent)
        if title:
            return title
        numbered = _TALENT_COUNT.match(talent)
        if numbered:
            base, count = numbered.groups()
            title = self._tooltip_title(f"{base}_N") or self._tooltip_title(base)
            if title:
                # Numbered titles read "Bind #bind_count#" or just "Exhaust".
                return _TOKEN.sub(count, title) if _TOKEN.search(title) else f"{title} {count}"
        return None

    def _tooltip_title(self, tooltip_id: str) -> str | None:
        tooltip = self.client.tooltips.get(tooltip_id)
        key = tooltip.get("title") if tooltip else f"tooltip@title@{tooltip_id}"
        return self.client.text(key)

    # //////////////////////////////////////////////////////////////////////////////////////////////////
    # //////////////////////////////////////////////////////////////////////////////////////////////////
    # Templates

    def resolve(self, template: str, effect_ids: list[str]) -> Resolution:
        """
        Fill in a template's placeholders and strip its markup.

        Args:
            template: The raw template from the text catalogue.
            effect_ids: The effect ids the owning card or row links to, in order.

        Returns:
            The resolved text, with lines separated by "\n", and the placeholders it could not fill.
        """
        effects = [self.client.effects.get(effect_id, {}) for effect_id in effect_ids]
        unresolved: list[str] = []

        def fill(match: re.Match) -> str:
            name = match.group(1)
            if _BATTLE_ONLY.match(name):
                return ""
            value = self._value(name, effects)
            if value is None:
                unresolved.append(name)
                return match.group(0)
            return value

        text = _TOKEN.sub(fill, template)
        text = _CAL.sub(self._calculate, text)
        text = _TRIGGER.sub(self._trigger, text)
        text = _CARD_REF.sub(lambda m: self.card_name(m.group(1)) or m.group(0), text)
        text = _KEYWORD.sub(lambda m: m.group(1), text)
        text = text.replace("<br>", "\n")
        text = _COLOR_MARKERS.sub("", text)
        text = _TAGS.sub("", text)
        text = _EMPTY_BRACKETS.sub("", text)
        return Resolution(text.strip(), unresolved)

    def _value(self, name: str, effects: list[dict]) -> str | None:
        for handler, pattern in _HANDLERS:
            match = pattern.match(name)
            if match:
                return getattr(self, f"_{handler}")(effects, *match.groups())
        return None

    def _calculate(self, match: re.Match) -> str:
        # `{cal}a*b{/}` multiplies two resolved values. If a battle-only value was dropped out of it, the whole
        # expression has nothing to show.
        expression = _TAGS.sub("", match.group(1)).strip()
        if not expression or "#" in expression or not _ARITHMETIC.match(expression):
            return ""
        try:
            return format_number(eval(expression, {"__builtins__": {}}, {}))  # noqa: S307 - digits and operators only
        except (SyntaxError, ZeroDivisionError, TypeError):
            return ""

    def _trigger(self, match: re.Match) -> str:
        title = self._tooltip_title(match.group(1))
        if not title:
            return match.group(0)
        return title if title.endswith(":") else f"{title}:"

    # //////////////////////////////////////////////////////////////////////////////////////////////////
    # //////////////////////////////////////////////////////////////////////////////////////////////////
    # Value handlers

    @staticmethod
    def _effect(effects: list[dict], index: str) -> dict | None:
        position = int(index)
        return effects[position] if position < len(effects) and effects[position] else None

    @staticmethod
    def _field(row: dict | None, name: str) -> str | None:
        if row is None:
            return None
        value = row.get(name)
        return None if value in (None, "", "none") else format_number(value)

    @staticmethod
    def _is_percent(effect: dict) -> bool:
        kind = effect.get("eff", "")
        return kind.startswith(_PERCENT_EFFECTS) and _FLAT_ATTR not in effect.get("eff_attr", "")

    def _as_percent(self, effect: dict | None, name: str) -> str | None:
        # One field of an effect, with a "%" added when the effect's value is a percentage of a stat.
        value = self._field(effect, name)
        if value is None:
            return None
        return f"{value}%" if self._is_percent(effect) else value

    def _raw(self, effects, index):
        return self._field(self._effect(effects, index), "eff_value")

    def _percent(self, effects, index):
        return self._as_percent(self._effect(effects, index), "eff_value")

    def _count(self, effects, index):
        return self._field(self._effect(effects, index), "eff_count_value")

    def _target_count(self, effects, index):
        return self._field(self._effect(effects, index), "eff_card_target_count")

    def _condition(self, effects, slot, index):
        return self._field(self._effect(effects, index), f"eff_condition_value_{slot}")

    def _condition_percent(self, effects, slot, index):
        return self._as_percent(self._effect(effects, index), f"eff_condition_value_{slot}")

    def _condition_count(self, effects, slot, index):
        return self._field(self._effect(effects, index), f"eff_condition_count_value_{slot}")

    def _run_pct(self, effects, index):
        value = self._field(self._effect(effects, index), "run_pct")
        return f"{value}%" if value is not None else None

    def _status_effect(self, effects: list[dict], index: str, slot: str) -> dict | None:
        # `cs_*_N_M`: effect N applies a status, and that status's own effect M holds the value.
        effect = self._effect(effects, index)
        statuses = parse_list(effect.get("link_cs_id")) if effect else []
        status = self.client.statuses.get(statuses[0]) if statuses else None
        linked = parse_list(status.get("link_skill_eff_id")) if status else []
        position = int(slot)
        return self.client.effects.get(linked[position]) if position < len(linked) else None

    def _status_value(self, effects, index, slot):
        return self._field(self._status_effect(effects, index, slot), "eff_value")

    def _status_count(self, effects, index, slot):
        return self._field(self._status_effect(effects, index, slot), "eff_count_value")

    def _status_target_count(self, effects, index, slot):
        return self._field(self._status_effect(effects, index, slot), "eff_card_target_count")

    def _status_condition(self, effects, condition_slot, index, slot):
        return self._field(self._status_effect(effects, index, slot), f"eff_condition_value_{condition_slot}")

    def _status_run_pct(self, effects, index, slot):
        value = self._field(self._status_effect(effects, index, slot), "run_pct")
        return f"{value}%" if value is not None else None

    def _status_max(self, effects, status_id):
        status = self.client.statuses.get(status_id)
        return self._field(status, "overlay_value_max")

    def _during_effect(self, effects: list[dict], index: str, slot: str) -> dict | None:
        effect = self._effect(effects, index)
        linked = effect.get(f"during_eff_{slot}_link_skill_eff_id") if effect else None
        return self.client.effects.get(linked) if linked and linked != "none" else None

    def _during_raw(self, effects, index, slot):
        return self._field(self._during_effect(effects, index, slot), "eff_value")

    def _during_percent(self, effects, index, slot):
        return self._as_percent(self._during_effect(effects, index, slot), "eff_value")

    def _during_target_count(self, effects, index, slot):
        return self._field(self._during_effect(effects, index, slot), "eff_card_target_count")

    def _during_count(self, effects, index, slot):
        return self._field(self._during_effect(effects, index, slot), "eff_count_value")

    def _during_status_value(self, effects, index, slot):
        during = self._during_effect(effects, index, slot)
        return self._status_value([during], "0", "0") if during else None

    def _leech(self, effects, kind, index):
        effect = self._effect(effects, index)
        match = re.search(rf"DMG_ATTR_LEECH_{kind.upper()}_PCT_(\d+)", effect.get("eff_attr", "")) if effect else None
        return match.group(1) if match else None

    def _damage_kind(self, effects, index):
        effect = self._effect(effects, index)
        on_defense = effect is not None and "DMG_ATTR_BASE_ON_DEF" in effect.get("eff_attr", "")
        return self.client.text("dmg_attr_class_base_on_def" if on_defense else "dmg_attr_class_base_on_atk")

    def _effect_by_id(self, effects, effect_id):
        return self._field(self.client.effects.get(effect_id), "eff_value")

    def _assigned(self, effects):
        return _ASSIGNED_COMBATANT
