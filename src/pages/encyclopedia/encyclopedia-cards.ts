import { cardImages } from '@/lib/deck-builder-assets'
import rawCards from './data/encyclopedia-cards.json'
import type { CardCharacterEntry, CardSeason, EncyclopediaCard, EncyclopediaCards } from './encyclopedia.types'

// Cast is safe at the top level. The generator writes the file in this shape.
const data = rawCards as EncyclopediaCards

// Art the deck builder does not ship. The generator writes each card's image relative to `src/pages/`.
const ENCYCLOPEDIA_ART = import.meta.glob('/src/pages/encyclopedia/data/card-art/*.webp', { eager: true, query: '?url', import: 'default' }) as Record<string, string>

export const ENCYCLOPEDIA_CARDS: EncyclopediaCard[] = data.cards
export const CARD_SEASONS: CardSeason[] = data.seasons
export const CARD_CHARACTERS: CardCharacterEntry[] = data.characters

/**
 * The bundled URL of a card's art.
 * @param card The card.
 * @returns The URL, or undefined when the card has no art.
 */
export function cardImageUrl(card: EncyclopediaCard): string | undefined {
  return card.image ? cardImages[`../pages/${card.image}`] ?? ENCYCLOPEDIA_ART[`/src/pages/${card.image}`] : undefined
}
