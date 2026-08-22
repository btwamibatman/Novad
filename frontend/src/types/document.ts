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

export type ToolJobStatus = 'pending' | 'running' | 'review' | 'completed' | 'failed'
export type CompressionMode = 'low' | 'recommended' | 'extreme'
export type RedactionMode = 'black' | 'pseudonymize'
export type RedactionCategory = 'personal' | 'financial' | 'visual' | 'service' | 'context'

export interface RedactionFinding {
  id: string
  page: number
  group: RedactionCategory
  category: string
  text: string
  confidence: number
  pdf_rect: number[]
  rect: { x: number; y: number; width: number; height: number }
}

export interface RedactionArea {
  id: string
  page: number
  rect: RedactionFinding['rect']
}

export interface ToolJobRead {
  id: number
  source_document_id: number | null
  kind: 'compression' | 'word_to_pdf' | 'pdf_to_word' | 'redaction'
  status: ToolJobStatus
  stage: string
  progress: number
  source_filename: string
  source_content_type: string
  options: Record<string, unknown>
  findings: RedactionFinding[]
  result_filename: string | null
  result_content_type: string | null
  result_size_bytes: number | null
  result_artifact_id: number | null
  result_meta: Record<string, unknown>
  error_message: string | null
  created_at: string
  started_at: string | null
  finished_at: string | null
}

export type DocumentArtifactStatus = 'verifying' | 'ready_for_ai' | 'needs_review' | 'failed'

export interface ArtifactCoverageReport {
  page_count?: number
  checked_pages?: number[]
  unchecked_pages?: number[]
  native_text_pages?: number[]
  image_only_pages?: number[]
  verification_completed?: boolean
  [key: string]: unknown
}

export interface ArtifactVerificationReport {
  passed?: boolean
  risks?: string[]
  source_hash_verified?: boolean
  artifact_hash_verified?: boolean
  selected_text_residual_count?: number
  remaining_finding_count?: number
  [key: string]: unknown
}

export interface DocumentArtifactRead {
  id: number
  source_document_id: number
  kind: string
  status: DocumentArtifactStatus
  filename: string
  content_type: string
  size_bytes: number
  source_sha256: string
  artifact_sha256: string
  privacy_policy: DocumentPrivacyPolicy
  policy_version: string
  detector_version: string
  coverage_report: ArtifactCoverageReport
  verification_report: ArtifactVerificationReport
  error_message: string | null
  created_at: string
  updated_at: string
  verified_at: string | null
}

export interface DocumentPrivacyPolicy {
  categories: RedactionCategory[]
  redaction_mode: RedactionMode | null
  selected_finding_count: number
  manual_confirmation: boolean
  flattened: boolean
  selectable_text: boolean
  render_dpi: number | null
  image_format: string | null
  jpeg_quality: number | null
}

export type AIAnalysisTask = 'summary' | 'content_review' | 'layout_review'
export type AIAnalysisJobStatus =
  | 'pending'
  | 'running'
  | 'retry_scheduled'
  | 'completed'
  | 'failed'
  | 'cancelled'
export type AIFileRetention = 'delete_after_analysis' | 'retain_48h'
export type RemoteCleanupStatus =
  | 'not_applicable'
  | 'pending'
  | 'retained'
  | 'deleted'
  | 'failed'
export type AIAnalysisFindingCategory =
  | 'grammar'
  | 'style'
  | 'logic'
  | 'consistency'
  | 'ocr'
  | 'layout'
  | 'accessibility'
  | 'other'
export type AIAnalysisFindingSeverity = 'critical' | 'high' | 'medium' | 'low'
export type AIAnalysisEvidenceBasis = 'native_text' | 'ocr' | 'vision'

export interface AIAnalysisCoverage {
  pages_reviewed: number[]
  complete: boolean
  limitations: string[]
}

export interface AIAnalysisKeyPoint {
  text: string
  page: number | null
  evidence: string
  evidence_verified: boolean
}

export interface AIAnalysisFinding {
  category: AIAnalysisFindingCategory
  severity: AIAnalysisFindingSeverity
  page: number
  evidence: string
  explanation: string
  suggestion: string
  confidence: number
  basis: AIAnalysisEvidenceBasis
  requires_human_review: boolean
  evidence_verified: boolean
}

export interface ProtectedDocumentAnalysis {
  task: AIAnalysisTask
  overview: string
  verdict: string
  key_points: AIAnalysisKeyPoint[]
  findings: AIAnalysisFinding[]
  coverage: AIAnalysisCoverage
}

export interface AIAnalysisJobRead {
  id: number
  artifact_id: number
  task: AIAnalysisTask
  status: AIAnalysisJobStatus
  stage: string
  progress: number
  worker_active: boolean
  provider: string
  model: string | null
  retention: AIFileRetention
  result: Partial<ProtectedDocumentAnalysis>
  usage: Record<string, unknown>
  attempts: number
  not_before: string | null
  error_code: string | null
  public_error: string | null
  remote_file_present: boolean
  remote_cleanup_status: RemoteCleanupStatus
  remote_cleanup_error: string | null
  provider_file_expires_at: string | null
  created_at: string
  started_at: string | null
  finished_at: string | null
}

export interface AIAnalysisJobCreate {
  artifact_id: number
  task: AIAnalysisTask
  retention: AIFileRetention
  consent_to_external_processing: boolean
  acknowledge_provider_data_terms: boolean
}

export interface AIProviderInfo {
  provider: string
  model: string
  service_tier: 'unpaid' | 'paid'
  max_remote_retention_hours: number
  requires_verified_artifact: boolean
}
