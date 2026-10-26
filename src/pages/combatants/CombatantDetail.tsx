import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { Loader2, User } from 'lucide-react'
import { api, assetUrl } from '@/lib/api'
import { AssetImage } from '@/components/ui/asset-image'
import type { GearSlot, FinalStats, BaseStats } from '@/lib/types'
import { InfoPopover } from '@/components/ui/info-popover'

// ─── Grade helpers ─────────────────────────────────────────────────────────

// Graded against the Legendary theoretical max (~70 = 7 roll-units × 10).
// Uses potential_high so unupgraded pieces reflect their ceiling, not current state.
// Scale: SSS ≥ 93% · SS+ ≥ 86% · SS ≥ 79% · S ≥ 70% · A ≥ 61% · B ≥ 53% · C otherwise
function scoreGrade(score: number): { label: string; color: string } {
  if (score >= 65) return { label: 'SSS', color: 'text-[#ffd700]' }
  if (score >= 60) return { label: 'SS+', color: 'text-[#ff9d00]' }
  if (score >= 55) return { label: 'SS',  color: 'text-[#ff6b6b]' }
  if (score >= 49) return { label: 'S',   color: 'text-[#c084fc]' }
  if (score >= 43) return { label: 'A',   color: 'text-[#60a5fa]' }
  if (score >= 37) return { label: 'B',   color: 'text-[#4ade80]' }
  return                   { label: 'C',   color: 'text-[#94a3b8]' }
}

function RollArrows({ count }: { count: number }) {
  if (count <= 1) return null
  const arrows = count === 2 ? '›' : count === 3 ? '››' : '›››'
  return <span className="text-[#c084fc] text-[11px] mr-0.5 leading-none">{arrows}</span>
}

function pieceImageUrl(setId: number, slotNum: number): string {
  return assetUrl(`/assets/game/pieces/item_piece_set_${String(setId).padStart(3, '0')}_${slotNum}.png`)
}

// ─── EquippedByAvatar ──────────────────────────────────────────────────────

function EquippedByAvatar({ portrait, name }: { portrait?: string; name?: string }) {
  if (!name && !portrait) return null

  const initial = name ? (
    <div
      className="absolute top-2 right-2 w-6 h-6 rounded-full bg-[#282828] flex items-center justify-center"
      title={name}
      aria-label={name}
    >
      <User size={12} className="text-[#8a8a8a]" />
    </div>
  ) : null

  if (portrait) {
    return (
      <AssetImage
        src={portrait}
        alt={name ?? ''}
        title={name}
        className="absolute top-2 right-2 w-6 h-6 rounded-full object-cover border border-[#282828]"
        fallback={initial}
      />
    )
  }

  return initial
}

// ─── GearSlotCard ──────────────────────────────────────────────────────────

export function GearSlotCard({
  slot,
  equippedToPortrait,
  equippedToName,
}: {
  slot: GearSlot
  equippedToPortrait?: string
  equippedToName?: string
}) {
  const { t } = useTranslation()

  if (slot.main_stat === null) {
    return (
      <div className="bg-[#121212] border border-[#282828] rounded-xl p-3 space-y-1">
        <p className="text-xs font-medium text-[#8a8a8a]">{slot.slot}</p>
        <p className="text-xs text-[#8a8a8a] italic">{t('combatants.detail.empty')}</p>
      </div>
    )
  }

  const displayScore =
    slot.priority_score != null && slot.priority_score > 0
      ? slot.priority_score
      : slot.score
  // Grade based on potential_high so it reflects the piece ceiling (consistent across upgrade levels).
  // Falls back to gear_score if potential_high is absent (e.g. optimizer results).
  const gradeBase = slot.potential_high ?? slot.score
  const grade = gradeBase != null ? scoreGrade(gradeBase) : null
  // The grade is a ceiling when the piece can still grow past its current score
  const gradeIsCeiling = slot.potential_high != null && slot.potential_high > (slot.score ?? 0)
  const hasPieceImg = slot.set_id != null && slot.slot_num != null

  const pieceFallback = (
    <div className="w-10 h-10 bg-[#282828] rounded-lg flex items-center justify-center">
      <span className="text-[11px] text-[#8a8a8a]">{slot.slot_num ?? '?'}</span>
    </div>
  )

  return (
    <div className="bg-[#181818] border border-[#282828] rounded-xl overflow-hidden">
      {/* Header */}
      <div className="relative flex items-center gap-2.5 px-3 pt-3 pb-2.5 border-b border-[#1e1e1e]">
        <div className="relative shrink-0">
          {hasPieceImg ? (
            <AssetImage
              src={pieceImageUrl(slot.set_id!, slot.slot_num!)}
              alt={slot.set_name ?? slot.slot}
              className="w-10 h-10 object-contain rounded-lg"
              fallback={pieceFallback}
            />
          ) : (
            pieceFallback
          )}
          {slot.level != null && slot.level > 0 && (
            <span className="absolute -bottom-1 -right-1 bg-[#c084fc] text-[#121212] text-[11px] font-bold px-1 py-px rounded leading-tight">
              +{slot.level}
            </span>
          )}
        </div>

        <div className="flex-1 min-w-0">
          <p title={slot.set_name ?? slot.slot} className="text-xs text-[#b3b3b3] truncate">
            {slot.set_name ?? slot.slot}
          </p>
          <p className="text-sm font-semibold text-[#ffffff] truncate">{slot.main_stat}</p>
        </div>

        <EquippedByAvatar portrait={equippedToPortrait} name={equippedToName} />
      </div>

      {/* Substats */}
      <div className="px-3 py-2 space-y-1">
        {slot.substats.map((s, i) => {
          const eff = s.efficiency
          const effColor = eff == null ? '' : eff >= 80 ? 'text-[#4ade80]' : eff >= 60 ? 'text-[#facc15]' : 'text-[#f87171]'
          return (
            <div key={i} className="flex items-center justify-between text-xs">
              <div className="flex items-center text-[#b3b3b3]">
                <RollArrows count={s.roll_count} />
                <span>{s.name}</span>
              </div>
              <div className="flex items-center gap-1.5 tabular-nums">
                <span className="text-[#ffffff] font-medium">{s.value}</span>
                {eff != null && (
                  <span className={effColor}>{eff}%</span>
                )}
              </div>
            </div>
          )
        })}
      </div>

      {/* Score */}
      {displayScore != null && (
        <div className="px-3 pb-3 pt-1 border-t border-[#1e1e1e] mt-1">
          <div className="flex items-center justify-between text-sm">
            <span className="text-[#b3b3b3]">Score</span>
            <div className="flex items-center gap-1.5">
              <span className="text-[#c084fc] font-bold">{displayScore.toFixed(1)}</span>
              {grade && (
                <span
                  title={gradeIsCeiling ? t('combatants.detail.gradeCeilingTip') : undefined}
                  className={`text-xs font-bold ${grade.color}`}
                >
                  {gradeIsCeiling ? t('combatants.detail.gradeCeiling', { grade: grade.label }) : `(${grade.label})`}
                </span>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export function FinalStatsPanel({ stats, compact = false }: { stats: FinalStats; compact?: boolean }) {
  const { t } = useTranslation()

  const rows: Array<{ label: string; value: string; tip?: string }> = [
    { label: 'ATK', value: stats.ATK.toLocaleString() },
    { label: 'DEF', value: stats.DEF.toLocaleString() },
    { label: 'HP', value: stats.HP.toLocaleString() },
    { label: 'Crit Rate', value: `${stats.CRate.toFixed(1)}%` },
    { label: 'Crit DMG', value: `${stats.CDmg.toFixed(1)}%` },
    { label: 'EHP', value: stats.EHP.toLocaleString(), tip: t('combatants.detail.ehpTip') },
    { label: 'Avg DMG', value: stats.AvgDMG.toLocaleString() },
    ...(stats.ExtraDMG && stats.ExtraDMG > 0 ? [{ label: 'Extra DMG%', value: `+${stats.ExtraDMG.toFixed(1)}%` }] : []),
    ...(stats.Ego && stats.Ego > 0 ? [{ label: 'Ego', value: stats.Ego.toLocaleString() }] : []),
  ]
  return (
    <div className={`bg-[#181818] border border-[#282828] rounded-xl ${compact ? 'p-2.5' : 'p-4'}`}>
      <p className={`text-xs font-medium text-[#b3b3b3] ${compact ? 'mb-1.5' : 'mb-3'}`}>
        {t('combatants.detail.finalStats')}
      </p>
      <div className={`grid grid-cols-2 ${compact ? 'gap-x-4 gap-y-0.5' : 'gap-x-6 gap-y-2'}`}>
        {rows.map(r => (
          <div key={r.label} className={`flex justify-between ${compact ? 'text-xs' : 'text-sm'}`}>
            <span className="flex items-center gap-1 text-[#b3b3b3]">
              {r.label}
              {r.tip && <InfoPopover content={r.tip} />}
            </span>
            <span className="text-[#c084fc] font-semibold">{r.value}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

export function BaseStatsPanel({ stats }: { stats: BaseStats }) {
  const { t } = useTranslation()

  const rows = [
    { label: 'ATK', value: stats.s_atk.toLocaleString() },
    { label: 'DEF', value: stats.s_def.toLocaleString() },
    { label: 'HP', value: stats.s_hp.toLocaleString() },
    { label: 'Crit Rate', value: `${stats.s_cri}%` },
    { label: 'Crit DMG', value: `${stats.s_cri_dmg_rate}%` },
  ]

  return (
    <div className="bg-[#181818] border border-[#282828] rounded-xl p-4">
      <p className="text-xs font-medium text-[#b3b3b3] mb-3">
        {t('combatants.detail.baseStats')}
      </p>
      <div className="grid grid-cols-2 gap-x-6 gap-y-2">
        {rows.map(r => (
          <div key={r.label} className="flex justify-between text-sm">
            <span className="text-[#b3b3b3]">{r.label}</span>
            <span className="text-[#60a5fa] font-semibold">{r.value}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

interface CombatantDetailProps {
  charId: string
}

export function CombatantDetail({ charId }: CombatantDetailProps) {
  const { t } = useTranslation()

  const { data, isLoading, error } = useQuery({
    queryKey: ['combatants', charId, 'stats'],
    queryFn: () => api.combatantStats(charId),
    enabled: !!charId,
  })

  if (isLoading) {
    return (
      <div role="status" aria-label={t('combatants.detail.loading')} className="flex items-center p-6 text-[#b3b3b3]">
        <Loader2 size={16} className="animate-spin mr-2" />
        <span className="text-sm">{t('combatants.detail.loadingText')}</span>
      </div>
    )
  }

  if (error) {
    return (
      <div role="alert" className="p-4 text-sm text-[#f3727f]">
        {t('combatants.detail.error')}
      </div>
    )
  }

  if (!data) return null

  return (
    <div className="space-y-4 mt-4">
      <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
        {data.gear_slots.map((slot) => (
          <GearSlotCard key={slot.slot} slot={slot} />
        ))}
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        {data.base_stats && <BaseStatsPanel stats={data.base_stats} />}
        <FinalStatsPanel stats={data.final_stats} />
      </div>
    </div>
  )
}
