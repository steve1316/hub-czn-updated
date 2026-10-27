import { describe, it, expect } from "vitest"
import { settingsKey } from "./run-settings"

describe("settingsKey", () => {
  it("ignores the order object keys were written in", () => {
    expect(settingsKey({ a: 1, b: { c: 2, d: 3 } })).toBe(settingsKey({ b: { d: 3, c: 2 }, a: 1 }))
  })

  it("changes when a nested value changes", () => {
    expect(settingsKey({ weights: { ATK: 1 } })).not.toBe(settingsKey({ weights: { ATK: 2 } }))
  })

  it("keeps array order significant", () => {
    expect(settingsKey({ cards: [1, 2] })).not.toBe(settingsKey({ cards: [2, 1] }))
  })

  it("treats an undefined field the same as a missing one", () => {
    expect(settingsKey({ a: 1, b: undefined })).toBe(settingsKey({ a: 1 }))
  })

  it("tells null apart from a missing field", () => {
    expect(settingsKey({ a: null })).not.toBe(settingsKey({}))
  })
})
