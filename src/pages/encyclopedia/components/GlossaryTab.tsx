import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { GLOSSARY, glossaryById } from '../encyclopedia-content'
import { filterGlossary, localized, resolveLang } from '../encyclopedia.utils'
import type { GlossaryCategory } from '../encyclopedia.types'
import { DetailHeader, DetailSection, EncyclopediaLayout, ListRow } from './EncyclopediaLayout'
import { FilterSection } from './FilterSection'
import { RichDescription } from './RichDescription'

const CATEGORY_ORDER: GlossaryCategory[] = ['status', 'card-type', 'mechanic']

export function GlossaryTab() {
  const { t, i18n } = useTranslation()
  const lang = resolveLang(i18n.language)
  const [search, setSearch] = useState('')
  const [category, setCategory] = useState<GlossaryCategory | null>(null)
  const [selectedId, setSelectedId] = useState<string | null>(null)

  const filtered = useMemo(() => filterGlossary(GLOSSARY, search, category, lang), [search, category, lang])
  const selected = selectedId ? glossaryById.get(selectedId) ?? null : null
  const categoryLabel = (c: string) => t(`encyclopedia.glossary.category.${c}`)

  return (
    <EncyclopediaLayout
      search={search}
      onSearch={setSearch}
      searchPlaceholder={t('encyclopedia.searchText')}
      filters={
        <FilterSection
          label={t('encyclopedia.glossary.categoryLabel')}
          options={CATEGORY_ORDER}
          value={category}
          onChange={v => setCategory(v as GlossaryCategory | null)}
          format={categoryLabel}
        />
      }
      count={filtered.length}
      detail={
        selected && (
          <div className="flex max-w-2xl flex-col gap-5">
            <DetailHeader title={localized(selected.term, lang)} meta={categoryLabel(selected.category)} />

            <div className="rounded-lg border border-[#282828] bg-[#161616] p-4">
              <RichDescription text={localized(selected.definition, lang)} className="text-sm leading-relaxed text-[#d4d4d4]" />
            </div>

            {selected.seeAlso.length > 0 && (
              <DetailSection label={t('encyclopedia.glossary.seeAlso')}>
                <div className="flex flex-wrap gap-2">
                  {selected.seeAlso.map(ref => {
                    const target = glossaryById.get(ref)
                    if (!target) return null
                    return (
                      <button
                        key={ref}
                        type="button"
                        onClick={() => setSelectedId(ref)}
                        className="rounded-md border border-[#3a3a3a] px-2.5 py-1 text-sm text-[#e9d5ff] hover:border-[#c084fc]"
                      >
                        {localized(target.term, lang)}
                      </button>
                    )
                  })}
                </div>
              </DetailSection>
            )}
          </div>
        )
      }
    >
      {filtered.map(entry => (
        <ListRow key={entry.id} selected={selectedId === entry.id} onSelect={() => setSelectedId(entry.id)}>
          <span className="min-w-0 flex-1">
            <span className="block truncate text-sm font-medium text-[#e9d5ff]">{localized(entry.term, lang)}</span>
            <span className="block text-xs text-[#8a8a8a]">{categoryLabel(entry.category)}</span>
          </span>
        </ListRow>
      ))}
    </EncyclopediaLayout>
  )
}
