import type { CardEntry } from '@/lib/types'
import { DECK_BUILDER_PERSONA_IMAGE_OVERRIDE_FIELD, findCommonEpiphanyById, findDivineEpiphanyById } from '@/pages/deck-builder/deck-builder.utils'
import type { DeckBuilderExportSlot } from '@/pages/deck-builder/deck-builder.types'
import type { Block, DeckCard, EpiphanyRating, Guide } from './guides.types'

export { localized, resolveLang } from '@/lib/localized-text'

/**
 * Picture URLs keyed by their file name instead of their path.
 * @param modules The result of an eager `import.meta.glob` with the `?url` query.
 * @returns File name -> URL.
 */
export function globByFileName(modules: Record<string, string>): Record<string, string> {
  return Object.fromEntries(Object.entries(modules).map(([path, url]) => [path.split('/').pop(), url]))
}

/** The colour a rating chip takes, from its whole score. */
export type RatingTone = 'gold' | 'purple' | 'blue' | 'grey' | 'red'

/** One piece of a prose block as the page lays it out. */
export type ProsePart = { kind: 'heading'; text: string } | { kind: 'terms'; terms: { term: string; lines: string[] }[] } | { kind: 'text'; text: string }

/** A guide deck turned into a Deck Builder squad slot. */
export interface GuideDeckImport {
  /** The slot, in the same shape saved and exported decks use. */
  slot: DeckBuilderExportSlot
  /** Names of the cards that load without part of what the guide shows, each named once. */
  partial: string[]
}

/** A guide deck on its way to the Deck Builder, through the navigation state. */
export interface GuideDeckHandoff extends GuideDeckImport {
  /** The guide character's name, for the Deck Builder's notice. */
  name: string
}

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
 * The name a deck card goes by: its epiphany's name when it shows one, else the card's own.
 * @param card The deck card.
 * @returns The name, or the card id when the sheet gave none.
 */
export function deckCardName(card: DeckCard): string {
  return card.epiphany?.name ?? card.name ?? card.cardId
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
 * Whether a short prose line can head the block after it. Prose and band headings are not headed by the line before them.
 * @param next The block after the prose, if any.
 * @returns True when the next block is content such as cards, sets or teams.
 */
export function headsNext(next: Block | undefined): boolean {
  return next !== undefined && next.type !== 'prose' && next.type !== 'heading'
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
 * @param persona The Persona art key, such as `all_umbra`, which swaps in that engraving combination's picture.
 * @returns The character's own entry, or a stand-in carrying the guide's name.
 */
export function cardEntry(cardId: string, name: string | undefined, cardsById: Record<string, CardEntry>, persona?: string): CardEntry {
  const entry: CardEntry = (
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
  return persona ? ({ ...entry, [DECK_BUILDER_PERSONA_IMAGE_OVERRIDE_FIELD]: `${persona}.webp` } as CardEntry) : entry
}

/**
 * Turn a guide deck into a Deck Builder slot, with each copy's epiphany level and divine or common line.
 * @param charResId The guide character's res_id.
 * @param cards Every copy in the deck.
 * @returns The slot, and the cards whose extra line or Persona engravings the Deck Builder cannot take.
 */
export function guideDeckToSlot(charResId: number, cards: DeckCard[]): GuideDeckImport {
  const partial = new Set<string>()
  const slotCards = cards.map(card => {
    const divine = card.extra?.id.startsWith('div_') ? findDivineEpiphanyById(card.extra.id) : null
    const common = card.extra?.id.startsWith('com_') ? findCommonEpiphanyById(card.extra.id) : null
    // The guide only knows a Persona's art, not which engravings make it
    if ((card.extra && !divine && !common) || card.persona) partial.add(card.name ?? card.cardId)
    return {
      card_id: card.cardId,
      selected_variant_id: card.epiphany?.level ? `${card.cardId}_epiphany_${card.epiphany.level}` : null,
      selected_divine_god: divine ? card.extra?.god ?? divine.god : null,
      selected_divine_epiphany_id: divine?.id ?? null,
      selected_common_epiphany_id: common?.id ?? null,
      selected_persona_engraving_ids: [null, null] as [null, null],
    }
  })
  return {
    slot: { combatant_id: charResId, equipment: { weapon_id: null, armor_id: null, accessory_id: null }, cards: slotCards },
    partial: [...partial],
  }
}

/** How the guide list is ordered: A-Z, or the latest update first. */
export type GuideSort = 'name' | 'updated'

/**
 * Turn a guide's "M/D" update date into a number that orders by date.
 * @param updated The date as the sheet writes it.
 * @returns The month x 100 plus the day, or -1 when there is no usable date.
 */
function updatedOrder(updated: string | undefined): number {
  const match = /^(\d{1,2})\/(\d{1,2})$/.exec(updated ?? '')
  return match ? Number(match[1]) * 100 + Number(match[2]) : -1
}

/**
 * Filter the guide list by name and put it in order.
 * @param list The guides.
 * @param query The search text, matched anywhere in the name.
 * @param sort A-Z, or the latest update first with undated guides last.
 * @returns The matching guides in order.
 */
export function filterGuides<T extends { name: string; updated?: string }>(list: T[], query: string, sort: GuideSort): T[] {
  const q = query.trim().toLowerCase()
  return list
    .filter(g => g.name.toLowerCase().includes(q))
    .sort((a, b) => (sort === 'updated' ? updatedOrder(b.updated) - updatedOrder(a.updated) : 0) || a.name.localeCompare(b.name))
}
