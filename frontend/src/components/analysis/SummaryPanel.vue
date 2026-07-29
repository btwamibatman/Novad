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
  if (document.value.ai_error) return t('common.error')
  if (document.value.ai_summary) return document.value.ai_model || t('common.generated')
  return document.value.status === 'processed'
    ? t('common.ready')
    : t('common.analyze_first')
})
const summary = computed(() => {
  const text =
    document.value?.ai_summary ||
    document.value?.ai_error ||
    (document.value?.status === 'processed'
      ? t('summary.not_generated')
      : document.value
        ? t('summary.must_analyze')
        : t('summary.analyze_first_help'))
  return warning.value ? `${warning.value}\n\n${text}` : text
})
</script>

<template>
  <article class="panel">
    <div class="panel-head">
      <h2 class="panel-title">{{ t('summary.title') }}</h2>
      <span class="muted">{{ state }}</span>
    </div>
    <div class="panel-body">
      <div class="notice">{{ t('summary.notice') }}</div>
      <div class="preview">{{ summary }}</div>
    </div>
  </article>
</template>
