import { createI18n } from 'vue-i18n'

import en from './en.json'
import ru from './ru.json'

export type AppLocale = 'en' | 'ru'

export const supportedLocales: AppLocale[] = ['en', 'ru']

function initialLocale(): AppLocale {
  const stored = localStorage.getItem('document-console-language')
  return supportedLocales.includes(stored as AppLocale) ? (stored as AppLocale) : 'en'
}

export const i18n = createI18n({
  legacy: false,
  locale: initialLocale(),
  fallbackLocale: 'en',
  messages: { en, ru },
})
