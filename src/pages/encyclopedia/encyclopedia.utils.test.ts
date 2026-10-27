import { describe, it, expect } from 'vitest'
import { buildMatcher, cardGroupKey, filterCards, filterGlossary, linkDescription, resolveLang, localized } from './encyclopedia.utils'
import type { EncyclopediaCard, GlossaryEntry } from './encyclopedia.types'

function entry(id: string, aliases: string[]): GlossaryEntry {
  return {
    id,
    term: { en: id },
    aliases,
    category: 'mechanic',
    definition: { en: 'def' },
    seeAlso: [],
  }
}

describe('buildMatcher / linkDescription', () => {
  it('returns the whole text as one segment when the glossary is empty', () => {
    const segs = linkDescription('Inflict Agony on the target.', buildMatcher([]))
    expect(segs).toEqual([{ kind: 'text', value: 'Inflict Agony on the target.' }])
  })

  it('returns an empty array for empty text', () => {
    expect(linkDescription('', buildMatcher([entry('agony', ['Agony'])]))).toEqual([])
  })

  it('matches a single alias case-insensitively', () => {
    const segs = linkDescription('inflict agony now', buildMatcher([entry('agony', ['Agony'])]))
    expect(segs).toEqual([
      { kind: 'text', value: 'inflict ' },
      { kind: 'term', value: 'agony', termId: 'agony' },
      { kind: 'text', value: ' now' },
    ])
  })

  it('respects word boundaries', () => {
    const m = buildMatcher([entry('agony', ['Agony'])])
    expect(linkDescription('Agonyx', m)).toEqual([{ kind: 'text', value: 'Agonyx' }])
    const trailing = linkDescription('Agony.', m)
    expect(trailing[0]).toEqual({ kind: 'term', value: 'Agony', termId: 'agony' })
    expect(trailing[1]).toEqual({ kind: 'text', value: '.' })
  })

  it('prefers the longest alias on overlap', () => {
    const m = buildMatcher([entry('count', ['Count']), entry('action-count', ['Action Count'])])
    const segs = linkDescription('an Action Count of 1', m)
    expect(segs).toContainEqual({ kind: 'term', value: 'Action Count', termId: 'action-count' })
    expect(segs.some(s => s.kind === 'term' && s.termId === 'count')).toBe(false)
  })

  it('links every occurrence of a term', () => {
    const m = buildMatcher([entry('agony', ['Agony'])])
    const terms = linkDescription('Agony then Agony', m).filter(s => s.kind === 'term')
    expect(terms).toHaveLength(2)
  })

  it('does not auto-link term.en — only explicit aliases', () => {
    const m = buildMatcher([entry('order', [])])
    expect(linkDescription('Order DMG up', m)).toEqual([{ kind: 'text', value: 'Order DMG up' }])
  })
})

describe('buildMatcher / linkDescription with card keywords and card names', () => {
  const keywords = [
    { name: 'Ignition', definition: 'Cost goes down.' },
    { name: 'Incinerate:', definition: 'When Exhausted.' },
    { name: 'Agony', definition: 'Game definition.' },
  ]
  const cardLinks = [{ name: 'Contaminated Spore', id: 'card_ds02_00009' }]

  it('links keywords and card names with their exact case only', () => {
    const m = buildMatcher([], keywords, cardLinks)
    expect(linkDescription('[Ignition] Create Contaminated Spore', m)).toEqual([
      { kind: 'text', value: '[' },
      { kind: 'keyword', value: 'Ignition', definition: 'Cost goes down.' },
      { kind: 'text', value: '] Create ' },
      { kind: 'card', value: 'Contaminated Spore', cardId: 'card_ds02_00009' },
    ])
    expect(linkDescription('ignition and contaminated spore', m)).toEqual([{ kind: 'text', value: 'ignition and contaminated spore' }])
  })

  it('keeps glossary aliases case-insensitive', () => {
    const m = buildMatcher([entry('quietus', ['Quietus'])], keywords, cardLinks)
    expect(linkDescription('quietus', m)).toEqual([{ kind: 'term', value: 'quietus', termId: 'quietus' }])
  })

  it('prefers a glossary alias over a keyword of the same name', () => {
    const m = buildMatcher([entry('agony', ['Agony'])], keywords, cardLinks)
    expect(linkDescription('Agony', m)).toEqual([{ kind: 'term', value: 'Agony', termId: 'agony' }])
  })

  it('prefers the longest name on overlap', () => {
    const m = buildMatcher([entry('incinerate', ['Incinerate'])], keywords, cardLinks)
    expect(linkDescription('Incinerate: Draw 1', m)[0]).toEqual({ kind: 'keyword', value: 'Incinerate:', definition: 'When Exhausted.' })
  })
})

describe('resolveLang / localized', () => {
  it('resolveLang always returns en', () => {
    expect(resolveLang('en')).toBe('en')
    expect(resolveLang('pt-BR')).toBe('en')
    expect(resolveLang('xx')).toBe('en')
  })

  it('localized returns the English text', () => {
    expect(localized({ en: 'Hello' }, 'en')).toBe('Hello')
  })
})

describe('filterGlossary', () => {
  const glossary: GlossaryEntry[] = [
    { ...entry('Agony', []), category: 'status', definition: { en: 'Damage at the end of the turn.' } },
    { ...entry('Exhaust', []), category: 'card-type', definition: { en: 'Removed after use.' } },
    { ...entry('Quietus', []), category: 'mechanic', definition: { en: 'Procs when Discarded.' } },
  ]

  it('matches the search in the term or the definition, ignoring case', () => {
    expect(filterGlossary(glossary, ' DISCARD ', null, 'en').map(e => e.id)).toEqual(['Quietus'])
    expect(filterGlossary(glossary, 'agony', null, 'en').map(e => e.id)).toEqual(['Agony'])
  })

  it('keeps only the picked category, and every entry when no category is picked', () => {
    expect(filterGlossary(glossary, '', 'card-type', 'en').map(e => e.id)).toEqual(['Exhaust'])
    expect(filterGlossary(glossary, '', null, 'en')).toHaveLength(3)
  })
})

describe('filterCards', () => {
  function card(id: string, fields: Partial<EncyclopediaCard> = {}): EncyclopediaCard {
    return { id, name: id, cost: 1, card_type: 'Attack', description: '', group: 'neutral', kind: 'neutral', image: null, ...fields }
  }

  const cards = [
    card('strike', { group: 'combatant', kind: 'starting', character_id: 1003, description: 'Deal Damage' }),
    card('guard', { group: 'combatant', kind: 'starting', character_id: 1004, card_type: 'Skill' }),
    card('memory', { group: 'season', kind: 'power', season: 5, card_type: 'Upgrade' }),
    card('bash', { group: 'season', kind: 'neutral', season: 1 }),
  ]
  const none = { group: null, character: null, type: null, query: '' }

  it('keys each season apart', () => {
    expect(cardGroupKey(cards[2])).toBe('season-5')
    expect(cardGroupKey(cards[0])).toBe('combatant')
  })

  it('keeps every card when nothing is picked', () => {
    expect(filterCards(cards, none)).toHaveLength(4)
  })

  it('keeps one season, one character or one card type', () => {
    expect(filterCards(cards, { ...none, group: 'season-1' }).map(c => c.id)).toEqual(['bash'])
    expect(filterCards(cards, { ...none, group: 'combatant', character: 1004 }).map(c => c.id)).toEqual(['guard'])
    expect(filterCards(cards, { ...none, type: 'Upgrade' }).map(c => c.id)).toEqual(['memory'])
  })

  it('searches names and card text, ignoring case', () => {
    expect(filterCards(cards, { ...none, query: 'GUARD' }).map(c => c.id)).toEqual(['guard'])
    expect(filterCards(cards, { ...none, query: 'damage' }).map(c => c.id)).toEqual(['strike'])
  })
})
