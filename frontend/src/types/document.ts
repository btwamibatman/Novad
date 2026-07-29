export type DocumentStatus = 'uploaded' | 'analyzing' | 'processed' | 'failed'
export type ExtractionQuality = 'unknown' | 'high' | 'medium' | 'low'
export type ContentReviewMode = 'quick' | 'thorough'

export interface AnalysisProgress {
  stage?: string
  completed_pages?: number
  total_pages?: number | null
}

export interface ExtractionQualityMeta {
  requires_manual_review?: boolean
  manual_review_pages?: Array<number | null>
  [key: string]: unknown
}

export interface ContentReviewMeta {
  complete?: boolean
  batch_count?: number
  reviewed_chars?: number
  [key: string]: unknown
}

export interface LayoutReviewMeta {
  complete?: boolean
  reviewed_pages?: number[]
  [key: string]: unknown
}

export interface DocumentRead {
  id: number
  user_id: number
  filename: string
  content_type: string
  size_bytes: number
  status: DocumentStatus
  analysis_progress: AnalysisProgress
  extracted_text: string
  extraction_quality: ExtractionQuality
  extraction_quality_meta: ExtractionQualityMeta
  detected_language: string | null
  language_distribution: Record<string, number>
  word_count: number
  char_count: number
  error_message: string | null
  ai_summary: string
  ai_model: string | null
  ai_error: string | null
  ai_summary_meta: Record<string, unknown>
  content_review: string
  content_review_model: string | null
  content_review_error: string | null
  content_review_mode: ContentReviewMode | null
  content_review_meta: ContentReviewMeta
  layout_review: string
  layout_review_model: string | null
  layout_review_error: string | null
  layout_review_meta: LayoutReviewMeta
  created_at: string
  updated_at: string
}

export interface DashboardSummary {
  total_documents: number
  processed_documents: number
  failed_documents: number
  storage_bytes: number
  detected_languages: Record<string, number>
}

export interface AIChatMessage {
  role: 'user' | 'assistant'
  content: string
}

export interface AIChatRequest {
  question: string
  history: AIChatMessage[]
}

export interface AIChatResponse {
  answer: string
  model: string
  truncated_context: boolean
  privacy_applied: boolean
  masked_entity_count: number
}
