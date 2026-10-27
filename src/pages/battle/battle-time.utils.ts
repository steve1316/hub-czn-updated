import i18n from '@/i18n'

/**
 * Format a capture time as a short relative time, such as "12m ago", or a date once it is a day old.
 * @param iso The capture time as an ISO string.
 * @returns The formatted time, or the input when it cannot be parsed.
 */
export function formatBattleTime(iso: string): string {
  try {
    const d = new Date(iso)
    const now = Date.now()
    const diffMs = now - d.getTime()
    const diffMin = Math.floor(diffMs / 60_000)
    if (diffMin < 1) return i18n.t('battle.timeNow')
    if (diffMin < 60) return i18n.t('battle.minutesAgo', { count: diffMin })
    const diffH = Math.floor(diffMin / 60)
    if (diffH < 24) return i18n.t('battle.hoursAgo', { count: diffH })
    return d.toLocaleDateString(undefined, { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' })
  } catch {
    return iso
  }
}

/**
 * Format a capture time as a full local date and time, for a tooltip on the short form.
 * @param iso The capture time as an ISO string.
 * @returns The full date and time, or an empty string when it cannot be parsed.
 */
export function battleTimeTitle(iso: string): string {
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? '' : d.toLocaleString()
}
