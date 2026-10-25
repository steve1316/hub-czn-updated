import { useTranslation } from 'react-i18next'
import { CardImage } from '@/pages/deck-builder/components/CardImage'
import type { CardEntry } from '@/lib/types'
import { cn } from '@/lib/utils'
import { cardEntry, LEVEL_NUMERALS, localized, resolveLang } from '../../guides.utils'
import type { CardItem, EpiphanyRating, LocalizedText } from '../../guides.types'
import { CostGem } from './CostGem'
import { RatingChip } from './RatingChip'

/** Props for CardListBlock. */
interface CardListBlockProps {
  /** The text above the cards. */
  intro?: LocalizedText
  /** The cards, with folded epiphany sets as one item each. */
  items: CardItem[]
  /** The guide character's cards by id. */
  cardsById: Record<string, CardEntry>
}

/** Props for EpiphanyRows. */
interface EpiphanyRowsProps {
  /** The card's rated epiphany levels. */
  epiphanies: EpiphanyRating[]
}

/**
 * The whole score of a rating, so the best epiphany can be picked out.
 * @param rating The author's rating, such as "5/5".
 * @returns The score, or -1 when there is none.
 */
function score(rating: string | undefined): number {
  const value = parseFloat(rating ?? '')
  return Number.isNaN(value) ? -1 : value
}

/**
 * One row per rated epiphany level, with the best score highlighted.
 * @param props The card's epiphanies.
 * @returns The rows.
 */
function EpiphanyRows({ epiphanies }: EpiphanyRowsProps) {
  const { i18n } = useTranslation()
  const lang = resolveLang(i18n.language)
  const best = Math.max(...epiphanies.map(ep => score(ep.rating)))

  return (
    <div className="mt-2 flex flex-col gap-1">
      {epiphanies.map(ep => {
        const note = localized(ep.note, lang)
        return (
          <div
            key={ep.level}
            title={ep.name}
            className={cn(
              'grid grid-cols-[44px_34px_1fr] items-start gap-2 rounded px-1.5 py-1 text-xs',
              best >= 0 && score(ep.rating) === best && 'bg-[#c084fc]/9 outline outline-[#c084fc]/30',
            )}
          >
            <span className="flex items-center gap-1 font-bold text-[#ffffff]">
              {LEVEL_NUMERALS[ep.level - 1]}
              <CostGem cost={ep.cost} small />
            </span>
            <span>{ep.rating && <RatingChip rating={ep.rating} />}</span>
            <span className="leading-relaxed text-[#b3b3b3]">{note}</span>
          </div>
        )
      })}
    </div>
  )
}

/**
 * A list of cards as tiles, each with its cost, rating and note, or its rated epiphany levels when the sheet rates them one by one.
 * @param props The intro, the cards and the character's cards.
 * @returns The card tiles.
 */
export function CardListBlock({ intro, items, cardsById }: CardListBlockProps) {
  const { i18n } = useTranslation()
  const lang = resolveLang(i18n.language)

  return (
    <div className="flex flex-col gap-3">
      {intro && (
        <p className="text-sm leading-relaxed text-[#cbd5e1]">{localized(intro, lang)}</p>
      )}
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        {items.map((item, index) => {
          const card = cardEntry(item.cardId, item.name, cardsById)
          const note = localized(item.note, lang)
          return (
            <article
              key={`${item.cardId}-${index}`}
              className={cn('flex gap-3 rounded-lg border border-[#282828] bg-[#181818] p-3', item.epiphanies && 'sm:col-span-2')}
            >
              <div className="relative h-24 w-16 shrink-0">
                <CardImage card={card} className="h-full w-full rounded" />
                <CostGem cost={item.cost} small className="absolute top-1 left-1" />
              </div>
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <h4 className="truncate text-sm font-bold text-[#ffffff]">{item.name ?? card.name}</h4>
                  {item.rating && <RatingChip rating={item.rating} />}
                </div>
                {note && <p className="mt-1 text-xs leading-relaxed whitespace-pre-line text-[#b3b3b3]">{note}</p>}
                {item.epiphanies && <EpiphanyRows epiphanies={item.epiphanies} />}
              </div>
            </article>
          )
        })}
      </div>
    </div>
  )
}
