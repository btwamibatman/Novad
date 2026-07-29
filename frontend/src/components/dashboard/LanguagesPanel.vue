<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

import { useDocumentsStore } from '@/stores/documents'
import { formatNumber } from '@/utils/format'

const { t } = useI18n()
const documentsStore = useDocumentsStore()
const languages = computed(() =>
  Object.entries(documentsStore.summary?.detected_languages ?? {}).sort(
    (a, b) => b[1] - a[1],
  ),
)
</script>

<template>
  <article class="panel">
    <div class="panel-head">
      <h2 class="panel-title">{{ t('languages.title') }}</h2>
    </div>
    <div class="panel-body">
      <div class="language-list">
        <span v-if="!languages.length" class="muted">{{ t('languages.empty') }}</span>
        <span
          v-for="[language, count] in languages"
          :key="language"
          class="badge processed"
        >
          {{ language }} {{ formatNumber(count) }}
        </span>
      </div>
    </div>
  </article>
</template>
