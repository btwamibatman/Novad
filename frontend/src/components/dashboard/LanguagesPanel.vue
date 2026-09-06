<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

import { useDocumentsStore } from '@/stores/documents'
import { formatNumber, languageName } from '@/utils/format'

const { t, locale } = useI18n()
const documentsStore = useDocumentsStore()
const languages = computed(() =>
  Object.entries(documentsStore.summary?.detected_languages ?? {}).sort(
    (a, b) => b[1] - a[1],
  ),
)
</script>

<template>
  <details class="language-overview">
    <summary>{{ t('languages.title') }}</summary>
    <div class="language-overview-body">
      <div class="language-list">
        <span v-if="!languages.length" class="muted">{{ t('languages.empty') }}</span>
        <span
          v-for="[language, count] in languages"
          :key="language"
          class="language-total"
        >
          {{ languageName(language, locale) }} · {{ formatNumber(count) }}
        </span>
      </div>
      <p v-if="languages.length" class="control-help">{{ t('languages.shares_help') }}</p>
    </div>
  </details>
</template>

<style scoped>
.language-overview { border-top: 1px solid var(--border-soft); padding-top: 16px; color: var(--text-soft); }
summary { cursor: pointer; width: fit-content; }
.language-overview-body { padding-top: 12px; }
.language-total { font-size: 14px; }
.control-help { margin: 8px 0 0; }
</style>
