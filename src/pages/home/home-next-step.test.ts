import { describe, expect, it } from "vitest"
import { homeNextStep } from "./home-next-step"

describe("homeNextStep", () => {
  it("points at Setup until the checks pass", () => {
    expect(homeNextStep(false, false)).toBe("setup")
    expect(homeNextStep(false, true)).toBe("setup")
  })

  it("points at Capture once setup passes but no gear is captured", () => {
    expect(homeNextStep(true, false)).toBe("capture")
  })

  it("points at the Optimizer once gear is captured", () => {
    expect(homeNextStep(true, true)).toBe("optimizer")
  })

  it("waits while the setup check is still loading", () => {
    expect(homeNextStep(null, false)).toBeNull()
  })
})
