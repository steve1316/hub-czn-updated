import type { LocalizedText } from '@/lib/localized-text'

// Guides are imported from an English-only sheet.
export type { Lang, LocalizedText } from '@/lib/localized-text'

/** One epiphany level of a rated card, folded from the sheet's run of renders. */
export interface EpiphanyRating {
  /** The epiphany level, 1-5. */
  level: number
  /** The game's name for this level ("Flicker Blade (Unbound)"), or the base name with a numeral ("Sword Resonance II"). */
  name: string
  /** The cost printed on this level, -1 for an X cost. */
  cost: number
  /** The author's rating, such as "5/5". */
  rating?: string
  /** The author's comment on this level, from a "Flow 2:" style line under the cards. */
  note: LocalizedText
}

/** One card in a card-list. */
export interface CardItem {
  /** The client card id, such as `c_30134_uni2`. */
  cardId: string
  /** The card's display name. */
  name?: string
  /** The Persona art key, such as `all_umbra`, for a Persona card whose engravings give it its own art. */
  persona?: string
  /** The cost printed on the card, -1 for an X cost. Absent when the card is folded into `epiphanies`. */
  cost?: number
  /** The author's rating, such as "4/5". */
  rating?: string
  /** The author's comment on the card. */
  note: LocalizedText
  /** How many pictures of this card the sheet shows side by side with the same rating, set when more than one. */
  count?: number
  /** Every rated epiphany level, when the sheet rates the card's levels one by one. */
  epiphanies?: EpiphanyRating[]
}

/** The epiphany a deck card shows, read off its sheet picture. */
export interface DeckEpiphany {
  /** 0 for the base card, else the epiphany level 1-5. */
  level: number
  /** The level's display name. */
  name: string
  /** The level's card text. */
  text: LocalizedText
}

/** A divine or common epiphany line added to a deck card. */
export interface DeckExtra {
  /** The catalog id, such as "div_0098" or "com_0065". */
  id: string
  /** The divine god's display name, absent for a common epiphany. */
  god?: string
  /** The line as the card shows it. */
  text: LocalizedText
}

/** One card in a deck strip. Every copy is listed. */
export interface DeckCard {
  /** The client card id. */
  cardId: string
  /** The card's display name. */
  name?: string
  /** The Persona art key, such as `all_umbra`, for a Persona card whose engravings give it its own art. */
  persona?: string
  /** The cost the card shows, after any extra line that reduces it. -1 for an X cost. */
  cost?: number
  /** The epiphany it shows. Absent when it could not be read or the card has none. */
  epiphany?: DeckEpiphany
  /** The card's own text, set only when the card has no epiphanies. */
  text?: LocalizedText
  /** The divine or common line added to it. */
  extra?: DeckExtra
}

/** One part of a sheet line listing sets, such as "BlackWing | Executioners | Flex". */
export interface SetItem {
  /** The sheet's own text for this part. */
  label: string
  /** The memory fragment set id, absent when the part names no set (such as "Flex"). */
  setId?: number
  /** The set's full name. */
  name?: string
  /** How many pieces the set bonus needs. */
  pieces?: number
  /** The set bonus text. */
  bonus?: string
  /** The set icon path, served by the sidecar. */
  icon?: string
}

/** One character in a team-grid group. */
export interface TeamMember {
  /** The character or partner res_id. */
  charResId: number
  /** The display name. */
  name: string
}

/** One colour of the potentials picture's legend. */
export interface PotentialsLegendEntry {
  /** The highlight colour in the picture that this entry explains. */
  colour: 'purple' | 'gold' | 'blue'
  /** What the author marks with that colour, such as "Main Damage Boosts". */
  text: LocalizedText
}

/** The author's comment on one ego manifestation level. */
export interface EgoNote {
  /** The level, 1-6, counted in the order the sheet lists them. */
  level: number
  /** The comment. */
  text: LocalizedText
  /** True when the sheet writes the comment mostly in bold, which marks the author's key lines. */
  bold?: boolean
}

export type Block =
  | { type: 'prose'; body: LocalizedText }
  | { type: 'heading'; text: LocalizedText }
  | {
      type: 'potentials'
      image: string | null
      treeImage: string
      coloured: boolean
      legend: PotentialsLegendEntry[]
      ego: EgoNote[]
    }
  | {
      type: 'card-list'
      intro?: LocalizedText
      items: CardItem[]
    }
  | {
      type: 'image'
      image: string
    }
  | {
      type: 'deck'
      cards: DeckCard[]
    }
  | {
      type: 'set-list'
      items: SetItem[]
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
      groups: { title?: LocalizedText; members: TeamMember[] }[]
    }

/** One page of a guide. Every guide has the same pages, in the same order. */
export interface GuideSection {
  /** The page id, such as "decks" or "potentials". */
  id: string
  /** The page name shown in the nav. */
  title: LocalizedText
  /** The page's content, with each sheet band's title as a heading block. */
  blocks: Block[]
  /** True when the sheet has nothing for this page. */
  missing?: boolean
}

export interface GuideSource {
  url: string
  label: LocalizedText
}

export interface Guide {
  charResId: number
  name: string
  source?: GuideSource
  /** The sheet's last edit date, such as "10/24". */
  updated?: string
  sections: GuideSection[]
}
