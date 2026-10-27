import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate, useParams } from 'react-router-dom'
import { ChevronLeft, ExternalLink, Search } from 'lucide-react'
import { InfoPopover } from '@/components/ui/info-popover'
import { getCharacterFaceUrl } from '@/lib/deck-builder-assets'
import { openExternal } from '@/lib/browser'
import { cn } from '@/lib/utils'
import { GUIDE_LIST } from './guides-registry'
import { getGuide } from './guides-content'
import { filterGuides, resolveLang, localized, type GuideSort } from './guides.utils'
import { GuidePage } from './components/GuidePage'
import { RatingChip } from './components/blocks/RatingChip'

// One chip per rating colour, for the "How ratings work" tip
const RATING_EXAMPLES = ['6/5', '5/5', '4/5', '3/5', '2/5']

/**
 * The guide list, or one guide when the address names a character.
 * @returns The page.
 */
export function GuidesPage() {
  const { t, i18n } = useTranslation()
  const lang = resolveLang(i18n.language)
  const navigate = useNavigate()
  const { charId } = useParams()
  const [query, setQuery] = useState('')
  const [sort, setSort] = useState<GuideSort>('name')
  const guide = charId ? getGuide(Number(charId)) : undefined
  const shown = filterGuides(GUIDE_LIST, query, sort)

  if (guide) {
    return (
      <div className="flex h-full flex-col overflow-hidden">
        <div className="flex shrink-0 items-center gap-3 border-b border-[#282828] px-3 py-2">
          <button
            type="button"
            onClick={() => navigate('/guides')}
            className="flex items-center gap-1 rounded px-2 py-1 text-sm text-[#b3b3b3] hover:bg-[#282828] hover:text-[#ffffff]"
          >
            <ChevronLeft size={16} />
            {t('guides.backToList')}
          </button>
          <span className="text-base font-bold text-[#ffffff]">{guide.name}</span>
          {guide.updated && (
            <span className="rounded-full bg-[#282828] px-2 py-0.5 text-xs text-[#b3b3b3]">{t('guides.updated', { date: guide.updated })}</span>
          )}
          <span className="flex items-center gap-1 text-sm text-[#b3b3b3]">
            {t('guides.ratingsHelp')}
            <InfoPopover
              ariaLabel={t('guides.ratingsHelp')}
              content={
                <div className="flex flex-col gap-2">
                  <p>{t('guides.ratingsHelpBody')}</p>
                  <div className="flex gap-1.5">
                    {RATING_EXAMPLES.map(rating => <RatingChip key={rating} rating={rating} />)}
                  </div>
                </div>
              }
            />
          </span>
          {guide.source && (
            <button
              type="button"
              onClick={() => openExternal(guide.source!.url)}
              className="ml-auto flex items-center gap-1 rounded px-2 py-1 text-sm text-[#b3b3b3] hover:bg-[#282828] hover:text-[#c084fc]"
            >
              <ExternalLink size={14} />
              {localized(guide.source.label, lang)}
            </button>
          )}
        </div>
        <div className="min-h-0 flex-1">
          <GuidePage key={guide.charResId} guide={guide} />
        </div>
      </div>
    )
  }

  return (
    <div className="flex h-full flex-col overflow-hidden">
      <div className="shrink-0 border-b border-[#282828] p-6">
        <h1 className="text-xl font-bold text-[#ffffff]">{t('guides.title')}</h1>
        <p className="mt-2 text-sm text-[#b3b3b3]">{t('guides.description')}</p>
        <div className="mt-4 flex flex-wrap items-center gap-3">
          <label className="flex w-72 items-center gap-2 rounded-md border border-[#3a3a3a] bg-[#181818] px-3 py-1.5 focus-within:border-[#c084fc]">
            <Search size={16} className="text-[#8a8a8a]" />
            <input
              type="search"
              value={query}
              onChange={e => setQuery(e.target.value)}
              placeholder={t('guides.search')}
              className="w-full bg-transparent text-sm text-[#ffffff] outline-none placeholder:text-[#8a8a8a]"
            />
          </label>
          <div className="flex gap-1 rounded-md border border-[#282828] bg-[#181818] p-1">
            {(['name', 'updated'] as const).map(option => (
              <button
                key={option}
                type="button"
                aria-pressed={sort === option}
                onClick={() => setSort(option)}
                className={cn(
                  'rounded px-3 py-1 text-sm transition-colors',
                  sort === option ? 'bg-[#c084fc] font-semibold text-[#1a1022]' : 'text-[#b3b3b3] hover:bg-[#222] hover:text-[#e5e7eb]',
                )}
              >
                {t(option === 'name' ? 'guides.sortName' : 'guides.sortUpdated')}
              </button>
            ))}
          </div>
        </div>
      </div>
      <div className="flex-1 overflow-y-auto p-6">
        {shown.length === 0 ? (
          <p className="text-sm text-[#8a8a8a]">{t('guides.noMatch', { query: query.trim() })}</p>
        ) : (
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5">
            {shown.map(entry => {
              const face = getCharacterFaceUrl(entry.charResId)
              return (
                <button
                  key={entry.charResId}
                  type="button"
                  onClick={() => navigate(`/guides/${entry.charResId}`)}
                  className="flex flex-col items-center gap-2 rounded-lg border border-[#282828] bg-[#181818] p-4 transition-colors hover:border-[#c084fc44] hover:bg-[#282828]"
                >
                  {face ? (
                    <img src={face} alt={entry.name} className="h-20 w-20 rounded-full object-cover" />
                  ) : (
                    <div className="grid h-20 w-20 place-items-center rounded-full bg-[#222] text-xl font-bold text-[#8a8a8a]">
                      {entry.name.charAt(0)}
                    </div>
                  )}
                  <span className="text-base font-medium text-[#ffffff]">{entry.name}</span>
                  {entry.updated && <span className="text-xs text-[#8a8a8a]">{t('guides.updated', { date: entry.updated })}</span>}
                </button>
              )
            })}
          </div>
        )}
      </div>
    </div>
  )
}
