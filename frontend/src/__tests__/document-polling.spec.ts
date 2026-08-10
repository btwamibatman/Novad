import { effectScope } from 'vue'
import { createPinia, setActivePinia } from 'pinia'

import { makeDocument } from './fixtures'
import { useDocumentPolling } from '@/composables/useDocumentPolling'
import { useDocumentsStore } from '@/stores/documents'

describe('document polling', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('continues polling after a transient load failure', async () => {
    const store = useDocumentsStore()
    store.documents = [makeDocument({ status: 'analyzing' })]
    const transientError = new Error('Temporary network failure')
    const load = vi
      .spyOn(store, 'load')
      .mockRejectedValueOnce(transientError)
      .mockImplementationOnce(async () => {
        store.documents = [makeDocument({ status: 'processed' })]
      })
    const onError = vi.fn()
    const scope = effectScope()
    const polling = scope.run(() => useDocumentPolling(onError))

    if (!polling) {
      throw new Error('Polling scope was not created')
    }

    try {
      polling.schedule()
      await vi.advanceTimersByTimeAsync(1500)

      expect(load).toHaveBeenCalledTimes(1)
      expect(onError).toHaveBeenCalledWith(transientError)

      await vi.advanceTimersByTimeAsync(1500)

      expect(load).toHaveBeenCalledTimes(2)
    } finally {
      scope.stop()
    }
  })

  it('does not retry after its scope is disposed during a request', async () => {
    const store = useDocumentsStore()
    store.documents = [makeDocument({ status: 'analyzing' })]
    const transientError = new Error('Temporary network failure')
    let rejectLoad: (error: Error) => void = () => undefined
    const load = vi.spyOn(store, 'load').mockImplementation(
      () =>
        new Promise<void>((_resolve, reject) => {
          rejectLoad = reject
        }),
    )
    const scope = effectScope()
    const polling = scope.run(() => useDocumentPolling(vi.fn()))

    if (!polling) {
      throw new Error('Polling scope was not created')
    }

    polling.schedule()
    vi.advanceTimersByTime(1500)
    expect(load).toHaveBeenCalledTimes(1)

    scope.stop()
    rejectLoad(transientError)
    await Promise.resolve()
    await Promise.resolve()

    expect(vi.getTimerCount()).toBe(0)
    await vi.advanceTimersByTimeAsync(1500)
    expect(load).toHaveBeenCalledTimes(1)
  })
})
