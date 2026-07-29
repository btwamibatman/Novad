export interface QuotaErrorDetail {
  message: string
  used_bytes: number
  quota_bytes: number
  remaining_bytes: number
}

export type ApiErrorDetail = string | QuotaErrorDetail

export interface ApiErrorPayload {
  detail?: ApiErrorDetail
  [key: string]: unknown
}
