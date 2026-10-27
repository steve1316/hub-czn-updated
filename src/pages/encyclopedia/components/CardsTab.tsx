import { memo, useDeferredValue, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import type { TFunction } from 'i18next'
import { Maximize2 } from 'lucide-react'
import { Dialog } from 'radix-ui'
import { cn } from '@/lib/utils'
import { CostGem } from '@/pages/guides/components/blocks/CostGem'
import { CARD_CHARACTERS, CARD_SEASONS, ENCYCLOPEDIA_CARDS, cardImageUrl } from '../encyclopedia-cards'
import { findClarification } from '../encyclopedia-content'
import type { EncyclopediaCard } from '../encyclopedia.types'
import { SEASON_GROUP_PREFIX, cardGroupKey, filterCards, localized, resolveLang, uniqueSorted } from '../encyclopedia.utils'
import { ClarifiedText, DetailHeader, DetailSection, EncyclopediaLayout } from './EncyclopediaLayout'
import { FilterSection } from './FilterSection'
import { RichDescription } from './RichDescription'

// The Group filter's choices, in archive order: combatant, neutral, each season, monster, status ailment, curse.
const GROUPS = [...new Set(ENCYCLOPEDIA_CARDS.map(cardGroupKey))]
const CHARACTER_NAMES = new Map(CARD_CHARACTERS.map(c => [c.id, c.name]))
const SEASON_TITLES = new Map(CARD_SEASONS.map(s => [s.number, s.title]))

/**
 * The label for a Group filter key.
 * @param key A `cardGroupKey` value, such as "season-5".
 * @param t The translate function.
 * @returns Such as "Season 5" or "Combatant".
 */
function groupLabel(key: string, t: TFunction): string {
  return key.startsWith(SEASON_GROUP_PREFIX) ? t('cards.groups.season', { n: key.slice(SEASON_GROUP_PREFIX.length) }) : t(`cards.groups.${key}`)
}

/**
 * A card's cost as printed.
 * @param cost The cost, -1 for X, or null.
 * @returns Such as "2", "X" or "-".
 */
function costLabel(cost: number | null): string {
  return cost == null ? '-' : cost < 0 ? 'X' : String(cost)
}

/**
 * The short line about a card: who or what it belongs to, what sort of card it is, and its type.
 * @param card The card.
 * @param t The translate function.
 * @param longSeason Whether to name the season by its title as well as its number.
 * @returns Such as "Nia · Starting card · Skill".
 */
function cardMeta(card: EncyclopediaCard, t: TFunction, longSeason = false): string {
  const parts: string[] = []
  if (card.group === 'combatant') parts.push(CHARACTER_NAMES.get(card.character_id ?? 0) ?? '', t(`cards.kinds.${card.kind}`))
  else if (card.group === 'season') {
    const title = SEASON_TITLES.get(card.season ?? 0)
    parts.push(longSeason && title ? t('cards.seasonTitle', { n: card.season, title }) : t('cards.groups.season', { n: card.season }), t(`cards.kinds.${card.kind}`))
  } else if (card.group === 'neutral') parts.push(card.classes?.length ? card.classes.join(', ') : t('cards.anyClass'))
  else if (card.group === 'monster') parts.push(card.faction ?? '')
  parts.push(card.card_type)
  return [...new Set(parts.filter(Boolean))].join(' · ')
}

/** Props for CardTile. */
interface CardTileProps {
  /** The card this tile shows. */
  card: EncyclopediaCard
  /** Whether the card is the one open in the detail pane. */
  selected: boolean
  /** Opens a card by its id. Must be stable so unchanged tiles skip re-rendering. */
  onSelect: (cardId: string) => void
}

/**
 * One card in the grid: its art with the cost on it, and its name under it. Players know cards by their art first.
 * @param props See `CardTileProps`.
 * @returns The tile button.
 */
const CardTile = memo(function CardTile({ card, selected, onSelect }: CardTileProps) {
  const { t } = useTranslation()
  const imageUrl = cardImageUrl(card)
  return (
    <button
      type="button"
      aria-pressed={selected}
      title={`${card.name}\n${cardMeta(card, t)}`}
      onClick={() => onSelect(card.id)}
      className={cn(
        'flex flex-col gap-1 rounded-md p-1 text-left transition-colors',
        selected ? 'bg-[#1f1730] ring-2 ring-[#c084fc]' : 'hover:bg-[#1f1f1f]',
      )}
    >
      <span className="relative block aspect-[2/3] w-full overflow-hidden rounded bg-[#1f1f2a]">
        {imageUrl && <img src={imageUrl} alt="" loading="lazy" decoding="async" className="h-full w-full object-cover" />}
        <CostGem cost={card.cost ?? undefined} className="absolute top-1 left-1" />
      </span>
      <span className={cn('line-clamp-2 text-xs leading-snug', selected ? 'text-white' : 'text-[#d4d4d4]')}>{card.name}</span>
    </button>
  )
})

/** Props for CardArt. */
interface CardArtProps {
  /** The bundled URL of the card's art. */
  url: string
  /** The card's name, used for the alt text and the viewer's title. */
  name: string
}

/**
 * The card's art in the detail pane. Clicking it opens the art as large as the window allows, so the details can be seen.
 * @param props See `CardArtProps`.
 * @returns The art button and its full-size viewer.
 */
function CardArt({ url, name }: CardArtProps) {
  const { t } = useTranslation()
  return (
    <Dialog.Root>
      <Dialog.Trigger asChild>
        <button
          type="button"
          title={t('cards.viewArt')}
          className="group relative h-60 w-40 shrink-0 cursor-zoom-in overflow-hidden rounded-lg border border-[#282828] hover:border-[#c084fc]"
        >
          <img src={url} alt={name} className="h-full w-full object-cover" />
          <span className="absolute right-1.5 bottom-1.5 rounded bg-[#0d0d0d]/80 p-1 text-white opacity-0 transition-opacity group-hover:opacity-100 group-focus-visible:opacity-100">
            <Maximize2 size={14} />
          </span>
        </button>
      </Dialog.Trigger>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-black/80" />
        <Dialog.Content className="fixed top-1/2 left-1/2 z-50 flex -translate-x-1/2 -translate-y-1/2 flex-col items-center gap-3 focus:outline-none">
          <Dialog.Title className="text-base font-semibold text-white">{name}</Dialog.Title>
          <Dialog.Description className="sr-only">{t('cards.closeArt')}</Dialog.Description>
          <Dialog.Close asChild>
            <button type="button" title={t('cards.closeArt')} className="cursor-zoom-out">
              <img src={url} alt={name} className="h-[min(85vh,632px)] w-auto rounded-xl shadow-2xl" />
            </button>
          </Dialog.Close>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}

/**
 * The Cards tab: every card in the game's card archive, filtered by group, combatant and card type.
 * @returns The tab body.
 */
export function CardsTab() {
  const { t, i18n } = useTranslation()
  const lang = resolveLang(i18n.language)
  const [search, setSearch] = useState('')
  const [group, setGroup] = useState<string | null>(null)
  const [character, setCharacter] = useState<string | null>(null)
  const [type, setType] = useState<string | null>(null)
  const [selectedId, setSelectedId] = useState<string | null>(null)

  // Card types offered are the ones in the picked group, so no choice ever empties the list on its own.
  const types = useMemo(() => uniqueSorted(ENCYCLOPEDIA_CARDS.filter(c => !group || cardGroupKey(c) === group).map(c => c.card_type)), [group])

  // Typing stays responsive while the long list filters behind it.
  const deferredSearch = useDeferredValue(search)
  const filtered = useMemo(
    () => filterCards(ENCYCLOPEDIA_CARDS, { group, character: character ? Number(character) : null, type, query: deferredSearch }),
    [group, character, type, deferredSearch],
  )

  const pickGroup = (next: string | null) => {
    setGroup(next)
    setCharacter(null)
    setType(null)
  }

  const selected = ENCYCLOPEDIA_CARDS.find(c => c.id === selectedId) ?? null
  const imageUrl = selected ? cardImageUrl(selected) : undefined
  const clar = selected ? findClarification('card', selected.id) : undefined

  return (
    <EncyclopediaLayout
      search={search}
      onSearch={setSearch}
      searchPlaceholder={t('cards.search')}
      filters={
        <>
          <FilterSection label={t('cards.group')} options={GROUPS} value={group} onChange={pickGroup} format={key => groupLabel(key, t)} />
          {group === 'combatant' && (
            <FilterSection
              label={t('cards.character')}
              options={CARD_CHARACTERS.map(c => String(c.id))}
              value={character}
              onChange={setCharacter}
              format={id => CHARACTER_NAMES.get(Number(id)) ?? id}
            />
          )}
          <FilterSection label={t('cards.type')} options={types} value={type} onChange={setType} />
        </>
      }
      count={filtered.length}
      detail={
        selected && (
          <div className="flex max-w-2xl flex-col gap-5">
            <DetailHeader
              title={selected.name}
              meta={
                <>
                  <span>{cardMeta(selected, t, true)}</span>
                  <span className="mt-1 block font-mono text-[#93c5fd]">{t('cards.cost', { cost: costLabel(selected.cost) })}</span>
                </>
              }
              media={imageUrl && <CardArt url={imageUrl} name={selected.name} />}
            />

            <ClarifiedText clarification={clar && localized(clar.text, lang)} gameText={selected.description || t('cards.noText')} />

            {selected.epiphanies && (
              <DetailSection label={t('cards.epiphanies')}>
                <ol className="flex flex-col gap-2">
                  {selected.epiphanies.map(epiphany => (
                    <li key={epiphany.level} className="rounded-lg border border-[#282828] bg-[#161616] p-3">
                      <p className="mb-1 flex items-center gap-2 text-sm font-semibold text-[#e5e7eb]">
                        <span className="grid h-6 w-6 shrink-0 place-items-center rounded border border-[#075985] bg-[#082f49] font-mono text-xs text-[#93c5fd]">
                          {costLabel(epiphany.cost)}
                        </span>
                        {epiphany.name}
                      </p>
                      <RichDescription text={epiphany.description} className="text-sm leading-relaxed text-[#d4d4d4]" />
                    </li>
                  ))}
                </ol>
              </DetailSection>
            )}
          </div>
        )
      }
    >
      <div className="grid grid-cols-3 gap-1 p-2">
        {filtered.map(card => (
          <CardTile key={card.id} card={card} selected={selectedId === card.id} onSelect={setSelectedId} />
        ))}
      </div>
    </EncyclopediaLayout>
  )
}
