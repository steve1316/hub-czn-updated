/** A content language the app can show. */
export type Lang = 'en'

/** Text in each available language. English is the only language shown. */
export type LocalizedText = { en: string }

/**
 * Maps an i18next language code to a content language. English is the only one.
 * @param _lng - The i18next language code, ignored.
 * @returns Always `en`.
 */
export function resolveLang(_lng: string): Lang {
  return 'en'
}

/**
 * Picks the text for the given language, falling back to English when that language is empty.
 * @param text - The text in each available language.
 * @param lang - The language to show.
 * @returns The text in `lang`, or the English text when there is none.
 */
export function localized(text: LocalizedText, lang: Lang): string {
  return text[lang] || text.en
}
