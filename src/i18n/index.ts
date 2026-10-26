import i18n from 'i18next'
import { initReactI18next } from 'react-i18next'
import en from './en'

const LANG_KEY = 'hub-czn.lang'

i18n.use(initReactI18next).init({
  resources: {
    en: { translation: en },
  },
  lng: 'en',
  fallbackLng: 'en',
  interpolation: { escapeValue: false },
})

// English is the only language. Overwrite any language saved by an older version, such as `pt-BR`.
try {
  localStorage.setItem(LANG_KEY, 'en')
} catch {
  // Storage can be unavailable, and the app still works without it.
}

export { LANG_KEY }
export default i18n
