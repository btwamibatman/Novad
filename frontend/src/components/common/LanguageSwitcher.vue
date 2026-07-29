<script setup lang="ts">
import { useI18n } from 'vue-i18n'

import { supportedLocales, type AppLocale } from '@/i18n'
import { usePreferences } from '@/composables/usePreferences'

defineProps<{
  auth?: boolean
}>()

const { t } = useI18n()
const { locale, setLocale } = usePreferences()

function selectLocale(nextLocale: AppLocale): void {
  if (nextLocale !== locale.value) {
    setLocale(nextLocale)
  }
}
</script>

<template>
  <div
    class="language-switcher"
    :class="{ 'auth-languages': auth }"
    role="group"
    :aria-label="t('language.switcher_label')"
  >
    <button
      v-for="option in supportedLocales"
      :key="option"
      class="language-button"
      :class="{ active: locale === option }"
      type="button"
      :aria-pressed="locale === option"
      @click="selectLocale(option)"
    >
      {{ option === 'en' ? 'ENG' : 'RUS' }}
    </button>
  </div>
</template>
