/** The page the Home screen points a player at next. */
export type HomeNextStep = 'setup' | 'capture' | 'optimizer'

/**
 * Pick the next thing a player should do: finish setup, then capture their gear, then build sets.
 * @param setupDone Whether the setup checks pass, or null while they are still loading.
 * @param hasGear Whether any Memory Fragments have been captured.
 * @returns The next step, or null while the setup check is still loading.
 */
export function homeNextStep(setupDone: boolean | null, hasGear: boolean): HomeNextStep | null {
  if (setupDone == null) return null
  if (!setupDone) return 'setup'
  return hasGear ? 'optimizer' : 'capture'
}
