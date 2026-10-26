// Track B fit for an enemy's damage decrease from its DEF. These must match `DEF_REDUCE_NUM` and `DEF_REDUCE_DEN_C` in
// api/optimizer/expected_damage.py, which a pytest checks.
export const DEF_REDUCE_NUM = 268
export const DEF_REDUCE_DEN_C = 503

/**
 * Estimate an enemy's damage decrease from its DEF, for when the game's own value is unknown.
 * @param def The enemy's DEF.
 * @returns The estimated damage decrease as a fraction.
 */
export function estimatedDamageDecrease(def: number): number {
  return DEF_REDUCE_NUM / (def + DEF_REDUCE_DEN_C)
}

/**
 * An enemy's damage decrease, using the game's own value when it is known.
 * @param dmgDecrease The enemy's real damage decrease, or 0 when it is unknown.
 * @param monsterDef The enemy's DEF, used to estimate the decrease when it is unknown.
 * @returns The damage decrease as a fraction.
 */
export function damageDecrease(dmgDecrease: number, monsterDef: number): number {
  return dmgDecrease > 0 ? dmgDecrease : estimatedDamageDecrease(monsterDef)
}

/**
 * Share of damage that gets through an enemy's damage decrease.
 * @param dmgDecrease The enemy's real damage decrease, or 0 when it is unknown.
 * @param monsterDef The enemy's DEF, used to estimate the decrease when it is unknown.
 * @returns The fraction of damage that passes, from 0 to 1.
 */
export function damagePasses(dmgDecrease: number, monsterDef: number): number {
  return 1 - damageDecrease(dmgDecrease, monsterDef)
}
