import { useTranslation } from 'react-i18next'
import { resolveLang, localized } from '../../guides.utils'
import type { EgoNote, PotentialsLegendEntry } from '../../guides.types'

// Each guide's potentials tree picture, keyed by file name.
const potentialsPictures = Object.fromEntries(
  Object.entries(
    import.meta.glob('../../data/potentials/*.webp', {
      eager: true,
      query: '?url',
      import: 'default',
    }) as Record<string, string>,
  ).map(([path, url]) => [path.split('/').pop(), url]),
) as Record<string, string>

// The legend colours, matching the highlights in the author's pictures.
const LEGEND_COLOURS: Record<PotentialsLegendEntry['colour'], string> = {
  purple: '#c084fc',
  gold: '#facc15',
  blue: '#60a5fa',
}

/** Props for PotentialsBlock. */
interface PotentialsBlockProps {
  /** The tree picture's file name under `data/potentials`, or null when the sheet has none. */
  image: string | null
  /** What each highlight colour in the picture means. */
  legend: PotentialsLegendEntry[]
  /** The author's comment on each ego manifestation level. */
  ego: EgoNote[]
}

/**
 * The potentials tree with its colour legend, and the ego manifestation notes.
 * @param props The picture, legend and ego notes.
 * @returns The block.
 */
export function PotentialsBlock({ image, legend, ego }: PotentialsBlockProps) {
  const { t, i18n } = useTranslation()
  const lang = resolveLang(i18n.language)
  const picture = image ? potentialsPictures[image] : undefined

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start">
        {picture ? (
          <img src={picture} alt="" className="max-w-full rounded-lg border border-[#282828] sm:max-w-sm" />
        ) : (
          <div className="flex h-40 w-full items-center justify-center rounded-lg border border-dashed border-[#555] text-sm text-[#666] italic sm:w-80">
            {t('guides.potentialsPictureMissing')}
          </div>
        )}
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
                <span className="shrink-0 self-start rounded bg-[#c084fc]/20 px-1.5 py-0.5 text-[10px] font-bold text-[#c084fc]">E{note.level}</span>
                <p className="min-w-0 flex-1 text-xs leading-relaxed whitespace-pre-line text-[#b3b3b3]">{localized(note.text, lang)}</p>
              </li>
            ))}
          </ol>
        </div>
      )}
    </div>
  )
}
