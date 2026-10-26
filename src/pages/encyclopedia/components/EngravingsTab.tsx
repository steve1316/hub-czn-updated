import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { DECK_BUILDER_PERSONA_ENGRAVING_CARDS } from '@/pages/deck-builder/deck-builder-persona-engraving.utils'
import type { DeckBuilderPersonaEngraving } from '@/pages/deck-builder/deck-builder.types'
import { findClarification } from '../encyclopedia-content'
import { localized, resolveLang, uniqueSorted } from '../encyclopedia.utils'
import { ClarifiedText, DetailHeader, DetailSection, EncyclopediaLayout, ListRow } from './EncyclopediaLayout'
import { FilterSection } from './FilterSection'

const ALL_ENGRAVINGS: DeckBuilderPersonaEngraving[] =
  DECK_BUILDER_PERSONA_ENGRAVING_CARDS.flatMap(card => card.engravings)

const EIDOLONS = uniqueSorted(ALL_ENGRAVINGS.map(e => e.eidolon))
const CARD_TYPES = uniqueSorted(ALL_ENGRAVINGS.map(e => e.card_type))

function Badge({ children }: { children: string }) {
  return (
    <span className="rounded border border-[#334155] bg-[#1e293b] px-1.5 py-0.5 text-[11px] font-bold uppercase tracking-wide text-[#cbd5e1]">
      {children}
    </span>
  )
}

export function EngravingsTab() {
  const { t, i18n } = useTranslation()
  const lang = resolveLang(i18n.language)
  const [search, setSearch] = useState('')
  const [eidolon, setEidolon] = useState<string | null>(null)
  const [cardType, setCardType] = useState<string | null>(null)
  const [selectedId, setSelectedId] = useState<string | null>(null)

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase()
    return ALL_ENGRAVINGS.filter(e => {
      if (eidolon && e.eidolon !== eidolon) return false
      if (cardType && e.card_type !== cardType) return false
      if (q && !e.description.toLowerCase().includes(q)) return false
      return true
    })
  }, [search, eidolon, cardType])

  const selected = useMemo(
    () => ALL_ENGRAVINGS.find(e => e.engraving_id === selectedId) ?? null,
    [selectedId],
  )
  const clar = selected ? findClarification('engraving', selected.engraving_id) : undefined

  return (
    <EncyclopediaLayout
      search={search}
      onSearch={setSearch}
      searchPlaceholder={t('encyclopedia.searchText')}
      filters={
        <>
          <FilterSection label={t('encyclopedia.engravings.eidolon')} options={EIDOLONS} value={eidolon} onChange={setEidolon} />
          <FilterSection label={t('encyclopedia.engravings.cardType')} options={CARD_TYPES} value={cardType} onChange={setCardType} />
        </>
      }
      count={filtered.length}
      detail={
        selected && (
          <div className="flex max-w-2xl flex-col gap-5">
            <DetailHeader
              title={`${selected.eidolon} · ${selected.card_type}`}
              meta={selected.modifiers.length > 0 && (
                <span className="flex flex-wrap gap-1">
                  {selected.modifiers.map(m => <Badge key={m}>{m}</Badge>)}
                </span>
              )}
            />

            <ClarifiedText clarification={clar && localized(clar.text, lang)} gameText={selected.description} />

            {selected.allowed_classes.length > 0 && (
              <DetailSection label={t('encyclopedia.engravings.classes')}>
                <div className="flex flex-wrap gap-1">
                  {selected.allowed_classes.map(c => <Badge key={c}>{c}</Badge>)}
                </div>
              </DetailSection>
            )}
          </div>
        )
      }
    >
      {filtered.map(e => (
        <ListRow key={e.engraving_id} selected={selectedId === e.engraving_id} onSelect={() => setSelectedId(e.engraving_id)}>
          <span className="min-w-0 flex-1">
            <span className="mb-1 flex gap-1">
              <Badge>{e.eidolon}</Badge>
              <Badge>{e.card_type}</Badge>
            </span>
            <span className="line-clamp-2 text-sm text-[#cbd5e1]">{e.description}</span>
          </span>
        </ListRow>
      ))}
    </EncyclopediaLayout>
  )
}
