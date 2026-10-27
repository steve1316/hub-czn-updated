import { useTranslation } from 'react-i18next'
import { CardImage } from '@/pages/deck-builder/components/CardImage'
import type { CardEntry } from '@/lib/types'
import { cn } from '@/lib/utils'
import { cardEntry, levelNumeral, localized, ratingScore, resolveLang } from '../../guides.utils'
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

/** A level must score at least this to be highlighted as the best one. */
const HIGHLIGHT_MIN_SCORE = 4

/**
 * One row per rated epiphany level, with the best score highlighted when one level clearly wins.
 * @param props The card's epiphanies.
 * @returns The rows.
 */
function EpiphanyRows({ epiphanies }: EpiphanyRowsProps) {
  const { i18n } = useTranslation()
  const lang = resolveLang(i18n.language)
  const scores = epiphanies.map(ep => ratingScore(ep.rating))
  const best = Math.max(...scores)
  // Only a single best level is lit, and only when it is a good one.
  const highlighted = best >= HIGHLIGHT_MIN_SCORE && scores.filter(score => score === best).length === 1 ? best : null

  return (
    <div className="mt-2 flex flex-col gap-1">
      {epiphanies.map(ep => {
        const note = localized(ep.note, lang)
        return (
          <div
            key={ep.level}
            title={ep.name}
            className={cn(
              'grid grid-cols-[56px_40px_1fr] items-start gap-2 rounded px-2 py-1 text-sm',
              highlighted !== null && ratingScore(ep.rating) === highlighted && 'bg-[#c084fc]/9 outline outline-[#c084fc]/30',
            )}
          >
            <span className="flex items-center gap-1 font-bold text-[#ffffff]">
              {levelNumeral(ep.level)}
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
          const card = cardEntry(item.cardId, item.name, cardsById, item.persona)
          const note = localized(item.note, lang)
          return (
            <article
              key={`${item.cardId}-${index}`}
              className={cn('flex gap-3 rounded-lg border border-[#282828] bg-[#181818] p-3', item.epiphanies && 'sm:col-span-2')}
            >
              <div className="relative h-36 w-24 shrink-0">
                <CardImage card={card} className="h-full w-full rounded" />
                <CostGem cost={item.cost} className="absolute top-1.5 left-1.5" />
              </div>
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <h4 className="truncate text-base font-bold text-[#ffffff]">{item.name ?? card.name}</h4>
                  {item.count && item.count > 1 && <span className="shrink-0 text-sm font-bold text-[#b3b3b3]">x{item.count}</span>}
                  {item.rating && <RatingChip rating={item.rating} />}
                </div>
                {note && <p className="mt-1 text-sm leading-relaxed whitespace-pre-line text-[#b3b3b3]">{note}</p>}
                {item.epiphanies && <EpiphanyRows epiphanies={item.epiphanies} />}
              </div>
            </article>
          )
        })}
      </div>
    </div>
  )
}
