<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import AnalysisPanel from '@/components/analysis/AnalysisPanel.vue'
import ContentReviewPanel from '@/components/analysis/ContentReviewPanel.vue'
import LayoutReviewPanel from '@/components/analysis/LayoutReviewPanel.vue'
import SummaryPanel from '@/components/analysis/SummaryPanel.vue'
import { useDocumentsStore } from '@/stores/documents'

type Tab = 'analysis' | 'summary' | 'content' | 'layout'

const { t } = useI18n()
const documentsStore = useDocumentsStore()
const active = ref<Tab>('analysis')
const document = computed(() => documentsStore.selectedDocument)

watch(
  () => documentsStore.selectedId,
  () => {
    active.value = 'analysis'
  },
)

const tabs: Tab[] = ['analysis', 'summary', 'content', 'layout']
</script>

<template>
  <section v-if="document" class="document-workspace" aria-live="polite">
    <div class="workspace-head">
      <div>
        <span class="eyebrow">{{ t('workspace.title') }}</span>
        <h2>{{ document.filename }}</h2>
      </div>
      <span class="badge" :class="document.status">{{ t(`status.${document.status}`) }}</span>
    </div>
    <div class="workspace-tabs" role="tablist" :aria-label="t('workspace.tabs')">
      <button
        v-for="tab in tabs"
        :key="tab"
        class="workspace-tab"
        :class="{ active: active === tab }"
        type="button"
        role="tab"
        :aria-selected="active === tab"
        @click="active = tab"
      >
        {{ t(`workspace.${tab}`) }}
      </button>
    </div>
    <AnalysisPanel v-if="active === 'analysis'" />
    <SummaryPanel v-else-if="active === 'summary'" />
    <ContentReviewPanel v-else-if="active === 'content'" />
    <LayoutReviewPanel v-else />
  </section>
  <div v-else class="compact-empty">{{ t('workspace.select') }}</div>
</template>
