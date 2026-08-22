<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink } from 'vue-router'

import { aiAnalysisApi } from '@/api/ai'
import { useApiErrorHandler } from '@/composables/useApiErrorHandler'
import { useToasts } from '@/composables/useToasts'
import { useDocumentsStore } from '@/stores/documents'

const { t } = useI18n()
const documentsStore = useDocumentsStore()
const { handle } = useApiErrorHandler()
const { show } = useToasts()
const providerInfo = ref<Awaited<ReturnType<typeof aiAnalysisApi.getProviderInfo>> | null>(null)
const providerInfoState = ref<'loading' | 'ready' | 'error'>('loading')
const document = computed(() => documentsStore.selectedDocument)
const isPdf = computed(() => document.value?.content_type === 'application/pdf')
const pending = computed(
  () =>
    document.value !== null &&
    documentsStore.isPending('layout-review', document.value.id),
)
const originalImagesAllowed = computed(
  () =>
    providerInfo.value !== null &&
    !(
      providerInfo.value.provider.toLowerCase() === 'gemini' &&
      providerInfo.value.service_tier === 'unpaid'
    ),
)
const protectedRoute = computed(() => ({
  name: 'tools',
  query: {
    task: 'layout_review',
    ...(document.value ? { document_id: String(document.value.id) } : {}),
  },
}))
const originalImagesMessage = computed(() => {
  if (providerInfoState.value === 'loading') return t('layout_review.provider_checking')
  if (providerInfoState.value === 'error') return t('layout_review.provider_unavailable')
  return t('layout_review.unpaid_original_blocked')
})
const state = computed(() => {
  if (!document.value) return t('common.no_document_selected')
  if (document.value.layout_review_error) return t('common.error')
  if (document.value.layout_review) {
    const meta = document.value.layout_review_meta
    return t('layout_review.state', {
      pages: meta.reviewed_pages?.join(', ') || t('common.reviewed'),
      coverage: meta.complete ? t('common.full') : t('common.sample'),
    })
  }
  return isPdf.value ? t('common.ready') : t('common.pdf_only')
})
const content = computed(
  () =>
    document.value?.layout_review ||
    document.value?.layout_review_error ||
    (isPdf.value
      ? t('layout_review.start')
      : document.value
        ? t('layout_review.pdf_only')
        : t('layout_review.select_pdf')),
)

async function review(): Promise<void> {
  if (
    !document.value ||
    !originalImagesAllowed.value ||
    !window.confirm(t('layout_review.consent_confirm'))
  ) {
    return
  }
  try {
    await documentsStore.reviewLayout(document.value.id)
    show(t('layout_review.completed'), 'success')
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

onMounted(async () => {
  try {
    providerInfo.value = await aiAnalysisApi.getProviderInfo()
    providerInfoState.value = 'ready'
  } catch {
    // Fail closed: the protected-copy route remains available without disclosure data.
    providerInfo.value = null
    providerInfoState.value = 'error'
  }
})
</script>

<template>
  <article class="panel">
    <div class="panel-head">
      <h2 class="panel-title">{{ t('layout_review.title') }}</h2>
      <span class="muted">{{ state }}</span>
    </div>
    <div class="panel-body">
      <p class="section-help">{{ t('layout_review.notice') }}</p>
      <div class="review-controls">
        <RouterLink class="button primary" :to="protectedRoute">
          {{ t('layout_review.protected_action') }}
        </RouterLink>
        <button
          v-if="originalImagesAllowed"
          class="button"
          :class="{ loading: pending }"
          type="button"
          :disabled="documentsStore.busy || !isPdf"
          :aria-busy="pending"
          @click="review"
        >
          {{ pending ? t('layout_review.reviewing') : t('layout_review.original_action') }}
        </button>
        <small v-else>{{ originalImagesMessage }}</small>
      </div>
      <p v-if="originalImagesAllowed" class="control-help">
        {{ t('layout_review.legacy_help') }}
      </p>
      <div class="preview">{{ content }}</div>
    </div>
  </article>
</template>
