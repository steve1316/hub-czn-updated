import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { cn } from '@/lib/utils'
import { resolveLang, localized, globByFileName } from '../../guides.utils'
import type { EgoNote, PotentialsLegendEntry } from '../../guides.types'

// Each guide's potentials tree picture, keyed by file name.
const potentialsPictures = globByFileName(
  import.meta.glob('../../data/potentials/*.webp', {
    eager: true,
    query: '?url',
    import: 'default',
  }) as Record<string, string>,
)

// The legend colours, matching the highlights in the author's pictures.
const LEGEND_COLOURS: Record<PotentialsLegendEntry['colour'], string> = {
  purple: '#c084fc',
  gold: '#facc15',
  blue: '#60a5fa',
}

/** Props for PotentialsBlock. */
interface PotentialsBlockProps {
  /** The author's tree picture file name under `data/potentials`, or null when the sheet has none. */
  image: string | null
  /** The file name of the clean tree drawn with the author's ring colours, under `data/potentials`. */
  treeImage: string
  /** True when the author's ring colours could be read onto `treeImage`. */
  coloured: boolean
  /** What each highlight colour in the picture means. */
  legend: PotentialsLegendEntry[]
  /** The author's comment on each ego manifestation level. */
  ego: EgoNote[]
}

/**
 * The potentials tree with its colour legend, and the ego manifestation notes.
 * @param props The pictures, legend and ego notes.
 * @returns The block.
 */
export function PotentialsBlock({ image, treeImage, coloured, legend, ego }: PotentialsBlockProps) {
  const { t, i18n } = useTranslation()
  const lang = resolveLang(i18n.language)
  const [showAuthor, setShowAuthor] = useState(false)
  const tree = potentialsPictures[treeImage]
  const author = image ? potentialsPictures[image] : undefined
  const authorSelected = showAuthor && !!author
  const picture = authorSelected ? author : tree ?? author

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start">
        <div className="flex flex-col gap-2 sm:max-w-sm">
          {picture ? (
            <img src={picture} alt="" className="max-w-full rounded-lg border border-[#282828]" />
          ) : (
            <div className="flex h-40 w-full items-center justify-center rounded-lg border border-dashed border-[#555] text-sm text-[#8a8a8a] italic sm:w-80">
              {t('guides.potentialsPictureMissing')}
            </div>
          )}
          {tree && author && (
            <div className="flex gap-2 text-xs">
              {[
                { label: t('guides.potentialsTree'), active: !authorSelected, onClick: () => setShowAuthor(false) },
                { label: t('guides.potentialsAuthorPicture'), active: authorSelected, onClick: () => setShowAuthor(true) },
              ].map(tab => (
                <button
                  key={tab.label}
                  type="button"
                  onClick={tab.onClick}
                  className={cn('rounded px-2 py-1', tab.active ? 'bg-[#c084fc]/20 font-bold text-[#c084fc]' : 'bg-[#181818] text-[#b3b3b3] hover:text-white')}
                >
                  {tab.label}
                </button>
              ))}
            </div>
          )}
          {tree && !coloured && !authorSelected && <p className="text-xs text-[#8a8a8a] italic">{t('guides.potentialsNoColours')}</p>}
        </div>
        <ul className="flex flex-col gap-2">
          {legend.map(entry => (
            <li key={entry.colour} className="flex items-center gap-2 text-sm text-[#cbd5e1]">
              <span className="h-3 w-3 shrink-0 rounded-sm" style={{ backgroundColor: LEGEND_COLOURS[entry.colour] }} />
              {localized(entry.text, lang)}
            </li>
          ))}
        </ul>
      </div>
      {ego.length > 0 && (
        <div className="flex flex-col gap-2">
          <h3 className="text-sm font-bold tracking-wide text-[#c084fc]">{t('guides.egoManifestation')}</h3>
          <ol className="flex flex-col gap-2">
            {ego.map(note => (
              <li key={note.level} className="flex gap-3 rounded-lg border border-[#282828] bg-[#181818] p-3">
                <span className="shrink-0 self-start rounded bg-[#c084fc]/20 px-1.5 py-0.5 text-[11px] font-bold text-[#c084fc]">E{note.level}</span>
                <p className={cn('min-w-0 flex-1 text-xs leading-relaxed whitespace-pre-line text-[#b3b3b3]', note.bold && 'font-bold text-[#e5e5e5]')}>
                  {localized(note.text, lang)}
                </p>
              </li>
            ))}
          </ol>
        </div>
      )}
    </div>
  )
}
