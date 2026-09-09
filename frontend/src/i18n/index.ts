import { createI18n } from 'vue-i18n'

import en from './en.json'
import ru from './ru.json'
import sharedRefinementEn from './shared-refinement.en.json'
import sharedRefinementRu from './shared-refinement.ru.json'
import toolsRefinementEn from './tools-refinement.en.json'
import toolsRefinementRu from './tools-refinement.ru.json'

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
  messages: {
    en: { ...en, ...sharedRefinementEn, ...toolsRefinementEn },
    ru: { ...ru, ...sharedRefinementRu, ...toolsRefinementRu },
  },
})
