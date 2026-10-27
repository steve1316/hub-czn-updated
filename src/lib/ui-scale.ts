import { getCurrentWebview } from '@tauri-apps/api/webview'
import { inTauri } from './api'

// //////////////////////////////////////////////////////////////////////////////////////////////////
// //////////////////////////////////////////////////////////////////////////////////////////////////
// Interface size

/** The interface sizes Ctrl +/- steps through, as zoom factors. */
export const UI_SCALES = [0.9, 1, 1.1, 1.25, 1.5]

const STORAGE_KEY = 'czn_ui_scale'

/**
 * Read a stored interface size.
 * @param raw The stored string, or null when nothing is stored.
 * @returns The size, or 1 when the value is missing or not one of `UI_SCALES`.
 */
export function parseUiScale(raw: string | null): number {
  const value = Number(raw)
  return UI_SCALES.includes(value) ? value : 1
}

/**
 * The size one step up or down from the current one, stopping at both ends.
 * @param current The current size.
 * @param dir 1 for bigger, -1 for smaller, 0 to reset to 100%.
 * @returns The new size.
 */
export function nextUiScale(current: number, dir: -1 | 0 | 1): number {
  if (dir === 0) return 1
  const index = UI_SCALES.indexOf(current)
  const next = (index === -1 ? UI_SCALES.indexOf(1) : index) + dir
  return UI_SCALES[Math.min(Math.max(next, 0), UI_SCALES.length - 1)]
}

/**
 * The interface size the user picked last time.
 * @returns The stored size, or 1.
 */
export function loadUiScale(): number {
  try {
    return parseUiScale(localStorage.getItem(STORAGE_KEY))
  } catch {
    return 1
  }
}

/**
 * Zoom the window to a size. Only the Tauri shell can zoom, so this does nothing in a plain browser.
 * @param scale The zoom factor.
 */
export function applyUiScale(scale: number): void {
  if (inTauri()) getCurrentWebview().setZoom(scale).catch(() => { })
}

/**
 * Step the interface size, remember it and apply it.
 * @param dir 1 for bigger, -1 for smaller, 0 to reset to 100%.
 */
export function stepUiScale(dir: -1 | 0 | 1): void {
  const scale = nextUiScale(loadUiScale(), dir)
  try {
    localStorage.setItem(STORAGE_KEY, String(scale))
  } catch { }
  applyUiScale(scale)
}
