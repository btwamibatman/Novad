<script setup lang="ts">
import { computed, nextTick } from 'vue'
import { useI18n } from 'vue-i18n'

import { documentsApi } from '@/api/documents'
import { useDocumentsStore } from '@/stores/documents'
import type { DocumentRead } from '@/types/document'
import { documentLanguage } from '@/utils/documents'
import { formatBytes } from '@/utils/format'

const props = defineProps<{
  document: DocumentRead
}>()

const emit = defineEmits<{
  analyze: [documentId: number]
  summarize: [documentId: number]
  remove: [documentId: number]
}>()

const { t, locale } = useI18n()
const documentsStore = useDocumentsStore()
const selected = computed(() => documentsStore.selectedId === props.document.id)
const needsAnalysis = computed(() => ['uploaded', 'failed'].includes(props.document.status))

async function select(): Promise<void> {
  documentsStore.selectedId = props.document.id
  await nextTick()
  window.document.getElementById('document-selection')?.focus({ preventScroll: true })
}

function download(): void {
  window.location.href = documentsApi.downloadUrl(props.document.id)
}

function primaryAction(): void {
  if (needsAnalysis.value) {
    emit('analyze', props.document.id)
  } else {
    select()
  }
}
</script>

<template>
  <tr
    :data-document-id="document.id"
    :data-selected="selected"
    @click="select"
  >
    <td>
      <button class="file-name file-select" type="button" :aria-expanded="selected" aria-controls="document-selection" @click.stop="select">
        {{ document.filename }}
      </button>
      <span v-if="document.detected_language || Object.keys(document.language_distribution).length" class="file-language">{{ documentLanguage(document, locale) }}</span>
    </td>
    <td>
      <span class="badge" :class="document.status">{{ t(`status.${document.status}`) }}</span>
    </td>
    <td>{{ formatBytes(document.size_bytes) }}</td>
    <td><time :datetime="document.created_at" :title="new Date(document.created_at).toLocaleString(locale)">{{ new Date(document.created_at).toLocaleDateString(locale, { day: 'numeric', month: 'short', year: 'numeric' }) }}</time></td>
    <td>
      <div class="row-actions" @click.stop>
        <button
          class="button small"
          :class="{ loading: documentsStore.isPending('analyze', document.id) }"
          type="button"
          :disabled="documentsStore.busy"
          :aria-busy="documentsStore.isPending('analyze', document.id)"
          @click="primaryAction"
        >
          {{
            needsAnalysis && documentsStore.isPending('analyze', document.id)
              ? t('documents.analyzing')
              : document.status === 'failed'
                ? t('documents.retry_analysis')
                : needsAnalysis
                  ? t('documents.analyze')
                  : document.status === 'analyzing'
                    ? t('documents.view_progress')
                    : t('documents.open_result')
          }}
        </button>
        <details class="row-menu">
          <summary class="icon-btn small" role="button" :aria-label="t('documents.more')">⋯</summary>
          <div class="row-menu-popover">
            <button
              class="menu-action"
              type="button"
              :disabled="documentsStore.busy || document.status !== 'processed'"
              @click="emit('summarize', document.id)"
            >
              {{ t('summary.legacy_action') }}
            </button>
            <button class="menu-action" type="button" :disabled="documentsStore.busy" @click="download">
              {{ t('documents.download') }}
            </button>
            <button
              class="menu-action danger-text"
              type="button"
              :disabled="documentsStore.busy"
              @click="emit('remove', document.id)"
            >
              {{ t('documents.delete') }}
            </button>
          </div>
        </details>
      </div>
    </td>
  </tr>
</template>

<style scoped>
.file-select { display: block; border: 0; padding: 2px 0; background: transparent; color: var(--text); text-align: left; overflow-wrap: anywhere; line-height: 1.5; }
.file-select:hover { text-decoration: underline; text-underline-offset: 3px; }
.file-language { display: block; color: var(--text-soft); margin-top: 4px; font-size: 14px; }
td { padding-top: 16px; padding-bottom: 16px; }
time { color: var(--text-soft); font-size: 14px; }
.row-actions { flex-wrap: nowrap; align-items: start; }
</style>
