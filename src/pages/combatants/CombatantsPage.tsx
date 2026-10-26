import { useState, useCallback } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { Users, Loader2, ChevronDown, ChevronRight, Download, ExternalLink } from 'lucide-react'
import { api, assetUrl, ApiError } from '@/lib/api'
import { EmptyState, RetryButton } from '@/components/ui/empty-state'
import { AssetImage } from '@/components/ui/asset-image'
import { openExternal } from '@/lib/browser'
import { downloadJson } from '@/lib/download'
import type { Combatant } from '@/lib/types'
import { GearSlotCard, FinalStatsPanel } from './CombatantDetail'
import { GlobalScoring, CharacterScoring } from './ScoringSection'
import { Button } from '@/components/ui/button'

// ─── Attribute badge ───────────────────────────────────────────────────────

const ATTR_ICON: Record<string, string> = {
  Passion:  '/assets/game/icon_type_ego_passion.png',
  Order:    '/assets/game/icon_type_ego_order.png',
  Justice:  '/assets/game/icon_type_ego_justice.png',
  Void:     '/assets/game/icon_type_ego_void.png',
  Instinct: '/assets/game/icon_type_ego_instinct.png',
}

function AttrBadge({ attr }: { attr: string }) {
  const icon = ATTR_ICON[attr]
  if (icon) {
    return (
      <AssetImage
        src={assetUrl(icon)}
        alt={attr}
        title={attr}
        className="w-7 h-7 shrink-0 object-contain"
      />
    )
  }
  return (
    <span className="text-xs font-semibold px-1.5 py-0.5 rounded border leading-tight shrink-0 bg-[#282828] text-[#b3b3b3] border-[#333333]">
      {attr}
    </span>
  )
}

// ─── Collapse art — absolute, fills container height, natural width ────────

function CollapseBackground({ resId }: { resId: number }) {
  const cls = 'absolute left-0 top-0 pointer-events-none select-none'
  const style = { height: '100%', width: 'auto' }
  const url = (variant: string) => assetUrl(`/assets/game/collapse/collapse_${resId}_${variant}.png`)
  return (
    <AssetImage
      src={url('02')}
      alt=""
      className={cls}
      style={style}
      maxRetries={0}
      fallback={<AssetImage src={url('01')} alt="" className={cls} style={style} fallback={null} />}
    />
  )
}

// ─── Partner badge ─────────────────────────────────────────────────────────

function PartnerBadge({
  partnerResId,
  partnerName,
}: {
  partnerResId: number | null | undefined
  partnerName: string | null | undefined
}) {
  const [imgOk, setImgOk] = useState(true)
  if (!partnerResId && !partnerName) return null
  return (
    <div className="flex items-center gap-2 bg-[#141414]/90 border border-[#2a2a2a] rounded-lg px-2 py-1.5">
      {partnerResId && imgOk ? (
        <AssetImage
          src={assetUrl(`/assets/game/tp_skill/battle_icon_tp_skill_${partnerResId}.png`)}
          alt={partnerName ?? ''}
          className="w-14 h-9 rounded object-cover shrink-0"
          onError={() => setImgOk(false)}
        />
      ) : (
        <div className="w-14 h-9 rounded bg-[#282828] shrink-0" />
      )}
      <div className="min-w-0">
        <p className="text-xs text-[#8a8a8a] leading-tight">Partner</p>
        <p className="text-sm text-[#e5e7eb] truncate leading-tight">{partnerName ?? '—'}</p>
      </div>
    </div>
  )
}

// ─── Expanded content ──────────────────────────────────────────────────────

function ExpandedContent({
  charId,
  resId,
  partnerResId,
  partnerName,
}: {
  charId: string
  resId: number
  partnerResId: number | null | undefined
  partnerName: string | null | undefined
}) {
  const { data, isLoading } = useQuery({
    queryKey: ['combatants', charId, 'stats'],
    queryFn: () => api.combatantStats(charId),
    staleTime: 30_000,
  })

  return (
    <div className="relative overflow-hidden border-t border-[#1e1e1e] bg-[#0e0e0e]">
      {/* Character art: left-anchored, fills full panel height */}
      <CollapseBackground resId={resId} />

      {/* Gradient: image fades right into background */}
      <div
        className="absolute inset-0 pointer-events-none"
        style={{
          background:
            'linear-gradient(to right, transparent 12%, rgba(14,14,14,0.55) 26%, rgba(14,14,14,0.82) 42%, #0e0e0e 58%)',
        }}
      />

      {/* Content */}
      <div className="relative z-10 flex flex-col pt-3 pb-5">
        {isLoading ? (
          <div className="flex items-center justify-center py-10">
            <Loader2 size={18} className="animate-spin text-[#c084fc]" />
          </div>
        ) : data ? (
          <>
            {/* Top: partner + compact stats — right-aligned, spanning right 3 of 6 cols */}
            <div className="px-4 mb-3 flex flex-col items-end gap-2">
              <PartnerBadge partnerResId={partnerResId} partnerName={partnerName} />
              <div style={{ width: 'calc(50% - 4px)' }}>
                <FinalStatsPanel stats={data.final_stats} compact />
              </div>
            </div>

            {/* Bottom: gear cards — full width */}
            <div className="grid grid-cols-3 2xl:grid-cols-6 gap-2 px-4">
              {data.gear_slots.map((slot) => (
                <GearSlotCard key={slot.slot} slot={slot} />
              ))}
            </div>

            <CharacterScoring charId={charId} resId={resId} />
          </>
        ) : null}
      </div>
    </div>
  )
}

// ─── Combatant list row ────────────────────────────────────────────────────

function CombatantRow({
  combatant,
  rank,
  expanded,
  onToggle,
}: {
  combatant: Combatant
  rank: number
  expanded: boolean
  onToggle: () => void
}) {
  const tpUrl = assetUrl(`/assets/game/tp_skill/battle_icon_tp_skill_${combatant.res_id}.png`)

  return (
    <div
      className={`rounded-xl overflow-hidden border transition-colors ${
        expanded ? 'border-[#c084fc]/40' : 'border-[#282828]'
      } bg-[#181818]`}
    >
      <button
        type="button"
        onClick={onToggle}
        aria-pressed={expanded}
        className={`w-full flex items-center gap-4 px-4 py-3 text-left transition-colors ${
          expanded ? 'bg-[#c084fc]/5' : 'hover:bg-[#1e1e1e]'
        }`}
      >
        {/* Rank */}
        <span className="w-6 text-right text-sm text-[#8a8a8a] tabular-nums shrink-0">
          {rank}
        </span>

        {/* Rectangular battle icon */}
        <div className="w-24 h-14 shrink-0 rounded-lg overflow-hidden bg-[#121212] border border-[#252525]">
          <AssetImage
            src={tpUrl}
            alt={combatant.name}
            className="w-full h-full object-cover"
          />
        </div>

        {/* Name + level */}
        <div className="flex-1 min-w-0">
          <p className="text-base font-semibold text-[#ffffff] truncate leading-tight">{combatant.name}</p>
          <p className="mt-0.5 text-sm text-[#b3b3b3] leading-tight">Lv. {combatant.level}</p>
        </div>

        {/* Attribute */}
        <AttrBadge attr={combatant.attribute} />

        {/* Class */}
        <span className="hidden sm:block w-24 text-center text-sm px-2 py-0.5 rounded bg-[#232323] text-[#b3b3b3] border border-[#2e2e2e] shrink-0">
          {combatant.class}
        </span>

        {/* Ego Manifestation */}
        {combatant.ego != null && (
          <span className={`w-7 text-sm font-bold shrink-0 tabular-nums ${
            combatant.ego === 6 ? 'text-[#ffd700]' : 'text-[#b3b3b3]'
          }`}>
            E{combatant.ego}
          </span>
        )}

        {/* GS score */}
        <div className="shrink-0 text-right w-16">
          {combatant.avg_gear_score > 0 ? (
            <span className="text-lg font-bold text-[#c084fc] tabular-nums">
              {combatant.avg_gear_score.toFixed(1)}
            </span>
          ) : (
            <span className="text-lg text-[#8a8a8a]">—</span>
          )}
          <p className="text-xs text-[#8a8a8a]">GS</p>
        </div>

        {/* Chevron */}
        <div className={`shrink-0 transition-colors ${expanded ? 'text-[#c084fc]' : 'text-[#8a8a8a]'}`}>
          {expanded ? <ChevronDown size={18} /> : <ChevronRight size={18} />}
        </div>
      </button>

      {expanded && (
        <ExpandedContent
          charId={combatant.char_id}
          resId={combatant.res_id}
          partnerResId={combatant.partner_res_id}
          partnerName={combatant.partner_name}
        />
      )}
    </div>
  )
}

// ─── Page ──────────────────────────────────────────────────────────────────

export function CombatantsPage() {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const [expandedId, setExpandedId] = useState<string | null>(null)

  const { data: combatants = [], isLoading, error } = useQuery({
    queryKey: ['combatants'],
    queryFn: () => api.combatants(),
    staleTime: 30_000,
  })

  const handleToggle = useCallback((charId: string) => {
    setExpandedId((prev) => (prev === charId ? null : charId))
  }, [])

  const [exporting, setExporting] = useState(false)

  const exportCombatants = useCallback(async () => {
    setExporting(true)
    try {
      const data = await api.combatantsExport()
      await downloadJson('combatants.json', data)
    } finally {
      setExporting(false)
    }
  }, [])

  if (error) {
    return (
      <div className="p-4">
        <p className="text-sm text-[#f3727f]">{t('combatants.loadError')}</p>
        <p className="mt-1 mb-3 text-sm text-[#b3b3b3]">{error instanceof ApiError ? error.message : t('empty.serviceDown')}</p>
        <RetryButton onClick={() => queryClient.invalidateQueries({ queryKey: ['combatants'] })} />
      </div>
    )
  }

  if (isLoading) {
    return (
      <div role="status" aria-label={t('combatants.loading')} className="flex-1 p-4 space-y-1.5">
        {Array.from({ length: 10 }).map((_, i) => (
          <div key={i} className="h-20 rounded-xl bg-[#181818] border border-[#282828] animate-pulse" />
        ))}
      </div>
    )
  }

  // Global weights also score Memory Fragments, so they stay editable before any combatant is captured.
  if (combatants.length === 0) {
    return (
      <div className="h-full flex flex-col gap-4 p-4">
        <GlobalScoring />
        <EmptyState icon={Users} title={t('combatants.empty')} hint={t('combatants.emptyHint')} className="flex-1" />
      </div>
    )
  }

  return (
    <div className="flex-1 flex flex-col overflow-hidden">
      <div className="flex items-center justify-end gap-2 px-4 pt-3 pb-1 shrink-0">
        <Button
          size="sm"
          variant="outline"
          disabled={exporting}
          onClick={exportCombatants}
          className="border-[#282828] text-[#b3b3b3] hover:text-[#ffffff] disabled:opacity-40"
        >
          {exporting
            ? <Loader2 size={13} className="mr-1 animate-spin" />
            : <Download size={13} className="mr-1" />
          }
          {t('combatants.exportJson')}
        </Button>
        <Button
          size="sm"
          variant="outline"
          onClick={() => openExternal('https://hub-czn.lovable.app')}
          className="border-[#282828] text-[#b3b3b3] hover:text-[#ffffff]"
        >
          <ExternalLink size={13} className="mr-1" />
          {t('combatants.saveCloud')}
        </Button>
      </div>
      <div className="flex-1 overflow-y-auto px-4 pb-4 space-y-1.5">
        <div className="pb-2">
          <GlobalScoring />
        </div>
        {combatants.map((c, i) => (
          <CombatantRow
            key={c.char_id}
            combatant={c}
            rank={i + 1}
            expanded={expandedId === c.char_id}
            onToggle={() => handleToggle(c.char_id)}
          />
        ))}
      </div>
    </div>
  )
}
