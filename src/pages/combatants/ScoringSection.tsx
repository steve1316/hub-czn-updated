import { useState, useMemo, useCallback } from "react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { useTranslation } from "react-i18next"
import { ChevronDown, ChevronRight } from "lucide-react"
import { api, assetUrl } from "@/lib/api"
import { AssetImage } from "@/components/ui/asset-image"
import type { CharPreset, GameData } from "@/lib/types"
import { ScoringPanel, DPS_WEIGHTS, TANK_WEIGHTS } from "./ScoringPanel"
import type { Preset } from "./ScoringPanel"
import { SUBSTAT_ROLLS } from "@/lib/substat-rolls"
import { formatMaxRolls } from "./gear-score-text"

const GS_SECTION_KEYS = ["calc", "formula", "example", "maxRolls", "weighted", "potential"] as const

/** The max-roll lines for the Gear Score help, built once from the generated roll ranges. */
const MAX_ROLLS_LINES = formatMaxRolls(SUBSTAT_ROLLS)

// //////////////////////////////////////////////////////////////////////////////////////////////////
// //////////////////////////////////////////////////////////////////////////////////////////////////
// Gear Score explanation

/**
 * Collapsed explainer for how the Gear Score is calculated.
 * @returns The explainer card.
 */
function GsExplanation() {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)

  return (
    <div className="rounded-xl border border-[#282828] bg-[#181818] overflow-hidden">
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center gap-2 px-4 py-3 text-sm text-[#b3b3b3] hover:text-[#ffffff] transition-colors"
      >
        {open ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        <span className="font-medium text-[#c084fc]">{t("scoring.howGSWorks")}</span>
      </button>
      {open && (
        <div className="px-4 pb-4 font-mono text-xs text-[#b3b3b3] leading-relaxed space-y-4">
          {GS_SECTION_KEYS.map((key) => (
            <div key={key}>
              <p className="text-[#ffffff] font-semibold mb-1">{t(`scoring.gs.${key}.heading`)}</p>
              <pre className="whitespace-pre-wrap font-mono text-[#b3b3b3]">{key === "maxRolls" ? `${t(`scoring.gs.${key}.body`)}\n${MAX_ROLLS_LINES}` : t(`scoring.gs.${key}.body`)}</pre>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// //////////////////////////////////////////////////////////////////////////////////////////////////
// //////////////////////////////////////////////////////////////////////////////////////////////////
// Recommended build card

/** Minimal set info needed to show a recommended set. */
interface SetInfo {
  /** Display name of the set. */
  name: string
  /** Asset path of the set icon. */
  icon_path?: string
}

/**
 * Read-only card showing the game's recommended sets, main stats and substats for a character.
 * @param preset - The game preset for the character.
 * @param setMap - Set info keyed by set id.
 * @returns The preset card.
 */
function CharPresetCard({ preset, setMap }: { preset: CharPreset; setMap: Record<number, SetInfo> }) {
  const { t } = useTranslation()

  const slotRows = [
    { slot: 4, stats: preset.main_stat_4 },
    { slot: 5, stats: preset.main_stat_5 },
    { slot: 6, stats: preset.main_stat_6 },
  ]

  return (
    <div className="rounded-xl border border-[#282828] bg-[#121212] p-4 space-y-4">
      <div>
        <p className="text-[10px] uppercase tracking-wider text-[#b3b3b3] mb-2">{t("scoring.preset.recommendedSets")}</p>
        <div className="flex flex-wrap gap-2">
          {preset.recommended_sets.map((id) => {
            const s = setMap[id]
            return (
              <div key={id} className="flex items-center gap-1.5 px-2 py-1 rounded-lg bg-[#282828] text-xs text-[#ffffff]">
                {s?.icon_path && <AssetImage src={assetUrl(s.icon_path)} fallback={null} className="w-4 h-4 object-contain" />}
                <span>{s?.name ?? `Set ${id}`}</span>
              </div>
            )
          })}
        </div>
      </div>

      <div>
        <p className="text-[10px] uppercase tracking-wider text-[#b3b3b3] mb-2">{t("scoring.preset.mainStats")}</p>
        <div className="space-y-1">
          {slotRows.map(({ slot, stats }) =>
            stats.length > 0 ? (
              <div key={slot} className="flex items-baseline gap-2 text-xs">
                <span className="text-[#b3b3b3] shrink-0">{t("scoring.preset.slot", { slot })}</span>
                <span className="text-[#ffffff]">{stats.join(" / ")}</span>
              </div>
            ) : null
          )}
        </div>
      </div>

      <div>
        <p className="text-[10px] uppercase tracking-wider text-[#b3b3b3] mb-2">{t("scoring.preset.substats")}</p>
        <div className="flex flex-wrap gap-1">
          {preset.substats.map((s, i) => (
            <span
              key={s}
              className={`text-xs px-2 py-0.5 rounded-full ${
                i === 0 ? "bg-[#c084fc]/20 text-[#c084fc] border border-[#c084fc]/30" : "bg-[#282828] text-[#b3b3b3]"
              }`}
            >
              {s}
            </span>
          ))}
        </div>
      </div>
    </div>
  )
}

// //////////////////////////////////////////////////////////////////////////////////////////////////
// //////////////////////////////////////////////////////////////////////////////////////////////////
// Weight editor

/**
 * Editor for scoring weights. With no `charId` it edits the global weights, otherwise one character's override.
 * Saving re-scores combatants and fragments.
 * @param charId - Character id for a per-character override, or undefined for the global weights.
 * @param resId - Resource id of the character, used to load the game preset.
 * @returns The weight editor and, for a character, its recommended build card.
 */
function WeightEditor({ charId, resId }: { charId?: string; resId?: number }) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const [localWeights, setLocalWeights] = useState<Record<string, number> | null>(null)
  const [activePreset, setActivePreset] = useState<Preset>("custom")
  const [saveError, setSaveError] = useState<string | null>(null)
  const isChar = charId !== undefined

  const { data: serverWeights = {}, isLoading: prioritiesLoading } = useQuery({
    queryKey: ["scoring/priorities"],
    queryFn: () => api.scoringPriorities(),
    staleTime: 60_000,
    select: (d) => d.weights,
  })

  const { data: gameData } = useQuery<GameData>({
    queryKey: ["game-data"],
    queryFn: () => api.gameData(),
    staleTime: Infinity,
    enabled: isChar,
  })
  const setMap = useMemo(() => {
    const map: Record<number, SetInfo> = {}
    for (const [id, s] of Object.entries(gameData?.sets ?? {})) {
      map[Number(id)] = s as SetInfo
    }
    return map
  }, [gameData])

  const { data: charPreset } = useQuery<CharPreset>({
    queryKey: ["scoring/char-preset", resId],
    queryFn: () => api.charPreset(resId!),
    enabled: isChar && resId != null,
    retry: false,
  })

  const { data: charServerWeights, isSuccess: charWeightsLoaded } = useQuery({
    queryKey: ["scoring/char-weights", charId],
    queryFn: () => api.charWeights(charId!),
    enabled: isChar,
    retry: false,
    select: (d) => d.weights,
  })

  const hasCharOverride = isChar && charWeightsLoaded && charServerWeights !== undefined

  // Clears local edits and refreshes everything that depends on the weights.
  const onSaved = (invalidateKey: unknown[]) => {
    setSaveError(null)
    setLocalWeights(null)
    queryClient.invalidateQueries({ queryKey: invalidateKey })
    queryClient.invalidateQueries({ queryKey: ["combatants"] })
    queryClient.invalidateQueries({ queryKey: ["fragments"] })
  }

  const invalidateKey = isChar ? ["scoring/char-weights", charId] : ["scoring/priorities"]
  const mutationOptions = { onSuccess: () => onSaved(invalidateKey), onError: (e: Error) => setSaveError(e.message) }

  const activeMutation = useMutation({
    mutationFn: (weights: Record<string, number>) => (isChar ? api.saveCharWeights(charId, weights) : api.saveScoringPriorities(weights)),
    ...mutationOptions,
  })

  const deleteCharMutation = useMutation({ mutationFn: () => api.deleteCharWeights(charId!), ...mutationOptions })

  // Base is the character override if it exists, else the global weights.
  const baseWeights = isChar ? (charServerWeights ?? serverWeights) : serverWeights
  const displayWeights = localWeights ?? baseWeights

  const isDirty = useMemo(
    () => Object.keys(displayWeights).some((k) => displayWeights[k] !== baseWeights[k]) || Object.keys(baseWeights).some((k) => baseWeights[k] !== displayWeights[k]),
    [displayWeights, baseWeights]
  )

  const handleWeightChange = useCallback(
    (stat: string, value: number) => {
      setLocalWeights((prev) => ({ ...(prev ?? baseWeights), [stat]: value }))
      setActivePreset("custom")
    },
    [baseWeights]
  )

  const handlePresetApply = useCallback((preset: "dps" | "tank") => {
    setLocalWeights(preset === "dps" ? { ...DPS_WEIGHTS } : { ...TANK_WEIGHTS })
    setActivePreset(preset)
  }, [])

  const handleSystemPreset = useCallback(() => {
    if (charPreset) {
      setLocalWeights({ ...charPreset.weights })
      setActivePreset("system")
    }
  }, [charPreset])

  const handleReset = useCallback(() => {
    setLocalWeights(Object.fromEntries(Object.keys(serverWeights).map((k) => [k, 1])))
    setActivePreset("custom")
  }, [serverWeights])

  const handleSave = useCallback(() => {
    if (prioritiesLoading) return
    activeMutation.mutate(displayWeights)
  }, [activeMutation, displayWeights, prioritiesLoading])

  return (
    <div className="space-y-4">
      {!prioritiesLoading && (
        <ScoringPanel
          weights={displayWeights}
          activePreset={activePreset}
          isDirty={isDirty}
          isSaving={activeMutation.isPending}
          saveError={saveError}
          onWeightChange={handleWeightChange}
          onPresetApply={handlePresetApply}
          onReset={handleReset}
          onSave={handleSave}
          onSystemPreset={charPreset ? handleSystemPreset : undefined}
          hasCharOverride={hasCharOverride}
          onResetToGlobal={() => deleteCharMutation.mutate()}
        />
      )}
      {isChar && (charPreset ? <CharPresetCard preset={charPreset} setMap={setMap} /> : <p className="text-xs text-[#b3b3b3]">{t("scoring.preset.noPreset")}</p>)}
    </div>
  )
}

// //////////////////////////////////////////////////////////////////////////////////////////////////
// //////////////////////////////////////////////////////////////////////////////////////////////////
// Public sections

/**
 * Collapsible section on the Combatants page holding the global scoring weights and the Gear Score explainer.
 * @returns The global scoring section.
 */
export function GlobalScoring() {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)

  return (
    <div className="rounded-xl border border-[#282828] bg-[#181818] overflow-hidden">
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center gap-2 px-4 py-3 text-sm hover:bg-[#1e1e1e] transition-colors"
      >
        {open ? <ChevronDown size={14} className="text-[#c084fc]" /> : <ChevronRight size={14} className="text-[#b3b3b3]" />}
        <span className="font-medium text-[#ffffff]">{t("scoring.globalTitle")}</span>
        <span className="ml-auto text-xs text-[#c084fc]">{open ? t("scoring.hide") : t("scoring.edit")}</span>
      </button>
      <p className="px-4 pb-3 text-xs text-[#b3b3b3] leading-relaxed">{t("scoring.intro")}</p>
      {open && (
        <div className="px-4 pb-4 space-y-4 border-t border-[#282828] pt-4">
          <WeightEditor />
          <GsExplanation />
        </div>
      )}
    </div>
  )
}

/**
 * Collapsible section in a combatant's detail view holding that character's weights and recommended build.
 * @param charId - Character id the weights belong to.
 * @param resId - Resource id of the character, used to load the game preset.
 * @returns The per-character scoring section.
 */
export function CharacterScoring({ charId, resId }: { charId: string; resId: number }) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)

  return (
    <div className="mx-4 mt-3 rounded-xl border border-[#282828] bg-[#181818] overflow-hidden">
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center gap-2 px-4 py-2.5 text-sm hover:bg-[#1e1e1e] transition-colors"
      >
        {open ? <ChevronDown size={14} className="text-[#c084fc]" /> : <ChevronRight size={14} className="text-[#b3b3b3]" />}
        <span className="font-medium text-[#ffffff]">{t("scoring.charTitle")}</span>
        <span className="text-xs text-[#b3b3b3] truncate">{t("scoring.charHint")}</span>
        <span className="ml-auto text-xs text-[#c084fc] shrink-0">{open ? t("scoring.hide") : t("scoring.edit")}</span>
      </button>
      {open && (
        <div className="px-4 pb-4">
          <WeightEditor charId={charId} resId={resId} />
        </div>
      )}
    </div>
  )
}
