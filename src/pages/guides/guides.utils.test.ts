import { describe, it, expect } from 'vitest'
import type { DeckCard, Guide } from './guides.types'
import { cardEntry, epiphanyRatings, guideDeckToSlot, headsNext, levelNumeral, localized, proseParts, ratingScore, ratingTone, resolveLang } from './guides.utils'

describe('resolveLang', () => {
  it('returns en for en and anything else', () => {
    expect(resolveLang('en')).toBe('en')
    expect(resolveLang('pt-BR')).toBe('en')
    expect(resolveLang('es')).toBe('en')
  })
})

describe('localized', () => {
  it('picks the string for the given language', () => {
    const t = { en: 'Hello' }
    expect(localized(t, 'en')).toBe('Hello')
  })
})

describe('ratingScore', () => {
  it('reads the score before the slash, or -1 when there is none', () => {
    expect(ratingScore('3.5/5')).toBe(3.5)
    expect(ratingScore('0/5')).toBe(0)
    expect(ratingScore(undefined)).toBe(-1)
    expect(ratingScore('?')).toBe(-1)
  })
})

describe('levelNumeral', () => {
  it('writes epiphany levels 1-5 as numerals', () => {
    expect(levelNumeral(1)).toBe('I')
    expect(levelNumeral(5)).toBe('V')
  })
})

describe('ratingTone', () => {
  it('colours a rating by its whole score', () => {
    expect(ratingTone('6/5')).toBe('gold')
    expect(ratingTone('5/5')).toBe('purple')
    expect(ratingTone('4/5')).toBe('blue')
    expect(ratingTone('3.5/5')).toBe('grey')
    expect(ratingTone('2/5')).toBe('red')
    expect(ratingTone('0/5')).toBe('red')
  })
})

describe('proseParts', () => {
  it('gathers term lines into one terms part', () => {
    const parts = proseParts('Equilux:\nStart of turn moves to hand\nTassel: base damage', false)
    expect(parts).toEqual([
      { kind: 'terms', terms: [{ term: 'Equilux', lines: ['Start of turn moves to hand'] }, { term: 'Tassel', lines: ['base damage'] }] },
    ])
  })
  it('reads a short piped line as a heading', () => {
    expect(proseParts('Cycle -2 | Blink Flow | 180 FM', false)).toEqual([{ kind: 'heading', text: 'Cycle -2 | Blink Flow | 180 FM' }])
  })
  it('keeps a plain sentence as text', () => {
    expect(proseParts('Plain sentence here.', false)).toEqual([{ kind: 'text', text: 'Plain sentence here.' }])
  })
})

describe('headsNext', () => {
  it('lets a short line head content but not prose or a band heading', () => {
    expect(headsNext({ type: 'set-list', items: [] })).toBe(true)
    expect(headsNext({ type: 'heading', text: { en: 'C7 Burning Life' } })).toBe(false)
    expect(headsNext({ type: 'prose', body: { en: 'More' } })).toBe(false)
    expect(headsNext(undefined)).toBe(false)
  })
})

describe('epiphanyRatings', () => {
  it('finds each rated epiphany across sections', () => {
    const flow = {
      cardId: 'c_30134_uni2',
      name: 'Radiant Sword Flow',
      note: { en: '' },
      epiphanies: [{ level: 5, name: 'Radiant Sword Flow V', cost: 1, rating: '5/5', note: { en: 'Pretty crazy' } }],
    }
    const guide: Guide = {
      charResId: 30134,
      name: 'Rossweisse',
      sections: [
        { id: 'notes', title: { en: 'Notes' }, blocks: [{ type: 'prose', body: { en: 'Hi' } }] },
        { id: 'card-ratings', title: { en: 'Card ratings' }, blocks: [{ type: 'card-list', items: [flow] }] },
      ],
    }
    expect(epiphanyRatings(guide).get('c_30134_uni2:5')).toEqual(flow.epiphanies[0])
    expect(epiphanyRatings(guide).has('c_30134_uni2:4')).toBe(false)
  })
})

describe('cardEntry', () => {
  it('gives a Persona the picture of its engraving combination', () => {
    const card = cardEntry('eidolon_card', 'Persona of Obsidian', {}, 'all_umbra') as unknown as Record<string, unknown>
    expect(card.name).toBe('Persona of Obsidian')
    expect(card.__deckBuilderPersonaImagePath).toBe('all_umbra.webp')
    expect((cardEntry('eidolon_card', 'Persona', {}) as unknown as Record<string, unknown>).__deckBuilderPersonaImagePath).toBeUndefined()
  })
})

describe('guideDeckToSlot', () => {
  const card = (over: Partial<DeckCard>): DeckCard => ({ cardId: 'c_30134_uni1', name: 'Sword Resonance', ...over })

  it('keeps every copy with its epiphany level as the Deck Builder variant', () => {
    const { slot } = guideDeckToSlot(30134, [
      card({ epiphany: { level: 2, name: 'Sword Resonance II', text: { en: '' } } }),
      card({ epiphany: { level: 0, name: 'Sword Resonance', text: { en: '' } } }),
      card({}),
    ])
    expect(slot.combatant_id).toBe(30134)
    expect(slot.equipment).toEqual({ weapon_id: null, armor_id: null, accessory_id: null })
    expect(slot.cards.map(c => c.selected_variant_id)).toEqual(['c_30134_uni1_epiphany_2', null, null])
  })

  it('carries divine and common lines by their catalog id', () => {
    const { slot, partial } = guideDeckToSlot(30134, [
      card({ extra: { id: 'div_0098', god: 'Nihilum', text: { en: '' } } }),
      card({ extra: { id: 'com_0065', text: { en: '' } } }),
    ])
    expect(slot.cards[0]).toMatchObject({ selected_divine_epiphany_id: 'div_0098', selected_divine_god: 'Nihilum', selected_common_epiphany_id: null })
    expect(slot.cards[1]).toMatchObject({ selected_divine_epiphany_id: null, selected_divine_god: null, selected_common_epiphany_id: 'com_0065' })
    expect(partial).toEqual([])
  })

  it('loads a card without a line the Deck Builder does not know and names it once', () => {
    const { slot, partial } = guideDeckToSlot(30134, [
      card({ extra: { id: 'div_9999', god: 'Nobody', text: { en: '' } } }),
      card({ extra: { id: 'div_9999', god: 'Nobody', text: { en: '' } } }),
      card({ cardId: 'eidolon_card', name: 'Persona', persona: 'all_umbra' }),
    ])
    expect(slot.cards).toHaveLength(3)
    expect(slot.cards[0]).toMatchObject({ selected_divine_epiphany_id: null, selected_divine_god: null })
    expect(partial).toEqual(['Sword Resonance', 'Persona'])
  })
})
