import { describe, it, expect } from 'vitest'
import { battleEnemy, DEFAULT_ENEMY, parseStoredEnemy, typedEnemy } from './battles-enemy'
import type { BattleRecord } from '@/lib/types'

describe('parseStoredEnemy', () => {
  it('keeps a stored enemy', () => {
    const enemy = { def: 431, dmgDecrease: 0.3454, source: { kind: 'battle', captureTime: '2026-10-26T10:00:00Z' } }
    expect(parseStoredEnemy(JSON.stringify(enemy), null)).toEqual(enemy)
  })

  it('turns the old Simulator DEF into a typed enemy', () => {
    expect(parseStoredEnemy(null, JSON.stringify({ charName: 'Rin', monsterDef: 300 }))).toEqual(typedEnemy(300))
  })

  it('falls back to the default enemy for missing or broken data', () => {
    expect(parseStoredEnemy(null, null)).toEqual(DEFAULT_ENEMY)
    expect(parseStoredEnemy('{"def": "x"}', 'not json')).toEqual(DEFAULT_ENEMY)
  })
})

describe('battleEnemy', () => {
  it('treats a negative captured decrease as none, which the simulate endpoint accepts', () => {
    const record = { enemy_def: 120.4, enemy_dmg_decrease: -0.1, capture_time: '2026-10-26T10:00:00Z' } as BattleRecord
    expect(battleEnemy(record).dmgDecrease).toBe(0)
  })
})
