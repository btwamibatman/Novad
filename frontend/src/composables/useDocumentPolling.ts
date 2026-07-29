import { onScopeDispose, watch } from 'vue'

import { useDocumentsStore } from '@/stores/documents'

const POLL_INTERVAL_MS = 1500

export function useDocumentPolling(onError: (error: unknown) => void) {
  const documentsStore = useDocumentsStore()
  let timer: number | null = null

  function clearTimer(): void {
    if (timer !== null) {
      window.clearTimeout(timer)
      timer = null
    }
  }

  function schedule(): void {
    clearTimer()
    if (!documentsStore.documents.some((document) => document.status === 'analyzing')) {
      return
    }
    timer = window.setTimeout(async () => {
      timer = null
      try {
        await documentsStore.load(false)
      } catch (error) {
        onError(error)
      }
    }, POLL_INTERVAL_MS)
  }

  watch(() => documentsStore.documents, schedule, { deep: true })
  onScopeDispose(clearTimer)

  return { schedule, stop: clearTimer }
}
