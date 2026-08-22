import { requestJson } from './client'
import type {
  CompressionMode,
  DocumentArtifactRead,
  RedactionArea,
  RedactionCategory,
  RedactionMode,
  ToolJobRead,
} from '@/types/document'

export const toolsApi = {
  listJobs(): Promise<ToolJobRead[]> {
    return requestJson('/api/tools/jobs')
  },
  listArtifacts(): Promise<DocumentArtifactRead[]> {
    return requestJson('/api/tools/artifacts')
  },
  getArtifact(artifactId: number): Promise<DocumentArtifactRead> {
    return requestJson(`/api/tools/artifacts/${artifactId}`)
  },
  compress(documentId: number, mode: CompressionMode): Promise<ToolJobRead> {
    return requestJson('/api/tools/compress', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ document_id: documentId, mode }),
    })
  },
  wordToPdf(file: File): Promise<ToolJobRead> {
    const body = new FormData()
    body.append('file', file)
    return requestJson('/api/tools/word-to-pdf', { method: 'POST', body })
  },
  pdfToWord(documentId: number): Promise<ToolJobRead> {
    return requestJson('/api/tools/pdf-to-word', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ document_id: documentId }),
    })
  },
  redactionPreview(documentId: number, categories: RedactionCategory[]): Promise<ToolJobRead> {
    return requestJson('/api/tools/redaction/preview', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ document_id: documentId, categories }),
    })
  },
  applyRedaction(jobId: number, areas: RedactionArea[], mode: RedactionMode): Promise<ToolJobRead> {
    return requestJson(`/api/tools/jobs/${jobId}/apply-redaction`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ areas, mode }),
    })
  },
  pagePreviewUrl(jobId: number, page: number): string {
    return `/api/tools/jobs/${jobId}/pages/${page}`
  },
  downloadUrl(jobId: number): string {
    return `/api/tools/jobs/${jobId}/download`
  },
  artifactPagePreviewUrl(artifactId: number, page: number): string {
    return `/api/tools/artifacts/${artifactId}/pages/${page}`
  },
  artifactDownloadUrl(artifactId: number): string {
    return `/api/tools/artifacts/${artifactId}/download`
  },
  deleteArtifact(artifactId: number): Promise<void> {
    return requestJson(`/api/tools/artifacts/${artifactId}`, { method: 'DELETE' })
  },
}
