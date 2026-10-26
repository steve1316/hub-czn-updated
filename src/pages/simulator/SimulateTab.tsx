import { useEffect, useState, type ReactNode } from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'
import { useLocation, useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { Play, Zap } from 'lucide-react'
import { api, assetUrl } from '@/lib/api'
import { AssetImage } from '@/components/ui/asset-image'
import type { BattleRecord, Combatant, SimulateDamageResponse, SimCardResult, SimDeckCard, DeckInfo } from '@/lib/types'
import { CharacterCombobox } from '@/components/ui/character-combobox'
import { damagePasses } from '@/lib/damage-reduction'
import { formatBattleTime } from '@/pages/battle/battle-time.utils'
import { battleEnemy, presetEnemy, typedEnemy, useBattlesEnemy } from '@/pages/battles/battles-enemy'
import { loadSavedDecks } from '@/pages/deck-builder/deck-builder-saved-decks.utils'
import { ENEMY_PRESET_GROUPS } from './simulator-damage.utils'
import { deckSlotToSimCards, type DeckBuilderHandoff } from './simulator-deck.utils'

const MORALE_PCT = 20

const STORAGE_KEY = 'czn_simulator_state'

const AUTO_DECK: DeckChoice = { kind: 'game', id: null }

/**
 * The deck to simulate: an in-game deck (a null id picks the highest-scoring one), or a Deck Builder card list. A card list with `saved`
 * came from a deck saved in the Deck Builder, one without was sent from it unsaved.
 */
type DeckChoice =
  | { kind: 'game'; id: number | null }
  | { kind: 'cards'; name: string; cards: SimDeckCard[]; saved?: { id: string; slotIndex: number } }

interface PersistedState {
  charName: string
  /** The deck to simulate. */
  deck: DeckChoice
  morale: number
  useSparks: boolean
  presetGroup: string
  weaken: boolean
  vulnerableStacks: number
  dmgReduction: boolean
  result: SimulateDamageResponse | null
  /** The name of the Deck Builder deck behind `result`, or null for an in-game deck. */
  resultDeckName: string | null
}

function loadPersistedState(): PersistedState | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return null
    return JSON.parse(raw) as PersistedState
  } catch {
    return null
  }
}

/**
 * The colours of an enemy chip.
 * @param active Whether the chip is the current enemy.
 * @returns The chip's colour classes.
 */
function chipClass(active: boolean): string {
  return active ? 'bg-[#fb923c] text-white' : 'bg-[#2a2a2a] text-[#888] hover:text-[#e5e7eb]'
}

function savePersistedState(s: PersistedState): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(s))
  } catch { }
}

function StatPill({ label, value, highlight }: { label: string; value: string; highlight?: boolean }) {
  return (
    <div className={`flex flex-col items-center rounded px-3 py-2 min-w-[80px] ${highlight ? 'bg-[#1a2a1a]' : 'bg-[#222]'}`}>
      <span className="text-[#888] text-[10px] uppercase tracking-wide">{label}</span>
      <span className={`font-bold text-sm mt-0.5 ${highlight ? 'text-[#a3e635]' : 'text-[#e5e7eb]'}`}>{value}</span>
    </div>
  )
}

/**
 * One deck in the Simulator's deck list.
 * @param label The deck's name.
 * @param sub The smaller line under the name, if any.
 * @param selected Whether this deck will be simulated.
 * @param onClick Select this deck.
 * @returns The button.
 */
function DeckButton({ label, sub, selected, onClick }: { label: ReactNode; sub?: string; selected: boolean; onClick?: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`text-left text-xs px-2 py-1.5 rounded transition-colors ${
        selected ? 'bg-[#c084fc] text-white' : 'bg-[#222] text-[#888] hover:text-[#e5e7eb]'
      }`}
    >
      <div className="font-medium">{label}</div>
      {sub && <div className={`text-[10px] mt-0.5 ${selected ? 'text-white/70' : 'text-[#555]'}`}>{sub}</div>}
    </button>
  )
}

/**
 * A heading over one group of decks in the deck list.
 * @param children The group's name.
 * @returns The heading.
 */
function DeckGroupLabel({ children }: { children: ReactNode }) {
  return <p className="text-[9px] text-[#555] uppercase tracking-wider mt-1 first:mt-0">{children}</p>
}

function CardRow({ card }: { card: SimCardResult }) {
  const { t } = useTranslation()
  const hasSpark = !!card.spark_id
  const coefficient = (card.eff_value / 100).toFixed(2)
  const displayName = card.name || card.card_id.replace(/^c_\d+_/, '')
  const [imgError, setImgError] = useState(false)

  return (
    <>
      <tr className="border-b border-[#2a2a2a] hover:bg-[#1e1e1e] transition-colors">
        <td className="px-3 py-2 text-xs">
          <div className="flex items-center gap-2">
            {card.icon_path && !imgError ? (
              <AssetImage
                src={assetUrl(card.icon_path)}
                alt=""
                className="w-12 h-12 rounded flex-shrink-0 object-cover"
                onError={() => setImgError(true)}
              />
            ) : (
              <div className="w-12 h-12 rounded flex-shrink-0 bg-[#282828]" />
            )}
            <div className="flex items-center gap-1">
              <span className="text-[#e5e7eb] font-medium">{displayName}</span>
              {hasSpark && (
                <span className="text-[#facc15] text-[10px]" title={t('simulator.epiphanyApplied')}>✦</span>
              )}
            </div>
          </div>
        </td>
        <td className="px-3 py-2 text-center text-[#b3b3b3] text-xs">{card.cost}</td>
        <td className="px-3 py-2 text-center text-[#b3b3b3] text-xs font-mono">{coefficient}×</td>
        <td className="px-3 py-2 text-center text-[#b3b3b3] text-xs">{card.hits}</td>
        <td className="px-3 py-2 text-right text-[#e5e7eb] text-xs font-mono">
          {card.normal_damage.toLocaleString()}
        </td>
        <td className="px-3 py-2 text-right text-[#e5e7eb] text-xs font-mono">
          {card.crit_damage.toLocaleString()}
        </td>
        <td className="px-3 py-2 text-right text-[#a3e635] text-xs font-mono font-bold">
          {card.avg_damage.toLocaleString()}
        </td>
      </tr>
      {card.hits > 1 && (
        <tr className="border-b border-[#282828] bg-[#141414]">
          <td className="px-3 py-1 text-[9px] text-[#555] pl-14" colSpan={4}>
            {t('simulator.perHit')}
          </td>
          <td className="px-3 py-1 text-right text-[#555] text-[10px] font-mono">
            {(card.normal_damage / card.hits).toLocaleString(undefined, { maximumFractionDigits: 0 })}
          </td>
          <td className="px-3 py-1 text-right text-[#555] text-[10px] font-mono">
            {(card.crit_damage / card.hits).toLocaleString(undefined, { maximumFractionDigits: 0 })}
          </td>
          <td className="px-3 py-1 text-right text-[#6a9e35] text-[10px] font-mono">
            {(card.avg_damage / card.hits).toLocaleString(undefined, { maximumFractionDigits: 0 })}
          </td>
        </tr>
      )}
    </>
  )
}

/**
 * The Simulate tab: per-card damage for a character's deck against the shared Simulator enemy.
 * @returns The tab.
 */
export function SimulateTab() {
  const { t } = useTranslation()
  const location = useLocation()
  const navigate = useNavigate()
  const { enemy, setEnemy } = useBattlesEnemy()
  // The name of a combatant sent from the Deck Builder who is not in the capture
  const [notOwned, setNotOwned] = useState<string | null>(null)

  const [initial] = useState(loadPersistedState)
  const [charName, setCharName] = useState(initial?.charName ?? '')
  const [deck, setDeck] = useState<DeckChoice>(initial?.deck ?? AUTO_DECK)
  const [morale, setMorale] = useState(initial?.morale ?? 0)
  const [useSparks, setUseSparks] = useState(initial?.useSparks ?? true)
  const [presetGroup, setPresetGroup] = useState(initial?.presetGroup ?? ENEMY_PRESET_GROUPS[0].group)
  const [weaken, setWeaken] = useState(initial?.weaken ?? false)
  const [vulnerableStacks, setVulnerableStacks] = useState(initial?.vulnerableStacks ?? 0)
  const [dmgReduction, setDmgReduction] = useState(initial?.dmgReduction ?? false)
  const [result, setResult] = useState<SimulateDamageResponse | null>(initial?.result ?? null)
  const [resultDeckName, setResultDeckName] = useState<string | null>(initial?.resultDeckName ?? null)
  const [savedDecks] = useState(loadSavedDecks)

  // Callers must pass every field that just changed in `patch` to override the closure snapshot.
  function persist(patch: Partial<PersistedState>) {
    savePersistedState({
      charName, deck, morale, useSparks, presetGroup,
      weaken, vulnerableStacks, dmgReduction, result, resultDeckName,
      ...patch,
    })
  }

  /**
   * Pick the deck to simulate.
   * @param choice The deck.
   */
  function selectDeck(choice: DeckChoice) {
    setDeck(choice)
    persist({ deck: choice })
  }

  const { data: status } = useQuery({
    queryKey: ['status'],
    queryFn: () => api.status(),
    refetchInterval: 5_000,
  })

  const { data: combatants = [] } = useQuery<Combatant[]>({
    queryKey: ['combatants'],
    queryFn: () => api.combatants(),
    enabled: status?.data_loaded ?? false,
    staleTime: 30_000,
  })

  const { data: decks = [] } = useQuery<DeckInfo[]>({
    queryKey: ['simulate-decks', charName],
    queryFn: () => api.simulateDecks(charName),
    enabled: charName !== '' && (status?.data_loaded ?? false),
    staleTime: 30_000,
  })

  // Apply a deck sent from the Deck Builder once the combatants load, then drop it from the router state so a reload does not resend it
  useEffect(() => {
    const handoff = (location.state as { deckBuilder?: DeckBuilderHandoff } | null)?.deckBuilder
    if (!handoff || combatants.length === 0) return
    navigate(location.pathname, { replace: true, state: null })
    const target = combatants.find((c) => c.res_id === handoff.combatantId)
    setNotOwned(target ? null : handoff.name)
    if (!target) return
    const choice: DeckChoice = { kind: 'cards', name: t('simulator.builderDeck', { name: target.name }), cards: handoff.cards }
    setCharName(target.char_id)
    setDeck(choice)
    persist({ charName: target.char_id, deck: choice })
  }, [location.state, combatants])

  // The slots of decks saved in the Deck Builder that belong to the selected character
  const combatant = combatants.find((c) => c.char_id === charName)
  const savedSlots = savedDecks.flatMap((saved) =>
    saved.payload.slots
      .map((slot, slotIndex) => ({ saved, slot, slotIndex }))
      .filter(({ slot }) => slot.combatant_id === combatant?.res_id && slot.cards.length > 0),
  )

  // Shares the History tab's cache entry, showing only the newest few
  const { data: recentBattles = [] } = useQuery<BattleRecord[], Error, BattleRecord[]>({
    queryKey: ['battle-history', 30],
    queryFn: () => api.battleHistory(30),
    select: (battles) => battles.slice(0, 5),
    staleTime: 10_000,
    retry: false,
  })

  const mutation = useMutation({
    mutationFn: async () => {
      const name = deck.kind === 'cards' ? deck.name : null
      const data = await api.simulateDamage({
        char_name: charName,
        ...(deck.kind === 'game' ? { deck_id: deck.id } : { cards: deck.cards }),
        morale,
        use_sparks: useSparks,
        monster_def: enemy.def,
        dmg_decrease: enemy.dmgDecrease,
        frightened: weaken,
        exposed_stacks: vulnerableStacks,
        fortitude: dmgReduction,
      })
      return { data, name }
    },
    onSuccess: ({ data, name }) => { setResult(data); setResultDeckName(name); persist({ result: data, resultDeckName: name }) },
  })

  // A deck sent unsaved from the Deck Builder, listed on its own until another deck is picked
  const sentDeck = deck.kind === 'cards' && !deck.saved ? deck : null
  const canRun = charName !== '' && !mutation.isPending && (status?.data_loaded ?? false)
  const moraleMultDisplay = `×${(1 + morale * MORALE_PCT / 100).toFixed(2)}`
  const defReductionPreview = `${(damagePasses(enemy.dmgDecrease, enemy.def) * 100).toFixed(1)}%`
  const activeGroup = ENEMY_PRESET_GROUPS.find((group) => group.group === presetGroup) ?? ENEMY_PRESET_GROUPS[0]
  const source = enemy.source

  return (
    <div className="flex h-full overflow-hidden">
      {/* Left panel */}
      <div className="w-64 shrink-0 flex flex-col gap-4 p-4 bg-[#181818] border-r border-[#282828] overflow-y-auto">
        {!status?.data_loaded && (
          <div className="text-[#f87171] text-xs bg-[#2a1a1a] border border-[#5a2020] rounded px-3 py-2">
            {t('simulator.noData')}
          </div>
        )}

        <div className="flex flex-col gap-1">
          <label className="text-[#b3b3b3] text-xs">{t('simulator.character')}</label>
          <CharacterCombobox
            combatants={combatants}
            value={charName}
            onChange={(v) => { setCharName(v); setDeck(AUTO_DECK); setNotOwned(null); persist({ charName: v, deck: AUTO_DECK }) }}
          />
          {notOwned && <p className="text-[#f87171] text-[10px]">{t('simulator.notOwned', { name: notOwned })}</p>}
        </div>

        {charName && (decks.length > 0 || savedSlots.length > 0 || sentDeck) && (
          <div className="flex flex-col gap-1">
            <label className="text-[#b3b3b3] text-xs">{t('simulator.deck')}</label>
            <div className="flex flex-col gap-0.5 max-h-56 overflow-y-auto pr-0.5">
              {sentDeck && (
                <>
                  <DeckGroupLabel>{t('simulator.deckGroups.builder')}</DeckGroupLabel>
                  <DeckButton label={sentDeck.name} sub={t('simulator.unsaved')} selected />
                </>
              )}
              {decks.length > 0 && (
                <>
                  {(sentDeck || savedSlots.length > 0) && <DeckGroupLabel>{t('simulator.deckGroups.game')}</DeckGroupLabel>}
                  <DeckButton
                    label={t('simulator.deckAuto')}
                    selected={deck.kind === 'game' && deck.id === null}
                    onClick={() => selectDeck(AUTO_DECK)}
                  />
                  {decks.map((d) => {
                    const label = d.bookmark_slot > 0
                      ? t('simulator.deckSlot', { slot: d.bookmark_slot })
                      : `#${d.deck_id}`
                    return (
                      <DeckButton
                        key={d.deck_id}
                        label={
                          <span className="flex items-center justify-between gap-2">
                            <span className="truncate">{d.name || label}</span>
                            {d.bookmark_slot > 0 && !d.name && <span className="shrink-0 text-[9px] opacity-60">★</span>}
                          </span>
                        }
                        sub={t('simulator.deckPoints', { point: d.point.toLocaleString(), count: d.card_count })}
                        selected={deck.kind === 'game' && deck.id === d.deck_id}
                        onClick={() => selectDeck({ kind: 'game', id: d.deck_id })}
                      />
                    )
                  })}
                </>
              )}
              {savedSlots.length > 0 && (
                <>
                  <DeckGroupLabel>{t('simulator.deckGroups.saved')}</DeckGroupLabel>
                  {savedSlots.map(({ saved, slot, slotIndex }) => {
                    const choice: DeckChoice = { kind: 'cards', name: saved.name, cards: deckSlotToSimCards(slot), saved: { id: saved.id, slotIndex } }
                    return (
                      <DeckButton
                        key={`${saved.id}-${slotIndex}`}
                        label={<span className="block truncate">{saved.name}</span>}
                        sub={t('simulator.deckCards', { count: slot.cards.length })}
                        selected={deck.kind === 'cards' && deck.saved?.id === saved.id && deck.saved.slotIndex === slotIndex}
                        onClick={() => selectDeck(choice)}
                      />
                    )
                  })}
                </>
              )}
            </div>
          </div>
        )}

        <div className="flex flex-col gap-1">
          <div className="flex justify-between items-center">
            <label className="text-[#b3b3b3] text-xs">{t('simulator.morale')}</label>
            <span className="text-[#c084fc] text-xs font-mono">{morale} {moraleMultDisplay}</span>
          </div>
          <input
            type="range"
            min={0}
            max={20}
            value={morale}
            onChange={(e) => { const v = Number(e.target.value); setMorale(v); persist({ morale: v }) }}
            className="w-full accent-[#c084fc]"
          />
          <div className="flex justify-between text-[#555] text-[10px]">
            <span>0</span>
            <span>10</span>
            <span>20</span>
          </div>
        </div>

        {/* Monster DEF */}
        <div className="flex flex-col gap-1">
          <div className="flex justify-between items-center">
            <label className="text-[#b3b3b3] text-xs">{t('simulator.monsterDef')}</label>
            <span className="text-[#fb923c] text-xs font-mono">{defReductionPreview} {t('simulator.dmgPasses')}</span>
          </div>
          <select
            value={activeGroup.group}
            onChange={(e) => { setPresetGroup(e.target.value); persist({ presetGroup: e.target.value }) }}
            className="mt-1 bg-[#222] border border-[#333] text-[#e5e7eb] text-xs rounded px-2 py-1"
          >
            {ENEMY_PRESET_GROUPS.map((group) => (
              <option key={group.group} value={group.group}>{t(`simulator.presetGroups.${group.group}`)}</option>
            ))}
          </select>
          <div className="flex flex-wrap gap-1">
            {activeGroup.presets.map((p) => (
              <button
                key={p.label}
                type="button"
                title={t('simulator.presetTip', { def: p.def, pct: (p.dmg_decrease * 100).toFixed(1) })}
                onClick={() => setEnemy(presetEnemy(activeGroup.group, p))}
                className={`text-[10px] px-1.5 py-0.5 rounded transition-colors ${chipClass(
                  source.kind === 'preset' && source.group === activeGroup.group && source.label === p.label,
                )}`}
              >
                {p.label}
              </button>
            ))}
          </div>
          {recentBattles.length > 0 && (
            <div className="mt-1">
              <p className="text-[9px] text-[#555] uppercase tracking-wider mb-1">{t('simulator.recentBattles')}</p>
              <div className="flex flex-wrap gap-1">
                {recentBattles.map((b) => (
                  <button
                    key={b.capture_time}
                    type="button"
                    title={t('simulator.recentTip', { def: Math.round(b.enemy_def), pct: (b.enemy_dmg_decrease * 100).toFixed(1) })}
                    onClick={() => setEnemy(battleEnemy(b))}
                    className={`flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded transition-colors ${chipClass(
                      source.kind === 'battle' && source.captureTime === b.capture_time,
                    )}`}
                  >
                    <span className={b.battle_result === 'CLEAR' ? 'text-[#a3e635]' : 'text-[#f87171]'}>●</span>
                    {formatBattleTime(b.capture_time)} · {Math.round(b.enemy_def)}
                  </button>
                ))}
              </div>
            </div>
          )}
          <input
            type="number"
            min={0}
            max={9999}
            value={enemy.def}
            onChange={(e) => setEnemy(typedEnemy(Math.max(0, Number(e.target.value))))}
            className="mt-1 bg-[#222] border border-[#333] text-[#e5e7eb] text-xs rounded px-2 py-1 font-mono"
          />
        </div>

        {/* Buffs & Debuffs */}
        <div className="flex flex-col gap-2">
          <label className="text-[#b3b3b3] text-xs">{t('simulator.buffsDebuffs')}</label>

          <div className="flex flex-col gap-1.5 bg-[#1e1e1e] rounded p-2">
            <div className="flex items-center justify-between">
              <label className="text-[#f87171] text-xs cursor-pointer" htmlFor="weaken">
                {t('simulator.weaken')}
                <span className="ml-1 text-[#555] text-[10px]">{t('simulator.weakenHint')}</span>
              </label>
              <input
                id="weaken"
                type="checkbox"
                checked={weaken}
                onChange={(e) => { setWeaken(e.target.checked); persist({ weaken: e.target.checked }) }}
                className="accent-[#f87171]"
              />
            </div>

            <div className="flex items-center justify-between">
              <label className="text-[#34d399] text-xs cursor-pointer" htmlFor="dmg-reduction">
                {t('simulator.dmgReduction')}
                <span className="ml-1 text-[#555] text-[10px]">{t('simulator.dmgReductionHint')}</span>
              </label>
              <input
                id="dmg-reduction"
                type="checkbox"
                checked={dmgReduction}
                onChange={(e) => { setDmgReduction(e.target.checked); persist({ dmgReduction: e.target.checked }) }}
                className="accent-[#34d399]"
              />
            </div>

            <div className="flex flex-col gap-0.5 mt-1">
              <div className="flex justify-between items-center">
                <span className="text-[#facc15] text-xs">{t('simulator.vulnerable')}</span>
                <span className="text-[#facc15] text-xs font-mono">
                  {vulnerableStacks > 0
                    ? t('simulator.vulnerableHint', { mult: (1 + vulnerableStacks * 0.5).toFixed(1) })
                    : 'off'}
                </span>
              </div>
              <input
                type="range"
                min={0}
                max={5}
                value={vulnerableStacks}
                onChange={(e) => { const v = Number(e.target.value); setVulnerableStacks(v); persist({ vulnerableStacks: v }) }}
                className="w-full accent-[#facc15]"
              />
              <div className="flex justify-between text-[#555] text-[10px]">
                <span>0</span>
                <span>1</span>
                <span>2</span>
                <span>3</span>
                <span>4</span>
                <span>5</span>
              </div>
            </div>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <input
            id="use-sparks"
            type="checkbox"
            checked={useSparks}
            onChange={(e) => { setUseSparks(e.target.checked); persist({ useSparks: e.target.checked }) }}
            className="accent-[#c084fc]"
          />
          <label htmlFor="use-sparks" className="text-[#b3b3b3] text-xs cursor-pointer">
            {t('simulator.useSparks')}
          </label>
        </div>

        <button
          type="button"
          disabled={!canRun}
          onClick={() => mutation.mutate()}
          className="flex items-center justify-center gap-2 px-4 py-2 rounded bg-[#c084fc] text-[#fff] text-sm font-bold disabled:opacity-40 disabled:cursor-not-allowed hover:bg-[#a855f7] transition-colors"
        >
          <Play size={14} />
          {mutation.isPending ? t('simulator.running') : t('simulator.run')}
        </button>

        {mutation.isError && (
          <div className="text-[#f87171] text-xs bg-[#2a1a1a] border border-[#5a2020] rounded px-3 py-2">
            {(mutation.error as Error)?.message ?? t('simulator.error')}
          </div>
        )}

        <div className="mt-auto text-[#555] text-[10px] leading-relaxed border-t border-[#282828] pt-3">
          <p>{t('simulator.formulaNote', { pct: MORALE_PCT })}</p>
          <p className="mt-1">{t('simulator.buffNote')}</p>
        </div>
      </div>

      {/* Right results area */}
      <div className="flex-1 overflow-y-auto p-4">
        {!result && !mutation.isPending && (
          <div className="flex flex-col items-center justify-center h-full gap-3 text-[#444]">
            <Zap size={40} />
            <p className="text-sm">{t('simulator.empty')}</p>
          </div>
        )}

        {mutation.isPending && (
          <div className="flex items-center justify-center h-full text-[#888] text-sm">
            {t('simulator.running')}…
          </div>
        )}

        {result && !mutation.isPending && (
          <div className="flex flex-col gap-4">
            {/* Stats summary */}
            <div>
              <div className="flex items-baseline gap-2 mb-3">
                <h3 className="text-[#ffffff] font-bold text-sm">{result.char_name}</h3>
                {(resultDeckName || result.deck_id != null) && (
                  <span className="text-[#555] text-[10px]">{resultDeckName ?? `deck #${result.deck_id}`}</span>
                )}
              </div>
              <div className="flex flex-wrap gap-2 mb-4">
                <StatPill label="ATK" value={Math.round(result.atk).toLocaleString()} />
                <StatPill label="CRate" value={`${result.crate.toFixed(1)}%`} />
                <StatPill label="CDmg" value={`${result.cdmg.toFixed(1)}%`} />
                <StatPill label={t('simulator.critFactor')} value={`×${result.crit_factor.toFixed(3)}`} />
                <StatPill label={t('simulator.morale')} value={`${result.morale_stacks} (${result.morale_mult.toFixed(2)}×)`} />
                <StatPill
                  label={`DEF ${result.monster_def}`}
                  value={`${(result.def_reduction * 100).toFixed(1)}%`}
                />
                {result.buff_mult !== 1 && (
                  <StatPill
                    label={t('simulator.buffMult')}
                    value={`×${result.buff_mult.toFixed(3)}`}
                    highlight={result.buff_mult > 1}
                  />
                )}
              </div>
            </div>

            {/* Totals */}
            <div className="grid grid-cols-3 gap-2">
              <div className="bg-[#1e1e1e] rounded px-4 py-3 flex flex-col gap-0.5">
                <span className="text-[#888] text-[10px] uppercase tracking-wide">{t('simulator.totalNormal')}</span>
                <span className="text-[#e5e7eb] font-bold text-lg font-mono">
                  {result.total_normal.toLocaleString()}
                </span>
              </div>
              <div className="bg-[#1e1e1e] rounded px-4 py-3 flex flex-col gap-0.5">
                <span className="text-[#888] text-[10px] uppercase tracking-wide">{t('simulator.totalCrit')}</span>
                <span className="text-[#e5e7eb] font-bold text-lg font-mono">
                  {result.total_crit.toLocaleString()}
                </span>
              </div>
              <div className="bg-[#1a2a1a] rounded px-4 py-3 flex flex-col gap-0.5">
                <span className="text-[#888] text-[10px] uppercase tracking-wide">{t('simulator.totalAvg')}</span>
                <span className="text-[#a3e635] font-bold text-lg font-mono">
                  {result.total_avg.toLocaleString()}
                </span>
              </div>
            </div>

            {/* Card table */}
            {result.cards.length === 0 ? (
              <div className="text-[#888] text-sm text-center py-8">{t('simulator.noDmgCards')}</div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm border-collapse">
                  <thead>
                    <tr className="border-b border-[#333] text-[#888] text-xs uppercase tracking-wide">
                      <th className="px-3 py-2 text-left min-w-[160px]">{t('simulator.col.card')}</th>
                      <th className="px-3 py-2 text-center">{t('simulator.col.cost')}</th>
                      <th className="px-3 py-2 text-center">{t('simulator.col.coefficient')}</th>
                      <th className="px-3 py-2 text-center">{t('simulator.col.hits')}</th>
                      <th className="px-3 py-2 text-right">{t('simulator.col.normal')}</th>
                      <th className="px-3 py-2 text-right">{t('simulator.col.crit')}</th>
                      <th className="px-3 py-2 text-right text-[#a3e635]">{t('simulator.col.avg')}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {[...result.cards]
                      .sort((a, b) => b.avg_damage - a.avg_damage)
                      .map((card, i) => (
                        <CardRow key={`${card.card_id}-${card.spark_id}-${i}`} card={card} />
                      ))}
                  </tbody>
                </table>
                <p className="text-[#555] text-[10px] mt-2 px-1">
                  ✦ = {t('simulator.epiphanyApplied')}
                  &nbsp;·&nbsp; {t('simulator.avgNote')}
                </p>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
