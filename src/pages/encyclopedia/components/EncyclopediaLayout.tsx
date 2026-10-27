import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { cn } from '@/lib/utils'
import { RichDescription } from './RichDescription'

/** Props for EncyclopediaLayout. */
interface EncyclopediaLayoutProps {
  /** The search box's current text. */
  search: string
  /** Called with the new search text. */
  onSearch: (value: string) => void
  /** The search box's placeholder, which says what it searches. */
  searchPlaceholder: string
  /** The filter sections under the search box. */
  filters: ReactNode
  /** How many entries pass the filters, shown above the list. */
  count: number
  /** Shown in place of the list, such as a loading or error state. */
  listFallback?: ReactNode
  /** The list rows. */
  children: ReactNode
  /** The selected entry's details, or null to ask for a pick. */
  detail: ReactNode | null
}

/**
 * The shape every Encyclopedia tab shares: a filter rail, the matching entries, and the picked entry's details.
 * @param props The search, filters, rows and detail pane.
 * @returns The three-pane tab body.
 */
export function EncyclopediaLayout({ search, onSearch, searchPlaceholder, filters, count, listFallback, children, detail }: EncyclopediaLayoutProps) {
  const { t } = useTranslation()

  return (
    <div className="flex h-full overflow-hidden">
      <aside className="flex w-56 shrink-0 flex-col gap-4 overflow-y-auto border-r border-[#282828] bg-[#181818] p-3">
        <input
          type="search"
          placeholder={searchPlaceholder}
          aria-label={searchPlaceholder}
          value={search}
          onChange={e => onSearch(e.target.value)}
          className="w-full rounded border border-[#333] bg-[#222] px-2.5 py-2 text-sm text-[#e5e7eb] placeholder:text-[#8a8a8a]"
        />
        {filters}
      </aside>

      <div className="flex w-80 shrink-0 flex-col border-r border-[#282828]">
        <p className="shrink-0 border-b border-[#282828] px-4 py-2 text-xs text-[#8a8a8a]">{t('encyclopedia.count', { count })}</p>
        <div className="min-h-0 flex-1 overflow-y-auto">
          {listFallback ?? (count === 0 ? <p className="p-4 text-sm text-[#8a8a8a]">{t('encyclopedia.empty')}</p> : children)}
        </div>
      </div>

      <section className="min-w-0 flex-1 overflow-y-auto p-6">
        {detail ?? <p className="text-sm text-[#8a8a8a]">{t('encyclopedia.selectPrompt')}</p>}
      </section>
    </div>
  )
}

/** Props for ListRow. */
interface ListRowProps {
  /** Whether this row's entry is the one in the detail pane. */
  selected: boolean
  /** Called when the row is picked. */
  onSelect: () => void
  /** The row's content. */
  children: ReactNode
}

/**
 * One entry in the middle list.
 * @param props Whether it is picked, the pick handler and its content.
 * @returns The row button.
 */
export function ListRow({ selected, onSelect, children }: ListRowProps) {
  return (
    <button
      type="button"
      aria-pressed={selected}
      onClick={onSelect}
      className={cn(
        'flex w-full items-center gap-3 border-b border-[#1e1e1e] px-4 py-2.5 text-left transition-colors',
        selected ? 'bg-[#1f1730] shadow-[inset_3px_0_0_#c084fc]' : 'hover:bg-[#1a1a1a]',
      )}
    >
      {children}
    </button>
  )
}

/** Props for DetailHeader. */
interface DetailHeaderProps {
  /** The entry's name. */
  title: string
  /** A short line under the name, such as its slot or category. */
  meta?: ReactNode
  /** A picture shown left of the name. */
  media?: ReactNode
}

/**
 * The top of the detail pane: an optional picture, the entry's name and a short line about it.
 * @param props The name, the line under it and the picture.
 * @returns The header.
 */
export function DetailHeader({ title, meta, media }: DetailHeaderProps) {
  return (
    <div className="flex items-center gap-4">
      {media}
      <div className="min-w-0">
        <h3 className="text-xl font-bold text-white">{title}</h3>
        {meta && <div className="mt-1 text-sm text-[#b3b3b3]">{meta}</div>}
      </div>
    </div>
  )
}

/** Props for DetailSection. */
interface DetailSectionProps {
  /** The section's label. */
  label: string
  /** The section's content. */
  children: ReactNode
}

/**
 * A labelled block in the detail pane.
 * @param props The label and content.
 * @returns The section.
 */
export function DetailSection({ label, children }: DetailSectionProps) {
  return (
    <div>
      <p className="mb-1.5 text-xs font-semibold text-[#8a8a8a]">{label}</p>
      {children}
    </div>
  )
}

/** Props for ClarifiedText. */
interface ClarifiedTextProps {
  /** The hand-written plain-words version, when there is one. */
  clarification?: string
  /** The text as the game writes it. */
  gameText: string
}

/**
 * An entry's description: the plain-words version first when there is one, then the game's own text.
 * @param props The clarification and the game text.
 * @returns The description box.
 */
export function ClarifiedText({ clarification, gameText }: ClarifiedTextProps) {
  const { t } = useTranslation()

  return (
    <div className="flex flex-col gap-3 rounded-lg border border-[#282828] bg-[#161616] p-4">
      {clarification ? (
        <>
          <div>
            <p className="mb-1 text-xs font-semibold text-[#c084fc]">{t('encyclopedia.clarification')}</p>
            <RichDescription text={clarification} className="text-sm leading-relaxed text-[#e5e7eb]" />
          </div>
          <div>
            <p className="mb-1 text-xs font-semibold text-[#8a8a8a]">{t('encyclopedia.gameText')}</p>
            <RichDescription text={gameText} className="text-sm leading-relaxed text-[#b3b3b3]" />
          </div>
        </>
      ) : (
        <RichDescription text={gameText} className="text-sm leading-relaxed text-[#d4d4d4]" />
      )}
    </div>
  )
}
