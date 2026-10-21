import { ref } from 'vue'

import { i18n, supportedLocales, type AppLocale } from '@/i18n'
import { readStoredValue, writeStoredValue } from '@/utils/storage'

type Theme = 'dark' | 'light'

const storedTheme = readStoredValue('document-console-theme')
const theme = ref<Theme>(storedTheme === 'light' ? 'light' : 'dark')

function applyTheme(): void {
  document.documentElement.dataset.theme = theme.value
  writeStoredValue('document-console-theme', theme.value)
}

applyTheme()

export function usePreferences() {
  function toggleTheme(): void {
    theme.value = theme.value === 'dark' ? 'light' : 'dark'
    applyTheme()
  }

  function setLocale(locale: AppLocale): void {
    if (!supportedLocales.includes(locale)) {
      return
    }
    i18n.global.locale.value = locale
    document.documentElement.lang = locale
    writeStoredValue('document-console-language', locale)
  }

  return {
    theme,
    locale: i18n.global.locale,
    toggleTheme,
    setLocale,
  }
}
