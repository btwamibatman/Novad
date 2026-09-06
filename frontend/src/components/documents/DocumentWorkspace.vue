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

function navigateTabs(event: KeyboardEvent, index: number): void {
  let next = index
  if (event.key === 'ArrowRight') next = (index + 1) % tabs.length
  else if (event.key === 'ArrowLeft') next = (index + tabs.length - 1) % tabs.length
  else if (event.key === 'Home') next = 0
  else if (event.key === 'End') next = tabs.length - 1
  else return
  event.preventDefault()
  active.value = tabs[next]!
  const buttons = (event.currentTarget as HTMLElement).parentElement?.querySelectorAll<HTMLButtonElement>('[role="tab"]')
  buttons?.[next]?.focus()
}
</script>

<template>
  <section v-if="document" class="document-workspace" :aria-label="document.filename">
    <div class="workspace-head">
      <div>
        <h2>{{ document.filename }}</h2>
      </div>
      <span class="badge" :class="document.status">{{ t(`status.${document.status}`) }}</span>
    </div>
    <div class="workspace-tabs" role="tablist" :aria-label="t('workspace.tabs')">
      <button
        v-for="(tab, index) in tabs"
        :key="tab"
        class="workspace-tab"
        :class="{ active: active === tab }"
        type="button"
        role="tab"
        :id="`workspace-tab-${tab}`"
        :aria-controls="`workspace-panel-${tab}`"
        :aria-selected="active === tab"
        :tabindex="active === tab ? 0 : -1"
        @keydown="navigateTabs($event, index)"
        @click="active = tab"
      >
        {{ t(`workspace.${tab}`) }}
      </button>
    </div>
    <div :id="`workspace-panel-${active}`" role="tabpanel" :aria-labelledby="`workspace-tab-${active}`" tabindex="0">
      <AnalysisPanel v-if="active === 'analysis'" />
      <SummaryPanel v-else-if="active === 'summary'" />
      <ContentReviewPanel v-else-if="active === 'content'" />
      <LayoutReviewPanel v-else />
    </div>
  </section>
</template>

<style scoped>
.workspace-head { align-items: start; }
.workspace-head > div { min-width: 0; }
.workspace-head h2 { font-size: 20px; line-height: 1.5; overflow-wrap: anywhere; }
[role="tabpanel"] :deep(> .panel) { border: 0; border-radius: 0; box-shadow: none; }
[role="tabpanel"] :deep(.preview) { border: 0; background: transparent; padding: 0; }
</style>
