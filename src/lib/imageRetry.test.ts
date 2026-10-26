import { describe, it, expect } from "vitest"
import { MAX_IMAGE_RETRIES, imageRetryDelay, imageRetryUrl } from "./imageRetry"

describe("imageRetryUrl", () => {
  it("leaves the url alone on the first attempt", () => {
    expect(imageRetryUrl("http://x/assets/a.png", 0)).toBe("http://x/assets/a.png")
  })

  it("adds a cache-busting param on retries", () => {
    expect(imageRetryUrl("http://x/assets/a.png", 2)).toBe("http://x/assets/a.png?_retry=2")
  })

  it("uses & when the url already has a query", () => {
    expect(imageRetryUrl("http://x/a.png?v=1", 1)).toBe("http://x/a.png?v=1&_retry=1")
  })
})

describe("imageRetryDelay", () => {
  it("backs off exponentially", () => {
    expect([1, 2, 3].map(imageRetryDelay)).toEqual([500, 1000, 2000])
  })

  it("allows three retries", () => {
    expect(MAX_IMAGE_RETRIES).toBe(3)
  })
})
