import { ref } from 'vue'

import { i18n, supportedLocales, type AppLocale } from '@/i18n'

type Theme = 'dark' | 'light'

const storedTheme = localStorage.getItem('document-console-theme')
const theme = ref<Theme>(storedTheme === 'light' ? 'light' : 'dark')

function applyTheme(): void {
  document.documentElement.dataset.theme = theme.value
  localStorage.setItem('document-console-theme', theme.value)
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
    localStorage.setItem('document-console-language', locale)
  }

  return {
    theme,
    locale: i18n.global.locale,
    toggleTheme,
    setLocale,
  }
}
