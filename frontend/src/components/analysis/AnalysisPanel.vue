<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

import { useDocumentsStore } from '@/stores/documents'
import { useApiErrorHandler } from '@/composables/useApiErrorHandler'
import { analysisStage } from '@/utils/documents'

const { t } = useI18n()
const documentsStore = useDocumentsStore()
const { handle } = useApiErrorHandler()
const document = computed(() => documentsStore.selectedDocument)
const state = computed(() => {
  if (!document.value) return t('common.no_document_selected')
  return document.value.status === 'uploaded'
    ? t('status.uploaded')
    : t(`analysis.stage.${analysisStage(document.value)}`)
})
const text = computed(
  () =>
    document.value?.extracted_text ||
    (document.value ? t('analysis.run') : t('analysis.select_processed')),
)
const progress = computed(() => document.value?.analysis_progress)

async function retry(): Promise<void> {
  if (!document.value) return
  try {
    await documentsStore.analyze(document.value.id)
  } catch (error) {
    handle(error)
  }
}
</script>

<template>
  <article class="panel">
    <div class="panel-head">
      <h2 class="panel-title">{{ t('analysis.title') }}</h2>
      <span class="muted">{{ state }}</span>
    </div>
    <div class="panel-body">
      <div v-if="document?.status === 'analyzing'" role="status" aria-live="polite">
        <p>{{ state }}</p>
        <p v-if="progress?.total_pages" class="muted">
          {{ t('analysis.pages', { completed: progress.completed_pages ?? 0, total: progress.total_pages }) }}
        </p>
        <p v-if="progress?.stage === 'queued'" class="muted">{{ t('analysis.waiting') }}</p>
      </div>
      <div v-else-if="document?.status === 'failed'" role="alert">
        <p>{{ document.error_message || t('analysis.failed') }}</p>
        <p class="muted">{{ t('analysis.file_saved') }}</p>
        <button class="button" type="button" :disabled="documentsStore.busy" @click="retry">
          {{ t('analysis.retry') }}
        </button>
      </div>
      <div v-else class="preview">{{ text }}</div>
    </div>
  </article>
</template>
