import { requestJson } from './client'
import type { DashboardSummary } from '@/types/document'

export const dashboardApi = {
  summary(): Promise<DashboardSummary> {
    return requestJson('/api/dashboard/summary')
  },
}
