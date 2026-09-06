<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink } from 'vue-router'

import { useDocumentsStore } from '@/stores/documents'
import { aiState, documentLanguage } from '@/utils/documents'
import { formatBytes, languageName } from '@/utils/format'

const { t, te, locale } = useI18n()
const documentsStore = useDocumentsStore()
const document = computed(() => documentsStore.selectedDocument)
const state = computed(() => (document.value ? aiState(document.value) : 'none'))
const languageShares = computed(() => Object.entries(document.value?.language_distribution ?? {})
  .filter(([, share]) => share > 0).sort((a, b) => b[1] - a[1]))
const progress = computed(() => {
  if (document.value?.status !== 'analyzing') {
    return ''
  }
  const value = document.value.analysis_progress
  return t('analysis.progress', {
    completed: value.completed_pages ?? 0,
    total: value.total_pages ?? '?',
    stage: te(`tools.stage.${value.stage}`) ? t(`tools.stage.${value.stage}`) : t('status.analyzing'),
  })
})
</script>

<template>
  <aside v-if="document" class="panel document-details" :aria-label="t('details.title')">
    <div class="panel-head">
      <h2 class="panel-title">{{ t('details.title') }}</h2>
    </div>
    <div class="panel-body">
      <RouterLink class="button tools-link" :to="{ name: 'tools', query: { document_id: String(document.id) } }">{{ t('details.open_tools') }} <span aria-hidden="true">→</span></RouterLink>
      <div class="detail-grid">
        <div class="detail-row">
          <span class="detail-label">{{ t('details.status') }}</span>
          <span><span class="badge" :class="document.status">{{ t(`status.${document.status}`) }}</span></span>
        </div>
        <div v-if="progress" class="detail-row">
          <span class="detail-label">{{ t('analysis.title') }}</span>
          <span>{{ progress }}</span>
        </div>
        <div class="detail-row">
          <span class="detail-label">{{ t('details.size') }}</span>
          <span>{{ formatBytes(document.size_bytes) }}</span>
        </div>
        <div class="detail-row">
          <span class="detail-label">{{ t('details.language') }}</span>
          <span>{{ documentLanguage(document, locale) }}</span>
        </div>
        <div v-if="languageShares.length" class="language-shares">
          <span class="detail-label">{{ t('details.language_share') }}</span>
          <ul>
            <li v-for="[language, share] in languageShares" :key="language"><span>{{ languageName(language, locale) }}</span><span>{{ Math.round(share * 100) }}%</span></li>
          </ul>
          <p class="control-help">{{ t('details.language_share_help') }}</p>
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
          <span class="detail-label">{{ t('details.ai_results') }}</span>
          <span>{{ t(`details.ai_${state}`) }}</span>
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
        <details class="technical-details">
          <summary>{{ t('details.technical') }}</summary>
          <div class="detail-row"><span class="detail-label">{{ t('details.id') }}</span><span>#{{ document.id }}</span></div>
          <div class="detail-row"><span class="detail-label">{{ t('details.type') }}</span><span>{{ document.content_type }}</span></div>
        </details>
      </div>
    </div>
  </aside>
</template>

<style scoped>
.document-details { align-self: start; }
.document-details .panel-head { background: transparent; }
.detail-row { grid-template-columns: minmax(100px, 0.85fr) minmax(0, 1fr); }
.detail-row > span { overflow-wrap: anywhere; }
.detail-grid { gap: 16px; }
.tools-link { margin-bottom: 24px; width: 100%; }
.language-shares { padding: 16px 0; border-block: 1px solid var(--border-soft); }
.language-shares ul { list-style: none; margin: 8px 0; padding: 0; }
.language-shares li { display: flex; justify-content: space-between; gap: 12px; }
.language-shares p { margin: 8px 0 0; }
.technical-details { padding-top: 16px; border-top: 1px solid var(--border-soft); }
.technical-details summary { color: var(--text-soft); cursor: pointer; }
.technical-details .detail-row { margin-top: 12px; }
</style>
