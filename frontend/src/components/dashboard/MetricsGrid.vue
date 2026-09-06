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
  <dl class="summary-row" :aria-label="t('metrics.label')">
    <div class="summary-item"><dt>{{ t('metrics.documents') }}</dt><dd>{{ total }}</dd></div>
    <div class="summary-item"><dt>{{ t('metrics.processed') }}</dt><dd>{{ processed }}</dd></div>
    <div class="summary-item"><dt>{{ t('metrics.failed') }}</dt><dd>{{ failed }}</dd></div>
    <div class="summary-item"><dt>{{ t('metrics.storage') }}</dt><dd>{{ storage }}</dd></div>
  </dl>
</template>

<style scoped>
.summary-row { display: flex; flex-wrap: wrap; gap: 12px 32px; margin: 0; padding: 8px 0 16px; border-bottom: 1px solid var(--border-soft); }
.summary-item { display: flex; align-items: baseline; gap: 10px; }
dt { color: var(--text-soft); font-size: 14px; }
dd { margin: 0; font-weight: 650; font-size: 18px; font-variant-numeric: tabular-nums; }
@media (max-width: 520px) { .summary-row { display: grid; grid-template-columns: 1fr 1fr; gap: 12px 20px; } }
</style>
