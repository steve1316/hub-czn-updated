import type { SubstatRoll } from "@/lib/substat-rolls"

/**
 * The "Stat max rolls" lines for the Gear Score help, one stat per line.
 * @param rolls The substat roll ranges, normally `SUBSTAT_ROLLS`.
 * @returns The lines joined by newlines, each indented like the rest of the help text.
 */
export function formatMaxRolls(rolls: SubstatRoll[]): string {
  return rolls.map((roll) => `  - ${roll.name}: ${roll.max}${roll.percent ? "%" : ""}`).join("\n")
}
