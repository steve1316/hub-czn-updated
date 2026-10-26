import type { SimDeckCard } from "@/lib/types"
import type { DeckBuilderExportSlot } from "@/pages/deck-builder/deck-builder.types"

const EPIPHANY_VARIANT = /_epiphany_(\d+)$/i

/** One Deck Builder combatant's deck, sent to the Simulate tab through router state. */
export interface DeckBuilderHandoff {
  /** The combatant's character res_id, matched against `Combatant.res_id`. */
  combatantId: number
  /** The combatant's name, shown when they are not in the loaded capture. */
  name: string
  /** The deck's cards with their epiphany levels. */
  cards: SimDeckCard[]
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
