import { describe, it, expect } from 'vitest'
import { damageDecrease, damagePasses, estimatedDamageDecrease } from './damage-reduction'

describe('estimatedDamageDecrease', () => {
  it('follows the fitted DEF curve', () => {
    expect(estimatedDamageDecrease(500)).toBeCloseTo(268 / 1003, 6)
  })
})

describe('damageDecrease', () => {
  it("uses the enemy's real damage decrease when there is one", () => {
    expect(damageDecrease(0.3509, 258)).toBe(0.3509)
  })

  it('estimates the decrease from DEF when there is none', () => {
    expect(damageDecrease(0, 500)).toBeCloseTo(268 / 1003, 6)
  })
})

describe('damagePasses', () => {
  it("uses the enemy's real damage decrease when there is one", () => {
    expect(damagePasses(0.2735, 220)).toBeCloseTo(0.7265, 6)
  })

  it('estimates the decrease from DEF when there is none', () => {
    expect(damagePasses(0, 300)).toBeCloseTo(1 - 268 / 803, 6)
  })
})
