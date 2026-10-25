import { describe, it, expect } from 'vitest'
import type { Guide } from './guides.types'
import { epiphanyRatings, localized, proseParts, ratingTone, resolveLang } from './guides.utils'

describe('resolveLang', () => {
  it('returns en only for en', () => {
    expect(resolveLang('en')).toBe('en')
  })
  it('returns pt-BR for pt-BR and anything else', () => {
    expect(resolveLang('pt-BR')).toBe('pt-BR')
    expect(resolveLang('es')).toBe('pt-BR')
  })
})

describe('localized', () => {
  it('picks the string for the given language', () => {
    const t = { en: 'Hello', 'pt-BR': 'Olá' }
    expect(localized(t, 'en')).toBe('Hello')
    expect(localized(t, 'pt-BR')).toBe('Olá')
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
