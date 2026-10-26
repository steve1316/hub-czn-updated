import type { MemoryFragment, Stat } from '@/lib/types'

/** Which way a Fragments column is sorted. */
export type SortDir = 'asc' | 'desc'

/**
 * Pick the stat a stat column shows for a fragment.
 * @param f The fragment.
 * @param key The column key.
 * @returns The stat, null when the fragment has none in that column, or undefined for a column that is not a stat.
 */
function statFor(f: MemoryFragment, key: string): Stat | null | undefined {
  if (key === 'main') return f.main_stat
  const sub = /^sub([1-4])$/.exec(key)
  return sub ? f.substats[Number(sub[1]) - 1] ?? null : undefined
}

/**
 * Get the plain value a non-stat column sorts by.
 * @param f The fragment.
 * @param key The column key.
 * @returns The value to compare.
 */
function sortValue(f: MemoryFragment, key: string): string | number {
  switch (key) {
    case 'slot':      return f.slot_num
    case 'set':       return f.set_name
    case 'level':     return f.level
    case 'gs':        return f.priority_score > 0 ? f.priority_score : f.gear_score
    case 'potential': return f.potential_low
    case 'equipped':  return f.equipped_to ?? ''
    default:          return ''
  }
}

/**
 * Compare two fragments for a Fragments table column. Stat columns group by stat name and then order by value, with
 * fragments missing that stat kept at the bottom in both directions.
 * @param a The first fragment.
 * @param b The second fragment.
 * @param key The column key.
 * @param dir The sort direction.
 * @returns A negative number when `a` comes first, a positive one when `b` does, or 0.
 */
export function compareFragments(a: MemoryFragment, b: MemoryFragment, key: string, dir: SortDir): number {
  const sign = dir === 'asc' ? 1 : -1
  const sa = statFor(a, key)
  const sb = statFor(b, key)
  if (sa !== undefined && sb !== undefined) {
    if (!sa || !sb) return sa ? -1 : sb ? 1 : 0
    return sign * (sa.name.localeCompare(sb.name) || sa.value - sb.value)
  }
  const av = sortValue(a, key)
  const bv = sortValue(b, key)
  if (typeof av === 'number' && typeof bv === 'number') return sign * (av - bv)
  return sign * String(av).localeCompare(String(bv))
}
