import { onScopeDispose, watch } from 'vue'

import { useDocumentsStore } from '@/stores/documents'

const POLL_INTERVAL_MS = 3000

export function useDocumentPolling(onError: (error: unknown) => void) {
  const documentsStore = useDocumentsStore()
  let timer: number | null = null
  let stopped = false

  function clearTimer(): void {
    if (timer !== null) {
      window.clearTimeout(timer)
      timer = null
    }
  }

  function scheduleNext(): void {
    clearTimer()
    if (
      stopped ||
      !documentsStore.documents.some((document) => document.status === 'analyzing')
    ) {
      return
    }
    timer = window.setTimeout(async () => {
      timer = null
      try {
        await documentsStore.load(false)
      } catch (error) {
        onError(error)
        scheduleNext()
      }
    }, POLL_INTERVAL_MS)
  }

  function schedule(): void {
    stopped = false
    scheduleNext()
  }

  function stop(): void {
    stopped = true
    clearTimer()
  }

  watch(() => documentsStore.documents, schedule, { deep: true })
  onScopeDispose(stop)

  return { schedule, stop }
}
