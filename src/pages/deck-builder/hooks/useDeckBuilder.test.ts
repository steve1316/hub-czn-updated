import { describe, it, expect } from "vitest"
import { createEmptySlot } from "../deck-builder.utils"
import type { DeckBuilderImportedCard } from "../deck-builder.types"
import { createDeckBuilderExportSlot } from "./useDeckBuilder"

const UNLOADED: DeckBuilderImportedCard[] = [{
  card_id: "c_1043_srt1",
  selected_variant_id: "c_1043_srt1_epiphany_2",
  selected_divine_god: null,
  selected_divine_epiphany_id: null,
  selected_common_epiphany_id: null,
  selected_persona_engraving_ids: [null, null],
}]

describe("createDeckBuilderExportSlot", () => {
  it("keeps the cards of a slot whose cards failed to load", () => {
    const slot = { ...createEmptySlot(), combatantId: 1043, unloadedCards: UNLOADED, error: "boom" }
    expect(createDeckBuilderExportSlot(slot).cards).toEqual(UNLOADED)
  })

  it("exports the loaded cards otherwise", () => {
    expect(createDeckBuilderExportSlot({ ...createEmptySlot(), combatantId: 1043 }).cards).toEqual([])
  })
})
