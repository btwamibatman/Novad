<script setup lang="ts">
import { useI18n } from 'vue-i18n'

import DocumentWorkspace from '@/components/documents/DocumentWorkspace.vue'
import LanguagesPanel from '@/components/dashboard/LanguagesPanel.vue'
import MetricsGrid from '@/components/dashboard/MetricsGrid.vue'
import DocumentDetails from '@/components/documents/DocumentDetails.vue'
import DocumentTable from '@/components/documents/DocumentTable.vue'
import { useDocumentsStore } from '@/stores/documents'

const { t } = useI18n()
const documentsStore = useDocumentsStore()
</script>

<template>
  <main class="documents-page">
    <MetricsGrid />
    <DocumentTable />
    <p v-if="documentsStore.documents.length && !documentsStore.selectedDocument" class="selection-hint">
      {{ t('documents.selection_hint') }}
    </p>
    <section
      v-if="documentsStore.selectedDocument"
      id="document-selection"
      class="document-selection"
      tabindex="-1"
      :aria-label="t('details.title')"
    >
      <DocumentWorkspace />
      <DocumentDetails />
    </section>
    <LanguagesPanel />
  </main>
</template>

<style scoped>
.documents-page { display: grid; gap: 20px; }
.document-selection { display: grid; grid-template-columns: minmax(0, 1fr) minmax(300px, 360px); gap: 20px; scroll-margin-top: 20px; }
.document-selection > * { min-width: 0; }
.selection-hint { margin: 0; padding: 8px 4px; color: var(--text-soft); }
@media (max-width: 1000px) {
  .document-selection { grid-template-columns: 1fr; }
}
</style>
