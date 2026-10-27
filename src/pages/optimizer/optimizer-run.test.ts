import { describe, it, expect } from "vitest"
import { runnableConfig } from "./optimizer-run"
import type { OptimizerConfig } from "@/lib/types"

const BASE: OptimizerConfig = {
  char_name: "Renoa",
  four_piece_sets: [],
  two_piece_sets: [],
  main_stat_4: null,
  main_stat_5: null,
  main_stat_6: null,
  top_percent: 100,
  include_equipped: true,
  excluded_heroes: [],
  max_results: 10,
  stat_weights: null,
  allow_wildcards: false,
  min_priority_substats: 0,
  stat_constraints: null,
}

describe("runnableConfig", () => {
  it("drops weights that are all zero", () => {
    expect(runnableConfig({ ...BASE, stat_weights: { ATK: 0, CRate: 0 } }).stat_weights).toBeNull()
  })

  it("keeps weights when any is set", () => {
    expect(runnableConfig({ ...BASE, stat_weights: { ATK: 0, CRate: 2 } }).stat_weights).toEqual({ ATK: 0, CRate: 2 })
  })
})
