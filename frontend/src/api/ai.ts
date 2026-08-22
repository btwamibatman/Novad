import { requestJson } from './client'
import type {
  AIAnalysisJobCreate,
  AIAnalysisJobRead,
  AIProviderInfo,
} from '@/types/document'

export const aiAnalysisApi = {
  getProviderInfo(): Promise<AIProviderInfo> {
    return requestJson('/api/ai/provider-info')
  },
  listJobs(): Promise<AIAnalysisJobRead[]> {
    return requestJson('/api/ai/jobs')
  },
  getJob(jobId: number): Promise<AIAnalysisJobRead> {
    return requestJson(`/api/ai/jobs/${jobId}`)
  },
  createJob(payload: AIAnalysisJobCreate): Promise<AIAnalysisJobRead> {
    return requestJson('/api/ai/jobs', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
  },
  deleteRemoteFile(jobId: number): Promise<AIAnalysisJobRead> {
    return requestJson(`/api/ai/jobs/${jobId}/remote-file`, { method: 'DELETE' })
  },
  cancelJob(jobId: number): Promise<AIAnalysisJobRead> {
    return requestJson(`/api/ai/jobs/${jobId}/cancel`, { method: 'POST' })
  },
}
