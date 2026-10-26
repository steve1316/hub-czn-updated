import { describe, it, expect } from 'vitest'
import type { Guide } from './guides.types'
import { cardEntry, epiphanyRatings, headsNext, levelNumeral, localized, proseParts, ratingScore, ratingTone, resolveLang } from './guides.utils'

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
