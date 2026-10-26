import { describe, it, expect } from "vitest"
import { loadWorkingSquad, persistWorkingSquad, type WorkingSquad } from "./deck-builder-saved-decks.utils"

/**
 * A minimal in-memory stand-in for `sessionStorage`.
 * @returns The storage.
 */
function memoryStorage(): Pick<Storage, "getItem" | "setItem"> {
  const values = new Map<string, string>()
  return {
    getItem: (key) => values.get(key) ?? null,
    setItem: (key, value) => { values.set(key, value) },
  }
}

const SQUAD: WorkingSquad = {
  payload: {
    version: 1,
    exported_at: "2026-10-26T00:00:00Z",
    slots: [{ combatant_id: 1017, equipment: { weapon_id: null, armor_id: null, accessory_id: null }, cards: [] }],
  },
  savedDeckId: "deck_1",
}

describe("working squad", () => {
  it("brings back the squad it kept", () => {
    const storage = memoryStorage()
    persistWorkingSquad(SQUAD, storage)
    expect(loadWorkingSquad(storage)).toEqual(SQUAD)
  })

  it("returns null when nothing was kept", () => {
    expect(loadWorkingSquad(memoryStorage())).toBeNull()
  })

  it("returns null for a damaged value", () => {
    const storage = memoryStorage()
    storage.setItem("hub-czn:deck-builder:working-squad", "{not json")
    expect(loadWorkingSquad(storage)).toBeNull()
    storage.setItem("hub-czn:deck-builder:working-squad", JSON.stringify({ payload: { slots: "nope" }, savedDeckId: null }))
    expect(loadWorkingSquad(storage)).toBeNull()
  })
})
