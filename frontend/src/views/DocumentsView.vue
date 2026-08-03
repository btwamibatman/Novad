<script setup lang="ts">
import DocumentWorkspace from '@/components/documents/DocumentWorkspace.vue'
import LanguagesPanel from '@/components/dashboard/LanguagesPanel.vue'
import MetricsGrid from '@/components/dashboard/MetricsGrid.vue'
import DocumentDetails from '@/components/documents/DocumentDetails.vue'
import DocumentTable from '@/components/documents/DocumentTable.vue'
import DocumentUpload from '@/components/documents/DocumentUpload.vue'
</script>

<template>
  <MetricsGrid />
  <main class="layout">
    <section class="main-column">
      <DocumentTable />
      <DocumentWorkspace />
    </section>
    <aside class="side-column">
      <DocumentUpload />
      <DocumentDetails />
      <LanguagesPanel />
    </aside>
  </main>
</template>
