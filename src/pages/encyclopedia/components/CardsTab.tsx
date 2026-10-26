import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { TriangleAlert } from 'lucide-react'
import { api, ApiError } from '@/lib/api'
import { EmptyState, RetryButton } from '@/components/ui/empty-state'
import type { CardEntry, CardCharacter } from '@/lib/types'
import { CardImage } from '@/pages/deck-builder/components/CardImage'
import { DetailHeader, DetailSection, EncyclopediaLayout, ListRow } from './EncyclopediaLayout'
import { FilterSection } from './FilterSection'

const TYPE_COLORS: Record<string, string> = {
  DMG:     'bg-[#7f1d1d] text-[#fca5a5]',
  Draw:    'bg-[#1e3a5f] text-[#93c5fd]',
  Buff:    'bg-[#14532d] text-[#86efac]',
  Cost:    'bg-[#3b1f6e] text-[#c4b5fd]',
  Discard: 'bg-[#292524] text-[#a8a29e]',
  Exhaust: 'bg-[#292524] text-[#a8a29e]',
  Get:     'bg-[#1a2e1a] text-[#86efac]',
  Change:  'bg-[#1c2a3a] text-[#7dd3fc]',
  Copy:    'bg-[#1c2a3a] text-[#7dd3fc]',
  Use:     'bg-[#2a1c1c] text-[#fca5a5]',
}

const CARD_FILTERS = ['dmg', 'support']

function TypeBadge({ type }: { type: string }) {
  const cls = TYPE_COLORS[type] ?? 'bg-[#222] text-[#b3b3b3]'
  return (
    <span className={`text-[11px] font-bold px-1.5 py-0.5 rounded uppercase tracking-wide ${cls}`}>
      {type}
    </span>
  )
}

/**
 * One number in the card detail's stat row.
 * @param props The stat's label and value, or null when the card has none.
 * @returns The stat tile.
 */
function Stat({ label, value }: { label: string; value: string | null }) {
  return (
    <div className="rounded-lg border border-[#282828] bg-[#161616] px-3 py-2">
      <p className="text-xs text-[#8a8a8a]">{label}</p>
      <p className="mt-0.5 font-mono text-base text-[#e5e7eb]">{value ?? '-'}</p>
    </div>
  )
}

export function CardsTab() {
  const { t } = useTranslation()
  const [selectedChar, setSelectedChar] = useState<string | null>(null)
  const [search, setSearch] = useState('')
  const [filterType, setFilterType] = useState<string | null>(null)
  const [selectedId, setSelectedId] = useState<string | null>(null)

  const { data: characters = [] } = useQuery<CardCharacter[]>({
    queryKey: ['card-characters'],
    queryFn: () => api.cardCharacters(),
    staleTime: Infinity,
  })

  const { data: allCards = [], isLoading, error, refetch } = useQuery<CardEntry[]>({
    queryKey: ['cards', selectedChar],
    queryFn: () => api.cards(selectedChar ? Number(selectedChar) : undefined),
    staleTime: Infinity,
  })

  const filtered = allCards.filter(card => {
    if (filterType === 'dmg' && card.eff_value === 0) return false
    if (filterType === 'support' && card.eff_value > 0) return false
    if (search) {
      const q = search.toLowerCase()
      if (!card.name.toLowerCase().includes(q)) return false
    }
    return true
  })

  const charName = (id: number | null) => {
    const c = characters.find(ch => ch.char_res_id === id)
    return c ? c.name || `#${c.char_res_id}` : null
  }
  const selected = allCards.find(card => card.card_id === selectedId) ?? null

  return (
    <EncyclopediaLayout
      search={search}
      onSearch={setSearch}
      searchPlaceholder={t('encyclopedia.search')}
      filters={
        <>
          <FilterSection label={t('cards.filterType')} options={CARD_FILTERS} value={filterType} onChange={setFilterType} format={f => t(`cards.filter.${f}`)} />
          <FilterSection
            label={t('cards.character')}
            options={characters.map(c => String(c.char_res_id))}
            value={selectedChar}
            onChange={setSelectedChar}
            format={id => charName(Number(id)) ?? id}
          />
        </>
      }
      count={filtered.length}
      listFallback={
        isLoading ? (
          <p className="p-4 text-sm text-[#8a8a8a]">{t('common.loading')}</p>
        ) : error ? (
          <EmptyState
            icon={TriangleAlert}
            title={t('cards.loadError')}
            hint={error instanceof ApiError ? error.message : t('empty.serviceDown')}
            action={<RetryButton onClick={() => refetch()} />}
          />
        ) : undefined
      }
      detail={
        selected && (
          <div className="flex max-w-2xl flex-col gap-5">
            <DetailHeader
              title={selected.name || t('cards.unnamed')}
              meta={charName(selected.char_res_id) ?? t('cards.shared')}
              media={<CardImage card={selected} className="h-48 w-32 shrink-0 rounded-lg border border-[#282828]" />}
            />

            {selected.effect_types.length > 0 && (
              <DetailSection label={t('cards.col.type')}>
                <div className="flex flex-wrap gap-1">
                  {selected.effect_types.map(type => <TypeBadge key={type} type={type} />)}
                </div>
              </DetailSection>
            )}

            <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
              <Stat label={t('cards.col.cost')} value={String(selected.cost)} />
              <Stat label={t('cards.col.coefficient')} value={selected.eff_value > 0 ? `${(selected.eff_value / 100).toFixed(2)}× ATK` : null} />
              <Stat label={t('cards.col.hits')} value={selected.hits > 0 ? String(selected.hits) : null} />
              <Stat label={t('cards.col.spark')} value={selected.spark_count > 0 ? `+${selected.spark_count}` : null} />
            </div>
          </div>
        )
      }
    >
      {filtered.map(card => (
        <ListRow key={card.card_id} selected={selectedId === card.card_id} onSelect={() => setSelectedId(card.card_id)}>
          <span className="grid h-8 w-8 shrink-0 place-items-center rounded-md border border-[#075985] bg-[#082f49] font-mono text-sm font-bold text-[#93c5fd]">
            {card.cost}
          </span>
          <span className="min-w-0 flex-1">
            <span className="block truncate text-sm font-medium text-[#e5e7eb]">
              {card.name || <span className="italic text-[#8a8a8a]">{t('cards.unnamed')}</span>}
            </span>
            {card.effect_types.length > 0 && (
              <span className="mt-1 flex flex-wrap gap-1">
                {card.effect_types.map(type => <TypeBadge key={type} type={type} />)}
              </span>
            )}
          </span>
        </ListRow>
      ))}
    </EncyclopediaLayout>
  )
}
