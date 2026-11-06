import { createPinia, setActivePinia } from 'pinia'

import { dashboardApi } from '@/api/dashboard'
import { documentsApi } from '@/api/documents'
import { makeDocument } from './fixtures'
import { useDocumentsStore } from '@/stores/documents'
import type { DashboardSummary, DocumentRead } from '@/types/document'

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((yes) => { resolve = yes })
  return { promise, resolve }
}

function makeSummary(totalDocuments: number): DashboardSummary {
  return {
    total_documents: totalDocuments,
    processed_documents: totalDocuments,
    failed_documents: 0,
    storage_bytes: totalDocuments * 1024,
    detected_languages: { en: totalDocuments },
  }
}

describe('documents store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('selects a document by id', () => {
    const store = useDocumentsStore()
    store.documents = [makeDocument({ id: 7 })]
    store.selectedId = 7

    expect(store.selectedDocument?.id).toBe(7)
  })

  it('filters by status and text from document results', () => {
    const store = useDocumentsStore()
    store.documents = [
      makeDocument({ id: 1, filename: 'report.pdf', ai_summary: 'Quarterly revenue' }),
      makeDocument({ id: 2, filename: 'scan.pdf', status: 'failed' }),
    ]

    store.search = 'revenue'
    expect(store.filteredDocuments.map((document) => document.id)).toEqual([1])

    store.search = ''
    store.statusFilter = 'failed'
    expect(store.filteredDocuments.map((document) => document.id)).toEqual([2])
  })

  it('clears session-bound document state', () => {
    const store = useDocumentsStore()
    store.documents = [makeDocument()]
    store.selectedId = 1
    store.search = 'sample'

    store.clear()

    expect(store.documents).toEqual([])
    expect(store.selectedId).toBeNull()
    expect(store.search).toBe('')
  })

  it('keeps the newest result when concurrent loads finish out of order', async () => {
    const firstSummary = deferred<DashboardSummary>()
    const firstDocuments = deferred<DocumentRead[]>()
    const secondSummary = deferred<DashboardSummary>()
    const secondDocuments = deferred<DocumentRead[]>()
    vi.spyOn(dashboardApi, 'summary')
      .mockReturnValueOnce(firstSummary.promise)
      .mockReturnValueOnce(secondSummary.promise)
    vi.spyOn(documentsApi, 'list')
      .mockReturnValueOnce(firstDocuments.promise)
      .mockReturnValueOnce(secondDocuments.promise)
    const store = useDocumentsStore()

    const firstLoad = store.load(false)
    const secondLoad = store.load(false)
    secondSummary.resolve(makeSummary(2))
    secondDocuments.resolve([makeDocument({ id: 2, filename: 'new.pdf' })])
    await secondLoad
    firstSummary.resolve(makeSummary(1))
    firstDocuments.resolve([makeDocument({ id: 1, filename: 'old.pdf' })])
    await firstLoad

    expect(store.summary?.total_documents).toBe(2)
    expect(store.documents.map((document) => document.filename)).toEqual(['new.pdf'])
    expect(store.loading).toBe(false)
  })

  it('does not restore documents from a request started before clear', async () => {
    const pendingSummary = deferred<DashboardSummary>()
    const pendingDocuments = deferred<DocumentRead[]>()
    vi.spyOn(dashboardApi, 'summary').mockReturnValue(pendingSummary.promise)
    vi.spyOn(documentsApi, 'list').mockReturnValue(pendingDocuments.promise)
    const store = useDocumentsStore()

    const load = store.load(false)
    store.clear()
    pendingSummary.resolve(makeSummary(1))
    pendingDocuments.resolve([makeDocument()])
    await load

    expect(store.summary).toBeNull()
    expect(store.documents).toEqual([])
    expect(store.loading).toBe(false)
  })
})
