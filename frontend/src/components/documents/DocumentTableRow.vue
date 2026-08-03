<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

import { documentsApi } from '@/api/documents'
import { useDocumentsStore } from '@/stores/documents'
import type { DocumentRead } from '@/types/document'
import { aiState, documentLanguage } from '@/utils/documents'
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
const state = computed(() => aiState(props.document))
const aiClass = computed(() => {
  if (state.value === 'error') return 'failed'
  if (state.value === 'ready') return 'processed'
  return 'neutral'
})
const needsAnalysis = computed(() => ['uploaded', 'failed'].includes(props.document.status))

function select(): void {
  documentsStore.selectedId = props.document.id
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
      <p class="file-name">{{ document.filename }}</p>
      <span class="file-meta">
        #{{ document.id }}
        {{
          t('documents.created', {
            date: new Date(document.created_at).toLocaleString(locale),
          })
        }}
      </span>
    </td>
    <td>{{ document.content_type }}</td>
    <td>
      <span class="badge" :class="document.status">{{ t(`status.${document.status}`) }}</span>
    </td>
    <td>{{ formatBytes(document.size_bytes) }}</td>
    <td>{{ documentLanguage(document) }}</td>
    <td>{{ document.word_count || 0 }}</td>
    <td><span class="badge" :class="aiClass">{{ t(`ai.${state}`) }}</span></td>
    <td>
      <div class="row-actions" @click.stop>
        <button
          class="button small primary"
          :class="{ loading: documentsStore.isPending('analyze', document.id) }"
          type="button"
          :disabled="documentsStore.busy"
          :aria-busy="documentsStore.isPending('analyze', document.id)"
          @click="primaryAction"
        >
          {{
            needsAnalysis && documentsStore.isPending('analyze', document.id)
              ? t('documents.analyzing')
              : needsAnalysis
                ? t('documents.analyze')
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
              {{ t('documents.summarize') }}
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
