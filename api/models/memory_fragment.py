"""
Memory Fragment data model for CZN.
Represents a single piece of equipment with all its properties.
"""

from dataclasses import dataclass, field
from typing import Optional

from .stat import Stat, SubstatRoll
from game_data import (
    STATS,
    EQUIPMENT_SLOTS,
    RARITY,
    SETS,
    LEGENDARY,
    MAX_LEVEL,
    MAX_LEVEL_PER_RARITY,
    substat_roll_range,
    get_character_name,
)


@dataclass
class MemoryFragment:
    id: int
    slot_name: str
    slot_num: int
    rarity: str
    rarity_num: int
    set_name: str
    set_id: int
    level: int
    locked: bool
    equipped_to: Optional[str]
    equipped_char_id: int
    main_stat: Optional[Stat] = None
    substats: list[Stat] = field(default_factory=list)
    gear_score: float = 0.0
    priority_score: float = 0.0
    potential_low: float = 0.0
    potential_high: float = 0.0

    @classmethod
    def from_json(cls, data: dict) -> "MemoryFragment":
        res_id = data["res_id"]
        res_str = str(res_id)
        slot_num = int(res_str[2])
        rarity_num = int(res_str[3])
        set_id = int(res_str[4:])

        main_stat = None
        substat_map = {}
        substat_rolls = {}

        for stat_data in data.get("stat_list", []):
            raw_stat = stat_data["stat"]
            stat_info = STATS.get(raw_stat, (raw_stat, raw_stat, False, 1, 1))
            slot = stat_data["slot"]
            stat_type = stat_data["type"]
            value = stat_data["value"]

            if slot == 0 and stat_type == 0:
                main_stat = Stat(name=stat_info[0], raw_name=raw_stat, value=value,
                                is_percentage=stat_info[2], is_main=True)
            else:
                if slot not in substat_map:
                    substat_map[slot] = Stat(
                        name=stat_info[0], raw_name=raw_stat, value=value,
                        is_percentage=stat_info[2], roll_count=1,
                        base_value=value if stat_type in [1, 2] else 0.0, rarity_num=rarity_num
                    )
                    substat_rolls[slot] = [(value, stat_type)]
                else:
                    substat_map[slot].value += value
                    substat_map[slot].roll_count += 1
                    substat_rolls[slot].append((value, stat_type))
                    if stat_type == 3:
                        substat_map[slot].upgrade_values.append(value)
                    elif stat_type in [1, 2] and substat_map[slot].base_value == 0:
                        substat_map[slot].base_value = value

        for slot, stat in substat_map.items():
            max_roll, min_roll = substat_roll_range(stat.raw_name, rarity_num)

            for value, stat_type in substat_rolls.get(slot, []):
                is_min = abs(value - min_roll) < 0.01
                is_max = abs(value - max_roll) < 0.01
                stat.rolls.append(SubstatRoll(value=value, stat_type=stat_type,
                                             is_min_roll=is_min, is_max_roll=is_max))

            if stat.base_value == 0 and stat.rolls:
                stat.base_value = stat.rolls[0].value

        substats = list(substat_map.values())
        char_id = data.get("char_res_id", 0)
        equipped_to = get_character_name(char_id)
        set_info = SETS.get(set_id, {"name": f"Unknown({set_id})"})
        set_name = set_info["name"] if isinstance(set_info, dict) else set_info

        return cls(
            id=data["id"], slot_name=EQUIPMENT_SLOTS.get(slot_num, f"Unknown({slot_num})"),
            slot_num=slot_num, rarity=RARITY.get(rarity_num, f"Unknown({rarity_num})"),
            rarity_num=rarity_num, set_name=set_name, set_id=set_id,
            level=data.get("level", 0), locked=data.get("lock", False),
            equipped_to=equipped_to, equipped_char_id=char_id,
            main_stat=main_stat, substats=substats,
        )

    def calculate_base_score(self) -> float:
        base_score = 0.0
        for sub in self.substats:
            stat_info = STATS.get(sub.raw_name, (sub.name, sub.name, sub.is_percentage, 1, 1))
            max_roll = stat_info[3]
            normalized = sub.value / (max_roll * sub.roll_count) if max_roll > 0 else 0
            base_score += normalized * sub.roll_count
        self.gear_score = round(base_score * 10, 1)
        return self.gear_score

    def calculate_priority_score(self, priorities: dict[str, int]) -> float:
        priority_score = 0.0
        for sub in self.substats:
            stat_info = STATS.get(sub.raw_name, (sub.name, sub.name, sub.is_percentage, 1, 1))
            max_roll = stat_info[3]
            normalized = sub.value / (max_roll * sub.roll_count) if max_roll > 0 else 0
            priority = priorities.get(sub.name, 0)
            priority_score += normalized * priority * sub.roll_count
        self.priority_score = round(priority_score * 10, 1)
        return self.priority_score

    def calculate_potential(self) -> tuple[float, float]:
        # Every level adds one roll, either a new substat or an upgrade. Each roll is scored on the Legendary scale, so a lower rarity
        # gains less per roll.
        remaining_rolls = max(0, MAX_LEVEL_PER_RARITY.get(self.rarity_num, MAX_LEVEL) - self.level)
        roll_scores = []
        for sub in self.substats:
            legend_max = substat_roll_range(sub.raw_name, LEGENDARY)[0]
            if legend_max > 0:
                best, worst = substat_roll_range(sub.raw_name, self.rarity_num)
                roll_scores.append((best / legend_max * 10, worst / legend_max * 10))

        if remaining_rolls == 0 or not roll_scores:
            self.potential_low = self.gear_score
            self.potential_high = self.gear_score
            return (self.gear_score, self.gear_score)

        low_gain = remaining_rolls * min(worst for _, worst in roll_scores)
        high_gain = remaining_rolls * max(best for best, _ in roll_scores)

        self.potential_low = round(self.gear_score + low_gain, 1)
        self.potential_high = round(self.gear_score + high_gain, 1)
        return (self.potential_low, self.potential_high)

    def get_total_stats(self) -> dict[str, float]:
        stats = {}
        if self.main_stat:
            stats[self.main_stat.name] = stats.get(self.main_stat.name, 0) + self.main_stat.value
        for sub in self.substats:
            stats[sub.name] = stats.get(sub.name, 0) + sub.value
        return stats