import { useI18n } from 'vue-i18n'

import { aiAnalysisApi } from '@/api/ai'

export function useExternalTextConsent() {
  const { t } = useI18n()

  return async (): Promise<boolean | null> => {
    const info = await aiAnalysisApi.getProviderInfo()
    if (info.provider.toLowerCase() === 'ollama') return false
    return window.confirm(t('analysis.external_text_consent')) ? true : null
  }
}
