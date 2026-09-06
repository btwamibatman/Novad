import type { DocumentRead } from '@/types/document'
import { languageName } from '@/utils/format'

export type Translate = (
  key: string,
  params?: Record<string, string | number>,
) => string

export function documentLanguage(document: DocumentRead, locale = 'en'): string {
  const languages = Object.entries(document.language_distribution)
    .filter(([, share]) => share > 0)
    .sort((a, b) => b[1] - a[1])
    .map(([language]) => languageName(language, locale))
  return languages.join(', ') || (document.detected_language ? languageName(document.detected_language, locale) : '—')
}

export function qualityWarning(document: DocumentRead | null, t: Translate): string {
  const meta = document?.extraction_quality_meta
  if (!document || !meta?.requires_manual_review) {
    return ''
  }
  const pages = (meta.manual_review_pages ?? []).filter(
    (page): page is number => page !== null,
  )
  const pageLabel = pages.length
    ? t('analysis.pages_to_verify', { pages: pages.join(', ') })
    : ''
  return t('analysis.quality_warning', {
    quality: t(`quality.${document.extraction_quality}`),
    pages: pageLabel,
  })
}

export function aiState(document: DocumentRead): 'error' | 'ready' | 'none' {
  if (
    document.ai_error ||
    document.content_review_error ||
    document.layout_review_error
  ) {
    return 'error'
  }
  if (document.ai_summary || document.content_review || document.layout_review) {
    return 'ready'
  }
  return 'none'
}
