import type { LocalizedText } from '@/lib/localized-text'

// Guides are imported from an English-only sheet, so `pt-BR` is usually absent and English is shown instead.
export type { Lang, LocalizedText } from '@/lib/localized-text'

export type Block =
  | { type: 'prose'; body: LocalizedText }
  | {
      type: 'card-list'
      intro?: LocalizedText
      items: { cardId: string; rating?: string; note: LocalizedText }[]
    }
  | {
      type: 'partner-list'
      items: { charResId: number; name: string; rating: string; note: LocalizedText }[]
    }
  | {
      type: 'gear-list'
      intro?: LocalizedText
      items: { image?: string; name: string; note?: LocalizedText }[]
    }
  | {
      type: 'rating-list'
      items: { label: string; text: LocalizedText }[]
    }
  | {
      type: 'team-grid'
      groups: { title?: LocalizedText; faces: number[] }[]
    }

export interface GuideSection {
  id: string
  title: LocalizedText
  blocks: Block[]
}

export interface GuideSource {
  url: string
  label: LocalizedText
}

export interface Guide {
  charResId: number
  name: string
  source?: GuideSource
  sections: GuideSection[]
}
