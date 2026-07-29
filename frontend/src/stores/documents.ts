import { computed, ref } from 'vue'
import { defineStore } from 'pinia'

import { dashboardApi } from '@/api/dashboard'
import { documentsApi } from '@/api/documents'
import { useAuthStore } from '@/stores/auth'
import type {
  ContentReviewMode,
  DashboardSummary,
  DocumentRead,
  DocumentStatus,
} from '@/types/document'

export interface PendingAction {
  action: string
  documentId: number | null
}

export const useDocumentsStore = defineStore('documents', () => {
  const documents = ref<DocumentRead[]>([])
  const summary = ref<DashboardSummary | null>(null)
  const selectedId = ref<number | null>(null)
  const search = ref('')
  const statusFilter = ref<'all' | DocumentStatus>('all')
  const loading = ref(false)
  const pendingAction = ref<PendingAction | null>(null)

  const selectedDocument = computed(
    () => documents.value.find((document) => document.id === selectedId.value) ?? null,
  )
  const processedDocuments = computed(() =>
    documents.value.filter((document) => document.status === 'processed'),
  )
  const filteredDocuments = computed(() => {
    const query = search.value.trim().toLocaleLowerCase()
    return documents.value.filter((document) => {
      const matchesStatus =
        statusFilter.value === 'all' || document.status === statusFilter.value
      const matchesSearch =
        !query ||
        [
          document.filename,
          document.content_type,
          document.detected_language,
          document.status,
          document.ai_summary,
          document.content_review,
          document.layout_review,
        ].some((value) => String(value ?? '').toLocaleLowerCase().includes(query))
      return matchesStatus && matchesSearch
    })
  })
  const busy = computed(() => loading.value || pendingAction.value !== null)

  function isPending(action: string, documentId: number | null = null): boolean {
    return (
      pendingAction.value?.action === action &&
      (documentId === null || pendingAction.value.documentId === documentId)
    )
  }

  async function load(refreshSession = true): Promise<void> {
    loading.value = true
    try {
      if (refreshSession) {
        await useAuthStore().checkSession()
      }
      const [nextSummary, nextDocuments] = await Promise.all([
        dashboardApi.summary(),
        documentsApi.list(),
      ])
      summary.value = nextSummary
      documents.value = nextDocuments
      if (
        selectedId.value !== null &&
        !documents.value.some((document) => document.id === selectedId.value)
      ) {
        selectedId.value = null
      }
    } finally {
      loading.value = false
    }
  }

  async function runDocumentAction(
    action: string,
    documentId: number,
    request: () => Promise<DocumentRead>,
  ): Promise<DocumentRead> {
    pendingAction.value = { action, documentId }
    try {
      const updated = await request()
      selectedId.value = updated.id
      await load()
      return updated
    } finally {
      pendingAction.value = null
    }
  }

  async function upload(file: File): Promise<DocumentRead> {
    pendingAction.value = { action: 'upload', documentId: null }
    try {
      const created = await documentsApi.upload(file)
      selectedId.value = created.id
      await load()
      return created
    } finally {
      pendingAction.value = null
    }
  }

  function analyze(documentId: number): Promise<DocumentRead> {
    return runDocumentAction('analyze', documentId, () => documentsApi.analyze(documentId))
  }

  function summarize(documentId: number): Promise<DocumentRead> {
    return runDocumentAction('summarize', documentId, () =>
      documentsApi.summarize(documentId),
    )
  }

  function reviewContent(
    documentId: number,
    mode: ContentReviewMode,
  ): Promise<DocumentRead> {
    return runDocumentAction('content-review', documentId, () =>
      documentsApi.reviewContent(documentId, mode),
    )
  }

  function reviewLayout(documentId: number): Promise<DocumentRead> {
    return runDocumentAction('layout-review', documentId, () =>
      documentsApi.reviewLayout(documentId),
    )
  }

  async function remove(documentId: number): Promise<void> {
    pendingAction.value = { action: 'delete', documentId }
    try {
      await documentsApi.remove(documentId)
      if (selectedId.value === documentId) {
        selectedId.value = null
      }
      await load()
    } finally {
      pendingAction.value = null
    }
  }

  function clear(): void {
    documents.value = []
    summary.value = null
    selectedId.value = null
    search.value = ''
    statusFilter.value = 'all'
    loading.value = false
    pendingAction.value = null
  }

  return {
    documents,
    summary,
    selectedId,
    search,
    statusFilter,
    loading,
    pendingAction,
    selectedDocument,
    processedDocuments,
    filteredDocuments,
    busy,
    isPending,
    load,
    upload,
    analyze,
    summarize,
    reviewContent,
    reviewLayout,
    remove,
    clear,
  }
})
