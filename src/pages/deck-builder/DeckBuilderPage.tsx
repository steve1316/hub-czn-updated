import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useLocation, useNavigate } from 'react-router-dom'
import { X } from 'lucide-react'
import type { CardCharacter } from '@/lib/types'
import { deckSlotToSimCards, matchingSavedSlot, type DeckBuilderHandoff } from '@/pages/simulator/simulator-deck.utils'
import { CombatantDeckColumn } from './components/CombatantDeckColumn'
import { SquadStrip } from './components/SquadStrip'
import { DeckBuilderHeader } from './components/DeckBuilderHeader'
import {
  VariantSettingsModal,
  type VariantModalInitialSection,
} from './components/VariantSettingsModal'
import { createDeckBuilderExportSlot, useDeckBuilder } from './hooks/useDeckBuilder'
import type { SquadSlot } from './deck-builder.types'
import type { GuideDeckHandoff } from '@/pages/guides/guides.utils'

type DeckBuilderCardCharacter = CardCharacter & {
  class?: string | null
  attribute?: string | null
}

export function DeckBuilderPage() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const location = useLocation()
  const deckBuilder = useDeckBuilder()
  const guideDeck = (location.state as { guideDeck?: GuideDeckHandoff } | null)?.guideDeck
  const [guideNotice, setGuideNotice] = useState<string[] | null>(null)
  const [activeSlot, setActiveSlot] = useState(0)
  const slot = deckBuilder.squad[activeSlot]
  const variantModalTarget = deckBuilder.variantModalTarget
  const [variantModalInitialSection, setVariantModalInitialSection] =
    useState<VariantModalInitialSection>('epiphany')

  /**
   * Open the Simulate tab with one combatant's deck, epiphanies included.
   * @param slot The squad slot to simulate.
   * @param index The slot's index in the squad.
   */
  function simulateSlot(slot: SquadSlot, index: number) {
    if (slot.combatantId === null) return
    const character = deckBuilder.characters.find(c => c.char_res_id === slot.combatantId)
    const exported = createDeckBuilderExportSlot(slot)
    const handoff: DeckBuilderHandoff = {
      combatantId: slot.combatantId,
      name: character?.name || `#${slot.combatantId}`,
      cards: deckSlotToSimCards(exported),
      saved: matchingSavedSlot(deckBuilder.savedDecks, deckBuilder.selectedSavedDeckId, index, exported),
    }
    navigate('/battles/simulate', { state: { deckBuilder: handoff } })
  }

  // A deck opened from a guide goes in once the squad from an earlier visit is back, so it is not overwritten
  useEffect(() => {
    if (!guideDeck || !deckBuilder.restored) return
    navigate(location.pathname, { replace: true, state: null })
    deckBuilder
      .placeIncomingSlot(guideDeck.slot, () => window.confirm(t('deckBuilder.guide.replaceConfirm', { name: guideDeck.name })))
      .then(result => {
        if (!result) return
        setActiveSlot(result.index)
        setGuideNotice([
          t('deckBuilder.guide.loaded', { name: guideDeck.name, slot: result.index + 1 }),
          ...(result.dropped > 0 ? [t('deckBuilder.guide.dropped', { count: result.dropped })] : []),
          ...(guideDeck.partial.length > 0 ? [t('deckBuilder.guide.partial', { cards: guideDeck.partial.join(', ') })] : []),
        ])
      })
      .catch(error => console.error('[Deck Builder] Failed to load the guide deck:', error))
  }, [guideDeck, deckBuilder.restored])

  const variantModalCombatantClass = variantModalTarget
    ? (
        deckBuilder.characters.find(
          character =>
            character.char_res_id ===
            deckBuilder.squad[variantModalTarget.slotIndex]?.combatantId,
        ) as DeckBuilderCardCharacter | undefined
      )?.class ?? null
    : null

  return (
    <div className="flex h-full flex-col bg-[#0f0f14] text-white">
      <DeckBuilderHeader
        savedDecks={deckBuilder.savedDecks}
        selectedSavedDeckId={deckBuilder.selectedSavedDeckId}
        onReset={deckBuilder.resetBuilder}
        onImportDeck={deckBuilder.importDeck}
        onExportDeck={deckBuilder.exportDeck}
        onLoadSavedDeck={deckBuilder.loadSavedDeck}
        onSaveCurrentDeck={deckBuilder.saveCurrentDeck}
        onSaveCurrentDeckAs={deckBuilder.saveCurrentDeckAs}
        onDeleteSavedDeck={deckBuilder.deleteSavedDeck}
      />

      {guideNotice && (
        <div role="status" className="mx-4 mt-4 flex items-start gap-3 rounded-md border border-[#c084fc55] bg-[#1f1730] px-4 py-2.5 text-sm text-[#e5e7eb]">
          <div className="flex-1">
            {guideNotice.map(line => <p key={line}>{line}</p>)}
          </div>
          <button type="button" aria-label={t('deckBuilder.guide.dismiss')} onClick={() => setGuideNotice(null)} className="rounded p-0.5 text-[#b3b3b3] hover:text-[#ffffff]">
            <X size={16} />
          </button>
        </div>
      )}

      {deckBuilder.isLoading ? (
        <div className="flex min-h-0 flex-1 items-center justify-center text-sm text-[#888]">
          {t('deckBuilder.loadingCombatants')}
        </div>
      ) : (
        <main className="flex min-h-0 flex-1 flex-col gap-3 overflow-hidden p-4">
          <SquadStrip
            squad={deckBuilder.squad}
            costs={deckBuilder.slotBuildCosts}
            characters={deckBuilder.characters}
            activeSlot={activeSlot}
            onSelect={setActiveSlot}
          />

          <CombatantDeckColumn
            key={activeSlot}
            slotIndex={activeSlot}
            slot={slot}
            slotBuildCost={deckBuilder.slotBuildCosts[activeSlot]}
            characters={deckBuilder.characters}
            onSelectCombatant={combatantId => deckBuilder.selectCombatant(activeSlot, combatantId)}
            onDuplicateCard={instanceId => deckBuilder.duplicateCard(activeSlot, instanceId)}
            onRemoveCard={instanceId => deckBuilder.removeCard(activeSlot, instanceId)}
            onAddDeckBuilderCard={item => deckBuilder.addDeckBuilderCard(activeSlot, item)}
            onOpenDeckCardVariants={(item, initialSection = 'epiphany') => {
              setVariantModalInitialSection(initialSection)
              deckBuilder.openDeckCardVariants(activeSlot, item)
            }}
            onOpenAvailableCardVariants={item => {
              setVariantModalInitialSection('epiphany')
              deckBuilder.openAvailableCardVariants(activeSlot, item)
            }}
            onSelectEquipment={(equipmentSlot, item) => deckBuilder.selectEquipment(activeSlot, equipmentSlot, item)}
            onClearEquipment={equipmentSlot => deckBuilder.clearEquipment(activeSlot, equipmentSlot)}
            onClearDeck={() => deckBuilder.clearDeck(activeSlot)}
            onSimulate={() => simulateSlot(slot, activeSlot)}
          />
        </main>
      )}

      {variantModalTarget && (
        <VariantSettingsModal
          target={variantModalTarget}
          combatantClass={variantModalCombatantClass}
          initialSection={variantModalInitialSection}
          onClose={deckBuilder.closeVariantModal}
          onApplySettings={deckBuilder.applyEpiphanySettings}
          onClearSettings={
            variantModalTarget.type === 'deck'
              ? deckBuilder.clearEpiphanySettings
              : undefined
          }
        />
      )}
    </div>
  )
}
