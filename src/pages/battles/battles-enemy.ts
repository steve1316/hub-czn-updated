import { useOutletContext } from 'react-router-dom'
import i18n from '@/i18n'
import type { BattleRecord } from '@/lib/types'
import { damageDecrease } from '@/lib/damage-reduction'
import { formatBattleTime } from '@/pages/battle/battle-time.utils'
import { ENEMY_PRESET_GROUPS, type EnemyPreset } from '@/pages/simulator/simulator-damage.utils'

const STORAGE_KEY = 'czn_battles_enemy'
// The Simulator's own state before the Battles merge. Only its typed DEF is carried over.
const LEGACY_SIMULATOR_KEY = 'czn_simulator_state'

/** Where the Simulator's enemy came from. */
export type EnemySource =
  | { kind: 'preset'; group: string; label: string }
  | { kind: 'battle'; captureTime: string }
  | { kind: 'typed' }

/** The enemy the Simulator hits, shared by every Battles tab. */
export interface SimEnemy {
  /** The enemy's DEF. */
  def: number
  /** The enemy's real damage decrease as a fraction. 0 means a typed DEF, so the sidecar estimates it. */
  dmgDecrease: number
  /** Where the enemy came from, which names it in the enemy bar. */
  source: EnemySource
}

/** What the Battles shell hands its tabs through the router outlet. */
export interface BattlesContext {
  /** The current Simulator enemy. */
  enemy: SimEnemy
  /** Replace the Simulator enemy and remember it. */
  setEnemy: (enemy: SimEnemy) => void
}

/**
 * The enemy from a preset button.
 * @param group The preset's stage kind, such as "combat".
 * @param preset The preset itself.
 * @returns The enemy with the preset's game data.
 */
export function presetEnemy(group: string, preset: EnemyPreset): SimEnemy {
  return { def: preset.def, dmgDecrease: preset.dmg_decrease, source: { kind: 'preset', group, label: preset.label } }
}

/**
 * The enemy from a captured battle.
 * @param record The captured battle.
 * @returns The enemy with the decrease the game reported.
 */
export function battleEnemy(record: BattleRecord): SimEnemy {
  // A negative decrease is clamped to 0, which the simulate endpoint accepts and treats as "estimate from DEF"
  return { def: Math.round(record.enemy_def), dmgDecrease: Math.max(0, record.enemy_dmg_decrease), source: { kind: 'battle', captureTime: record.capture_time } }
}

/**
 * The enemy from a typed DEF, whose decrease is estimated.
 * @param def The typed DEF.
 * @returns The enemy with no known decrease.
 */
export function typedEnemy(def: number): SimEnemy {
  return { def, dmgDecrease: 0, source: { kind: 'typed' } }
}

export const DEFAULT_ENEMY: SimEnemy = presetEnemy(ENEMY_PRESET_GROUPS[0].group, ENEMY_PRESET_GROUPS[0].presets[0])

/**
 * Whether a parsed value is a usable stored enemy.
 * @param value The parsed JSON.
 * @returns True when it has a numeric DEF and decrease and a known source.
 */
function isSimEnemy(value: unknown): value is SimEnemy {
  const enemy = value as SimEnemy | null
  return typeof enemy?.def === 'number' && typeof enemy.dmgDecrease === 'number' && ['preset', 'battle', 'typed'].includes(enemy.source?.kind)
}

/**
 * Read the stored enemy, carrying over the old Simulator's typed DEF when there is none.
 * @param raw The stored enemy JSON, or null.
 * @param legacyRaw The old Simulator state JSON, or null.
 * @returns The enemy to start with.
 */
export function parseStoredEnemy(raw: string | null, legacyRaw: string | null): SimEnemy {
  try {
    const enemy: unknown = raw ? JSON.parse(raw) : null
    if (isSimEnemy(enemy)) return enemy
  } catch { }
  try {
    const legacy = legacyRaw ? (JSON.parse(legacyRaw) as { monsterDef?: unknown }) : null
    if (typeof legacy?.monsterDef === 'number') return typedEnemy(legacy.monsterDef)
  } catch { }
  return DEFAULT_ENEMY
}

/**
 * Load the stored enemy from localStorage.
 * @returns The stored enemy, or the default one.
 */
export function loadEnemy(): SimEnemy {
  try {
    const stored = localStorage.getItem(STORAGE_KEY)
    const enemy = parseStoredEnemy(stored, localStorage.getItem(LEGACY_SIMULATOR_KEY))
    // Store a migrated enemy right away, as the Simulator rewrites its old state without the DEF
    if (!stored) saveEnemy(enemy)
    return enemy
  } catch {
    return DEFAULT_ENEMY
  }
}

/**
 * Remember the enemy in localStorage.
 * @param enemy The enemy to store.
 */
export function saveEnemy(enemy: SimEnemy): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(enemy))
  } catch { }
}

/**
 * The damage decrease the Simulator will use, which is the estimate from DEF for a typed enemy.
 * @param enemy The enemy.
 * @returns The decrease as a fraction.
 */
export function enemyDecrease(enemy: SimEnemy): number {
  return damageDecrease(enemy.dmgDecrease, enemy.def)
}

/**
 * A short name for the enemy, such as "Boss Lv7" or "Battle 12m ago".
 * @param enemy The enemy.
 * @returns The translated name.
 */
export function enemyLabel(enemy: SimEnemy): string {
  const source = enemy.source
  if (source.kind === 'preset') {
    const group = i18n.t(`simulator.presetGroups.${source.group}`)
    return source.label === 'All' ? group : `${group} ${source.label}`
  }
  if (source.kind === 'battle') return i18n.t('battles.enemy.battle', { time: formatBattleTime(source.captureTime) })
  return i18n.t('battles.enemy.typed')
}

/**
 * Read the Simulator enemy that the Battles shell shares with its tabs.
 * @returns The enemy and its setter.
 */
export function useBattlesEnemy(): BattlesContext {
  return useOutletContext<BattlesContext>()
}
