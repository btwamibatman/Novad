<script setup lang="ts">
import { useI18n } from 'vue-i18n'

import DocumentTableRow from './DocumentTableRow.vue'
import { useApiErrorHandler } from '@/composables/useApiErrorHandler'
import { useToasts } from '@/composables/useToasts'
import { useDocumentsStore } from '@/stores/documents'

const { t } = useI18n()
const documentsStore = useDocumentsStore()
const { handle } = useApiErrorHandler()
const { show } = useToasts()

async function analyze(documentId: number): Promise<void> {
  try {
    await documentsStore.analyze(documentId)
    show(t('analysis.queued'), 'success')
  } catch (error) {
    handle(error)
  }
}

async function summarize(documentId: number): Promise<void> {
  try {
    await documentsStore.summarize(documentId)
    show(t('summary.generated'), 'success')
  } catch (error) {
    handle(error)
  }
}

async function remove(documentId: number): Promise<void> {
  if (!window.confirm(t('delete.confirm'))) {
    return
  }
  try {
    await documentsStore.remove(documentId)
    show(t('delete.completed'), 'success')
  } catch (error) {
    handle(error)
  }
}
</script>

<template>
  <article class="panel">
    <div class="panel-head">
      <h2 class="panel-title">{{ t('documents.title') }}</h2>
      <span class="muted">
        {{
          documentsStore.loading
            ? t('common.loading')
            : t('documents.shown', { count: documentsStore.filteredDocuments.length })
        }}
      </span>
    </div>
    <div class="panel-body">
      <div class="filters">
        <input
          v-model="documentsStore.search"
          class="field"
          :placeholder="t('documents.search_placeholder')"
          :aria-label="t('documents.search_label')"
        />
        <select
          v-model="documentsStore.statusFilter"
          class="select"
          :aria-label="t('documents.status_filter_label')"
        >
          <option value="all">{{ t('status.all') }}</option>
          <option value="uploaded">{{ t('status.uploaded') }}</option>
          <option value="analyzing">{{ t('status.analyzing') }}</option>
          <option value="processed">{{ t('status.processed') }}</option>
          <option value="failed">{{ t('status.failed') }}</option>
        </select>
      </div>
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>{{ t('documents.file') }}</th>
              <th>{{ t('documents.type') }}</th>
              <th>{{ t('documents.status') }}</th>
              <th>{{ t('documents.size') }}</th>
              <th>{{ t('documents.language') }}</th>
              <th>{{ t('documents.words') }}</th>
              <th>AI</th>
              <th>{{ t('documents.actions') }}</th>
            </tr>
          </thead>
          <tbody>
            <template v-if="documentsStore.loading && !documentsStore.documents.length">
              <tr v-for="index in 4" :key="index">
                <td colspan="8">
                  <div class="skeleton" style="height: 28px; border-radius: 6px"></div>
                </td>
              </tr>
            </template>
            <tr v-else-if="!documentsStore.filteredDocuments.length">
              <td colspan="8" class="muted">{{ t('documents.empty') }}</td>
            </tr>
            <DocumentTableRow
              v-for="document in documentsStore.filteredDocuments"
              v-else
              :key="document.id"
              :document="document"
              @analyze="analyze"
              @summarize="summarize"
              @remove="remove"
            />
          </tbody>
        </table>
      </div>
    </div>
  </article>
</template>
