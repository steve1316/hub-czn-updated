import { useEffect, useRef, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import { ChevronDown, ChevronRight, Play, Square } from 'lucide-react'
import { api } from '@/lib/api'
import { damageDecrease } from '@/lib/damage-reduction'
import type { OptimizerConfig, EquipmentSet, Monster, Combatant, OptimizeProgress, CharPreset } from '@/lib/types'
import { InfoPopover } from '@/components/ui/info-popover'
import { CharacterCombobox } from '@/components/ui/character-combobox'
import { SetCombobox } from './SetCombobox'
import type { ComboboxOption } from './SetCombobox'
import { PRIMARY_ACTION } from '@/components/ui/action-classes'

const SLOT_4_STATS = ['ATK%', 'DEF%', 'HP%', 'CRate', 'CDmg']
const SLOT_5_STATS = [
  'ATK%', 'DEF%', 'HP%',
  'Passion DMG%', 'Order DMG%', 'Justice DMG%', 'Void DMG%', 'Instinct DMG%',
]
const SLOT_6_STATS = ['ATK%', 'DEF%', 'HP%', 'Ego']

const MAIN_STAT_SLOTS = [
  { labelKey: 'optimizer.mainStatSlot4' as const, key: 'main_stat_4' as const, opts: SLOT_4_STATS },
  { labelKey: 'optimizer.mainStatSlot5' as const, key: 'main_stat_5' as const, opts: SLOT_5_STATS },
  { labelKey: 'optimizer.mainStatSlot6' as const, key: 'main_stat_6' as const, opts: SLOT_6_STATS },
]

const STAT_GROUPS = [
  { labelKey: 'scoring.group.offensive' as const, stats: ['ATK%', 'CRate', 'CDmg', 'Extra DMG%', 'DoT%', 'Flat ATK'] },
  { labelKey: 'scoring.group.defensive' as const, stats: ['DEF%', 'HP%', 'Flat DEF', 'Flat HP'] },
  { labelKey: 'scoring.group.elemental' as const, stats: ['Passion DMG%', 'Order DMG%', 'Justice DMG%', 'Void DMG%', 'Instinct DMG%'] },
  { labelKey: 'scoring.group.other' as const, stats: ['Ego'] },
] as const

function mapWeight(w: number): number {
  return Math.round(Math.max(0, Math.min(10, w)) / 10 * 3)
}

const DEFAULT_STAT_WEIGHTS: Record<string, number> = Object.fromEntries(
  STAT_GROUPS.flatMap(g => g.stats as readonly string[]).map(s => [s, 0])
)

interface OptimizerPanelProps {
  config: OptimizerConfig
  onChange: (config: OptimizerConfig) => void
  onRun: () => void
  onCancel: () => void
  isRunning: boolean
  progress: OptimizeProgress | null
  runError: string | null
}

export function OptimizerPanel({
  config,
  onChange,
  onRun,
  onCancel,
  isRunning,
  progress,
  runError,
}: OptimizerPanelProps) {
  const { t } = useTranslation()

  const { data: status } = useQuery({
    queryKey: ['status'],
    queryFn: () => api.status(),
    refetchInterval: 5_000,
  })

  const { data: combatants = [] } = useQuery<Combatant[]>({
    queryKey: ['combatants'],
    queryFn: () => api.combatants(),
    enabled: status?.data_loaded ?? false,
    staleTime: 30_000,
  })

  const { data: sets = [], isLoading: setsLoading } = useQuery<EquipmentSet[]>({
    queryKey: ['optimize/sets'],
    queryFn: () => api.optimizeSets(),
  })

  // Monster catalog feeds the Monster Picker dropdown.
  const { data: monsterCatalog = [] } = useQuery<Monster[]>({
    queryKey: ['optimize/monster-catalog'],
    queryFn: () => api.monsterCatalog(),
    staleTime: Infinity,  // catalog is static (built offline)
  })

  const selectedCombatant = combatants.find((c) => c.char_id === config.char_name)
  const selectedResId = selectedCombatant?.res_id ?? null

  const { data: charPreset } = useQuery<CharPreset>({
    queryKey: ['scoring/char-preset', selectedResId],
    queryFn: () => api.charPreset(selectedResId!),
    enabled: selectedResId != null,
    retry: false,
    staleTime: Infinity,
  })

  const { data: charSavedWeights } = useQuery({
    queryKey: ['scoring/char-weights', config.char_name],
    queryFn: () => api.charWeights(config.char_name),
    enabled: config.char_name !== '',
    retry: false,
    staleTime: 30_000,
    select: (d) => d.weights,
  })

  const { data: globalPriorities } = useQuery({
    queryKey: ['scoring/priorities'],
    queryFn: () => api.scoringPriorities(),
    staleTime: 60_000,
    select: (d) => d.weights,
  })

  // Stable refs so effects don't go stale
  const onChangeRef = useRef(onChange)
  onChangeRef.current = onChange
  const configRef = useRef(config)
  configRef.current = config

  const lastAutoFilledRef = useRef<string>(config.char_name)
  const lastWeightInitRef = useRef<string>(config.char_name)
  const queryClient = useQueryClient()
  const [helpOpen, setHelpOpen] = useState(false)

  function applyPreset(preset: CharPreset, charId: string, baseConfig: OptimizerConfig) {
    const fourIds = preset.recommended_sets.filter((id) =>
      sets.some((s) => s.id === id && s.pieces === 4)
    )
    const twoIds = preset.recommended_sets
      .filter((id) => sets.some((s) => s.id === id && s.pieces === 2))
      .slice(0, 3)
    const m4 = (preset.main_stat_4.find((s) => SLOT_4_STATS.includes(s as typeof SLOT_4_STATS[number])) ?? null) as string | null
    const m5 = (preset.main_stat_5.find((s) => SLOT_5_STATS.includes(s as typeof SLOT_5_STATS[number])) ?? null) as string | null
    const m6 = (preset.main_stat_6.find((s) => SLOT_6_STATS.includes(s as typeof SLOT_6_STATS[number])) ?? null) as string | null
    lastAutoFilledRef.current = charId
    onChangeRef.current({ ...baseConfig, char_name: charId, four_piece_sets: fourIds, two_piece_sets: twoIds, main_stat_4: m4, main_stat_5: m5, main_stat_6: m6 })
  }

  // Fallback: apply preset when it loads async (first visit, preset not yet cached)
  useEffect(() => {
    if (!sets.length || !charPreset) return
    const charName = configRef.current.char_name
    if (!charName || charName === lastAutoFilledRef.current) return
    applyPreset(charPreset, charName, configRef.current)
  }, [charPreset, sets]) // eslint-disable-line react-hooks/exhaustive-deps

  // Initialize stat_weights from char-weights (or global) when character changes
  useEffect(() => {
    const charName = configRef.current.char_name
    if (charName === lastWeightInitRef.current) return
    const sourceWeights = charSavedWeights ?? globalPriorities
    if (!sourceWeights) return
    lastWeightInitRef.current = charName

    const mapped: Record<string, number> = { ...DEFAULT_STAT_WEIGHTS }
    for (const [k, v] of Object.entries(sourceWeights)) {
      if (k in mapped) mapped[k] = mapWeight(v)
    }
    onChangeRef.current({ ...configRef.current, stat_weights: mapped })
  }, [config.char_name, charSavedWeights, globalPriorities])

  // Clamp min_priority_substats if a weight change drops the priority-stat
  // count below it -- otherwise the slot filter becomes mathematically
  // unsatisfiable (each piece has at most 1 substat per stat name) and the
  // optimizer returns "no build found" with no explanation.
  useEffect(() => {
    const priorityCount = Object.values(config.stat_weights ?? {}).filter((v) => v > 0).length
    if (config.min_priority_substats > priorityCount) {
      onChangeRef.current({ ...configRef.current, min_priority_substats: priorityCount })
    }
  }, [config.stat_weights, config.min_priority_substats])

  const dataLoaded = status?.data_loaded ?? false
  const disabled = isRunning

  const fourPieceOptions: ComboboxOption[] = sets
    .filter((s) => s.pieces === 4)
    .map((s) => ({ id: String(s.id), label: s.name, icon_path: `/assets/game/pieces/item_piece_set_${String(s.id).padStart(3, '0')}_1.png` }))

  const twoPieceOptions: ComboboxOption[] = sets
    .filter((s) => s.pieces === 2)
    .map((s) => ({ id: String(s.id), label: s.name, icon_path: `/assets/game/pieces/item_piece_set_${String(s.id).padStart(3, '0')}_1.png` }))

  const heroOptions: ComboboxOption[] = combatants.map((c) => ({
    id: c.char_id,
    label: c.name,
  }))

  function patch(partial: Partial<OptimizerConfig>) {
    onChange({ ...config, ...partial })
  }

  function patchWeight(stat: string, value: number) {
    const current = config.stat_weights ?? { ...DEFAULT_STAT_WEIGHTS }
    patch({ stat_weights: { ...current, [stat]: value } })
  }

  const canRun = dataLoaded && config.char_name !== '' && !isRunning

  const progressPct =
    progress && progress.total > 0
      ? Math.round((progress.checked / progress.total) * 100)
      : 0

  const sw = config.stat_weights ?? DEFAULT_STAT_WEIGHTS

  return (
    <aside className="w-72 shrink-0 bg-[#181818] border-r border-[#282828] flex flex-col">
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {/* How it works accordion */}
        <div className="rounded-lg border border-[#282828] overflow-hidden">
          <button
            type="button"
            aria-expanded={helpOpen}
            className="w-full flex items-center gap-2 px-3 py-2 text-xs text-[#b3b3b3] hover:text-[#ffffff]"
            onClick={() => setHelpOpen(v => !v)}
          >
            {helpOpen ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
            {t('optimizer.help.title')}
          </button>
          {helpOpen && (
            <div className="px-3 pb-3 space-y-1">
              <p className="text-xs text-[#b3b3b3] leading-relaxed">{t('optimizer.help.body')}</p>
              <p className="text-xs text-[#8a8a8a]">{t('optimizer.help.weightScale')}</p>
            </div>
          )}
        </div>

        {/* Character */}
        <div className="space-y-1">
          <label htmlFor="optimizer-char-combobox" className="text-xs font-medium text-[#b3b3b3]">
            {t('optimizer.character')}
          </label>
          <CharacterCombobox
            id="optimizer-char-combobox"
            combatants={combatants}
            value={config.char_name}
            ariaLabel={t('optimizer.character')}
            searchPlaceholder={t('optimizer.searchChar')}
            emptyLabel={t('optimizer.noCharFound')}
            onChange={(charId) => {
              lastWeightInitRef.current = ''
              lastAutoFilledRef.current = ''

              const combatant = combatants.find((c) => c.char_id === charId)
              const resId = combatant?.res_id ?? null
              const cached = resId != null
                ? queryClient.getQueryData<CharPreset>(['scoring/char-preset', resId])
                : undefined

              const base: OptimizerConfig = {
                ...config,
                char_name: charId,
                four_piece_sets: [],
                two_piece_sets: [],
                main_stat_4: null,
                main_stat_5: null,
                main_stat_6: null,
              }

              if (cached && sets.length) {
                applyPreset(cached, charId, base)
              } else {
                onChange(base)
              }
            }}
            disabled={disabled || combatants.length === 0}
            placeholder={t('optimizer.selectChar')}
          />
        </div>

        {/* 4-piece set */}
        <div className="space-y-1">
          <label className="text-xs font-medium text-[#b3b3b3]">
            {t('optimizer.fourPieceSet')}
          </label>
          <SetCombobox
            options={fourPieceOptions}
            selected={config.four_piece_sets.map(String)}
            onChange={(ids) => patch({ four_piece_sets: ids.map(Number) })}
            maxSelect={1}
            placeholder={t('optimizer.anyOption')}
            disabled={disabled}
            isLoading={setsLoading}
          />
        </div>

        {/* 2-piece sets */}
        <div className="space-y-1">
          <label className="text-xs font-medium text-[#b3b3b3]">
            {t('optimizer.twoPieceSets')}
          </label>
          <SetCombobox
            options={twoPieceOptions}
            selected={config.two_piece_sets.map(String)}
            onChange={(ids) => patch({ two_piece_sets: ids.map(Number) })}
            maxSelect={3}
            placeholder={t('optimizer.noneOption')}
            disabled={disabled}
            isLoading={setsLoading}
          />
        </div>

        {/* Wildcard toggle */}
        <div className="border-t border-[#282828] pt-3">
          <label className="flex items-center gap-2 cursor-pointer select-none">
            <input
              type="checkbox"
              checked={config.allow_wildcards}
              onChange={(e) => patch({ allow_wildcards: e.target.checked })}
              disabled={disabled}
              className="accent-[#c084fc]"
            />
            <span className="text-xs text-[#ffffff] flex items-center gap-1">
              {t('optimizer.allowWildcards')}
              <InfoPopover content={t('optimizer.allowWildcardsTip')} />
            </span>
          </label>
        </div>

        {/* Main stats */}
        {MAIN_STAT_SLOTS.map(({ labelKey, key, opts }) => (
          <div key={key} className="space-y-1">
            <label htmlFor={key} className="text-xs font-medium text-[#b3b3b3]">
              {t(labelKey)}
            </label>
            <select
              id={key}
              value={config[key] ?? ''}
              onChange={(e) => patch({ [key]: e.target.value || null })}
              disabled={disabled}
              className="w-full bg-[#282828] border border-[#333333] rounded px-2.5 h-8 text-sm text-[#ffffff] outline-none focus:border-[#c084fc] disabled:opacity-50 disabled:cursor-not-allowed"
            >
              <option value="">{t('optimizer.anyOption')}</option>
              {opts.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
          </div>
        ))}

        {/* Stat priority */}
        <div className="space-y-2">
          <p className="text-xs font-medium text-[#b3b3b3]">
            {t('optimizer.statPriorityLabel')}
          </p>
          <p className="text-xs text-[#8a8a8a]">
            {t('optimizer.statPriorityHint')}{' '}
            <Link to="/combatants" className="text-[#c084fc] hover:underline">{t('optimizer.statPriorityHintLink')}</Link>.
          </p>
          {STAT_GROUPS.map((group) => (
            <div key={group.labelKey}>
              <p className="text-xs font-medium text-[#8a8a8a] mb-1">{t(group.labelKey)}</p>
              <div className="flex flex-col gap-1">
                {group.stats.map((stat) => {
                  const statKey = stat as string
                  const val = sw[statKey] ?? 0
                  const id = `sw-${statKey.replace(/[^a-z0-9]/gi, '-').toLowerCase()}`
                  return (
                    <div key={statKey} className="flex items-center gap-1.5">
                      <label htmlFor={id} className="text-sm text-[#b3b3b3] flex-1 min-w-0">
                        {statKey}
                      </label>
                      <input
                        id={id}
                        type="number"
                        min={-1}
                        max={3}
                        step={1}
                        value={val}
                        disabled={disabled}
                        onChange={(e) => {
                          const n = Number(e.target.value)
                          if (!Number.isNaN(n)) patchWeight(statKey, n)
                        }}
                        onBlur={(e) => {
                          const clamped = Math.max(-1, Math.min(3, Math.round(Number(e.target.value))))
                          patchWeight(statKey, clamped)
                        }}
                        className="w-14 h-7 text-right text-sm bg-[#282828] border border-[#333333] rounded px-1.5 text-[#ffffff] focus:outline-none focus:border-[#c084fc] disabled:opacity-50"
                      />
                    </div>
                  )
                })}
              </div>
            </div>
          ))}
        </div>

        {/* Filters */}
        <div className="space-y-3">
          <div className="space-y-1">
            <label htmlFor="optimizer-top-pct" className="text-xs font-medium text-[#b3b3b3] flex items-center gap-1">
              {t('optimizer.topPercent')}
              <InfoPopover content={t('optimizer.topPercentTip')} />
            </label>
            <input
              id="optimizer-top-pct"
              type="number"
              min={1}
              max={100}
              value={config.top_percent}
              onChange={(e) => patch({ top_percent: Number(e.target.value) })}
              onBlur={(e) =>
                patch({ top_percent: Math.min(100, Math.max(1, Number(e.target.value))) })
              }
              disabled={disabled}
              className="w-full bg-[#282828] border border-[#333333] rounded px-2.5 h-8 text-sm text-[#ffffff] outline-none focus:border-[#c084fc] disabled:opacity-50 disabled:cursor-not-allowed"
            />
          </div>

          <div className="space-y-1">
            <label className="text-xs font-medium text-[#b3b3b3] flex items-center gap-1">
              {t('optimizer.minPrioritySubstats')}
              <InfoPopover content={t('optimizer.minPrioritySubstatsTip')} />
            </label>
            <div className="flex gap-1">
              {([0, 1, 2, 3] as const).map((n) => {
                // A piece can have at most 1 substat of any given stat. So a piece
                // can satisfy "≥N priority substats" only if at least N distinct
                // stats have weight > 0. Disable buttons that would make filtering
                // mathematically impossible (and produce a misleading "no build").
                const priorityStatCount = Object.values(sw).filter((v) => v > 0).length
                const impossible = n > priorityStatCount
                const isDisabled = disabled || impossible
                return (
                  <button
                    key={n}
                    type="button"
                    disabled={isDisabled}
                    title={impossible ? t('optimizer.minPrioritySubstatsImpossible', { n, count: priorityStatCount }) : undefined}
                    onClick={() => patch({ min_priority_substats: n })}
                    className={[
                      'flex-1 text-sm h-7 rounded border transition-colors disabled:opacity-50 disabled:cursor-not-allowed',
                      config.min_priority_substats === n
                        ? 'bg-[#c084fc]/20 border-[#c084fc] text-[#c084fc] font-semibold'
                        : 'bg-[#282828] border-[#333333] text-[#b3b3b3] hover:border-[#555555]',
                    ].join(' ')}
                  >
                    {n === 0 ? 'Any' : `${n}+`}
                  </button>
                )
              })}
            </div>
          </div>

          <div className="space-y-1">
            <label className="text-xs font-medium text-[#b3b3b3] flex items-center gap-1">
              {t('optimizer.statConstraints')}
              <InfoPopover content={t('optimizer.statConstraintsTip')} />
            </label>
            <div className="grid grid-cols-2 gap-x-2 gap-y-1.5">
              {(
                [
                  { key: 'CRate',  label: 'Crit Rate', placeholder: '0' },
                  { key: 'CDmg',   label: 'Crit DMG',  placeholder: '0' },
                  { key: 'ATK',    label: 'ATK',       placeholder: '0' },
                  { key: 'HP',     label: 'HP',        placeholder: '0' },
                  { key: 'EHP',    label: 'EHP',       placeholder: '0' },
                  { key: 'AvgDMG', label: 'Avg DMG',   placeholder: '0' },
                ] as const
              ).map(({ key, label, placeholder }) => {
                const val = config.stat_constraints?.[key] ?? 0
                return (
                  <div key={key} className="flex items-center gap-1">
                    <span className="text-xs text-[#b3b3b3] w-16 shrink-0">{label}</span>
                    <input
                      type="number"
                      min={0}
                      value={val || ''}
                      placeholder={placeholder}
                      disabled={disabled}
                      onChange={(e) => {
                        const num = Number(e.target.value)
                        const next = { ...(config.stat_constraints ?? {}), [key]: num }
                        patch({ stat_constraints: Object.values(next).every(v => !v) ? null : next })
                      }}
                      className="w-full bg-[#282828] border border-[#333333] rounded px-1.5 h-7 text-sm text-[#ffffff] outline-none focus:border-[#c084fc] disabled:opacity-50 disabled:cursor-not-allowed"
                    />
                  </div>
                )
              })}
            </div>
          </div>

          {/* AvgDMG configuration */}
          <div className="border-t border-[#282828] pt-3 space-y-2">
            <p className="text-xs font-medium text-[#b3b3b3]">
              {t('optimizer.avgDmg.title')}
            </p>
            <p className="text-xs text-[#8a8a8a]">{t('optimizer.avgDmg.hint')}</p>

            {/* Monster Picker - picking a monster fills target_def, its real damage decrease and treat_target_as_weak. Typing a DEF
                below overrides it with the estimate, and clearing the chip falls back to a custom DEF. */}
            {monsterCatalog.length > 0 && (
              <div className="space-y-1">
                <label className="text-xs font-medium text-[#8a8a8a]">
                  {t('optimizer.avgDmg.monster')}
                </label>
                <SetCombobox
                  options={monsterCatalog.map((m) => ({
                    id: m.id,
                    label: `${m.name} (DEF ${m.def}${m.has_weak ? ', weak' : ''})`,
                  }))}
                  selected={(() => {
                    const matched = monsterCatalog.find(
                      (m) =>
                        m.def === (config.target_def ?? 500) &&
                        m.dmg_decrease === (config.target_dmg_decrease ?? 0) &&
                        m.has_weak === (config.treat_target_as_weak ?? false)
                    )
                    return matched ? [matched.id] : []
                  })()}
                  onChange={(ids) => {
                    if (ids.length === 0) {
                      // Cleared — keep current target_def, just behaves as "Custom DEF".
                      return
                    }
                    const m = monsterCatalog.find((mm) => mm.id === ids[0])
                    if (m) {
                      patch({
                        target_def: m.def,
                        target_dmg_decrease: m.dmg_decrease,
                        treat_target_as_weak: m.has_weak,
                      })
                    }
                  }}
                  maxSelect={1}
                  placeholder={t('optimizer.avgDmg.monsterPlaceholder')}
                  disabled={disabled}
                />
              </div>
            )}

            <div className="space-y-1">
              <label htmlFor="optimizer-target-def" className="text-xs font-medium text-[#8a8a8a]">
                {t('optimizer.avgDmg.monsterDef')}
              </label>
              <div className="flex items-center gap-2">
                <input
                  id="optimizer-target-def"
                  type="number"
                  min={0}
                  max={2000}
                  step={50}
                  value={config.target_def ?? 500}
                  onChange={(e) =>
                    patch({
                      target_def: Math.max(0, Math.min(2000, parseInt(e.target.value) || 500)),
                      target_dmg_decrease: 0,
                    })
                  }
                  disabled={disabled}
                  className="w-20 bg-[#282828] border border-[#333333] rounded px-2 h-8 text-sm text-[#ffffff] outline-none focus:border-[#c084fc] disabled:opacity-50 disabled:cursor-not-allowed"
                />
                <span className="text-xs text-[#8a8a8a] tabular-nums">
                  DR {config.target_dmg_decrease ? '' : '≈ '}
                  {(damageDecrease(config.target_dmg_decrease ?? 0, config.target_def ?? 500) * 100).toFixed(1)}%
                </span>
              </div>
            </div>

            <label className="flex items-center gap-2 cursor-pointer select-none">
              <input
                type="checkbox"
                checked={config.treat_target_as_weak ?? false}
                onChange={(e) => patch({ treat_target_as_weak: e.target.checked })}
                disabled={disabled}
                className="accent-[#c084fc]"
              />
              <span className="text-xs text-[#b3b3b3]">
                {t('optimizer.avgDmg.weak')}
              </span>
            </label>

            {/* Multi-target modeling. 0 = auto-detect from the character's best damage card's target_class. */}
            <div className="space-y-1">
              <label htmlFor="optimizer-target-count" className="text-xs font-medium text-[#8a8a8a]">
                {t('optimizer.avgDmg.targetCount')}
              </label>
              <div className="flex items-center gap-2">
                <input
                  id="optimizer-target-count"
                  type="number"
                  min={0}
                  max={5}
                  step={1}
                  value={config.target_count ?? 1}
                  onChange={(e) => {
                    const raw = e.target.value
                    const parsed = parseInt(raw)
                    // Accept 0 as auto sentinel; clamp NaN/negative to 0
                    const next = Number.isNaN(parsed) ? 0 : Math.max(0, Math.min(5, parsed))
                    patch({ target_count: next })
                  }}
                  disabled={disabled}
                  className="w-20 bg-[#282828] border border-[#333333] rounded px-2 h-8 text-sm text-[#ffffff] outline-none focus:border-[#c084fc] disabled:opacity-50 disabled:cursor-not-allowed"
                />
                <span className="text-xs text-[#8a8a8a]">
                  {t('optimizer.avgDmg.targetCountHint')}
                </span>
              </div>
            </div>

            {/* DoT ticks knob */}
            <div className="space-y-1">
              <label htmlFor="optimizer-dot-ticks" className="text-xs font-medium text-[#8a8a8a]">
                {t('optimizer.avgDmg.dotTicks')}
              </label>
              <div className="flex items-center gap-2">
                <input
                  id="optimizer-dot-ticks"
                  type="number"
                  min={1}
                  max={10}
                  step={1}
                  value={config.dot_ticks ?? 3}
                  onChange={(e) =>
                    patch({
                      dot_ticks: Math.max(1, Math.min(10, parseInt(e.target.value) || 3)),
                    })
                  }
                  disabled={disabled}
                  className="w-20 bg-[#282828] border border-[#333333] rounded px-2 h-8 text-sm text-[#ffffff] outline-none focus:border-[#c084fc] disabled:opacity-50 disabled:cursor-not-allowed"
                />
                <span className="text-xs text-[#8a8a8a]">
                  {t('optimizer.avgDmg.dotTicksHint')}
                </span>
              </div>
            </div>
          </div>

          <div className="space-y-1">
            <label htmlFor="optimizer-max-results" className="text-xs font-medium text-[#b3b3b3] flex items-center gap-1">
              {t('optimizer.maxResults')}
              <InfoPopover content={t('optimizer.maxResultsTip')} />
            </label>
            <input
              id="optimizer-max-results"
              type="number"
              min={1}
              max={50}
              value={config.max_results}
              onChange={(e) => patch({ max_results: Number(e.target.value) })}
              onBlur={(e) =>
                patch({ max_results: Math.min(50, Math.max(1, Number(e.target.value))) })
              }
              disabled={disabled}
              className="w-full bg-[#282828] border border-[#333333] rounded px-2.5 h-8 text-sm text-[#ffffff] outline-none focus:border-[#c084fc] disabled:opacity-50 disabled:cursor-not-allowed"
            />
          </div>

          <label className="flex items-center gap-2 cursor-pointer select-none">
            <input
              type="checkbox"
              checked={config.include_equipped}
              onChange={(e) => patch({ include_equipped: e.target.checked })}
              disabled={disabled}
              className="accent-[#c084fc]"
            />
            <span className="text-xs text-[#ffffff] flex items-center gap-1">
              {t('optimizer.includeEquipped')}
              <InfoPopover content={t('optimizer.includeEquippedTip')} />
            </span>
          </label>
        </div>

        {/* Excluded heroes */}
        <div className="space-y-1">
          <label className="text-xs font-medium text-[#b3b3b3] flex items-center gap-1">
            {t('optimizer.excludeChars')}
            <InfoPopover content={t('optimizer.excludeCharsTip')} />
          </label>
          <SetCombobox
            options={heroOptions}
            selected={config.excluded_heroes}
            onChange={(ids) => patch({ excluded_heroes: ids })}
            maxSelect={99}
            placeholder={t('optimizer.noneOption')}
            disabled={disabled}
          />
        </div>

      </div>

      {/* Run controls stay pinned under the settings so they are always in view */}
      <div className="shrink-0 border-t border-[#282828] p-4 space-y-2">
        {/* Progress bar (running only) */}
        {isRunning && (
          <div className="space-y-1">
            <div className="h-1.5 bg-[#282828] rounded-full overflow-hidden">
              <div
                className="h-full bg-[#c084fc] rounded-full transition-all duration-300"
                style={{ width: `${progressPct}%` }}
              />
            </div>
            <p className="text-xs text-[#b3b3b3] tabular-nums">
              {progressPct}%
            </p>
          </div>
        )}

        {/* Run error */}
        {runError && (
          <p role="alert" className="text-xs text-[#f3727f]">
            {runError}
          </p>
        )}

        {/* Run / Cancel */}
        {isRunning ? (
          <button
            type="button"
            onClick={onCancel}
            className="w-full flex items-center justify-center gap-2 bg-[#282828] hover:bg-[#333333] border border-[#333333] rounded-md py-2 text-sm text-[#ffffff] transition-colors"
          >
            <Square size={13} />
            {t('optimizer.cancel')}
          </button>
        ) : (
          <button
            type="button"
            onClick={onRun}
            disabled={!canRun}
            className={`${PRIMARY_ACTION} w-full`}
          >
            <Play size={13} />
            {t('optimizer.run')}
          </button>
        )}
        {!isRunning && config.char_name === '' && (
          <p className="text-xs text-[#b3b3b3] text-center">{t('optimizer.pickCharacter')}</p>
        )}
      </div>
    </aside>
  )
}
