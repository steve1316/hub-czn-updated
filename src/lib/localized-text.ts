/** A content language the app can show. */
export type Lang = 'en' | 'pt-BR'

/** Text in each available language. English is always present, other languages only when translated. */
export type LocalizedText = { en: string } & Partial<Record<Exclude<Lang, 'en'>, string>>

/**
 * Maps an i18next language code to one of the supported content languages.
 * @param lng - The i18next language code.
 * @returns `en` for English, otherwise `pt-BR`.
 */
export function resolveLang(lng: string): Lang {
  return lng === 'en' ? 'en' : 'pt-BR'
}

/**
 * Picks the text for the given language, falling back to English when that language is missing or empty.
 * @param text - The text in each available language.
 * @param lang - The language to show.
 * @returns The text in `lang`, or the English text when there is none.
 */
export function localized(text: LocalizedText, lang: Lang): string {
  return text[lang] || text.en
}
