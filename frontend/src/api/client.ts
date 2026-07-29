import type { ApiErrorPayload } from '@/types/api'

export class ApiError extends Error {
  readonly status: number
  readonly payload: ApiErrorPayload | string | null
  readonly retryAfter: string | null

  constructor(
    message: string,
    status: number,
    payload: ApiErrorPayload | string | null,
    retryAfter: string | null,
  ) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.payload = payload
    this.retryAfter = retryAfter
  }
}

function errorMessage(payload: ApiErrorPayload | string | null): string {
  if (typeof payload === 'string') {
    return payload || 'Request failed'
  }
  const detail = payload?.detail
  if (typeof detail === 'string') {
    return detail
  }
  if (detail && typeof detail === 'object' && 'message' in detail) {
    return String(detail.message)
  }
  return 'Request failed'
}

export async function requestJson<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(path, {
    credentials: 'same-origin',
    ...init,
  })

  if (response.status === 204) {
    return undefined as T
  }

  const contentType = response.headers.get('content-type') ?? ''
  const payload = contentType.includes('application/json')
    ? ((await response.json()) as ApiErrorPayload)
    : await response.text()

  if (!response.ok) {
    throw new ApiError(
      errorMessage(payload),
      response.status,
      payload,
      response.headers.get('Retry-After'),
    )
  }

  return payload as T
}
