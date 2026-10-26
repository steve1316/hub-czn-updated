import { describe, it, expect } from "vitest"
import { AUTO_DECK, deckSlotToSimCards, matchingSavedSlot, persistedDeckChoice } from "./simulator-deck.utils"
import type { SavedDeck } from "@/pages/deck-builder/deck-builder-saved-decks.utils"
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

describe("matchingSavedSlot", () => {
  const slot: DeckBuilderExportSlot = {
    combatant_id: 1001,
    equipment: { weapon_id: null, armor_id: null, accessory_id: null },
    cards: [card("c_1", "c_1_epiphany_3"), card("c_2", null)],
  }
  const saved: SavedDeck = {
    id: "deck_1",
    name: "Main",
    created_at: "2026-10-26T00:00:00Z",
    updated_at: "2026-10-26T00:00:00Z",
    payload: { version: 1, exported_at: "2026-10-26T00:00:00Z", slots: [{ ...slot, combatant_id: 1002, cards: [] }, slot] },
  }

  it("points at the saved slot when the sent deck still matches it", () => {
    expect(matchingSavedSlot([saved], "deck_1", 1, slot)).toEqual({ id: "deck_1", slotIndex: 1 })
  })

  it("returns null once the deck was edited after saving", () => {
    expect(matchingSavedSlot([saved], "deck_1", 1, { ...slot, cards: [card("c_1", null), card("c_2", null)] })).toBeNull()
  })

  it("returns null when no saved deck is open, or it was deleted", () => {
    expect(matchingSavedSlot([saved], null, 1, slot)).toBeNull()
    expect(matchingSavedSlot([], "deck_1", 1, slot)).toBeNull()
  })
})

describe("persistedDeckChoice", () => {
  it("keeps a stored deck choice", () => {
    expect(persistedDeckChoice({ deck: { kind: "saved", id: "deck_1", slotIndex: 0 } })).toEqual({ kind: "saved", id: "deck_1", slotIndex: 0 })
  })

  it("turns the old in-game deck id into a game choice", () => {
    expect(persistedDeckChoice({ deckId: 42 })).toEqual({ kind: "game", id: 42 })
  })

  it("falls back to the auto pick when nothing was stored", () => {
    expect(persistedDeckChoice({})).toEqual(AUTO_DECK)
    expect(persistedDeckChoice({ deckId: null })).toEqual(AUTO_DECK)
  })
})
