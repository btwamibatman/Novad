import { computed, onScopeDispose, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import { documentsApi } from '@/api/documents'
import { ApiError } from '@/api/client'
import { useApiErrorHandler } from '@/composables/useApiErrorHandler'
import { useAuthStore } from '@/stores/auth'
import { useDocumentsStore } from '@/stores/documents'
import type { AIChatMessage, AIChatMode } from '@/types/document'

interface StoredChat {
  expires_at: string
  messages: AIChatMessage[]
}

export interface ChatPosition {
  left: number
  top: number
}

export function useDocumentChat() {
  const { t } = useI18n()
  const authStore = useAuthStore()
  const documentsStore = useDocumentsStore()
  const { handle } = useApiErrorHandler()
  const open = ref(false)
  const maximized = ref(false)
  const position = ref<ChatPosition | null>(null)
  const selectedDocumentId = ref<number | null>(null)
  const messages = ref<AIChatMessage[]>([])
  const asking = ref(false)
  const status = ref<'idle' | 'processing' | 'success' | 'error'>('idle')
  const errorMessage = ref('')
  const elapsedSeconds = ref(0)
  let timer: ReturnType<typeof setInterval> | null = null
  let failedRequest: { question: string; mode: AIChatMode; history: AIChatMessage[] } | null = null
  const sessionIdAtMount = authStore.session?.session_id
  let controller: AbortController | null = null

  const processedDocuments = computed(() => documentsStore.processedDocuments)
  const selectedDocument = computed(
    () =>
      processedDocuments.value.find(
        (document) => document.id === selectedDocumentId.value,
      ) ?? null,
  )

  function storageKey(documentId: number, sessionId = authStore.session?.session_id): string {
    return `document-console-chat:${sessionId || 'anonymous'}:${documentId}`
  }

  function sessionExpired(): boolean {
    const expiresAt = authStore.session?.expires_at
    return Boolean(expiresAt && new Date(expiresAt).getTime() <= Date.now())
  }

  function readMessages(documentId: number): AIChatMessage[] {
    if (!authStore.session || sessionExpired()) {
      return []
    }
    try {
      const stored = JSON.parse(
        sessionStorage.getItem(storageKey(documentId)) || 'null',
      ) as StoredChat | null
      if (!stored || stored.expires_at !== authStore.session.expires_at) {
        return []
      }
      return Array.isArray(stored.messages) ? stored.messages : []
    } catch {
      return []
    }
  }

  function writeMessages(documentId: number, nextMessages: AIChatMessage[]): void {
    if (!authStore.session) {
      return
    }
    const limitedMessages = nextMessages.slice(-40)
    sessionStorage.setItem(
      storageKey(documentId),
      JSON.stringify({
        expires_at: authStore.session.expires_at,
        messages: limitedMessages,
      }),
    )
    if (selectedDocumentId.value === documentId) {
      messages.value = limitedMessages
    }
  }

  function abortRequest(): void {
    controller?.abort()
    controller = null
    asking.value = false
    if (timer) clearInterval(timer)
    timer = null
    status.value = 'idle'
    errorMessage.value = ''
    failedRequest = null
  }

  function syncSelection(): void {
    if (
      selectedDocumentId.value !== null &&
      processedDocuments.value.some(
        (document) => document.id === selectedDocumentId.value,
      )
    ) {
      return
    }
    const selected = documentsStore.selectedDocument
    selectedDocumentId.value =
      selected?.status === 'processed'
        ? selected.id
        : processedDocuments.value[0]?.id ?? null
  }

  async function ask(question: string, mode: AIChatMode = 'question', retryHistory?: AIChatMessage[]): Promise<boolean> {
    const cleanQuestion = question.trim()
    const document = selectedDocument.value
    if (!document || !cleanQuestion || asking.value) {
      return false
    }

    abortRequest()
    const requestDocumentId = document.id
    const history = retryHistory ?? readMessages(requestDocumentId)
    writeMessages(requestDocumentId, [
      ...history,
      { role: 'user', content: cleanQuestion },
    ])

    controller = new AbortController()
    const requestController = controller
    asking.value = true
    status.value = 'processing'
    elapsedSeconds.value = 0
    const startedAt = Date.now()
    timer = setInterval(() => {
      elapsedSeconds.value = Math.floor((Date.now() - startedAt) / 1000)
    }, 1000)
    try {
      const response = await documentsApi.ask(
        requestDocumentId,
        {
          question: cleanQuestion,
          history: history.slice(-12).map(({ role, content }) => ({ role, content: content.slice(0, 1500) })),
          mode,
        },
        requestController.signal,
      )
      if (controller !== requestController || requestController.signal.aborted || selectedDocumentId.value !== requestDocumentId) {
        return false
      }
      writeMessages(requestDocumentId, [
        ...readMessages(requestDocumentId),
        {
          role: 'assistant',
          conclusions: response.conclusions,
          limitations: response.limitations,
          pages_reviewed: response.pages_reviewed,
          content: response.truncated_context
            ? `${response.answer}\n\n${t('chat.truncated_note')}`
            : response.answer,
        },
      ])
      status.value = 'success'
      return true
    } catch (error) {
      if (controller !== requestController || requestController.signal.aborted || (error instanceof Error && error.name === 'AbortError')) {
        return false
      }
      status.value = 'error'
      failedRequest = { question: cleanQuestion, mode, history }
      errorMessage.value = error instanceof ApiError && error.status === 429
        ? t('errors.rate_limit', { seconds: error.retryAfter || t('errors.a_few') })
        : error instanceof ApiError ? error.message : t('chat.connection_error')
      handle(error, false)
      return false
    } finally {
      if (controller === requestController) {
        controller = null
        asking.value = false
        if (timer) clearInterval(timer)
        timer = null
      }
    }
  }

  async function retry(): Promise<boolean> {
    if (!failedRequest || asking.value) return false
    const request = failedRequest
    return ask(request.question, request.mode, request.history)
  }

  function clearSessionMessages(): void {
    const sessionId = authStore.session?.session_id || sessionIdAtMount
    if (!sessionId) {
      return
    }
    const prefix = `document-console-chat:${sessionId}:`
    Object.keys(sessionStorage)
      .filter((key) => key.startsWith(prefix))
      .forEach((key) => sessionStorage.removeItem(key))
  }

  watch(
    [processedDocuments, () => documentsStore.selectedId],
    syncSelection,
    { immediate: true, deep: true },
  )
  watch(
    [selectedDocumentId, () => authStore.session?.expires_at],
    ([documentId]) => {
      abortRequest()
      messages.value = documentId ? readMessages(documentId) : []
    },
    { immediate: true },
  )

  onScopeDispose(abortRequest)

  return {
    open,
    maximized,
    position,
    selectedDocumentId,
    messages,
    asking,
    status,
    errorMessage,
    elapsedSeconds,
    retry,
    processedDocuments,
    selectedDocument,
    ask,
    abortRequest,
    clearSessionMessages,
  }
}
