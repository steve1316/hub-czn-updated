import type { SimDeckCard } from "@/lib/types"
import type { SavedDeck } from "@/pages/deck-builder/deck-builder-saved-decks.utils"
import type { DeckBuilderExportSlot } from "@/pages/deck-builder/deck-builder.types"

const EPIPHANY_VARIANT = /_epiphany_(\d+)$/i

/** The in-game deck pick that lets the sidecar choose the highest-scoring deck. */
export const AUTO_DECK: DeckChoice = { kind: "game", id: null }

/**
 * The deck to simulate: an in-game deck (a null id picks the highest-scoring one), a deck sent unsaved from the Deck Builder, or one
 * combatant's slot of a deck saved in the Deck Builder, read fresh on each run.
 */
export type DeckChoice =
  | { kind: "game"; id: number | null }
  | { kind: "cards"; name: string; cards: SimDeckCard[] }
  | ({ kind: "saved" } & SavedSlotRef)

/** One combatant's slot of a deck saved in the Deck Builder. */
export interface SavedSlotRef {
  /** The saved deck's id. */
  id: string
  /** The slot's index in the saved squad. */
  slotIndex: number
}

/** The Simulator's stored deck choice, including the in-game deck id kept by older versions. */
export interface StoredDeckChoice {
  /** The deck choice. */
  deck?: DeckChoice
  /** The in-game deck id kept by older versions, or null for the auto pick. */
  deckId?: number | null
}

/** One Deck Builder combatant's deck, sent to the Simulate tab through router state. */
export interface DeckBuilderHandoff {
  /** The combatant's character res_id, matched against `Combatant.res_id`. */
  combatantId: number
  /** The combatant's name, shown when they are not in the loaded capture. */
  name: string
  /** The deck's cards with their epiphany levels. */
  cards: SimDeckCard[]
  /** The saved deck slot the cards still match, so the Simulator lists it as saved, or null for unsaved changes. */
  saved: SavedSlotRef | null
}

/**
 * Turn a Deck Builder slot into the simulate endpoint's card list. Divine epiphanies and persona engravings are dropped, as the simulator cannot model them.
 * @param slot The exported Deck Builder slot.
 * @returns Each card with the epiphany level parsed from its variant id, or null for the base card.
 */
export function deckSlotToSimCards(slot: DeckBuilderExportSlot): SimDeckCard[] {
  return slot.cards.map((card) => {
    const level = card.selected_variant_id?.match(EPIPHANY_VARIANT)?.[1]
    return { card_id: card.card_id, epiphany_level: level ? Number(level) : null }
  })
}

/**
 * Find the saved deck slot that a Deck Builder slot still matches, card for card.
 * @param savedDecks The decks saved in the Deck Builder.
 * @param savedDeckId The id of the saved deck the squad was loaded from, or null.
 * @param slotIndex The slot's index in the squad.
 * @param slot The slot as it is now.
 * @returns The matching saved slot, or null when there is none or the slot was edited since saving.
 */
export function matchingSavedSlot(savedDecks: SavedDeck[], savedDeckId: string | null, slotIndex: number, slot: DeckBuilderExportSlot): SavedSlotRef | null {
  const deck = savedDecks.find((saved) => saved.id === savedDeckId)
  const saved = deck?.payload.slots[slotIndex]
  if (!deck || !saved || saved.combatant_id !== slot.combatant_id || JSON.stringify(saved.cards) !== JSON.stringify(slot.cards)) return null
  return { id: deck.id, slotIndex }
}

/**
 * Read the stored deck choice, turning an older version's in-game deck id into a game choice.
 * @param stored The stored Simulator state.
 * @returns The deck choice, or the auto pick when none was stored.
 */
export function persistedDeckChoice(stored: StoredDeckChoice): DeckChoice {
  if (stored.deck) return stored.deck
  return typeof stored.deckId === "number" ? { kind: "game", id: stored.deckId } : AUTO_DECK
}
