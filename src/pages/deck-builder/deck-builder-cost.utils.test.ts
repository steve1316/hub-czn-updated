import { describe, it, expect } from "vitest"
import { calculateDeckBuilderSlotCost } from "./deck-builder-cost.utils"
import type { DeckCardInstance, SquadSlot } from "./deck-builder.types"

/**
 * A monster card in a deck, with nothing selected on it.
 * @param id The card id, also used as its instance id and name.
 * @param rarity The rarity the generated card data gives it.
 * @returns The card instance.
 */
function monster(id: string, rarity: string | null): DeckCardInstance {
  return {
    instanceId: id,
    card: { card_id: id, char_res_id: null, name: id, cost: 1, eff_value: 0, hits: 0, spark_count: 0, effect_types: [] },
    description: null,
    variants: [],
    selectedVariant: null,
    selectedDivineGod: null,
    selectedDivineEpiphany: null,
    selectedCommonEpiphany: null,
    selectedPersonaEngravings: {} as DeckCardInstance["selectedPersonaEngravings"],
    group: "monster",
    rarity,
    tags: [],
  }
}

/**
 * A squad slot holding only the given cards.
 * @param cards The deck's cards.
 * @returns The slot.
 */
function slot(cards: DeckCardInstance[]): SquadSlot {
  return { combatantId: null, cards, equipment: {} as SquadSlot["equipment"], startingCards: [], epiphanyCards: [], egoSkill: null, isLoading: false, error: null, unloadedCards: null }
}

describe("monster card cost", () => {
  it("prices each rarity in its own bracket", () => {
    const cost = calculateDeckBuilderSlotCost(slot([monster("a", "Common"), monster("b", "Rare"), monster("c", "Legendary")]))
    expect([cost.monsterCommonCards, cost.monsterRareCards, cost.monsterLegendaryCards]).toEqual([20, 50, 80])
  })

  it("prices unique, which the game ranks above legendary, as legendary", () => {
    const cost = calculateDeckBuilderSlotCost(slot([monster("ghost", "Unique")]))
    expect(cost.monsterLegendaryCards).toBe(80)
    expect(cost.total).toBe(80)
  })

  it("falls back to common when a card has no rarity", () => {
    expect(calculateDeckBuilderSlotCost(slot([monster("a", null)])).monsterCommonCards).toBe(20)
  })
})
