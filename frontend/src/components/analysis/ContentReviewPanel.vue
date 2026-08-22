<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink } from 'vue-router'

import MarkdownContent from '@/components/common/MarkdownContent.vue'
import { useApiErrorHandler } from '@/composables/useApiErrorHandler'
import { useToasts } from '@/composables/useToasts'
import { useDocumentsStore } from '@/stores/documents'
import type { ContentReviewMode } from '@/types/document'
import { qualityWarning } from '@/utils/documents'

const { t } = useI18n()
const documentsStore = useDocumentsStore()
const { handle } = useApiErrorHandler()
const { show } = useToasts()
const mode = ref<ContentReviewMode>('quick')
const document = computed(() => documentsStore.selectedDocument)
const warning = computed(() =>
  qualityWarning(document.value, (key, params) => t(key, params ?? {})),
)
const pending = computed(
  () =>
    document.value !== null &&
    documentsStore.isPending('content-review', document.value.id),
)
const protectedRoute = computed(() => ({
  name: 'tools',
  query: {
    task: 'content_review',
    ...(document.value ? { document_id: String(document.value.id) } : {}),
  },
}))
const state = computed(() => {
  if (!document.value) return t('common.no_document_selected')
  if (document.value.content_review_error) return t('common.error')
  if (document.value.content_review) {
    const meta = document.value.content_review_meta
    return t('content_review.state', {
      mode: t(`content_review.mode_${document.value.content_review_mode || 'review'}`),
      coverage: meta.complete ? t('common.full') : t('common.sample'),
      batches: meta.batch_count
        ? t('content_review.batches', { count: meta.batch_count })
        : '',
    })
  }
  return document.value.status === 'processed'
    ? t('common.ready')
    : t('common.analyze_first')
})
const content = computed(() => {
  const text =
    document.value?.content_review ||
    document.value?.content_review_error ||
    (document.value?.status === 'processed'
      ? t('content_review.start')
      : document.value
        ? t('summary.must_analyze')
        : t('content_review.analyze_first_help'))
  return warning.value ? `${warning.value}\n\n${text}` : text
})

async function review(): Promise<void> {
  if (!document.value) return
  try {
    await documentsStore.reviewContent(document.value.id, mode.value)
    show(t('content_review.completed'), 'success')
  } catch (error) {
    const handled = handle(error)
    if (!handled) {
      try {
        await documentsStore.load()
      } catch (refreshError) {
        handle(refreshError)
      }
    }
  }
}
</script>

<template>
  <article class="panel">
    <div class="panel-head">
      <h2 class="panel-title">{{ t('content_review.title') }}</h2>
      <span class="muted">{{ state }}</span>
    </div>
    <div class="panel-body">
      <p class="section-help">{{ t('content_review.notice') }}</p>
      <div class="review-controls">
        <RouterLink class="button primary" :to="protectedRoute">
          {{ t('content_review.protected_action') }}
        </RouterLink>
        <select
          v-model="mode"
          class="select"
          :aria-label="t('content_review.depth_label')"
          :disabled="documentsStore.busy"
        >
          <option value="quick">{{ t('content_review.quick_short') }}</option>
          <option value="thorough">{{ t('content_review.thorough_short') }}</option>
        </select>
        <button
          class="button"
          :class="{ loading: pending }"
          type="button"
          :disabled="documentsStore.busy || document?.status !== 'processed'"
          :aria-busy="pending"
          @click="review"
        >
          {{ pending ? t('content_review.reviewing') : t('content_review.legacy_action') }}
        </button>
      </div>
      <p class="control-help">
        {{ t('content_review.legacy_help') }} {{ t(`content_review.${mode}_help`) }}
      </p>
      <MarkdownContent :content="content" />
    </div>
  </article>
</template>
