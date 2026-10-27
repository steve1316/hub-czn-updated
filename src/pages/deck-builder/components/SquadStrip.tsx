import { useTranslation } from 'react-i18next'
import type { CardCharacter } from '@/lib/types'
import type { SquadSlot } from '../deck-builder.types'
import type { DeckBuilderSlotCostBreakdown } from '../deck-builder-cost.utils'
import { CharacterAvatar } from './CharacterAvatar'

/** Props for SquadStrip. */
interface SquadStripProps {
  /** The three squad slots. */
  squad: SquadSlot[]
  /** Each slot's deck points, in squad order. */
  costs: DeckBuilderSlotCostBreakdown[]
  /** Every combatant the Deck Builder knows, for names and faces. */
  characters: CardCharacter[]
  /** The index of the slot being edited. */
  activeSlot: number
  /** Called with a slot index when it is picked. */
  onSelect: (index: number) => void
}

/**
 * The squad at a glance: one tab per slot with its combatant, deck points and card count. Picking a tab edits that deck.
 * @param props The squad, its costs and the selected slot.
 * @returns The strip of slot tabs.
 */
export function SquadStrip({ squad, costs, characters, activeSlot, onSelect }: SquadStripProps) {
  const { t } = useTranslation()

  return (
    <nav aria-label={t('deckBuilder.squad.label')} className="grid shrink-0 grid-cols-3 gap-3">
      {squad.map((slot, index) => {
        const character = characters.find(c => c.char_res_id === slot.combatantId)
        const cost = costs[index]
        const active = index === activeSlot

        return (
          <button
            key={index}
            type="button"
            aria-current={active ? 'true' : undefined}
            onClick={() => onSelect(index)}
            className={[
              'flex min-w-0 items-center gap-3 rounded-xl border px-3 py-2 text-left transition',
              active ? 'border-[#c084fc] bg-[#1f1730]' : 'border-[#282838] bg-[#15151f] hover:border-[#60a5fa]',
            ].join(' ')}
          >
            <CharacterAvatar character={character} />

            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-bold text-white">
                {character ? character.name || `#${character.char_res_id}` : t('deckBuilder.squad.empty')}
              </p>
              <p className="text-xs text-[#b3b3b3]">
                <span className={cost.isOverLimit ? 'font-bold text-[#f87171]' : undefined}>
                  {t('deckBuilder.squad.points', { total: cost.total, limit: cost.limit })}
                </span>
                {' / '}
                {t('deckBuilder.squad.cards', { count: slot.cards.length })}
              </p>
            </div>
          </button>
        )
      })}
    </nav>
  )
}
