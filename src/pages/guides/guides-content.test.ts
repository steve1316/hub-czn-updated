import { describe, it, expect } from 'vitest'
import { GUIDES } from './guides-content'
import type { LocalizedText } from './guides.types'

function expectLocalized(t: LocalizedText, ctx: string) {
  expect(t.en?.trim(), `${ctx}.en`).not.toBe('')
}

describe('guides content', () => {
  it('has at least the Tenebria guide', () => {
    expect(GUIDES.some(g => g.charResId === 1069)).toBe(true)
  })

  it('every section title and every block has English text', () => {
    for (const guide of GUIDES) {
      for (const section of guide.sections) {
        expectLocalized(section.title, `${guide.name}/${section.id}/title`)
        for (const [i, block] of section.blocks.entries()) {
          const ctx = `${guide.name}/${section.id}/block[${i}]`
          if (block.type === 'prose') expectLocalized(block.body, `${ctx}.body`)
          if (block.type === 'card-list') {
            if (block.intro) expectLocalized(block.intro, `${ctx}.intro`)
            for (const it of block.items) {
              expect(it.cardId?.trim(), `${ctx}.cardId`).not.toBe('')
              // Cards from other characters or the shared pool are not in the guide character's card list, so each one carries its name.
              expect(it.name?.trim(), `${ctx}.name`).not.toBe('')
              // A card's note is often empty, since the sheet writes one combined note under a row of cards.
              expect(typeof it.note.en, `${ctx}.note`).toBe('string')
              for (const ep of it.epiphanies ?? []) {
                expect(ep.level, `${ctx}.epiphanies[].level`).toBeGreaterThanOrEqual(1)
                expect(ep.level, `${ctx}.epiphanies[].level`).toBeLessThanOrEqual(5)
                expect(ep.name?.trim(), `${ctx}.epiphanies[].name`).not.toBe('')
              }
            }
          }
          if (block.type === 'partner-list') {
            for (const it of block.items) {
              expect(it.name?.trim(), `${ctx}.name`).not.toBe('')
              expect(typeof it.rating, `${ctx}.rating`).toBe('string')
              expect(typeof it.note.en, `${ctx}.note`).toBe('string')
            }
          }
          if (block.type === 'gear-list') {
            if (block.intro) expectLocalized(block.intro, `${ctx}.intro`)
            for (const it of block.items) {
              expect(it.name?.trim(), `${ctx}.name`).not.toBe('')
              if (it.note) expectLocalized(it.note, `${ctx}.note`)
            }
          }
          if (block.type === 'rating-list') {
            for (const it of block.items) {
              expect(it.label?.trim(), `${ctx}.label`).not.toBe('')
              expectLocalized(it.text, `${ctx}.text`)
            }
          }
          if (block.type === 'team-grid') {
            for (const group of block.groups) {
              if (group.title) expectLocalized(group.title, `${ctx}.title`)
              expect(Array.isArray(group.members), `${ctx}.members`).toBe(true)
              for (const member of group.members) {
                expect(typeof member.charResId, `${ctx}.members[].charResId`).toBe('number')
                expect(member.name?.trim(), `${ctx}.members[].name`).not.toBe('')
              }
            }
          }
          if (block.type === 'deck') {
            for (const card of block.cards) {
              expect(card.cardId?.trim(), `${ctx}.cardId`).not.toBe('')
              if (card.epiphany) {
                expect(card.epiphany.level, `${ctx}.epiphany.level`).toBeGreaterThanOrEqual(0)
                expect(card.epiphany.level, `${ctx}.epiphany.level`).toBeLessThanOrEqual(5)
              }
            }
          }
          if (block.type === 'set-list') {
            for (const item of block.items) {
              expect(item.label?.trim(), `${ctx}.label`).not.toBe('')
            }
          }
        }
      }
    }
  })

  it('has unique section ids per guide', () => {
    for (const guide of GUIDES) {
      const ids = guide.sections.map(s => s.id)
      expect(new Set(ids).size, guide.name).toBe(ids.length)
    }
  })
})
