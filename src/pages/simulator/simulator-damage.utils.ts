import enemyPresetsData from "./data/simulator-enemy-presets.json"

/** One enemy preset button, generated from the game's `mon_stat` table. */
export interface EnemyPreset {
  /** The button text, such as "Lv7" or "All". */
  label: string
  /** The enemy's DEF. */
  def: number
  /** The enemy's damage decrease as a fraction, straight from the game data. */
  dmg_decrease: number
}

/** A row of enemy presets for one kind of stage. */
export interface EnemyPresetGroup {
  /** The stage kind, such as "combat" or "boss". It names the row's i18n label. */
  group: string
  /** The presets in level order. */
  presets: EnemyPreset[]
}

export const ENEMY_PRESET_GROUPS: EnemyPresetGroup[] = enemyPresetsData
