<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

import { useDocumentsStore } from '@/stores/documents'
import { formatBytes } from '@/utils/format'

const { t } = useI18n()
const documentsStore = useDocumentsStore()

const total = computed(
  () => documentsStore.summary?.total_documents ?? documentsStore.documents.length,
)
const processed = computed(
  () =>
    documentsStore.summary?.processed_documents ??
    documentsStore.documents.filter((document) => document.status === 'processed').length,
)
const failed = computed(
  () =>
    documentsStore.summary?.failed_documents ??
    documentsStore.documents.filter((document) => document.status === 'failed').length,
)
const storage = computed(() => formatBytes(documentsStore.summary?.storage_bytes ?? 0))
</script>

<template>
  <section class="metrics" :aria-label="t('metrics.label')">
    <article class="metric">
      <p class="metric-label">{{ t('metrics.documents') }}</p>
      <p class="metric-value">{{ total }}</p>
    </article>
    <article class="metric">
      <p class="metric-label">{{ t('metrics.processed') }}</p>
      <p class="metric-value">{{ processed }}</p>
    </article>
    <article class="metric">
      <p class="metric-label">{{ t('metrics.failed') }}</p>
      <p class="metric-value">{{ failed }}</p>
    </article>
    <article class="metric">
      <p class="metric-label">{{ t('metrics.storage') }}</p>
      <p class="metric-value">{{ storage }}</p>
    </article>
  </section>
</template>
