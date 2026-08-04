<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

import { useDocumentsStore } from '@/stores/documents'
import { aiState, documentLanguage } from '@/utils/documents'
import { formatBytes } from '@/utils/format'

const { t, locale } = useI18n()
const documentsStore = useDocumentsStore()
const document = computed(() => documentsStore.selectedDocument)
const state = computed(() => (document.value ? aiState(document.value) : 'none'))
const aiClass = computed(() => {
  if (state.value === 'error') return 'failed'
  if (state.value === 'ready') return 'processed'
  return 'uploaded'
})
const progress = computed(() => {
  if (document.value?.status !== 'analyzing') {
    return ''
  }
  const value = document.value.analysis_progress
  return t('analysis.progress', {
    completed: value.completed_pages ?? 0,
    total: value.total_pages ?? '?',
    stage: value.stage || 'queued',
  })
})
</script>

<template>
  <article class="panel">
    <div class="panel-head">
      <h2 class="panel-title">{{ t('details.title') }}</h2>
      <span class="muted">{{ document ? `#${document.id}` : t('common.none') }}</span>
    </div>
    <div class="panel-body">
      <div v-if="!document" class="empty">{{ t('details.select_document') }}</div>
      <div v-else class="detail-grid">
        <div class="detail-row">
          <span class="detail-label">{{ t('details.filename') }}</span>
          <span>{{ document.filename }}</span>
        </div>
        <div class="detail-row">
          <span class="detail-label">{{ t('details.status') }}</span>
          <span><span class="badge" :class="document.status">{{ t(`status.${document.status}`) }}</span></span>
        </div>
        <div v-if="progress" class="detail-row">
          <span class="detail-label">{{ t('analysis.title') }}</span>
          <span>{{ progress }}</span>
        </div>
        <div class="detail-row">
          <span class="detail-label">{{ t('details.type') }}</span>
          <span>{{ document.content_type }}</span>
        </div>
        <div class="detail-row">
          <span class="detail-label">{{ t('details.size') }}</span>
          <span>{{ formatBytes(document.size_bytes) }}</span>
        </div>
        <div class="detail-row">
          <span class="detail-label">{{ t('details.language') }}</span>
          <span>{{ documentLanguage(document) }}</span>
        </div>
        <div class="detail-row">
          <span class="detail-label">{{ t('details.words') }}</span>
          <span>{{ document.word_count || 0 }}</span>
        </div>
        <div class="detail-row">
          <span class="detail-label">{{ t('details.characters') }}</span>
          <span>{{ document.char_count || 0 }}</span>
        </div>
        <div v-if="document.status === 'processed'" class="detail-row">
          <span class="detail-label">{{ t('details.text_quality') }}</span>
          <span>{{ t(`quality.${document.extraction_quality}`) }}</span>
        </div>
        <div class="detail-row">
          <span class="detail-label">AI</span>
          <span><span class="badge" :class="aiClass">{{ t(`ai.${state}`) }}</span></span>
        </div>
        <div class="detail-row">
          <span class="detail-label">{{ t('details.updated') }}</span>
          <span>{{ new Date(document.updated_at).toLocaleString(locale) }}</span>
        </div>
        <div v-if="document.error_message" class="detail-row">
          <span class="detail-label">{{ t('details.error') }}</span>
          <span>{{ document.error_message }}</span>
        </div>
        <div v-if="document.ai_error" class="detail-row">
          <span class="detail-label">{{ t('details.ai_error') }}</span>
          <span>{{ document.ai_error }}</span>
        </div>
        <div v-if="document.content_review_error" class="detail-row">
          <span class="detail-label">{{ t('details.content_review') }}</span>
          <span>{{ document.content_review_error }}</span>
        </div>
        <div v-if="document.layout_review_error" class="detail-row">
          <span class="detail-label">{{ t('details.layout_review') }}</span>
          <span>{{ document.layout_review_error }}</span>
        </div>
      </div>
    </div>
  </article>
</template>
