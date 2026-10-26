import { describe, it, expect } from "vitest"
import type { MemoryFragment, Stat } from "@/lib/types"
import { compareFragments } from "./fragment-sort"

function stat(name: string, value: number): Stat {
  return { name, value, formatted: `${name} ${value}`, is_percentage: true, roll_count: 1 }
}

function fragment(id: number, main: Stat | null, substats: Stat[] = []): MemoryFragment {
  return {
    id, slot_num: 1, slot_name: "", set_id: 1, set_name: "", rarity_num: 4, rarity: "", level: 5, locked: false,
    equipped_to: null, gear_score: 0, priority_score: 0, potential_low: 0, potential_high: 0, main_stat: main, substats,
  }
}

function sortIds(list: MemoryFragment[], key: string, dir: "asc" | "desc"): number[] {
  return [...list].sort((a, b) => compareFragments(a, b, key, dir)).map(f => f.id)
}

describe("compareFragments", () => {
  it("orders a stat column by name, then by value as a number", () => {
    const list = [fragment(1, stat("ATK%", 12.5)), fragment(2, stat("CRate", 3)), fragment(3, stat("ATK%", 5.7))]
    expect(sortIds(list, "main", "asc")).toEqual([3, 1, 2])
    expect(sortIds(list, "main", "desc")).toEqual([2, 1, 3])
  })

  it("keeps fragments without that substat at the bottom either way", () => {
    const list = [fragment(1, null, []), fragment(2, null, [stat("HP%", 2)]), fragment(3, null, [stat("HP%", 4)])]
    expect(sortIds(list, "sub1", "asc")).toEqual([2, 3, 1])
    expect(sortIds(list, "sub1", "desc")).toEqual([3, 2, 1])
  })

  it("sorts the score by the weighted score when there is one", () => {
    const a = { ...fragment(1, null), gear_score: 50, priority_score: 10 }
    const b = { ...fragment(2, null), gear_score: 20, priority_score: 0 }
    expect(sortIds([a, b], "gs", "asc")).toEqual([a.id, b.id])
  })
})
