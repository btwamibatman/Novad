import { computed, onScopeDispose, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import { documentsApi } from '@/api/documents'
import { useApiErrorHandler } from '@/composables/useApiErrorHandler'
import { useAuthStore } from '@/stores/auth'
import { useDocumentsStore } from '@/stores/documents'
import type { AIChatMessage } from '@/types/document'

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

  async function ask(question: string): Promise<boolean> {
    const cleanQuestion = question.trim()
    const document = selectedDocument.value
    if (!document || !cleanQuestion) {
      return false
    }

    abortRequest()
    const requestDocumentId = document.id
    const history = readMessages(requestDocumentId)
    writeMessages(requestDocumentId, [
      ...history,
      { role: 'user', content: cleanQuestion },
    ])

    controller = new AbortController()
    const requestController = controller
    asking.value = true
    try {
      const response = await documentsApi.ask(
        requestDocumentId,
        {
          question: cleanQuestion,
          history: history.slice(-12),
        },
        requestController.signal,
      )
      if (selectedDocumentId.value !== requestDocumentId) {
        return true
      }
      writeMessages(requestDocumentId, [
        ...readMessages(requestDocumentId),
        {
          role: 'assistant',
          content: response.truncated_context
            ? `${response.answer}\n\n${t('chat.truncated_note')}`
            : response.answer,
        },
      ])
      return true
    } catch (error) {
      if (error instanceof Error && error.name === 'AbortError') {
        return false
      }
      handle(error)
      return false
    } finally {
      if (controller === requestController) {
        controller = null
        asking.value = false
      }
    }
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
    processedDocuments,
    selectedDocument,
    ask,
    abortRequest,
    clearSessionMessages,
  }
}
