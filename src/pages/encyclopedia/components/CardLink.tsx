import { createContext, use } from 'react'
import { Popover } from 'radix-ui'
import { useTranslation } from 'react-i18next'
import { cardById, cardImageUrl, isListedCard } from '../encyclopedia-cards'
import { costLabel } from '../encyclopedia.utils'
import { LinkPopover } from './GlossaryTerm'

/** Opens a listed card in the Cards tab. Null outside the Cards tab, where card previews have no "Open card" button. */
export const OpenCardContext = createContext<((cardId: string) => void) | null>(null)

/**
 * A card name in card text, linked to a preview of that card.
 * @param props The card id and the linked text.
 * @param props.cardId The client id of the named card.
 * @param props.children The linked text.
 * @returns The link and its preview, or the plain text when the card is unknown.
 */
export function CardLink({ cardId, children }: { cardId: string; children: string }) {
  const { t } = useTranslation()
  const openCard = use(OpenCardContext)
  const card = cardById.get(cardId)

  if (!card) return <>{children}</>
  const imageUrl = cardImageUrl(card)
  return (
    <LinkPopover label={children} linkClassName="text-[#93c5fd] hover:text-[#bfdbfe]" bodyClassName="max-w-[360px]">
      <div className="flex gap-3">
        {imageUrl && <img src={imageUrl} alt={card.name} className="h-36 w-24 shrink-0 rounded border border-[#282828] object-cover" />}
        <div className="flex min-w-0 flex-col gap-1">
          <p className="font-bold text-[#e9d5ff]">{card.name}</p>
          <p className="text-[#8a8a8a]">
            {t('cards.cost', { cost: costLabel(card.cost) })} · {card.card_type}
          </p>
          <p className="leading-relaxed whitespace-pre-line">{card.description || t('cards.noText')}</p>
          {openCard && isListedCard(card.id) && (
            <Popover.Close asChild>
              <button
                type="button"
                onClick={() => openCard(card.id)}
                className="mt-1 self-start rounded border border-[#444] px-2 py-1 text-xs text-[#e5e7eb] hover:border-[#c084fc] hover:text-white"
              >
                {t('cards.openCard')}
              </button>
            </Popover.Close>
          )}
        </div>
      </div>
    </LinkPopover>
  )
}
