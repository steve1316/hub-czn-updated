import { GUIDES } from './guides-content'
import type { Guide } from './guides.types'

/** A guide as the list page shows it. */
export interface GuideListEntry {
  /** The guide character's res_id. */
  charResId: number
  /** The guide character's name. */
  name: string
  /** When the sheet last updated the guide, as "M/D", if it says. */
  updated?: string
}

export const GUIDE_LIST: GuideListEntry[] = GUIDES.map((g: Guide) => ({
  charResId: g.charResId,
  name: g.name,
  updated: g.updated,
}))
