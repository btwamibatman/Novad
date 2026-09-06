<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute } from 'vue-router'

import { toolsApi } from '@/api/tools'
import ProtectedArtifactAI from '@/components/tools/ProtectedArtifactAI.vue'
import { useApiErrorHandler } from '@/composables/useApiErrorHandler'
import { useToasts } from '@/composables/useToasts'
import { useDocumentsStore } from '@/stores/documents'
import type {
  CompressionMode,
  AIAnalysisTask,
  DocumentArtifactRead,
  RedactionCategory,
  RedactionFinding,
  RedactionMode,
  ToolJobRead,
} from '@/types/document'
import { formatBytes } from '@/utils/format'

type Tool = 'redaction' | 'compression' | 'conversion'
type ResizeHandle = 'nw' | 'ne' | 'sw' | 'se'
type RedactionRect = RedactionFinding['rect']

interface RedactionInteraction {
  kind: 'draw' | 'resize'
  id?: string
  handle?: ResizeHandle
  start: { x: number; y: number }
  original?: RedactionRect
}

const { t } = useI18n()
const route = useRoute()
const documentsStore = useDocumentsStore()
const { handle } = useApiErrorHandler()
const { show } = useToasts()
const activeTool = ref<Tool>('redaction')
const jobs = ref<ToolJobRead[]>([])
const artifacts = ref<DocumentArtifactRead[]>([])
const selectedDocumentId = ref<number | null>(null)
const compressionMode = ref<CompressionMode>('recommended')
const wordFile = ref<File | null>(null)
const categories = ref<RedactionCategory[]>(['personal', 'financial', 'visual'])
const redactionMode = ref<RedactionMode>('black')
const redactionJobId = ref<number | null>(null)
const selectedArtifactId = ref<number | null>(null)
const selectedFindingIds = ref<string[]>([])
const editableFindings = ref<RedactionFinding[]>([])
const previewElement = ref<HTMLElement | null>(null)
const draftRect = ref<RedactionRect | null>(null)
const currentPage = ref(1)
const submitting = ref(false)
const loadingWorkspace = ref(true)
const workspaceLoadFailed = ref(false)
const documentPickerOpen = ref(false)
const sourceSelect = ref<HTMLSelectElement | null>(null)
const wordInput = ref<HTMLInputElement | null>(null)
const previewFailed = ref(false)
const toolNames: Tool[] = ['redaction', 'compression', 'conversion']
let interaction: RedactionInteraction | null = null
let manualFindingSequence = 0
let hydratedReviewJobId: number | null = null
let pollTimer: ReturnType<typeof setInterval> | null = null

const pdfDocuments = computed(() =>
  documentsStore.documents.filter((document) => document.content_type === 'application/pdf'),
)
const selectedDocument = computed(() =>
  pdfDocuments.value.find((document) => document.id === selectedDocumentId.value) ?? null,
)
const requestedTask = computed<AIAnalysisTask>(() => {
  const raw = Array.isArray(route.query.task) ? route.query.task[0] : route.query.task
  return raw === 'summary' || raw === 'content_review' || raw === 'layout_review'
    ? raw
    : 'content_review'
})
const requestedDocumentId = computed(() => {
  const raw = Array.isArray(route.query.document_id)
    ? route.query.document_id[0]
    : route.query.document_id
  const parsed = Number(raw)
  return Number.isInteger(parsed) && parsed > 0 ? parsed : null
})
const redactionJob = computed(
  () => jobs.value.find((job) => job.id === redactionJobId.value) ?? null,
)
const protectedArtifact = computed(() => {
  const job = redactionJob.value
  if (job) {
    if (job.status !== 'completed') return null
    return artifacts.value.find((artifact) => artifact.id === job.result_artifact_id) ?? null
  }
  return artifacts.value.find((artifact) =>
    artifact.id === selectedArtifactId.value && artifact.source_document_id === selectedDocumentId.value,
  ) ?? null
})
const redactionStep = computed(() => {
  const job = redactionJob.value
  if (!job || job.status === 'failed') return 0
  if (job.status === 'completed') return 4
  if (job.status === 'review') return 2
  return job.options.operation === 'apply' ? 3 : 1
})
const pageCount = computed(() => Math.max(1, Number(redactionJob.value?.result_meta.page_count ?? 1)))
const pageFindings = computed(() =>
  editableFindings.value.filter((finding) => finding.page === currentPage.value),
)
const hasRunningJobs = computed(() =>
  jobs.value.some((job) => ['pending', 'running'].includes(job.status)) ||
  artifacts.value.some((artifact) => artifact.status === 'verifying'),
)
const sourceLocked = computed(
  () =>
    activeTool.value === 'redaction' &&
    Boolean(redactionJob.value && ['pending', 'running', 'review'].includes(redactionJob.value.status)),
)

watch(
  () => [redactionJob.value?.id, redactionJob.value?.status] as const,
  ([jobId, status]) => {
    const job = redactionJob.value
    if (job?.source_document_id && sourceLocked.value) {
      selectedDocumentId.value = job.source_document_id
    }
    if (status === 'review' && job && hydratedReviewJobId !== jobId) {
      hydratedReviewJobId = job.id
      editableFindings.value = job.findings.map((finding) => ({
        ...finding,
        rect: { ...finding.rect },
        pdf_rect: [...finding.pdf_rect],
      }))
      selectedFindingIds.value = editableFindings.value.map((finding) => finding.id)
      currentPage.value = job.findings[0]?.page ?? 1
    } else if (status !== 'review' && hydratedReviewJobId === jobId) {
      hydratedReviewJobId = null
    }
  },
)

watch(activeTool, (tool) => {
  if (tool === 'redaction' && redactionJob.value?.source_document_id && sourceLocked.value) {
    selectedDocumentId.value = redactionJob.value.source_document_id
  }
})
watch(currentPage, () => { previewFailed.value = false })

watch(requestedDocumentId, (id) => {
  if (!id || !pdfDocuments.value.some((document) => document.id === id)) return
  selectedDocumentId.value = id
  redactionJobId.value = null
  selectedArtifactId.value = null
  restoreWorkspaceSelection()
})

function restoreWorkspaceSelection(): void {
  let job = jobs.value.find(
    (item) => item.id === redactionJobId.value && item.kind === 'redaction',
  )
  if (!job) {
    const preferredSourceId = selectedDocumentId.value
    job =
      jobs.value.find(
        (item) =>
          item.kind === 'redaction' &&
          item.status === 'review' &&
          item.source_document_id === preferredSourceId,
      ) ??
      jobs.value.find(
        (item) =>
          item.kind === 'redaction' &&
          ['pending', 'running'].includes(item.status) &&
          item.source_document_id === preferredSourceId,
      ) ??
      jobs.value.find(
        (item) =>
          item.kind === 'redaction' &&
          item.source_document_id === preferredSourceId,
      )
  }
  if (job) {
    redactionJobId.value = job.id
    if (activeTool.value === 'redaction' && job.source_document_id !== null) {
      selectedDocumentId.value = job.source_document_id
    }
  }

  const linkedArtifact = artifacts.value.find(
    (artifact) => artifact.id === job?.result_artifact_id,
  )
  const currentArtifact = artifacts.value.find(
    (artifact) => artifact.id === selectedArtifactId.value,
  )
  const sourceId = job?.source_document_id ?? selectedDocumentId.value
  if (job && ['pending', 'running', 'review'].includes(job.status) && !linkedArtifact) {
    selectedArtifactId.value = null
    return
  }
  const sourceArtifact = artifacts.value.find(
    (artifact) => artifact.source_document_id === sourceId,
  )
  selectedArtifactId.value = linkedArtifact?.id ?? currentArtifact?.id ?? sourceArtifact?.id ?? null
}

async function loadWorkspace(): Promise<void> {
  workspaceLoadFailed.value = false
  try {
    const [loadedJobs, loadedArtifacts] = await Promise.all([
      toolsApi.listJobs(),
      toolsApi.listArtifacts(),
    ])
    jobs.value = loadedJobs
    artifacts.value = loadedArtifacts
    restoreWorkspaceSelection()
  } catch (error) {
    workspaceLoadFailed.value = true
    handle(error)
  } finally {
    loadingWorkspace.value = false
  }
}

async function run(request: () => Promise<ToolJobRead>): Promise<void> {
  submitting.value = true
  try {
    const job = await request()
    jobs.value = [job, ...jobs.value.filter((item) => item.id !== job.id)]
    if (job.kind === 'redaction') {
      redactionJobId.value = job.id
      if (job.source_document_id !== null) selectedDocumentId.value = job.source_document_id
    }
    show(t('tools.queued'), 'success')
  } catch (error) {
    handle(error)
  } finally {
    submitting.value = false
  }
}

function requireDocument(): number | null {
  if (!selectedDocumentId.value) {
    show(t('tools.choose_pdf'), 'error')
    return null
  }
  return selectedDocumentId.value
}

async function compress(): Promise<void> {
  const id = requireDocument()
  if (id) await run(() => toolsApi.compress(id, compressionMode.value))
}

async function convertWord(): Promise<void> {
  if (!wordFile.value) {
    show(t('tools.choose_word'), 'error')
    return
  }
  await run(() => toolsApi.wordToPdf(wordFile.value!))
}

async function convertPdf(): Promise<void> {
  const id = requireDocument()
  if (id) await run(() => toolsApi.pdfToWord(id))
}

async function previewRedaction(): Promise<void> {
  const id = requireDocument()
  if (!id) return
  if (!categories.value.length) {
    show(t('tools.choose_category'), 'error')
    return
  }
  submitting.value = true
  try {
    const job = await toolsApi.redactionPreview(id, categories.value)
    redactionJobId.value = job.id
    jobs.value = [job, ...jobs.value]
    show(t('tools.search_started'), 'success')
  } catch (error) {
    handle(error)
  } finally {
    submitting.value = false
  }
}

async function applyRedaction(): Promise<void> {
  if (!redactionJob.value || !selectedFindingIds.value.length) {
    show(t('tools.choose_finding'), 'error')
    return
  }
  await run(() =>
    toolsApi.applyRedaction(
      redactionJob.value!.id,
      editableFindings.value
        .filter((finding) => selectedFindingIds.value.includes(finding.id))
        .map((finding) => ({ id: finding.id, page: finding.page, rect: finding.rect })),
      redactionMode.value,
    ),
  )
}

function previewPoint(event: PointerEvent): { x: number; y: number } | null {
  const element = previewElement.value
  if (!element) return null
  const bounds = element.getBoundingClientRect()
  if (!bounds.width || !bounds.height) return null
  return {
    x: Math.max(0, Math.min(100, ((event.clientX - bounds.left) / bounds.width) * 100)),
    y: Math.max(0, Math.min(100, ((event.clientY - bounds.top) / bounds.height) * 100)),
  }
}

function startDrawing(event: PointerEvent): void {
  if ((event.target as HTMLElement).closest('.finding-overlay')) return
  const point = previewPoint(event)
  if (!point) return
  event.preventDefault()
  interaction = { kind: 'draw', start: point }
  draftRect.value = { x: point.x, y: point.y, width: 0, height: 0 }
}

function startResize(event: PointerEvent, finding: RedactionFinding, handle: ResizeHandle): void {
  const point = previewPoint(event)
  if (!point) return
  event.preventDefault()
  event.stopPropagation()
  interaction = {
    kind: 'resize',
    id: finding.id,
    handle,
    start: point,
    original: { ...finding.rect },
  }
}

function pointerMove(event: PointerEvent): void {
  if (!interaction) return
  const point = previewPoint(event)
  if (!point) return
  if (interaction.kind === 'draw') {
    draftRect.value = {
      x: Math.min(interaction.start.x, point.x),
      y: Math.min(interaction.start.y, point.y),
      width: Math.abs(point.x - interaction.start.x),
      height: Math.abs(point.y - interaction.start.y),
    }
    return
  }

  const finding = editableFindings.value.find((item) => item.id === interaction?.id)
  const original = interaction.original
  const handle = interaction.handle
  if (!finding || !original || !handle) return
  const minSize = 0.5
  const right = original.x + original.width
  const bottom = original.y + original.height
  const west = handle.includes('w')
  const north = handle.includes('n')
  const left = west ? Math.max(0, Math.min(point.x, right - minSize)) : original.x
  const top = north ? Math.max(0, Math.min(point.y, bottom - minSize)) : original.y
  const nextRight = west ? right : Math.min(100, Math.max(point.x, original.x + minSize))
  const nextBottom = north ? bottom : Math.min(100, Math.max(point.y, original.y + minSize))
  finding.rect = {
    x: left,
    y: top,
    width: nextRight - left,
    height: nextBottom - top,
  }
}

function pointerUp(): void {
  if (interaction?.kind === 'draw' && draftRect.value) {
    const rect = draftRect.value
    if (rect.width >= 0.5 && rect.height >= 0.5) {
      const id = `manual-${Date.now()}-${manualFindingSequence++}`
      editableFindings.value.push({
        id,
        page: currentPage.value,
        group: 'personal',
        category: 'MANUAL',
        text: '',
        confidence: 1,
        pdf_rect: [],
        rect: { ...rect },
      })
      selectedFindingIds.value.push(id)
    }
  }
  interaction = null
  draftRect.value = null
}

function cancelInteraction(): void {
  if (interaction?.kind === 'resize' && interaction.original) {
    const finding = editableFindings.value.find((item) => item.id === interaction?.id)
    if (finding) finding.rect = interaction.original
  }
  interaction = null
  draftRect.value = null
}

function toggleFinding(id: string): void {
  selectedFindingIds.value = selectedFindingIds.value.includes(id)
    ? selectedFindingIds.value.filter((item) => item !== id)
    : [...selectedFindingIds.value, id]
}

function chooseFile(event: Event): void {
  wordFile.value = (event.target as HTMLInputElement).files?.[0] ?? null
}

function sourceDocumentChanged(): void {
  if (sourceLocked.value) return
  documentsStore.selectedId = selectedDocumentId.value
  documentPickerOpen.value = false
  if (
    redactionJob.value &&
    ['pending', 'running', 'review'].includes(redactionJob.value.status)
  ) {
    return
  }
  const sourceId = selectedDocumentId.value
  const job = jobs.value.find(
    (item) => item.kind === 'redaction' && item.source_document_id === sourceId,
  )
  redactionJobId.value = job?.id ?? null
  selectedArtifactId.value =
    artifacts.value.find((artifact) => artifact.source_document_id === sourceId)?.id ?? null
  hydratedReviewJobId = null
}

async function changeDocument(): Promise<void> {
  documentPickerOpen.value = !documentPickerOpen.value
  if (documentPickerOpen.value) {
    await nextTick()
    sourceSelect.value?.focus()
  }
}

function navigateTools(event: KeyboardEvent, index: number): void {
  let next = index
  if (event.key === 'ArrowRight') next = (index + 1) % toolNames.length
  else if (event.key === 'ArrowLeft') next = (index + toolNames.length - 1) % toolNames.length
  else if (event.key === 'Home') next = 0
  else if (event.key === 'End') next = toolNames.length - 1
  else return
  event.preventDefault()
  activeTool.value = toolNames[next]!
  document.getElementById(`tool-tab-${activeTool.value}`)?.focus()
}

function addManualArea(): void {
  interaction = { kind: 'draw', start: { x: 25, y: 25 } }
  draftRect.value = { x: 25, y: 25, width: 25, height: 8 }
  pointerUp()
}

function resizeWithKeyboard(event: KeyboardEvent, finding: RedactionFinding, corner: ResizeHandle): void {
  if (!['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown'].includes(event.key)) return
  event.preventDefault()
  const step = event.shiftKey ? 5 : 1
  const rect = finding.rect
  if (event.key === 'ArrowLeft' || event.key === 'ArrowRight') {
    const delta = event.key === 'ArrowRight' ? step : -step
    if (corner.includes('w')) {
      const next = Math.max(0, Math.min(rect.x + delta, rect.x + rect.width - 0.5))
      rect.width += rect.x - next
      rect.x = next
    } else rect.width = Math.max(0.5, Math.min(100 - rect.x, rect.width + delta))
  } else {
    const delta = event.key === 'ArrowDown' ? step : -step
    if (corner.includes('n')) {
      const next = Math.max(0, Math.min(rect.y + delta, rect.y + rect.height - 0.5))
      rect.height += rect.y - next
      rect.y = next
    } else rect.height = Math.max(0.5, Math.min(100 - rect.y, rect.height + delta))
  }
}

function originalSize(job: ToolJobRead): number | null {
  const size = job.result_meta.original_size_bytes
  if (typeof size === 'number') return size
  return pdfDocuments.value.find((document) => document.id === job.source_document_id)?.size_bytes ?? null
}

function reduction(job: ToolJobRead): string | null {
  const value = job.result_meta.savings_percent
  return typeof value === 'number' ? String(value) : null
}

function jobStatus(job: ToolJobRead): string {
  if (job.kind === 'redaction' && job.status === 'completed') {
    const status = artifacts.value.find((artifact) => artifact.id === job.result_artifact_id)?.status
      ?? job.result_meta.artifact_status
    if (status === 'failed') return t('tools.protected_ai.artifact_status.failed')
    if (status === 'needs_review') return t('tools.protected_ai.artifact_status.needs_review')
    if (status === 'verifying') return t('tools.protected_ai.artifact_status.verifying')
    return t('tools.refinement.redaction_completed')
  }
  return t(`tools.status.${job.status}`)
}

function jobTone(job: ToolJobRead): string {
  if (job.kind === 'redaction' && job.status === 'completed') {
    const status = artifacts.value.find((artifact) => artifact.id === job.result_artifact_id)?.status
      ?? job.result_meta.artifact_status
    if (status === 'failed') return 'failed'
    if (status === 'needs_review' || status === 'verifying') return 'review'
  }
  return job.status
}

function jobError(job: ToolJobRead): string {
  if (job.error_message === 'Unable to apply redactions safely') return t('tools.refinement.redaction_failed')
  return t(job.kind === 'redaction' ? 'tools.refinement.redaction_failed' : 'tools.refinement.task_failed')
}

function openJob(job: ToolJobRead): void {
  activeTool.value = job.kind === 'redaction' ? 'redaction' : job.kind === 'compression' ? 'compression' : 'conversion'
  if (job.source_document_id && pdfDocuments.value.some((document) => document.id === job.source_document_id)) {
    selectedDocumentId.value = job.source_document_id
    documentsStore.selectedId = job.source_document_id
  }
  if (job.kind === 'redaction') {
    redactionJobId.value = job.id
    selectedArtifactId.value = job.result_artifact_id
    hydratedReviewJobId = null
  }
  void nextTick(() => document.getElementById(`tool-panel-${activeTool.value}`)?.focus())
}

function artifactDeleted(artifactId: number): void {
  artifacts.value = artifacts.value.filter((artifact) => artifact.id !== artifactId)
  if (selectedArtifactId.value === artifactId) selectedArtifactId.value = null
  void loadWorkspace()
}

onMounted(async () => {
  window.addEventListener('pointermove', pointerMove)
  window.addEventListener('pointerup', pointerUp)
  window.addEventListener('pointercancel', cancelInteraction)
  if (!documentsStore.documents.length) {
    try { await documentsStore.load(false) } catch (error) { handle(error) }
  }
  const linkedDocumentId = pdfDocuments.value.some(
    (document) => document.id === requestedDocumentId.value,
  )
    ? requestedDocumentId.value
    : null
  const storedDocumentId = pdfDocuments.value.some((document) => document.id === documentsStore.selectedId)
    ? documentsStore.selectedId : null
  selectedDocumentId.value = linkedDocumentId ?? storedDocumentId ?? pdfDocuments.value[0]?.id ?? null
  await loadWorkspace()
  pollTimer = setInterval(() => {
    if (hasRunningJobs.value) void loadWorkspace()
  }, 1500)
})

onBeforeUnmount(() => {
  window.removeEventListener('pointermove', pointerMove)
  window.removeEventListener('pointerup', pointerUp)
  window.removeEventListener('pointercancel', cancelInteraction)
  if (pollTimer) clearInterval(pollTimer)
})
</script>

<template>
  <main class="tools-page">
    <header class="tools-intro">
      <div>
        <h2>{{ t('tools.title') }}</h2>
        <p>{{ t('tools.subtitle') }}</p>
      </div>
    </header>

    <div class="tool-tabs" role="tablist" :aria-label="t('tools.title')">
      <button
        v-for="(tool, index) in toolNames"
        :key="tool"
        :id="`tool-tab-${tool}`"
        class="tool-tab"
        :class="{ active: activeTool === tool }"
        type="button"
        role="tab"
        :aria-selected="activeTool === tool"
        :aria-controls="`tool-panel-${tool}`"
        :tabindex="activeTool === tool ? 0 : -1"
        @click="activeTool = tool"
        @keydown="navigateTools($event, index)"
      >
        {{ t(`tools.${tool}.title`) }}
      </button>
    </div>

    <section class="tool-source" :aria-label="t('tools.source_document')">
      <div class="source-summary">
        <div class="source-label">
          <span>{{ t('tools.source_document') }}</span>
          <strong class="source-filename">{{ selectedDocument?.filename ?? t('tools.choose_pdf') }}</strong>
          <span v-if="selectedDocument">{{ formatBytes(selectedDocument.size_bytes) }}</span>
        </div>
        <button class="button" type="button" :disabled="sourceLocked || !pdfDocuments.length" :aria-expanded="documentPickerOpen" aria-controls="tool-document-picker" @click="changeDocument">
          {{ t('tools.refinement.change_document') }}
        </button>
      </div>
      <label v-show="documentPickerOpen" id="tool-document-picker" class="document-picker">
        <span>{{ t('tools.choose_pdf') }}</span>
        <select ref="sourceSelect" v-model="selectedDocumentId" class="select" :disabled="sourceLocked" @change="sourceDocumentChanged">
          <option :value="null">{{ t('tools.choose_pdf') }}</option>
          <option v-for="document in pdfDocuments" :key="document.id" :value="document.id">{{ document.filename }} · {{ formatBytes(document.size_bytes) }}</option>
        </select>
      </label>
      <p v-if="sourceLocked" class="control-help">{{ t('tools.redaction.source_locked') }}</p>
      <p v-else-if="!pdfDocuments.length" class="control-help">{{ t('tools.refinement.no_pdf') }} <RouterLink to="/documents">{{ t('nav.documents') }}</RouterLink></p>
      <p v-if="activeTool === 'conversion'" class="control-help">{{ t('tools.refinement.conversion_source_help') }}</p>
    </section>

    <section v-if="activeTool === 'compression'" id="tool-panel-compression" class="tool-workspace operation-surface" role="tabpanel" aria-labelledby="tool-tab-compression" tabindex="0">
      <div class="panel-body">
        <fieldset class="compression-modes">
          <legend class="visually-hidden">{{ t('tools.compression.title') }}</legend>
          <label v-for="mode in (['low', 'recommended', 'extreme'] as CompressionMode[])" :key="mode" class="mode-card" :class="{ selected: compressionMode === mode }">
            <input v-model="compressionMode" type="radio" :value="mode" />
            <span><strong>{{ t(`tools.compression.${mode}`) }}</strong></span>
            <small>{{ t(`tools.compression.${mode}_saving`) }}</small>
            <p>{{ t(`tools.compression.${mode}_help`) }}</p>
          </label>
        </fieldset>
        <p class="control-help">{{ t('tools.compression.estimate_note') }}</p>
        <button class="button primary" type="button" :disabled="submitting || !selectedDocumentId" @click="compress">
          {{ t('tools.compression.action') }}
        </button>
      </div>
    </section>

    <section v-else-if="activeTool === 'conversion'" id="tool-panel-conversion" class="tool-workspace conversion-grid operation-surface" role="tabpanel" aria-labelledby="tool-tab-conversion" tabindex="0">
      <article class="conversion-operation">
        <h3>{{ t('tools.kind.word_to_pdf') }}</h3>
          <p class="section-help">{{ t('tools.conversion.word_help') }}</p>
          <input ref="wordInput" class="visually-hidden" type="file" accept=".doc,.docx,.odt" tabindex="-1" :aria-label="t('tools.refinement.choose_word_file')" @change="chooseFile" />
          <div class="word-source">
            <button class="button" type="button" @click="wordInput?.click()">{{ t(wordFile ? 'tools.refinement.change_file' : 'tools.refinement.choose_word_file') }}</button>
            <span class="source-filename" aria-live="polite">{{ wordFile?.name ?? t('tools.refinement.no_word_file') }}</span>
          </div>
          <button class="button primary" type="button" :disabled="submitting || !wordFile" @click="convertWord">{{ t('tools.conversion.to_pdf') }}</button>
      </article>
      <article class="conversion-operation">
        <h3>{{ t('tools.kind.pdf_to_word') }}</h3>
          <p class="section-help">{{ t('tools.conversion.pdf_help') }}</p>
          <p class="control-help">{{ t('tools.conversion.ocr_help') }}</p>
          <button class="button primary" type="button" :disabled="submitting || !selectedDocumentId" @click="convertPdf">{{ t('tools.conversion.to_word') }}</button>
      </article>
    </section>

    <section v-else id="tool-panel-redaction" class="tool-workspace operation-surface" role="tabpanel" aria-labelledby="tool-tab-redaction" tabindex="0">
      <div class="panel-body">
        <ol class="redaction-steps" :aria-label="t('tools.refinement.redaction_steps')">
          <li v-for="(step, index) in ['categories', 'detect', 'review', 'apply', 'result']" :key="step" :class="{ current: redactionStep === index, complete: redactionStep > index }" :aria-current="redactionStep === index ? 'step' : undefined">
            <span aria-hidden="true">{{ index + 1 }}</span>{{ t(`tools.refinement.step_${step}`) }}
          </li>
        </ol>
        <p v-if="redactionJob?.status === 'failed'" class="task-error" role="alert">{{ jobError(redactionJob) }}</p>
        <p v-if="redactionJob?.status === 'completed'" class="completion-notice" role="status">{{ t('tools.refinement.redaction_result_help') }}</p>
        <div
          v-if="redactionJob && ['pending', 'running'].includes(redactionJob.status)"
          class="redaction-processing"
        >
          <p class="section-help">
            {{ t(redactionJob.options.operation === 'apply' ? 'tools.redaction.protected_processing' : 'tools.refinement.detecting_help') }}
          </p>
          <div class="job-progress">
            <progress :value="redactionJob.progress" max="100" :aria-label="t('tools.refinement.progress')"></progress>
            <span>{{ t(`tools.stage.${redactionJob.stage}`, redactionJob.stage) }} · {{ redactionJob.progress }}%</span>
          </div>
        </div>

        <div v-else-if="redactionJob?.status !== 'review'" class="redaction-setup">
          <p class="section-help">{{ t('tools.redaction.help') }}</p>
          <fieldset class="category-grid">
            <legend class="visually-hidden">{{ t('tools.refinement.step_categories') }}</legend>
            <label v-for="category in (['personal', 'financial', 'visual', 'service', 'context'] as RedactionCategory[])" :key="category" class="check-card">
              <input v-model="categories" type="checkbox" :value="category" />
              <span><strong>{{ t(`tools.redaction.${category}`) }}</strong><small>{{ t(`tools.redaction.${category}_help`) }}</small></span>
            </label>
          </fieldset>
          <button class="button primary" type="button" :disabled="submitting || !selectedDocumentId || !categories.length" @click="previewRedaction">{{ t('tools.redaction.find') }}</button>
        </div>

        <div v-else class="redaction-review">
          <p class="review-notice">{{ t('tools.refinement.review_notice') }}</p>
          <div class="review-toolbar">
            <div>
              <strong>{{ t('tools.redaction.found', { count: editableFindings.length }) }}</strong>
              <span class="redaction-editor-help">{{ t('tools.redaction.editor_help') }}</span>
              <span class="redaction-editor-help">{{ t('tools.refinement.keyboard_area_help') }}</span>
            </div>
            <div class="page-switcher">
              <button class="icon-btn" type="button" :disabled="currentPage <= 1" :aria-label="t('tools.protected_ai.preview.previous_page')" @click="currentPage--">‹</button>
              <span>{{ currentPage }} / {{ pageCount }}</span>
              <button class="icon-btn" type="button" :disabled="currentPage >= pageCount" :aria-label="t('tools.protected_ai.preview.next_page')" @click="currentPage++">›</button>
            </div>
          </div>
          <div v-if="previewFailed" class="task-error" role="alert">{{ t('tools.refinement.preview_failed') }} <button class="button" type="button" @click="previewFailed = false">{{ t('tools.refinement.retry') }}</button></div>
          <div v-else ref="previewElement" class="redaction-preview" @pointerdown="startDrawing">
            <img :src="toolsApi.pagePreviewUrl(redactionJob.id, currentPage)" :alt="t('tools.redaction.page_preview', { page: currentPage })" @error="previewFailed = true" />
            <div
              v-for="finding in pageFindings"
              :key="finding.id"
              class="finding-overlay"
              :class="{ excluded: !selectedFindingIds.includes(finding.id) }"
              :style="{ left: `${finding.rect.x}%`, top: `${finding.rect.y}%`, width: `${finding.rect.width}%`, height: `${finding.rect.height}%` }"
              :title="`${finding.category}: ${finding.text || t(finding.category === 'MANUAL' ? 'tools.redaction.manual_item' : 'tools.redaction.visual_item')}`"
            >
              <button class="finding-toggle" type="button" :aria-label="t('tools.refinement.toggle_finding', { finding: finding.text || t('tools.redaction.manual_item') })" :aria-pressed="selectedFindingIds.includes(finding.id)" @click.stop="toggleFinding(finding.id)">
                {{ selectedFindingIds.includes(finding.id) ? '✓' : '×' }}
              </button>
              <button
                v-for="handle in (['nw', 'ne', 'sw', 'se'] as ResizeHandle[])"
                :key="handle"
                class="resize-handle"
                :class="`resize-${handle}`"
                type="button"
                :aria-label="t('tools.redaction.resize_area')"
                @pointerdown="startResize($event, finding, handle)"
                @keydown="resizeWithKeyboard($event, finding, handle)"
              ></button>
            </div>
            <div
              v-if="draftRect"
              class="finding-overlay draft"
              :style="{ left: `${draftRect.x}%`, top: `${draftRect.y}%`, width: `${draftRect.width}%`, height: `${draftRect.height}%` }"
            ></div>
          </div>
          <button class="button add-area" type="button" :disabled="previewFailed" @click="addManualArea">{{ t('tools.refinement.add_area') }}</button>
          <p v-if="!editableFindings.length" class="control-help">{{ t('tools.refinement.no_findings') }}</p>
          <div class="finding-list">
            <label v-for="finding in pageFindings" :key="finding.id">
              <input v-model="selectedFindingIds" type="checkbox" :value="finding.id" />
              <span>{{ finding.category }} · {{ finding.text || t(finding.category === 'MANUAL' ? 'tools.redaction.manual_item' : 'tools.redaction.visual_item') }}</span>
            </label>
          </div>
          <div class="apply-bar">
            <label><input v-model="redactionMode" type="radio" value="black" /> {{ t('tools.redaction.black') }}</label>
            <label><input v-model="redactionMode" type="radio" value="pseudonymize" /> {{ t('tools.redaction.pseudonymize') }}</label>
            <button class="button primary" type="button" :disabled="submitting || !selectedFindingIds.length || previewFailed" @click="applyRedaction">{{ t('tools.redaction.apply', { count: selectedFindingIds.length }) }}</button>
          </div>
        </div>
      </div>
    </section>

    <ProtectedArtifactAI
      v-if="activeTool === 'redaction' && protectedArtifact"
      :key="protectedArtifact.id"
      :artifact="protectedArtifact"
      :source-job="redactionJob"
      :initial-task="requestedTask"
      @deleted="artifactDeleted"
    />

    <section class="recent-tasks" aria-labelledby="recent-tasks-title" :aria-busy="loadingWorkspace">
      <h3 id="recent-tasks-title">{{ t('tools.refinement.recent_tasks') }}</h3>
      <p v-if="loadingWorkspace" role="status" class="control-help">{{ t('tools.refinement.loading_tasks') }}</p>
      <p v-else-if="workspaceLoadFailed" class="task-error" role="alert">{{ t('tools.refinement.load_failed') }} <button class="button" type="button" @click="loadWorkspace">{{ t('tools.refinement.retry') }}</button></p>
      <p v-else-if="!jobs.length" class="control-help">{{ t('tools.refinement.no_tasks') }}</p>
      <div v-if="jobs.length" class="task-list">
        <div class="task-column-headings" aria-hidden="true"><span>{{ t('tools.refinement.document') }}</span><span>{{ t('tools.refinement.operation') }}</span><span>{{ t('tools.refinement.status') }}</span><span>{{ t('tools.refinement.result') }}</span><span>{{ t('tools.refinement.action') }}</span></div>
        <article v-for="job in jobs" :key="job.id" class="task-row" :aria-label="`${job.source_filename}: ${t(`tools.kind.${job.kind}`)}`">
          <strong class="task-filename">{{ job.source_filename }}</strong>
          <span class="task-operation">{{ t(`tools.kind.${job.kind}`) }}</span>
          <div class="task-status">
            <span class="task-badge" :class="jobTone(job)">{{ jobStatus(job) }}</span>
            <div v-if="['pending', 'running'].includes(job.status)" class="job-progress">
              <progress :value="job.progress" max="100" :aria-label="t('tools.refinement.progress')"></progress>
              <span>{{ t(`tools.stage.${job.stage}`, job.stage) }} · {{ job.progress }}%</span>
            </div>
          </div>
          <div class="task-result">
            <template v-if="job.status === 'failed'">
              <p class="task-error">{{ jobError(job) }}</p>
              <details v-if="job.error_message"><summary>{{ t('tools.refinement.error_details') }}</summary><p class="error-detail">{{ job.error_message }}</p></details>
            </template>
            <template v-else-if="job.kind === 'compression' && job.status === 'completed'">
              <span v-if="originalSize(job) !== null">{{ t('tools.refinement.original') }}: {{ formatBytes(originalSize(job)!) }}</span>
              <span v-if="job.result_size_bytes !== null">{{ t('tools.refinement.result') }}: {{ formatBytes(job.result_size_bytes) }}</span>
              <strong v-if="reduction(job) !== null" class="reduction">{{ t('tools.refinement.reduction', { percent: reduction(job) }) }}</strong>
            </template>
            <span v-else-if="job.status === 'review'">{{ t('tools.refinement.review_task_help') }}</span>
            <span v-else-if="job.status === 'completed' && job.result_size_bytes !== null">{{ formatBytes(job.result_size_bytes) }}</span>
            <span v-else>{{ t(job.kind === 'redaction' && job.options.operation !== 'apply' ? 'tools.refinement.detection_pending' : 'tools.refinement.result_pending') }}</span>
          </div>
          <div class="task-action">
            <a v-if="job.status === 'completed' && job.result_filename" class="button" :href="toolsApi.downloadUrl(job.id)" :aria-label="t('tools.refinement.download_file', { filename: job.result_filename })">{{ t('tools.refinement.download') }}</a>
            <button v-else-if="job.status === 'review'" class="button" type="button" @click="openJob(job)">{{ t('tools.refinement.review') }}</button>
            <button v-else-if="job.status === 'failed'" class="button" type="button" @click="openJob(job)">{{ t('tools.refinement.open_tool') }}</button>
          </div>
        </article>
      </div>
    </section>
  </main>
</template>

<style scoped>
.tools-page { gap: 20px; }
.tools-intro h2 { margin: 0; }
.tools-intro p { margin: 6px 0 0; color: var(--text-soft); }
.tool-tabs { display: flex; flex-wrap: wrap; gap: 6px; border-bottom: 1px solid var(--border-soft); }
.tool-tab { min-height: 44px; padding: 10px 18px; border: 0; border-bottom: 2px solid transparent; background: transparent; color: var(--text-soft); font: inherit; font-weight: 600; cursor: pointer; }
.tool-tab.active { border-bottom-color: var(--accent); color: var(--accent); }
.tool-source { display: grid; gap: 12px; }
.source-summary { display: flex; align-items: center; justify-content: space-between; gap: 20px; }
.source-label { display: grid; gap: 5px; min-width: 0; }
.source-label > span { color: var(--text-soft); font-size: 14px; }
.source-summary > .button { flex-shrink: 0; }
.source-filename, .task-filename { overflow-wrap: anywhere; min-width: 0; }
.document-picker { width: min(640px, 100%); font-size: 14px; }
.operation-surface { min-height: 0; border-radius: 10px; background: var(--surface); border: 1px solid var(--border-soft); }
.operation-surface > .panel-body { padding: 24px; }
.control-help, .section-help, .redaction-editor-help { font-size: 14px; line-height: 1.55; }
.tool-source .control-help { margin: 0; }
.compression-modes, .category-grid { border: 0; padding: 0; min-width: 0; }
.compression-modes .mode-card { background: transparent; box-shadow: none; }
.compression-modes .mode-card.selected { border-color: var(--text-soft); background: var(--surface-2); }
.mode-card small, .mode-card p { font-size: 14px; }
.conversion-grid { gap: 0; }
.conversion-operation { display: flex; flex-direction: column; align-items: flex-start; gap: 16px; padding: 24px; min-width: 0; }
.conversion-operation + .conversion-operation { border-left: 1px solid var(--border-soft); }
.conversion-operation h3, .conversion-operation p { margin: 0; }
.conversion-operation > .button { margin-top: auto; }
.word-source { display: flex; align-items: center; flex-wrap: wrap; gap: 12px; width: 100%; }
.word-source > span { color: var(--text-soft); font-size: 14px; }
.redaction-steps { display: flex; flex-wrap: wrap; gap: 12px 24px; list-style: none; padding: 0 0 20px; margin: 0 0 20px; border-bottom: 1px solid var(--border-soft); }
.redaction-steps li { display: flex; align-items: center; gap: 8px; color: var(--text-soft); font-size: 14px; }
.redaction-steps li > span { display: grid; place-items: center; width: 24px; height: 24px; border-radius: 50%; background: var(--surface-2); }
.redaction-steps li.current { color: var(--text); font-weight: 600; }
.redaction-steps li.current > span { box-shadow: inset 0 0 0 1px var(--accent); }
.redaction-steps li.complete > span { color: var(--success); }
.category-grid { display: grid; grid-template-columns: 1fr; gap: 0; margin: 12px 0 20px; }
.check-card { border: 0; border-radius: 0; padding: 13px 0; background: transparent; align-items: start; gap: 12px; }
.check-card + .check-card { border-top: 1px solid var(--border-soft); }
.check-card input { margin-top: 4px; }
.check-card span { display: grid; grid-template-columns: 180px 1fr; gap: 18px; width: 100%; }
.check-card small { font-size: 14px; }
.review-notice, .completion-notice { color: var(--text); background: var(--surface-2); padding: 12px 16px; border-radius: 6px; line-height: 1.55; }
.add-area { margin-top: 14px; }
.finding-list label { font-size: 14px; padding: 6px 0; overflow-wrap: anywhere; }
.review-toolbar { gap: 18px; }
.review-toolbar > div:first-child { min-width: 0; }
.page-switcher { white-space: nowrap; }
.job-progress span { font-size: 14px; }
.recent-tasks { border-top: 1px solid var(--border-soft); padding-top: 20px; }
.recent-tasks h3 { margin: 0 0 16px; }
.task-row, .task-column-headings { display: grid; grid-template-columns: minmax(180px, 2fr) minmax(110px, 1fr) minmax(120px, 1fr) minmax(180px, 1.4fr) 115px; align-items: start; gap: 16px; }
.task-column-headings { padding: 0 0 12px; color: var(--text-soft); font-size: 14px; }
.task-row { padding: 18px 0; border-top: 1px solid var(--border-soft); font-size: 14px; }
.task-filename { color: var(--text); font-size: 15px; }
.task-operation, .task-result { color: var(--text-soft); }
.task-status, .task-result { display: grid; gap: 7px; min-width: 0; }
.task-badge { display: inline-flex; justify-self: start; width: fit-content; max-width: 100%; border-radius: 5px; padding: 3px 8px; line-height: 1.4; background: var(--surface-2); color: var(--text-soft); }
.task-badge.completed { color: var(--success); background: var(--success-soft); }
.task-badge.failed { color: var(--danger); background: var(--danger-soft); }
.task-badge.review { color: var(--warning); background: var(--warning-soft); }
.task-action { justify-self: end; }
.task-action .button { font-size: 14px; }
.task-error { margin: 0; color: var(--danger); line-height: 1.55; overflow-wrap: anywhere; }
.task-error > .button { margin-left: 8px; }
.task-result summary { cursor: pointer; color: var(--text-soft); }
.error-detail { margin: 8px 0 0; overflow-wrap: anywhere; }
.reduction { font-weight: 500; color: var(--success); }
.visually-hidden { position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px; overflow: hidden; clip: rect(0, 0, 0, 0); white-space: nowrap; border: 0; }
@media (max-width: 1050px) {
  .task-column-headings { display: none; }
  .task-row { grid-template-columns: minmax(0, 1.7fr) minmax(0, 1fr) auto; }
  .task-operation { grid-column: 1; grid-row: 2; }
  .task-status { grid-column: 2; grid-row: 1; }
  .task-result { grid-column: 2; grid-row: 2; }
  .task-action { grid-column: 3; grid-row: 1 / 3; }
}
@media (max-width: 760px) {
  .operation-surface > .panel-body, .conversion-operation { padding: 18px; }
  .check-card span { grid-template-columns: 1fr; gap: 4px; }
  .conversion-operation + .conversion-operation { border-left: 0; border-top: 1px solid var(--border-soft); }
  .source-summary, .review-toolbar { align-items: flex-start; flex-direction: column; }
  .task-row { grid-template-columns: minmax(0, 1fr) auto; gap: 10px 12px; }
  .task-filename { grid-column: 1 / -1; }
  .task-operation { grid-column: 1; grid-row: 2; }
  .task-status { grid-column: 1; grid-row: 3; }
  .task-result { grid-column: 1 / -1; grid-row: 4; }
  .task-action { grid-column: 2; grid-row: 2 / 4; }
  .tool-tab { padding-inline: 11px; }
  .apply-bar .button { margin-left: 0; }
}
</style>
