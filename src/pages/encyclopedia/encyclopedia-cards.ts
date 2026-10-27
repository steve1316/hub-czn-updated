import { cardImages } from '@/lib/deck-builder-assets'
import rawCards from './data/encyclopedia-cards.json'
import type { CardCharacterEntry, CardKeyword, CardLink, CardSeason, EncyclopediaCard, EncyclopediaCards, LinkedCard } from './encyclopedia.types'

// Cast is safe at the top level. The generator writes the file in this shape.
const data = rawCards as EncyclopediaCards

// Art the deck builder does not ship. The generator writes each card's image relative to `src/pages/`.
const ENCYCLOPEDIA_ART = import.meta.glob('/src/pages/encyclopedia/data/card-art/*.webp', { eager: true, query: '?url', import: 'default' }) as Record<string, string>

export const ENCYCLOPEDIA_CARDS: EncyclopediaCard[] = data.cards
export const CARD_SEASONS: CardSeason[] = data.seasons
export const CARD_CHARACTERS: CardCharacterEntry[] = data.characters
export const CARD_KEYWORDS: CardKeyword[] = data.keywords
export const CARD_LINKS: CardLink[] = data.card_links

// Every card a card link can open: the listed cards, then the ones only card text names.
export const cardById = new Map<string, LinkedCard>([...data.linked_cards, ...data.cards].map(card => [card.id, card]))
const LISTED_IDS = new Set(data.cards.map(card => card.id))

/**
 * Whether a card is in the Cards tab's list.
 * @param cardId The client card id.
 * @returns True for a listed card, false for one only card text names.
 */
export function isListedCard(cardId: string): boolean {
  return LISTED_IDS.has(cardId)
}

/**
 * The bundled URL of a card's art.
 * @param card The card, or any card text names.
 * @returns The URL, or undefined when the card has no art.
 */
export function cardImageUrl(card: Pick<EncyclopediaCard, 'image'>): string | undefined {
  return card.image ? cardImages[`../pages/${card.image}`] ?? ENCYCLOPEDIA_ART[`/src/pages/${card.image}`] : undefined
}
