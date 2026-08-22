<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import { aiAnalysisApi } from '@/api/ai'
import { toolsApi } from '@/api/tools'
import type {
  AIAnalysisJobRead,
  AIAnalysisTask,
  AIFileRetention,
  AIProviderInfo,
  DocumentArtifactRead,
  ToolJobRead,
} from '@/types/document'
import { formatBytes } from '@/utils/format'

const props = withDefaults(defineProps<{
  artifact: DocumentArtifactRead
  sourceJob: ToolJobRead | null
  initialTask?: AIAnalysisTask
}>(), {
  initialTask: 'content_review',
})

const emit = defineEmits<{
  deleted: [artifactId: number]
}>()

const { t, locale } = useI18n()
const jobs = ref<AIAnalysisJobRead[]>([])
const providerInfo = ref<AIProviderInfo | null>(null)
const selectedJobId = ref<number | null>(null)
const currentPage = ref(1)
const previewFailed = ref(false)
const consentOpen = ref(false)
const task = ref<AIAnalysisTask>('content_review')
const retention = ref<AIFileRetention>('delete_after_analysis')
const processingConsent = ref(false)
const termsConsent = ref(false)
const loadingJobs = ref(false)
const creatingJob = ref(false)
const deletingRemote = ref(false)
const cancellingJob = ref(false)
const deletingArtifact = ref(false)
const errorMessage = ref('')
let pollTimer: ReturnType<typeof setInterval> | null = null

const artifactJobs = computed(() =>
  jobs.value.filter((job) => job.artifact_id === props.artifact.id),
)
const selectedJob = computed(
  () =>
    artifactJobs.value.find((job) => job.id === selectedJobId.value) ??
    artifactJobs.value[0] ??
    null,
)
const pageCount = computed(() =>
  Math.max(1, Number(props.artifact.coverage_report.page_count ?? 1)),
)
const checkedPageCount = computed(
  () => props.artifact.coverage_report.checked_pages?.length ?? 0,
)
const coveragePercent = computed(() =>
  Math.round((checkedPageCount.value / pageCount.value) * 100),
)
const canPreview = computed(() =>
  ['ready_for_ai', 'needs_review'].includes(props.artifact.status),
)
const activeAnalysis = computed(() =>
  artifactJobs.value.some((job) =>
    job.worker_active || ['pending', 'running', 'retry_scheduled'].includes(job.status),
  ),
)
const hasRemoteCopies = computed(() =>
  artifactJobs.value.some((job) => job.remote_file_present),
)
const result = computed(() => selectedJob.value?.result ?? {})
const resultCoverage = computed(() => result.value.coverage)
const policyCategories = computed(() => {
  const categories = props.artifact.privacy_policy.categories
  const keys: Record<string, string> = {
    personal: 'tools.protected_ai.category.personal',
    financial: 'tools.protected_ai.category.financial',
    visual: 'tools.protected_ai.category.visual',
    service: 'tools.protected_ai.category.service',
    context: 'tools.protected_ai.category.context',
  }
  const values = categories.map((category) => keys[category] ? t(keys[category]) : category)
  return values.length ? values.join(', ') : t('tools.protected_ai.common.unspecified')
})

function readableError(error: unknown): string {
  return error instanceof Error ? error.message : t('tools.protected_ai.errors.request_failed')
}

function artifactStatusLabel(status: DocumentArtifactRead['status']): string {
  return t(`tools.protected_ai.artifact_status.${status}`)
}

function jobStatusLabel(status: AIAnalysisJobRead['status']): string {
  return t(`tools.protected_ai.job_status.${status}`)
}

function taskLabel(value: AIAnalysisTask): string {
  return t(`tools.protected_ai.task.${value}`)
}

function cleanupStatusLabel(status: AIAnalysisJobRead['remote_cleanup_status']): string {
  return t(`tools.protected_ai.cleanup_status.${status}`)
}

function stageLabel(stage: string): string {
  const knownStages = new Set([
    'queued',
    'restarting',
    'starting',
    'uploading',
    'provider_processing',
    'indexing_protected_copy',
    'analyzing',
    'completed',
    'cancelled',
    'quota_wait',
    'retry_wait',
    'failed',
  ])
  return knownStages.has(stage) ? t(`tools.protected_ai.stage.${stage}`) : stage
}

function findingCategoryLabel(value: string): string {
  return t(`tools.protected_ai.finding_category.${value}`)
}

function findingSeverityLabel(value: string): string {
  return t(`tools.protected_ai.finding_severity.${value}`)
}

function evidenceBasisLabel(value: string): string {
  return t(`tools.protected_ai.evidence_basis.${value}`)
}

function serviceTierLabel(value: AIProviderInfo['service_tier']): string {
  return t(`tools.protected_ai.service_tier.${value}`)
}

function formatExpiry(value: string | null): string {
  if (!value) return ''
  const parsed = new Date(value)
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString(locale.value)
}

function hasElapsedRemoteExpiry(): boolean {
  const now = Date.now()
  return artifactJobs.value.some((job) => {
    if (!job.remote_file_present || !job.provider_file_expires_at) return false
    const expiresAt = new Date(job.provider_file_expires_at).getTime()
    return Number.isFinite(expiresAt) && expiresAt <= now
  })
}

function badgeClass(status: DocumentArtifactRead['status'] | AIAnalysisJobRead['status']): string {
  if (status === 'ready_for_ai' || status === 'completed') return 'processed'
  if (status === 'failed' || status === 'cancelled' || status === 'needs_review') return 'failed'
  return 'neutral'
}

async function loadJobs(): Promise<void> {
  if (loadingJobs.value) return
  loadingJobs.value = true
  try {
    const [loaded, loadedProviderInfo] = await Promise.all([
      aiAnalysisApi.listJobs(),
      aiAnalysisApi.getProviderInfo(),
    ])
    jobs.value = loaded
    providerInfo.value = loadedProviderInfo
    const currentExists = loaded.some(
      (job) => job.id === selectedJobId.value && job.artifact_id === props.artifact.id,
    )
    if (!currentExists) {
      selectedJobId.value = loaded.find((job) => job.artifact_id === props.artifact.id)?.id ?? null
    }
    errorMessage.value = ''
  } catch (error) {
    errorMessage.value = readableError(error)
  } finally {
    loadingJobs.value = false
  }
}

async function pollActiveJobs(): Promise<void> {
  if (loadingJobs.value) return
  const activeJobs = artifactJobs.value.filter((job) =>
    job.worker_active || ['pending', 'running', 'retry_scheduled'].includes(job.status),
  )
  if (!activeJobs.length) return
  loadingJobs.value = true
  try {
    const updates = await Promise.all(
      activeJobs.map((job) => aiAnalysisApi.getJob(job.id)),
    )
    const byId = new Map(updates.map((job) => [job.id, job]))
    jobs.value = jobs.value.map((job) => byId.get(job.id) ?? job)
    errorMessage.value = ''
  } catch (error) {
    errorMessage.value = readableError(error)
  } finally {
    loadingJobs.value = false
  }
}

function openConsent(): void {
  task.value = props.initialTask
  retention.value = 'delete_after_analysis'
  processingConsent.value = false
  termsConsent.value = false
  errorMessage.value = ''
  consentOpen.value = true
}

async function createAnalysis(): Promise<void> {
  if (!processingConsent.value || !termsConsent.value) return
  creatingJob.value = true
  errorMessage.value = ''
  try {
    const job = await aiAnalysisApi.createJob({
      artifact_id: props.artifact.id,
      task: task.value,
      retention: retention.value,
      consent_to_external_processing: processingConsent.value,
      acknowledge_provider_data_terms: termsConsent.value,
    })
    jobs.value = [job, ...jobs.value.filter((item) => item.id !== job.id)]
    selectedJobId.value = job.id
    consentOpen.value = false
  } catch (error) {
    errorMessage.value = readableError(error)
  } finally {
    creatingJob.value = false
  }
}

async function deleteRemoteFile(): Promise<void> {
  if (!selectedJob.value) return
  deletingRemote.value = true
  errorMessage.value = ''
  try {
    const updated = await aiAnalysisApi.deleteRemoteFile(selectedJob.value.id)
    jobs.value = jobs.value.map((job) => (job.id === updated.id ? updated : job))
    await loadJobs()
  } catch (error) {
    errorMessage.value = readableError(error)
  } finally {
    deletingRemote.value = false
  }
}

async function cancelAnalysis(): Promise<void> {
  if (!selectedJob.value) return
  if (!window.confirm(t('tools.protected_ai.confirm.cancel_analysis'))) return
  cancellingJob.value = true
  errorMessage.value = ''
  try {
    const updated = await aiAnalysisApi.cancelJob(selectedJob.value.id)
    jobs.value = jobs.value.map((job) => (job.id === updated.id ? updated : job))
  } catch (error) {
    errorMessage.value = readableError(error)
  } finally {
    cancellingJob.value = false
  }
}

async function deleteArtifact(): Promise<void> {
  if (activeAnalysis.value || hasRemoteCopies.value) return
  if (!window.confirm(t('tools.protected_ai.confirm.delete_artifact'))) return
  deletingArtifact.value = true
  errorMessage.value = ''
  try {
    await toolsApi.deleteArtifact(props.artifact.id)
    emit('deleted', props.artifact.id)
  } catch (error) {
    errorMessage.value = readableError(error)
  } finally {
    deletingArtifact.value = false
  }
}

function showPage(page: number | null | undefined): void {
  if (!page || page < 1 || page > pageCount.value) return
  currentPage.value = page
  previewFailed.value = false
}

watch(
  () => props.artifact.id,
  () => {
    currentPage.value = 1
    previewFailed.value = false
    selectedJobId.value = null
    void loadJobs()
  },
  { immediate: true },
)

watch(currentPage, () => {
  previewFailed.value = false
})

onMounted(() => {
  pollTimer = setInterval(() => {
    if (activeAnalysis.value) {
      void pollActiveJobs()
    } else if (hasElapsedRemoteExpiry()) {
      void loadJobs()
    }
  }, 2000)
})

onBeforeUnmount(() => {
  if (pollTimer) clearInterval(pollTimer)
})
</script>

<template>
  <section class="protected-flow panel" aria-labelledby="protected-copy-title">
    <div class="panel-head protected-head">
      <div>
        <span class="eyebrow">{{ t('tools.protected_ai.protected_file') }}</span>
        <h3 id="protected-copy-title" class="panel-title">{{ artifact.filename }}</h3>
      </div>
      <span class="badge" :class="badgeClass(artifact.status)">
        {{ artifactStatusLabel(artifact.status) }}
      </span>
    </div>

    <div class="panel-body protected-body">
      <div class="artifact-meta">
        <span>{{ formatBytes(artifact.size_bytes) }}</span>
        <span>{{ t('tools.protected_ai.meta.document', { id: artifact.source_document_id }) }}</span>
        <span v-if="sourceJob">{{ t('tools.protected_ai.meta.redaction_job', { id: sourceJob.id }) }}</span>
      </div>

      <div class="coverage-row">
        <div>
          <strong>{{ t('tools.protected_ai.coverage.checked_pages', { checked: checkedPageCount, total: pageCount }) }}</strong>
          <small>
            {{ artifact.coverage_report.verification_completed ? t('tools.protected_ai.coverage.completed') : t('tools.protected_ai.coverage.in_progress') }}
          </small>
        </div>
        <progress :value="coveragePercent" max="100"></progress>
        <span>{{ coveragePercent }}%</span>
      </div>

      <p v-if="artifact.status === 'verifying'" class="flow-notice">
        {{ t('tools.protected_ai.notice.verifying') }}
      </p>
      <p v-else-if="artifact.status === 'needs_review'" class="flow-notice danger-notice">
        {{ t('tools.protected_ai.notice.needs_review') }}
      </p>
      <p v-else-if="artifact.status === 'failed'" class="flow-notice danger-notice">
        {{ artifact.error_message || t('tools.protected_ai.notice.failed') }}
      </p>

      <div v-if="canPreview" class="artifact-preview-grid">
        <div>
          <div class="preview-toolbar">
            <strong>{{ t('tools.protected_ai.preview.title') }}</strong>
            <div class="page-switcher">
              <button class="icon-btn" type="button" :aria-label="t('tools.protected_ai.preview.previous_page')" :disabled="currentPage <= 1" @click="showPage(currentPage - 1)">‹</button>
              <span>{{ currentPage }} / {{ pageCount }}</span>
              <button class="icon-btn" type="button" :aria-label="t('tools.protected_ai.preview.next_page')" :disabled="currentPage >= pageCount" @click="showPage(currentPage + 1)">›</button>
            </div>
          </div>
          <div class="final-preview">
            <img
              v-if="!previewFailed"
              :src="toolsApi.artifactPagePreviewUrl(artifact.id, currentPage)"
              :alt="t('tools.protected_ai.preview.page_alt', { page: currentPage })"
              @error="previewFailed = true"
            />
            <p v-else class="compact-empty">{{ t('tools.protected_ai.preview.unavailable') }}</p>
          </div>
        </div>

        <aside class="artifact-actions">
          <div class="verification-summary">
            <strong>{{ artifact.verification_report.passed ? t('tools.protected_ai.verification.passed') : t('tools.protected_ai.verification.issues') }}</strong>
            <span>{{ t('tools.protected_ai.verification.policy_version', { version: artifact.policy_version, detector: artifact.detector_version }) }}</span>
            <span>{{ t('tools.protected_ai.verification.policy_categories', { categories: policyCategories }) }}</span>
            <span v-if="artifact.privacy_policy.flattened">
              {{ t('tools.protected_ai.verification.flattened') }}
            </span>
            <span v-if="artifact.privacy_policy.render_dpi">
              {{ t('tools.protected_ai.verification.render', { dpi: artifact.privacy_policy.render_dpi, format: artifact.privacy_policy.image_format }) }}<template v-if="artifact.privacy_policy.jpeg_quality"> · {{ t('tools.protected_ai.verification.quality', { quality: artifact.privacy_policy.jpeg_quality }) }}</template>
            </span>
            <span v-if="artifact.coverage_report.image_only_pages?.length">
              {{ t('tools.protected_ai.verification.image_only_pages', { pages: artifact.coverage_report.image_only_pages.join(', ') }) }}
            </span>
            <span v-if="artifact.coverage_report.unchecked_pages?.length">
              {{ t('tools.protected_ai.verification.unchecked_pages', { pages: artifact.coverage_report.unchecked_pages.join(', ') }) }}
            </span>
            <span v-if="artifact.verification_report.risks?.length">
              {{ t('tools.protected_ai.verification.risks', { risks: artifact.verification_report.risks.join(', ') }) }}
            </span>
          </div>
          <a class="button" :href="toolsApi.artifactDownloadUrl(artifact.id)">{{ t('tools.protected_ai.actions.download') }}</a>
          <button
            v-if="artifact.status === 'ready_for_ai'"
            class="button primary"
            type="button"
            :disabled="!providerInfo"
            @click="openConsent"
          >
            {{ t('tools.protected_ai.actions.use_for_ai') }}
          </button>
          <button
            class="button danger"
            type="button"
            :disabled="deletingArtifact || activeAnalysis || hasRemoteCopies"
            @click="deleteArtifact"
          >
            {{ deletingArtifact ? t('tools.protected_ai.actions.deleting') : t('tools.protected_ai.actions.delete_copy') }}
          </button>
          <small v-if="hasRemoteCopies" class="remote-warning">
            {{ t('tools.protected_ai.actions.remote_delete_first') }}
          </small>
        </aside>
      </div>

      <div v-else-if="artifact.status === 'failed'" class="artifact-actions compact-actions">
        <button
          class="button danger"
          type="button"
          :disabled="deletingArtifact"
          @click="deleteArtifact"
        >
          {{ deletingArtifact ? t('tools.protected_ai.actions.deleting') : t('tools.protected_ai.actions.delete_failed_copy') }}
        </button>
      </div>

      <p v-if="errorMessage" class="flow-error" role="alert">{{ errorMessage }}</p>

      <section v-if="artifactJobs.length || loadingJobs" class="analysis-section" aria-labelledby="analysis-title">
        <div class="analysis-head">
          <div>
            <span class="eyebrow">{{ t('tools.protected_ai.analysis.eyebrow') }}</span>
            <h4 id="analysis-title">{{ t('tools.protected_ai.analysis.results') }}</h4>
          </div>
          <select v-if="artifactJobs.length > 1" v-model="selectedJobId" class="select analysis-select">
            <option v-for="job in artifactJobs" :key="job.id" :value="job.id">
              #{{ job.id }} · {{ taskLabel(job.task) }} · {{ jobStatusLabel(job.status) }}
            </option>
          </select>
        </div>

        <div v-if="selectedJob" class="analysis-result">
          <div class="analysis-job-row">
            <div>
              <strong>{{ taskLabel(selectedJob.task) }}</strong>
              <small>{{ selectedJob.provider }}<template v-if="selectedJob.model"> · {{ selectedJob.model }}</template></small>
              <small>
                {{ t('tools.protected_ai.analysis.remote_file', { status: cleanupStatusLabel(selectedJob.remote_cleanup_status) }) }}<template v-if="selectedJob.provider_file_expires_at"> · {{ t('tools.protected_ai.analysis.expires_at', { date: formatExpiry(selectedJob.provider_file_expires_at) }) }}</template>
              </small>
            </div>
            <span class="badge" :class="badgeClass(selectedJob.status)">{{ jobStatusLabel(selectedJob.status) }}</span>
          </div>

          <div v-if="['pending', 'running', 'retry_scheduled'].includes(selectedJob.status)" class="analysis-progress">
            <progress :value="selectedJob.progress" max="100"></progress>
            <span>{{ stageLabel(selectedJob.stage) }} · {{ selectedJob.progress }}%</span>
            <button
              class="button danger small cancel-button"
              type="button"
              :disabled="cancellingJob"
              @click="cancelAnalysis"
            >
              {{ cancellingJob ? t('tools.protected_ai.actions.cancelling') : t('tools.protected_ai.actions.cancel_analysis') }}
            </button>
          </div>
          <p v-if="selectedJob.public_error" class="flow-error">{{ selectedJob.public_error }}</p>
          <p v-if="selectedJob.remote_cleanup_error" class="flow-error">
            {{ selectedJob.remote_cleanup_error }}
          </p>

          <template v-if="selectedJob.status === 'completed'">
            <div class="result-summary">
              <div>
                <span class="result-label">{{ t('tools.protected_ai.results.overview') }}</span>
                <p>{{ result.overview }}</p>
              </div>
              <div v-if="result.verdict">
                <span class="result-label">{{ t('tools.protected_ai.results.verdict') }}</span>
                <p>{{ result.verdict }}</p>
              </div>
            </div>

            <div v-if="resultCoverage" class="result-coverage">
              <strong>{{ t('tools.protected_ai.results.coverage', { coverage: resultCoverage.complete ? t('tools.protected_ai.results.coverage_complete') : t('tools.protected_ai.results.coverage_partial') }) }}</strong>
              <span>{{ t('tools.protected_ai.results.pages', { pages: resultCoverage.pages_reviewed?.join(', ') || t('tools.protected_ai.common.unspecified') }) }}</span>
              <span v-if="resultCoverage.limitations?.length">{{ t('tools.protected_ai.results.limitations', { limitations: resultCoverage.limitations.join('; ') }) }}</span>
            </div>

            <div v-if="result.key_points?.length" class="result-block">
              <h5>{{ t('tools.protected_ai.results.key_points') }}</h5>
              <article v-for="(point, index) in result.key_points" :key="`${point.page}-${index}`" class="result-card">
                <div class="result-card-head">
                  <strong>{{ point.text }}</strong>
                  <button v-if="point.page" class="citation-link" type="button" @click="showPage(point.page)">{{ t('tools.protected_ai.results.page_short', { page: point.page }) }}</button>
                </div>
                <p v-if="point.evidence" class="evidence">{{ t('tools.protected_ai.results.evidence_quote', { evidence: point.evidence }) }}</p>
                <small>{{ point.evidence_verified ? t('tools.protected_ai.results.evidence_verified') : t('tools.protected_ai.results.evidence_needs_review') }}</small>
              </article>
            </div>

            <div v-if="result.findings?.length" class="result-block">
              <h5>{{ t('tools.protected_ai.results.findings') }}</h5>
              <article v-for="(finding, index) in result.findings" :key="`${finding.page}-${finding.category}-${index}`" class="result-card">
                <div class="result-card-head">
                  <span><strong>{{ findingCategoryLabel(finding.category) }}</strong> · {{ findingSeverityLabel(finding.severity) }}</span>
                  <button class="citation-link" type="button" @click="showPage(finding.page)">{{ t('tools.protected_ai.results.page_short', { page: finding.page }) }}</button>
                </div>
                <p>{{ finding.explanation }}</p>
                <p v-if="finding.evidence" class="evidence">{{ t('tools.protected_ai.results.evidence_quote', { evidence: finding.evidence }) }}</p>
                <p v-if="finding.suggestion"><strong>{{ t('tools.protected_ai.results.recommendation') }}</strong> {{ finding.suggestion }}</p>
                <small>
                  {{ t('tools.protected_ai.results.confidence_detail', {
                    confidence: Math.round(finding.confidence * 100),
                    basis: evidenceBasisLabel(finding.basis),
                    verification: finding.evidence_verified ? t('tools.protected_ai.results.evidence_verified_lower') : t('tools.protected_ai.results.evidence_needs_review_lower'),
                  }) }}
                </small>
              </article>
            </div>

          </template>

          <button
            v-if="selectedJob.remote_file_present"
            class="button small remote-delete-button"
            type="button"
            :disabled="deletingRemote || selectedJob.worker_active || selectedJob.remote_cleanup_status === 'pending' || ['pending', 'running', 'retry_scheduled'].includes(selectedJob.status)"
            @click="deleteRemoteFile"
          >
            {{ deletingRemote ? t('tools.protected_ai.actions.deleting') : t('tools.protected_ai.actions.delete_remote') }}
          </button>
        </div>
      </section>
    </div>

    <div v-if="consentOpen" class="consent-backdrop" role="presentation" @click.self="consentOpen = false">
      <section class="consent-dialog" role="dialog" aria-modal="true" aria-labelledby="consent-title">
        <div class="consent-head">
          <div>
            <span class="eyebrow">{{ t('tools.protected_ai.consent.eyebrow') }}</span>
            <h3 id="consent-title">{{ t('tools.protected_ai.consent.title') }}</h3>
          </div>
          <button class="icon-btn" type="button" :aria-label="t('tools.protected_ai.consent.close')" @click="consentOpen = false">×</button>
        </div>

        <form class="consent-form" @submit.prevent="createAnalysis">
          <p class="flow-notice">
            {{ t('tools.protected_ai.consent.notice') }}
          </p>

          <div v-if="providerInfo" class="provider-disclosure">
            <strong>{{ t('tools.protected_ai.consent.provider', { provider: providerInfo.provider }) }}</strong>
            <span>{{ t('tools.protected_ai.consent.model', { model: providerInfo.model }) }}</span>
            <span>{{ t('tools.protected_ai.consent.service_tier', { tier: serviceTierLabel(providerInfo.service_tier) }) }}</span>
            <span>{{ t('tools.protected_ai.consent.max_retention', { hours: providerInfo.max_remote_retention_hours }) }}</span>
            <small v-if="providerInfo.requires_verified_artifact">
              {{ t('tools.protected_ai.consent.verified_only') }}
            </small>
            <small v-if="providerInfo.service_tier === 'unpaid'" class="tier-warning">
              {{ t('tools.protected_ai.consent.unpaid_warning') }}
            </small>
            <a
              v-if="providerInfo.provider.toLowerCase() === 'gemini'"
              href="https://ai.google.dev/gemini-api/terms"
              target="_blank"
              rel="noopener noreferrer"
            >
              {{ t('tools.protected_ai.consent.gemini_terms') }}
            </a>
          </div>

          <label class="form-control">
            <span>{{ t('tools.protected_ai.consent.task_label') }}</span>
            <select v-model="task" class="select">
              <option value="summary">{{ taskLabel('summary') }}</option>
              <option value="content_review">{{ taskLabel('content_review') }}</option>
              <option value="layout_review">{{ taskLabel('layout_review') }}</option>
            </select>
          </label>

          <fieldset class="retention-options">
            <legend>{{ t('tools.protected_ai.consent.retention_legend') }}</legend>
            <label class="retention-card">
              <input v-model="retention" type="radio" value="delete_after_analysis" />
              <span><strong>{{ t('tools.protected_ai.consent.delete_after_analysis') }}</strong><small>{{ t('tools.protected_ai.consent.delete_after_analysis_help') }}</small></span>
            </label>
            <label class="retention-card">
              <input v-model="retention" type="radio" value="retain_48h" />
              <span><strong>{{ t('tools.protected_ai.consent.retain_48h') }}</strong><small>{{ t('tools.protected_ai.consent.retain_48h_help') }}</small></span>
            </label>
          </fieldset>

          <label class="consent-check">
            <input v-model="processingConsent" type="checkbox" />
            <span>{{ t('tools.protected_ai.consent.processing') }}</span>
          </label>
          <label class="consent-check">
            <input v-model="termsConsent" type="checkbox" />
            <span>{{ t('tools.protected_ai.consent.terms') }}</span>
          </label>

          <div class="consent-actions">
            <button class="button" type="button" @click="consentOpen = false">{{ t('tools.protected_ai.consent.cancel') }}</button>
            <button
              class="button primary"
              type="submit"
              :disabled="creatingJob || !processingConsent || !termsConsent"
            >
              {{ creatingJob ? t('tools.protected_ai.consent.starting') : t('tools.protected_ai.consent.submit') }}
            </button>
          </div>
        </form>
      </section>
    </div>
  </section>
</template>

<style scoped>
.protected-flow {
  margin-top: 16px;
}

.protected-head > div,
.analysis-head > div,
.analysis-job-row > div {
  display: grid;
  gap: 4px;
}

.protected-body,
.analysis-result,
.result-block {
  display: grid;
  gap: 14px;
}

.artifact-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 7px 16px;
  color: var(--text-soft);
  font-size: 12px;
}

.coverage-row {
  display: grid;
  grid-template-columns: minmax(190px, 1fr) minmax(120px, 280px) auto;
  align-items: center;
  gap: 12px;
}

.coverage-row > div {
  display: grid;
  gap: 3px;
}

.coverage-row small,
.analysis-job-row small,
.result-card small,
.verification-summary span,
.retention-card small,
.remote-warning {
  color: var(--text-soft);
}

.coverage-row progress,
.analysis-progress progress {
  width: 100%;
  accent-color: var(--accent);
}

.flow-notice,
.flow-error {
  margin: 0;
  border: 1px solid color-mix(in srgb, var(--warning) 34%, var(--border));
  border-radius: 8px;
  background: var(--warning-soft);
  padding: 11px 12px;
  font-size: 13px;
  line-height: 1.5;
}

.danger-notice,
.flow-error {
  border-color: color-mix(in srgb, var(--danger) 36%, var(--border));
  background: var(--danger-soft);
  color: var(--danger);
}

.artifact-preview-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(220px, 300px);
  gap: 16px;
  align-items: start;
}

.preview-toolbar,
.analysis-head,
.analysis-job-row,
.result-card-head,
.consent-head,
.consent-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.preview-toolbar {
  margin-bottom: 10px;
}

.final-preview {
  min-height: 240px;
  max-height: 620px;
  overflow: auto;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--surface-2);
}

.final-preview img {
  display: block;
  width: 100%;
  height: auto;
}

.artifact-actions,
.verification-summary {
  display: grid;
  gap: 10px;
}

.compact-actions {
  justify-items: start;
}

.artifact-actions .button {
  width: 100%;
  text-align: center;
}

.analysis-section {
  display: grid;
  gap: 12px;
  border-top: 1px solid var(--border-soft);
  padding-top: 16px;
}

.analysis-head h4,
.result-block h5,
.consent-head h3 {
  margin: 0;
}

.analysis-select {
  width: min(360px, 100%);
}

.analysis-job-row,
.result-summary,
.result-coverage,
.result-card {
  border: 1px solid var(--border-soft);
  border-radius: 8px;
  background: var(--surface-2);
  padding: 12px;
}

.analysis-progress,
.result-summary,
.result-coverage {
  display: grid;
  gap: 8px;
}

.cancel-button {
  justify-self: start;
}

.result-summary p,
.result-card p {
  margin: 5px 0 0;
  line-height: 1.5;
}

.result-label {
  color: var(--text-soft);
  font-size: 12px;
  font-weight: 700;
  text-transform: uppercase;
}

.result-card {
  display: grid;
  gap: 6px;
}

.citation-link {
  border: 0;
  background: transparent;
  color: var(--accent);
  padding: 2px 0;
  cursor: pointer;
  white-space: nowrap;
}

.evidence {
  color: var(--text-soft);
  font-style: italic;
}

.consent-backdrop {
  position: fixed;
  z-index: 50;
  inset: 0;
  display: grid;
  place-items: center;
  overflow: auto;
  background: rgb(0 0 0 / 55%);
  padding: 20px;
}

.consent-dialog {
  width: min(640px, 100%);
  max-height: calc(100dvh - 40px);
  overflow: auto;
  border: 1px solid var(--border);
  border-radius: 10px;
  background: var(--surface);
  box-shadow: var(--shadow);
}

.consent-head {
  border-bottom: 1px solid var(--border-soft);
  background: var(--surface-2);
  padding: 16px;
}

.consent-form {
  display: grid;
  gap: 14px;
  padding: 16px;
}

.form-control,
.form-control > span {
  display: grid;
  gap: 7px;
}

.provider-disclosure {
  display: grid;
  gap: 5px;
  border: 1px solid var(--border-soft);
  border-radius: 8px;
  background: var(--surface-2);
  padding: 12px;
}

.provider-disclosure span,
.provider-disclosure small {
  color: var(--text-soft);
}

.provider-disclosure .tier-warning {
  color: var(--danger);
}

.retention-options {
  display: grid;
  gap: 8px;
  margin: 0;
  border: 0;
  padding: 0;
}

.retention-options legend {
  margin-bottom: 8px;
  font-weight: 700;
}

.retention-card,
.consent-check {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  border: 1px solid var(--border-soft);
  border-radius: 8px;
  padding: 11px;
  cursor: pointer;
}

.retention-card > span {
  display: grid;
  gap: 3px;
}

.consent-actions {
  justify-content: flex-end;
  border-top: 1px solid var(--border-soft);
  padding-top: 14px;
}

@media (max-width: 760px) {
  .artifact-preview-grid,
  .coverage-row {
    grid-template-columns: 1fr;
  }

  .preview-toolbar,
  .analysis-head,
  .consent-actions {
    align-items: stretch;
    flex-direction: column;
  }

  .analysis-select {
    width: 100%;
  }
}
</style>
