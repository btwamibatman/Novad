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
  return 'uploaded'
})

function select(): void {
  documentsStore.selectedId = props.document.id
}

function download(): void {
  window.location.href = documentsApi.downloadUrl(props.document.id)
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
          class="button small"
          type="button"
          :disabled="documentsStore.busy"
          @click="select"
        >
          {{ t('documents.open') }}
        </button>
        <button
          class="button small"
          :class="{ loading: documentsStore.isPending('analyze', document.id) }"
          type="button"
          :disabled="documentsStore.busy"
          :aria-busy="documentsStore.isPending('analyze', document.id)"
          @click="emit('analyze', document.id)"
        >
          {{
            documentsStore.isPending('analyze', document.id)
              ? t('documents.analyzing')
              : t('documents.analyze')
          }}
        </button>
        <button
          class="button small"
          :class="{ loading: documentsStore.isPending('summarize', document.id) }"
          type="button"
          :disabled="documentsStore.busy || document.status !== 'processed'"
          :aria-busy="documentsStore.isPending('summarize', document.id)"
          @click="emit('summarize', document.id)"
        >
          {{
            documentsStore.isPending('summarize', document.id)
              ? t('documents.summarizing')
              : t('documents.summarize')
          }}
        </button>
        <button
          class="button small"
          type="button"
          :disabled="documentsStore.busy"
          @click="download"
        >
          {{ t('documents.download') }}
        </button>
        <button
          class="button small danger"
          :class="{ loading: documentsStore.isPending('delete', document.id) }"
          type="button"
          :disabled="documentsStore.busy"
          :aria-busy="documentsStore.isPending('delete', document.id)"
          @click="emit('remove', document.id)"
        >
          {{
            documentsStore.isPending('delete', document.id)
              ? t('documents.deleting')
              : t('documents.delete')
          }}
        </button>
      </div>
    </td>
  </tr>
</template>
