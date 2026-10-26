import { describe, expect, it } from "vitest"
import { SUBSTAT_ROLLS } from "@/lib/substat-rolls"
import en from "@/i18n/en"
import { formatMaxRolls } from "./gear-score-text"

describe("formatMaxRolls", () => {
  it("lists one line per stat with its highest roll", () => {
    const text = formatMaxRolls([
      { name: "Flat ATK", max: 8, min: 5, percent: false },
      { name: "ATK%", max: 1.3, min: 0.8, percent: true },
    ])
    expect(text).toBe("  - Flat ATK: 8\n  - ATK%: 1.3%")
  })

  it("covers every generated substat", () => {
    const text = formatMaxRolls(SUBSTAT_ROLLS)
    for (const roll of SUBSTAT_ROLLS) expect(text).toContain(`- ${roll.name}: ${roll.max}`)
  })
})

describe("gear score help text", () => {
  it("keeps no hardcoded roll values", () => {
    expect(en.scoring.gs.maxRolls.body).not.toMatch(/\d/)
  })

  it("describes weights as whole numbers from 0 to 10", () => {
    expect(en.scoring.gs.weighted.body).toContain("0 to 10")
  })
})
