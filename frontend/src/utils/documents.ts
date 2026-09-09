import type { DocumentRead } from '@/types/document'
import { languageName } from '@/utils/format'

export function documentLanguage(document: DocumentRead, locale = 'en'): string {
  const languages = Object.entries(document.language_distribution)
    .filter(([, share]) => share > 0)
    .sort((a, b) => b[1] - a[1])
    .map(([language]) => languageName(language, locale))
  return languages.join(', ') || (document.detected_language ? languageName(document.detected_language, locale) : '—')
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
