import { useTranslation } from 'react-i18next'
import { CardImage } from '@/pages/deck-builder/components/CardImage'
import type { CardEntry } from '@/lib/types'
import { cardEntry, levelNumeral, localized, resolveLang } from '../../guides.utils'
import type { DeckCard, EpiphanyRating } from '../../guides.types'
import { CostGem } from './CostGem'
import { RatingChip } from './RatingChip'

/** Props for DeckBlock. */
interface DeckBlockProps {
  /** Every copy in the deck, in the sheet's order. */
  cards: DeckCard[]
  /** The guide's rated epiphanies, keyed `${cardId}:${level}`. */
  ratings: Map<string, EpiphanyRating>
  /** The guide character's cards by id. */
  cardsById: Record<string, CardEntry>
}

/**
 * The key a deck card is grouped under in the legend: one row per card, level and extra line.
 * @param card The deck card.
 * @returns The grouping key.
 */
function legendKey(card: DeckCard): string {
  return `${card.cardId}:${card.epiphany?.level ?? ''}:${card.extra?.id ?? ''}`
}

/**
 * A deck as a strip of every copy, with a legend of each distinct card under it.
 * @param props The deck's cards, the guide's ratings and the character's cards.
 * @returns The strip and its legend.
 */
export function DeckBlock({ cards, ratings, cardsById }: DeckBlockProps) {
  const { t, i18n } = useTranslation()
  const lang = resolveLang(i18n.language)
  const legend = [...new Map(cards.map(card => [legendKey(card), card])).values()]

  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap gap-1.5">
        {cards.map((card, index) => {
          const level = card.epiphany?.level
          return (
            <div key={`${card.cardId}-${index}`} className="relative h-[114px] w-[76px] shrink-0">
              <CardImage card={cardEntry(card.cardId, card.name, cardsById, card.persona)} className="h-full w-full rounded" />
              <CostGem cost={card.cost} small className="absolute top-1 left-1" />
              {card.extra?.god && <span className="absolute top-0.5 right-1 text-sm text-[#fcd34d] [text-shadow:0_1px_2px_#000]">✦</span>}
              {level !== undefined && (
                <span
                  className={`absolute bottom-1 left-1 rounded border bg-[#0d0d0d]/85 px-1 text-[10px] font-bold text-[#ffffff] ${level === 0 ? 'border-[#555]' : 'border-[#c084fc]'}`}
                >
                  {level === 0 ? t('guides.base') : levelNumeral(level)}
                </span>
              )}
            </div>
          )
        })}
      </div>
      <div className="flex flex-col gap-1">
        {legend.map(card => {
          const level = card.epiphany?.level
          const rated = level ? ratings.get(`${card.cardId}:${level}`) : undefined
          return (
            <div
              key={legendKey(card)}
              className="grid grid-cols-[20px_170px_1fr_auto] items-start gap-2 rounded bg-[#1d1d1d] px-2 py-1.5 text-xs"
            >
              {card.cost === undefined ? <span /> : <CostGem cost={card.cost} small />}
              <span className="font-bold text-[#ffffff]">
                {card.epiphany?.name ?? card.name ?? card.cardId}
                {level === 0 && <span className="ml-1.5 rounded border border-[#555] px-1 text-[10px] font-normal text-[#b3b3b3]">{t('guides.base')}</span>}
              </span>
              <span className="leading-relaxed text-[#b3b3b3]">
                {card.epiphany ? localized(card.epiphany.text, lang) : card.text && localized(card.text, lang)}
                {card.extra && (
                  <span className={`block ${card.extra.god ? 'text-[#fcd34d]' : 'text-[#cbd5e1]'}`}>
                    {card.extra.god ? `✦ ${t('guides.divine')}: ` : ''}
                    {localized(card.extra.text, lang)}
                  </span>
                )}
              </span>
              {rated?.rating ? <RatingChip rating={rated.rating} quote={localized(rated.note, lang)} /> : <span />}
            </div>
          )
        })}
      </div>
    </div>
  )
}
