import { describe, it, expect } from "vitest"
import { battleTimeTitle } from "./battle-time.utils"

describe("battleTimeTitle", () => {
  it("spells out the full local date and time", () => {
    const iso = "2026-03-04T05:06:00Z"
    expect(battleTimeTitle(iso)).toBe(new Date(iso).toLocaleString())
  })

  it("is empty for a time that cannot be read", () => {
    expect(battleTimeTitle("not a date")).toBe("")
  })
})
