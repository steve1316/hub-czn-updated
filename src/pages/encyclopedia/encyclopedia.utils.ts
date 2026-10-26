import { localized } from '@/lib/localized-text'
import type {
  CardFilters,
  DescriptionSegment,
  EncyclopediaCard,
  GlossaryCategory,
  GlossaryEntry,
  Lang,
  Matcher,
} from './encyclopedia.types'

export { localized, resolveLang } from '@/lib/localized-text'

// A season card's Group key is this prefix plus the season number, such as "season-5".
export const SEASON_GROUP_PREFIX = 'season-'

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

/** Builds a matcher from the glossary. Only explicit `aliases` are linkable. */
export function buildMatcher(glossary: GlossaryEntry[]): Matcher {
  const aliasToTermId = new Map<string, string>()
  const aliases: string[] = []

  for (const entry of glossary) {
    for (const alias of entry.aliases) {
      const key = alias.toLowerCase()
      if (!aliasToTermId.has(key)) {
        aliasToTermId.set(key, entry.id)
        aliases.push(alias)
      }
    }
  }

  // Longest first so regex alternation prefers multi-word aliases.
  aliases.sort((a, b) => b.length - a.length)

  // `(?!)` never matches — used when there is nothing to link.
  const regex =
    aliases.length === 0
      ? /(?!)/g
      : new RegExp(`(?<![\\w])(?:${aliases.map(escapeRegExp).join('|')})(?![\\w])`, 'gi')

  return { regex, aliasToTermId }
}

/** Splits `text` into plain-text and glossary-term segments. */
export function linkDescription(text: string, matcher: Matcher): DescriptionSegment[] {
  if (!text) return []

  const segments: DescriptionSegment[] = []
  let last = 0
  matcher.regex.lastIndex = 0

  let match: RegExpExecArray | null
  while ((match = matcher.regex.exec(text)) !== null) {
    const value = match[0]
    // Safety guard: a malformed glossary with an empty-string alias would
    // produce zero-length matches; skip them to avoid an infinite loop.
    if (value.length === 0) {
      matcher.regex.lastIndex++
      continue
    }
    if (match.index > last) {
      segments.push({ kind: 'text', value: text.slice(last, match.index) })
    }
    // The regex is built only from aliasToTermId's keys, so a match always
    // resolves; the text fallback is a defensive default.
    const termId = matcher.aliasToTermId.get(value.toLowerCase())
    segments.push(termId ? { kind: 'term', value, termId } : { kind: 'text', value })
    last = match.index + value.length
  }

  if (last < text.length) {
    segments.push({ kind: 'text', value: text.slice(last) })
  }
  return segments
}

/**
 * Filter the glossary by search text and category.
 * @param glossary The glossary entries.
 * @param query The search text, matched anywhere in the term or the definition.
 * @param category The category to keep, or null for every category.
 * @param lang The language the term and definition are read in.
 * @returns The matching entries, in glossary order.
 */
export function filterGlossary(glossary: GlossaryEntry[], query: string, category: GlossaryCategory | null, lang: Lang): GlossaryEntry[] {
  const q = query.trim().toLowerCase()
  return glossary.filter(e => {
    if (category && e.category !== category) return false
    return !q || localized(e.term, lang).toLowerCase().includes(q) || localized(e.definition, lang).toLowerCase().includes(q)
  })
}

/**
 * The distinct non-empty values, sorted.
 * @param values The values, with repeats.
 * @returns Each value once, in sort order.
 */
export function uniqueSorted(values: string[]): string[] {
  return [...new Set(values)].filter(Boolean).sort()
}

/**
 * The Group filter key for a card: its archive group, with each season kept apart.
 * @param card The card.
 * @returns Such as "combatant" or "season-5".
 */
export function cardGroupKey(card: EncyclopediaCard): string {
  return card.group === 'season' ? `${SEASON_GROUP_PREFIX}${card.season}` : card.group
}

/**
 * Filters the Encyclopedia's cards by group, combatant, card type and search text.
 * @param cards Every card.
 * @param filters What to keep. A null filter keeps everything.
 * @returns The matching cards, in their original order.
 */
export function filterCards(cards: EncyclopediaCard[], filters: CardFilters): EncyclopediaCard[] {
  const q = filters.query.trim().toLowerCase()
  return cards.filter(card => {
    if (filters.group && cardGroupKey(card) !== filters.group) return false
    if (filters.character != null && card.character_id !== filters.character) return false
    if (filters.type && card.card_type !== filters.type) return false
    return !q || card.name.toLowerCase().includes(q) || card.description.toLowerCase().includes(q)
  })
}
