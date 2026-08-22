<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink } from 'vue-router'

import { useDocumentsStore } from '@/stores/documents'
import { useApiErrorHandler } from '@/composables/useApiErrorHandler'
import { useToasts } from '@/composables/useToasts'
import { qualityWarning } from '@/utils/documents'

const { t } = useI18n()
const documentsStore = useDocumentsStore()
const { handle } = useApiErrorHandler()
const { show } = useToasts()
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
const pending = computed(
  () => document.value !== null && documentsStore.isPending('summarize', document.value.id),
)
const protectedRoute = computed(() => ({
  name: 'tools',
  query: {
    task: 'summary',
    ...(document.value ? { document_id: String(document.value.id) } : {}),
  },
}))

async function summarize(): Promise<void> {
  if (!document.value) return
  try {
    await documentsStore.summarize(document.value.id)
    show(t('summary.generated'), 'success')
  } catch (error) {
    handle(error)
  }
}
</script>

<template>
  <article class="panel">
    <div class="panel-head">
      <h2 class="panel-title">{{ t('summary.title') }}</h2>
      <span class="muted">{{ state }}</span>
    </div>
    <div class="panel-body">
      <p class="section-help">{{ t('summary.notice') }}</p>
      <div class="review-controls">
        <RouterLink class="button primary" :to="protectedRoute">
          {{ t('summary.protected_action') }}
        </RouterLink>
        <button
          v-if="!document?.ai_summary"
          class="button"
          type="button"
          :class="{ loading: pending }"
          :disabled="documentsStore.busy || document?.status !== 'processed'"
          @click="summarize"
        >
          {{ pending ? t('documents.summarizing') : t('summary.legacy_action') }}
        </button>
      </div>
      <p class="control-help">{{ t('summary.legacy_help') }}</p>
      <div class="preview">{{ summary }}</div>
    </div>
  </article>
</template>
