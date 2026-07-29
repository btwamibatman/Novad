import { requestJson } from './client'
import type {
  AIChatRequest,
  AIChatResponse,
  ContentReviewMode,
  DocumentRead,
} from '@/types/document'

export const documentsApi = {
  list(): Promise<DocumentRead[]> {
    return requestJson('/api/documents')
  },

  upload(file: File): Promise<DocumentRead> {
    const formData = new FormData()
    formData.append('file', file)
    return requestJson('/api/documents/upload', {
      method: 'POST',
      body: formData,
    })
  },

  analyze(documentId: number): Promise<DocumentRead> {
    return requestJson(`/api/documents/${documentId}/analyze`, { method: 'POST' })
  },

  summarize(documentId: number): Promise<DocumentRead> {
    return requestJson(`/api/documents/${documentId}/summarize`, { method: 'POST' })
  },

  reviewContent(documentId: number, mode: ContentReviewMode): Promise<DocumentRead> {
    return requestJson(`/api/documents/${documentId}/content-review`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ mode }),
    })
  },

  reviewLayout(documentId: number): Promise<DocumentRead> {
    return requestJson(`/api/documents/${documentId}/layout-review`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ consent_to_external_image_processing: true }),
    })
  },

  ask(documentId: number, payload: AIChatRequest, signal: AbortSignal): Promise<AIChatResponse> {
    return requestJson(`/api/documents/${documentId}/ask`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
      signal,
    })
  },

  remove(documentId: number): Promise<void> {
    return requestJson(`/api/documents/${documentId}`, { method: 'DELETE' })
  },

  downloadUrl(documentId: number): string {
    return `/api/documents/${documentId}/download`
  },
}
