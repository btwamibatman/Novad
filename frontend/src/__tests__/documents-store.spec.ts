import { createPinia, setActivePinia } from 'pinia'

import { makeDocument } from './fixtures'
import { useDocumentsStore } from '@/stores/documents'

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
})
