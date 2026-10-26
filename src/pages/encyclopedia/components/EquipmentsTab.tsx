import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import {
  DECK_BUILDER_ITEMS,
  getDeckBuilderItemImageUrl,
  getItemRarityClassName,
} from '@/pages/deck-builder/deck-builder-items.utils'
import { findClarification } from '../encyclopedia-content'
import { localized, resolveLang } from '../encyclopedia.utils'
import { ClarifiedText, DetailHeader, DetailSection, EncyclopediaLayout, ListRow } from './EncyclopediaLayout'
import { FilterSection } from './FilterSection'

const SLOTS = ['Weapon', 'Armor', 'Accessory']
const RARITIES = ['Rare', 'Legendary', 'Unique']

export function EquipmentsTab() {
  const { t, i18n } = useTranslation()
  const lang = resolveLang(i18n.language)
  const [search, setSearch] = useState('')
  const [slot, setSlot] = useState<string | null>(null)
  const [rarity, setRarity] = useState<string | null>(null)
  const [selectedId, setSelectedId] = useState<string | null>(null)

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase()
    return DECK_BUILDER_ITEMS.filter(item => {
      if (slot && item.slot !== slot) return false
      if (rarity && item.rarity !== rarity) return false
      if (q && !item.name.toLowerCase().includes(q)) return false
      return true
    })
  }, [search, slot, rarity])

  const selected = useMemo(
    () => DECK_BUILDER_ITEMS.find(i => i.id === selectedId) ?? null,
    [selectedId],
  )
  const imageUrl = selected ? getDeckBuilderItemImageUrl(selected) : null
  const clar = selected ? findClarification('equipment', selected.id) : undefined

  return (
    <EncyclopediaLayout
      search={search}
      onSearch={setSearch}
      searchPlaceholder={t('encyclopedia.search')}
      filters={
        <>
          <FilterSection label={t('encyclopedia.equipments.slot')} options={SLOTS} value={slot} onChange={setSlot} />
          <FilterSection label={t('encyclopedia.equipments.rarity')} options={RARITIES} value={rarity} onChange={setRarity} />
        </>
      }
      count={filtered.length}
      detail={
        selected && (
          <div className="flex max-w-2xl flex-col gap-5">
            <DetailHeader
              title={selected.name}
              meta={`${selected.slot} · ${selected.rarity}`}
              media={imageUrl && (
                <img
                  src={imageUrl}
                  alt={selected.name}
                  className={`h-20 w-20 shrink-0 rounded-lg border object-cover ${getItemRarityClassName(selected.rarity)}`}
                />
              )}
            />

            <ClarifiedText clarification={clar && localized(clar.text, lang)} gameText={localized(selected.description, lang)} />

            {selected.stat_type && selected.stat_values?.length ? (
              <DetailSection label={`${t('encyclopedia.equipments.stat')} · ${selected.stat_type}`}>
                <div className="flex flex-wrap gap-2">
                  {selected.stat_values.map((v, i) => (
                    <span key={i} className="rounded bg-[#222] px-2.5 py-1 font-mono text-sm text-[#e5e7eb]" title={`Lv ${i + 1}`}>
                      {v}
                    </span>
                  ))}
                </div>
              </DetailSection>
            ) : null}

            {selected.source && (
              <DetailSection label={t('encyclopedia.equipments.source')}>
                <p className="text-sm text-[#d4d4d4]">{selected.source}</p>
              </DetailSection>
            )}
          </div>
        )
      }
    >
      {filtered.map(item => (
        <ListRow key={item.id} selected={selectedId === item.id} onSelect={() => setSelectedId(item.id)}>
          <span className={`h-2.5 w-2.5 shrink-0 rounded-full border ${getItemRarityClassName(item.rarity)}`} />
          <span className="min-w-0 flex-1">
            <span className="block truncate text-sm font-medium text-[#e5e7eb]">{item.name}</span>
            <span className="block text-xs text-[#8a8a8a]">{item.slot} · {item.rarity}</span>
          </span>
        </ListRow>
      ))}
    </EncyclopediaLayout>
  )
}
