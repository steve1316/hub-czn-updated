import type { CardEntry } from '@/lib/types'
import type { EpiphanyRating, Guide } from './guides.types'

export { localized, resolveLang } from '@/lib/localized-text'

/** The colour a rating chip takes, from its whole score. */
export type RatingTone = 'gold' | 'purple' | 'blue' | 'grey' | 'red'

/** One piece of a prose block as the page lays it out. */
export type ProsePart = { kind: 'heading'; text: string } | { kind: 'terms'; terms: { term: string; lines: string[] }[] } | { kind: 'text'; text: string }

// //////////////////////////////////////////////////////////////////////////////////////////////////
// //////////////////////////////////////////////////////////////////////////////////////////////////
// Prose patterns

// A line that is only a term, with its explanation on the lines below, such as "Equilux:".
const TERM_HEAD = /^([^:]{1,40}):$/
// A short term and its explanation on one line, such as "Tassel: base damage".
const TERM_PAIR = /^([^:]{1,32}):\s+(.+)$/
const TERM_MAX_WORDS = 4
const HEADING_MAX_LENGTH = 60

// Roman numerals for epiphany levels 1-5.
const LEVEL_NUMERALS = ['I', 'II', 'III', 'IV', 'V']

/**
 * An epiphany level as the game writes it.
 * @param level The epiphany level, 1-5.
 * @returns The numeral, such as "IV".
 */
export function levelNumeral(level: number): string {
  return LEVEL_NUMERALS[level - 1]
}

/**
 * The score of a rating.
 * @param rating The author's rating, such as "3.5/5".
 * @returns The score before the slash, or -1 when there is none.
 */
export function ratingScore(rating: string | undefined): number {
  const score = parseFloat(rating ?? '')
  return Number.isNaN(score) ? -1 : score
}

/**
 * The colour of a rating chip.
 * @param rating The author's rating, such as "5/5" or "3.5/5".
 * @returns Gold for 6 and up, purple for 5, blue for 4, grey for 3 (or no score) and red for 2 and below.
 */
export function ratingTone(rating: string): RatingTone {
  const score = Math.floor(ratingScore(rating))
  if (score < 0) return 'grey'
  if (score >= 6) return 'gold'
  if (score === 5) return 'purple'
  if (score === 4) return 'blue'
  if (score === 3) return 'grey'
  return 'red'
}

/**
 * A prose block split into headings, term lists and plain lines.
 * @param text The block's text.
 * @param beforeNonProse Whether the next block is not prose, so a short line here heads it.
 * @returns The parts in order. A short single line with no ":" is a heading when it lists things with " | " or leads into
 * non-prose. Lines such as "Equilux:" open a term whose explanation follows, and "Tassel: base damage" is a term on one line.
 */
export function proseParts(text: string, beforeNonProse: boolean): ProsePart[] {
  if (!text.includes('\n') && !text.includes(':') && text.length <= HEADING_MAX_LENGTH && (text.includes(' | ') || beforeNonProse)) {
    return [{ kind: 'heading', text }]
  }
  const parts: ProsePart[] = []
  // The term still taking explanation lines, until the next term starts.
  let open: { term: string; lines: string[] } | null = null
  const addTerm = (term: { term: string; lines: string[] }) => {
    const last = parts[parts.length - 1]
    if (last?.kind === 'terms') last.terms.push(term)
    else parts.push({ kind: 'terms', terms: [term] })
  }
  for (const line of text.split('\n')) {
    const head = line.match(TERM_HEAD)
    const pair = line.match(TERM_PAIR)
    if (head) {
      open = { term: head[1], lines: [] }
      addTerm(open)
    } else if (pair && pair[1].split(' ').length <= TERM_MAX_WORDS) {
      open = null
      addTerm({ term: pair[1], lines: [pair[2]] })
    } else if (open) {
      open.lines.push(line)
    } else {
      parts.push({ kind: 'text', text: line })
    }
  }
  return parts
}

/**
 * Every rated epiphany in a guide, so a deck card can show what the author thought of its level.
 * @param guide The guide.
 * @returns `${cardId}:${level}` -> that level's rating entry, from every card-list in every section.
 */
export function epiphanyRatings(guide: Guide): Map<string, EpiphanyRating> {
  const ratings = new Map<string, EpiphanyRating>()
  for (const section of guide.sections) {
    for (const block of section.blocks) {
      if (block.type !== 'card-list') continue
      for (const item of block.items) {
        for (const ep of item.epiphanies ?? []) ratings.set(`${item.cardId}:${ep.level}`, ep)
      }
    }
  }
  return ratings
}

/**
 * The card entry the card art needs, for any card a guide names.
 * @param cardId The client card id.
 * @param name The name the guide carries, used when the card is not in the guide character's own list.
 * @param cardsById The guide character's cards by id.
 * @returns The character's own entry, or a stand-in carrying the guide's name.
 */
export function cardEntry(cardId: string, name: string | undefined, cardsById: Record<string, CardEntry>): CardEntry {
  return (
    cardsById[cardId] ?? {
      card_id: cardId,
      char_res_id: null,
      name: name ?? cardId,
      cost: 0,
      eff_value: 0,
      hits: 0,
      spark_count: 0,
      effect_types: [],
    }
  )
}
