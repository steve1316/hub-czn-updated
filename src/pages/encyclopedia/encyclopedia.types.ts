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

/** Which part of the game's card archive a card is in. */
export type CardGroup = 'combatant' | 'neutral' | 'season' | 'monster' | 'ailment' | 'curse'

/** One epiphany of a card. */
export interface CardEpiphany {
  /** The epiphany level, 1-5. */
  level: number
  /** The game's name for this level, or the base name with a numeral. */
  name: string
  /** The cost printed on the card, -1 for an X cost. */
  cost: number
  /** The card text at this level. */
  description: string
}

/** One card from the game's card archive, generated into `encyclopedia-cards.json`. */
export interface EncyclopediaCard {
  /** The client card id, such as "c_1003_srt1". */
  id: string
  /** The card's name. */
  name: string
  /** The cost printed on the card, -1 for an X cost, or null when the card has none. */
  cost: number | null
  /** The card type as the game names it, such as "Attack". */
  card_type: string
  /** The card text, with its traits in front, such as "[Exhaust] 200% Damage.". */
  description: string
  /** Which part of the archive the card is in. */
  group: CardGroup
  /** What sort of card it is within its group, such as "starting", "ego" or "power". */
  kind: string
  /** The art path relative to `src/pages/`, or null when there is none. */
  image: string | null
  /** The combatant a combatant card belongs to. */
  character_id?: number
  /** The Chaos season a season card belongs to, 1-5. */
  season?: number
  /** The classes that may take a neutral card. Empty means any class. */
  classes?: string[]
  /** The faction a monster card comes from, such as "Nihilum Faction". */
  faction?: string | null
  /** The card's epiphanies, levels 1-5, when it has any. */
  epiphanies?: CardEpiphany[]
}

/** One Chaos season, as listed in `encyclopedia-cards.json`. */
export interface CardSeason {
  /** The season number, 1-5. */
  number: number
  /** The season's title in the game, such as "Forbidden Catalyst". */
  title: string
}

/** One combatant that has cards, as listed in `encyclopedia-cards.json`. */
export interface CardCharacterEntry {
  /** The combatant's res id. */
  id: number
  /** The combatant's name. */
  name: string
}

/** A game keyword that card text names, with the game's own definition. */
export interface CardKeyword {
  /** The keyword as card text shows it, such as "Ignition". Trigger names keep their colon, such as "Incinerate:". */
  name: string
  /** The game's definition of the keyword. */
  definition: string
}

/** A card name that card text refers to. */
export interface CardLink {
  /** The name as card text shows it, such as "Contaminated Spore". */
  name: string
  /** The client id of the card it refers to. */
  id: string
}

/** A card that card text names but the card list leaves out, with only what its preview shows. */
export type LinkedCard = Pick<EncyclopediaCard, 'id' | 'name' | 'cost' | 'card_type' | 'description' | 'image'>

/** The whole `encyclopedia-cards.json` file. */
export interface EncyclopediaCards {
  /** The seasons that have cards, in order. */
  seasons: CardSeason[]
  /** The combatants that have cards, by name. */
  characters: CardCharacterEntry[]
  /** Every card, in archive order. */
  cards: EncyclopediaCard[]
  /** The keywords card text names, by name. */
  keywords: CardKeyword[]
  /** The card names card text refers to, by name. */
  card_links: CardLink[]
  /** The cards `card_links` refers to that `cards` leaves out. */
  linked_cards: LinkedCard[]
}

/** What the Cards tab is filtered by. */
export interface CardFilters {
  /** A `cardGroupKey` value, or null for every group. */
  group: string | null
  /** A combatant's res id, or null for every combatant. */
  character: number | null
  /** A card type, or null for every type. */
  type: string | null
  /** Text to find in the name or card text. */
  query: string
}

/** One piece of linked text: plain text, a glossary term, a game keyword, or a card name. */
export type DescriptionSegment =
  | { kind: 'text'; value: string }
  | { kind: 'term'; value: string; termId: string }
  | { kind: 'keyword'; value: string; definition: string }
  | { kind: 'card'; value: string; cardId: string }

/** Finds the linkable names in text. */
export interface Matcher {
  /** Matches every linkable name, longest first. Glossary aliases match in any case, keywords and card names only exactly. */
  regex: RegExp
  /** Lower-cased glossary alias -> glossary term id. */
  aliasToTermId: Map<string, string>
  /** Keyword name -> its definition. */
  keywords: Map<string, string>
  /** Card name -> card id. */
  cardIds: Map<string, string>
}
