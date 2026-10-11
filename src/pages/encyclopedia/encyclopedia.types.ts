import type { LocalizedText } from '@/lib/localized-text'

export type { Lang, LocalizedText } from '@/lib/localized-text'

export type GlossaryCategory = 'status' | 'card-type' | 'mechanic'

export interface GlossaryEntry {
  id: string
  term: LocalizedText
  aliases: string[]
  category: GlossaryCategory
  definition: LocalizedText
  seeAlso: string[]
}

export type ClarificationKind = 'equipment' | 'engraving' | 'card'

export interface Clarification {
  kind: ClarificationKind
  refId: string
  text: LocalizedText
}

export interface EncyclopediaContent {
  glossary: GlossaryEntry[]
  clarifications: Clarification[]
}

export type DescriptionSegment =
  | { kind: 'text'; value: string }
  | { kind: 'term'; value: string; termId: string }

export interface Matcher {
  regex: RegExp
  aliasToTermId: Map<string, string>
}
