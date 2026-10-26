/**
 * Turn a settings object into a string that only changes when a value changes, so a page can tell whether its
 * results still match what is on screen. Object keys are sorted and undefined fields are dropped.
 * @param value Any JSON-like settings value.
 * @returns A stable key for the value.
 */
export function settingsKey(value: unknown): string {
  return JSON.stringify(value, (_key, v: unknown) => {
    if (v === null || typeof v !== 'object' || Array.isArray(v)) return v
    const entries = Object.entries(v as Record<string, unknown>).sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0))
    return Object.fromEntries(entries)
  })
}
