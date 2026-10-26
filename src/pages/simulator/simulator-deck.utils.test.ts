import { describe, it, expect } from "vitest"
import { deckSlotToSimCards } from "./simulator-deck.utils"
import type { DeckBuilderExportSlot, DeckBuilderImportedCard } from "@/pages/deck-builder/deck-builder.types"

/**
 * A Deck Builder card with only its variant set.
 * @param cardId The base card id.
 * @param variantId The chosen epiphany variant, or null for the base card.
 * @returns The exported card.
 */
function card(cardId: string, variantId: string | null): DeckBuilderImportedCard {
  return {
    card_id: cardId,
    selected_variant_id: variantId,
    selected_divine_god: null,
    selected_divine_epiphany_id: null,
    selected_common_epiphany_id: null,
    selected_persona_engraving_ids: [null, null],
  }
}

describe("deckSlotToSimCards", () => {
  it("turns each card's epiphany variant into its level", () => {
    const slot: DeckBuilderExportSlot = {
      combatant_id: 1001,
      equipment: { weapon_id: null, armor_id: null, accessory_id: null },
      cards: [card("c_1", "c_1_epiphany_3"), card("c_2", null)],
    }
    expect(deckSlotToSimCards(slot)).toEqual([{ card_id: "c_1", epiphany_level: 3 }, { card_id: "c_2", epiphany_level: null }])
  })
})
