<script setup lang="ts">
import { nextTick, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import DocumentTableRow from './DocumentTableRow.vue'
import DocumentUpload from './DocumentUpload.vue'
import { useApiErrorHandler } from '@/composables/useApiErrorHandler'
import { useToasts } from '@/composables/useToasts'
import { useDocumentsStore } from '@/stores/documents'

const { t } = useI18n()
const documentsStore = useDocumentsStore()
const { handle } = useApiErrorHandler()
const { show } = useToasts()
const uploadOpen = ref(false)
const uploadTrigger = ref<HTMLButtonElement | null>(null)

async function closeUpload(): Promise<void> {
  uploadOpen.value = false
  await nextTick()
  uploadTrigger.value?.focus()
}

async function reload(): Promise<void> {
  try {
    await documentsStore.load()
  } catch (error) {
    handle(error)
  }
}

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
  <article class="panel document-library" :aria-label="t('documents.title')" :aria-busy="documentsStore.loading">
    <div class="panel-head">
      <h2 class="panel-title">{{ t('documents.title') }}</h2>
      <span class="muted" role="status">
        {{
          documentsStore.loading
            ? t('common.loading')
            : t('documents.shown', { count: documentsStore.filteredDocuments.length })
        }}
      </span>
    </div>
    <div class="panel-body">
      <div class="library-toolbar">
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
        <button
          ref="uploadTrigger"
          class="button primary"
          type="button"
          :aria-expanded="uploadOpen"
          aria-controls="document-upload"
          @click="uploadOpen = !uploadOpen"
        >
          <span aria-hidden="true">＋</span> {{ t('upload.title') }}
        </button>
      </div>
      <DocumentUpload v-if="uploadOpen" id="document-upload" @close="closeUpload" />
      <div v-if="documentsStore.loadFailed" class="library-error" role="alert">
        <span>{{ t('documents.load_failed') }}</span>
        <button class="button small" type="button" :disabled="documentsStore.loading" @click="reload">{{ t('actions.refresh') }}</button>
      </div>
      <div class="table-wrap" role="region" :aria-label="t('documents.title')" tabindex="0">
        <table class="documents-table">
          <colgroup><col class="file-column" /><col class="status-column" /><col class="size-column" /><col class="date-column" /><col class="action-column" /></colgroup>
          <thead>
            <tr>
              <th scope="col">{{ t('documents.file') }}</th>
              <th scope="col">{{ t('documents.status') }}</th>
              <th scope="col">{{ t('documents.size') }}</th>
              <th scope="col">{{ t('documents.added') }}</th>
              <th scope="col">{{ t('documents.actions') }}</th>
            </tr>
          </thead>
          <tbody>
            <template v-if="documentsStore.loading && !documentsStore.documents.length">
              <tr v-for="index in 4" :key="index">
                <td colspan="5">
                  <div class="skeleton" style="height: 28px; border-radius: 6px"></div>
                </td>
              </tr>
            </template>
            <tr v-else-if="!documentsStore.filteredDocuments.length && !documentsStore.loadFailed">
              <td colspan="5" class="library-empty">
                <template v-if="documentsStore.documents.length">
                  <p>{{ t('documents.empty') }}</p>
                  <button class="button small" type="button" @click="documentsStore.search = ''; documentsStore.statusFilter = 'all'">{{ t('documents.clear_filters') }}</button>
                </template>
                <template v-else>
                  <strong>{{ t('documents.empty_title') }}</strong>
                  <p>{{ t('documents.empty_help') }}</p>
                </template>
              </td>
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

<style scoped>
.document-library .panel-head { background: transparent; border: 0; padding-bottom: 0; }
.document-library .panel-title { font-size: 22px; }
.library-toolbar { display: grid; grid-template-columns: minmax(160px, 1fr) 190px auto; gap: 12px; margin-bottom: 20px; }
.documents-table { table-layout: fixed; min-width: 920px; }
.file-column { width: auto; }
.status-column { width: 120px; }
.size-column { width: 85px; }
.date-column { width: 125px; }
.action-column { width: 200px; }
.library-empty { text-align: center; height: 200px; color: var(--text-soft); }
.library-empty strong { color: var(--text); font-size: 18px; }
.library-empty p { margin: 10px 0; }
.library-error { display: flex; flex-wrap: wrap; align-items: center; gap: 12px; color: var(--danger); margin-bottom: 16px; }
@media (max-width: 600px) {
  .library-toolbar { grid-template-columns: minmax(0, 1fr) auto; }
  .library-toolbar .field { grid-column: 1 / -1; }
}
</style>
