<script setup lang="ts">
import AnalysisPanel from '@/components/analysis/AnalysisPanel.vue'
import ContentReviewPanel from '@/components/analysis/ContentReviewPanel.vue'
import LayoutReviewPanel from '@/components/analysis/LayoutReviewPanel.vue'
import SummaryPanel from '@/components/analysis/SummaryPanel.vue'
import AIChatWindow from '@/components/chat/AIChatWindow.vue'
import LanguagesPanel from '@/components/dashboard/LanguagesPanel.vue'
import MetricsGrid from '@/components/dashboard/MetricsGrid.vue'
import DocumentDetails from '@/components/documents/DocumentDetails.vue'
import DocumentTable from '@/components/documents/DocumentTable.vue'
import DocumentUpload from '@/components/documents/DocumentUpload.vue'
import { useApiErrorHandler } from '@/composables/useApiErrorHandler'
import { useDocumentPolling } from '@/composables/useDocumentPolling'
import AppHeader from './AppHeader.vue'

const { handle } = useApiErrorHandler()

useDocumentPolling((error) => handle(error))
</script>

<template>
  <div class="shell">
    <AppHeader />
    <MetricsGrid />

    <main class="layout">
      <section class="main-column">
        <DocumentTable />
        <AnalysisPanel />
        <SummaryPanel />
        <ContentReviewPanel />
        <LayoutReviewPanel />
      </section>

      <aside class="side-column">
        <DocumentUpload />
        <DocumentDetails />
        <LanguagesPanel />
      </aside>
    </main>
  </div>

  <AIChatWindow />
</template>
