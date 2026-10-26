import { describe, it, expect } from "vitest"
import { ENEMY_PRESET_GROUPS } from "./simulator-damage.utils"

describe("ENEMY_PRESET_GROUPS", () => {
  it("carries the generated DEF and damage decrease for each preset", () => {
    const combat = ENEMY_PRESET_GROUPS.find((group) => group.group === "combat")
    expect(combat?.presets.find((preset) => preset.label === "Lv7")).toEqual({ label: "Lv7", def: 220, dmg_decrease: 0.2735 })
  })
})
