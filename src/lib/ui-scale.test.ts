import { describe, it, expect } from "vitest"
import { UI_SCALES, parseUiScale, nextUiScale } from "./ui-scale"

describe("parseUiScale", () => {
  it("reads a stored step", () => {
    expect(parseUiScale("1.25")).toBe(1.25)
  })

  it("falls back to 1 when nothing is stored", () => {
    expect(parseUiScale(null)).toBe(1)
  })

  it("falls back to 1 for a value that is not a step", () => {
    expect(parseUiScale("abc")).toBe(1)
    expect(parseUiScale("3")).toBe(1)
  })
})

describe("nextUiScale", () => {
  it("offers 90 to 150 percent", () => {
    expect(UI_SCALES).toEqual([0.9, 1, 1.1, 1.25, 1.5])
  })

  it("steps up and down one size", () => {
    expect(nextUiScale(1, 1)).toBe(1.1)
    expect(nextUiScale(1.25, -1)).toBe(1.1)
  })

  it("stops at both ends", () => {
    expect(nextUiScale(1.5, 1)).toBe(1.5)
    expect(nextUiScale(0.9, -1)).toBe(0.9)
  })

  it("resets to 100 percent on 0", () => {
    expect(nextUiScale(1.5, 0)).toBe(1)
  })
})
