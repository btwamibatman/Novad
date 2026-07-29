<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

import { usePreferences } from '@/composables/usePreferences'

const { t } = useI18n()
const { theme, toggleTheme } = usePreferences()
const icon = computed(() => (theme.value === 'dark' ? t('theme.sun') : t('theme.moon')))
</script>

<template>
  <button
    class="button icon-btn"
    type="button"
    :aria-label="t('theme.toggle')"
    :title="t('theme.toggle')"
    @click="toggleTheme"
  >
    <span>{{ icon }}</span>
  </button>
</template>
