<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

import { useDocumentsStore } from '@/stores/documents'
import { qualityWarning } from '@/utils/documents'

const { t } = useI18n()
const documentsStore = useDocumentsStore()
const document = computed(() => documentsStore.selectedDocument)
const warning = computed(() =>
  qualityWarning(document.value, (key, params) => t(key, params ?? {})),
)
const state = computed(() => {
  if (!document.value) return t('common.no_document_selected')
  return document.value.status === 'processed'
    ? t('analysis.extracted_text')
    : t(`status.${document.value.status}`)
})
const text = computed(
  () =>
    document.value?.extracted_text ||
    (document.value ? t('analysis.run') : t('analysis.select_processed')),
)
</script>

<template>
  <article class="panel">
    <div class="panel-head">
      <h2 class="panel-title">{{ t('analysis.title') }}</h2>
      <span class="muted">{{ state }}</span>
    </div>
    <div class="panel-body">
      <div v-if="warning" class="notice">{{ warning }}</div>
      <div class="preview">{{ text }}</div>
    </div>
  </article>
</template>
