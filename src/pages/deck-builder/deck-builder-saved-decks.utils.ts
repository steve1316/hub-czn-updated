import type { DeckBuilderExportPayload } from './deck-builder.types'

const SAVED_DECKS_STORAGE_KEY = 'hub-czn:deck-builder:saved-decks'
const SAVED_DECKS_STORAGE_VERSION = 1
// The squad being edited, kept in session storage so leaving the Deck Builder does not lose it
const WORKING_SQUAD_STORAGE_KEY = 'hub-czn:deck-builder:working-squad'

export type SavedDeck = {
  id: string
  name: string
  created_at: string
  updated_at: string
  payload: DeckBuilderExportPayload
}

/** The squad being edited, as kept between visits to the Deck Builder. */
export interface WorkingSquad {
  /** The squad in its export form. */
  payload: DeckBuilderExportPayload
  /** The id of the saved deck the squad was loaded from, or null. */
  savedDeckId: string | null
}

type SavedDecksStoragePayload = {
  version: number
  decks: SavedDeck[]
}

function getStorage() {
  if (typeof window === 'undefined') {
    return null
  }

  return window.localStorage
}

/**
 * Session storage, when running in a browser.
 * @returns The storage, or null outside a browser.
 */
function getSessionStorage() {
  return typeof window === 'undefined' ? null : window.sessionStorage
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function normalizeSavedDeck(value: unknown): SavedDeck | null {
  if (!isRecord(value)) {
    return null
  }

  const id = value.id
  const name = value.name
  const createdAt = value.created_at
  const updatedAt = value.updated_at
  const payload = value.payload

  if (
    typeof id !== 'string' ||
    !id.trim() ||
    typeof name !== 'string' ||
    !name.trim() ||
    typeof createdAt !== 'string' ||
    typeof updatedAt !== 'string' ||
    !isRecord(payload) ||
    !Array.isArray(payload.slots)
  ) {
    return null
  }

  return {
    id,
    name,
    created_at: createdAt,
    updated_at: updatedAt,
    payload: payload as DeckBuilderExportPayload,
  }
}

function createSavedDeckId() {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) {
    return `deck_${crypto.randomUUID()}`
  }

  return `deck_${Date.now()}_${Math.random().toString(36).slice(2, 10)}`
}

export function loadSavedDecks() {
  const storage = getStorage()

  if (!storage) {
    return []
  }

  try {
    const rawValue = storage.getItem(SAVED_DECKS_STORAGE_KEY)

    if (!rawValue) {
      return []
    }

    const parsed = JSON.parse(rawValue) as unknown

    if (!isRecord(parsed) || !Array.isArray(parsed.decks)) {
      return []
    }

    return parsed.decks
      .map(normalizeSavedDeck)
      .filter((deck): deck is SavedDeck => deck !== null)
      .sort((left, right) =>
        right.updated_at.localeCompare(left.updated_at),
      )
  } catch (error) {
    console.error('[Deck Builder] Failed to load saved decks:', error)
    return []
  }
}

export function persistSavedDecks(decks: SavedDeck[]) {
  const storage = getStorage()

  if (!storage) {
    return
  }

  const payload: SavedDecksStoragePayload = {
    version: SAVED_DECKS_STORAGE_VERSION,
    decks,
  }

  storage.setItem(SAVED_DECKS_STORAGE_KEY, JSON.stringify(payload))
}

export function createSavedDeck(
  name: string,
  payload: DeckBuilderExportPayload,
): SavedDeck {
  const now = new Date().toISOString()

  return {
    id: createSavedDeckId(),
    name: name.trim(),
    created_at: now,
    updated_at: now,
    payload,
  }
}

/**
 * Read the squad kept by `persistWorkingSquad`.
 * @param storage Where the squad is kept, session storage by default.
 * @returns The squad, or null when none was kept or the value is damaged.
 */
export function loadWorkingSquad(storage: Pick<Storage, 'getItem'> | null = getSessionStorage()): WorkingSquad | null {
  try {
    const parsed = JSON.parse(storage?.getItem(WORKING_SQUAD_STORAGE_KEY) ?? 'null') as unknown
    if (!isRecord(parsed) || !isRecord(parsed.payload) || !Array.isArray(parsed.payload.slots)) return null
    const savedDeckId = typeof parsed.savedDeckId === 'string' ? parsed.savedDeckId : null
    return { payload: parsed.payload as DeckBuilderExportPayload, savedDeckId }
  } catch {
    return null
  }
}

/**
 * Keep the squad being edited for the rest of this session.
 * @param squad The squad and the saved deck it came from.
 * @param storage Where to keep it, session storage by default.
 */
export function persistWorkingSquad(squad: WorkingSquad, storage: Pick<Storage, 'setItem'> | null = getSessionStorage()) {
  try {
    storage?.setItem(WORKING_SQUAD_STORAGE_KEY, JSON.stringify(squad))
  } catch (error) {
    console.error('[Deck Builder] Failed to keep the squad:', error)
  }
}