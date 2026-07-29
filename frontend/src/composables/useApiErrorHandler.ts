import { useI18n } from 'vue-i18n'

import { ApiError } from '@/api/client'
import { useToasts } from '@/composables/useToasts'
import { useAuthStore } from '@/stores/auth'
import { useDocumentsStore } from '@/stores/documents'
import { formatBytes } from '@/utils/format'
import type { ApiErrorPayload, QuotaErrorDetail } from '@/types/api'

function quotaDetail(error: ApiError): QuotaErrorDetail | null {
  if (!error.payload || typeof error.payload === 'string') {
    return null
  }
  const detail = (error.payload as ApiErrorPayload).detail
  if (
    detail &&
    typeof detail === 'object' &&
    'used_bytes' in detail &&
    'quota_bytes' in detail
  ) {
    return detail
  }
  return null
}

export function useApiErrorHandler() {
  const { t } = useI18n()
  const authStore = useAuthStore()
  const documentsStore = useDocumentsStore()
  const { show } = useToasts()

  function handle(error: unknown, showGeneric = true): boolean {
    if (error instanceof ApiError && error.status === 401) {
      documentsStore.clear()
      authStore.expire()
      return true
    }
    if (error instanceof ApiError && error.status === 429) {
      show(
        t('errors.rate_limit', {
          seconds: error.retryAfter || t('errors.a_few'),
        }),
        'error',
      )
      return true
    }
    if (showGeneric) {
      const detail = error instanceof ApiError ? quotaDetail(error) : null
      if (detail) {
        show(
          t('errors.quota', {
            message: detail.message,
            used: formatBytes(detail.used_bytes),
            quota: formatBytes(detail.quota_bytes),
          }),
          'error',
        )
      } else {
        show(error instanceof Error ? error.message : t('errors.request_failed'), 'error')
      }
    }
    return false
  }

  return { handle }
}
