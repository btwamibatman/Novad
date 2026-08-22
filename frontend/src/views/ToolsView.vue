<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
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
let interaction: RedactionInteraction | null = null
let manualFindingSequence = 0
let hydratedReviewJobId: number | null = null
let pollTimer: ReturnType<typeof setInterval> | null = null

const pdfDocuments = computed(() =>
  documentsStore.documents.filter((document) => document.content_type === 'application/pdf'),
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
  const linkedId = redactionJob.value?.result_artifact_id
  const linked = artifacts.value.find((artifact) => artifact.id === linkedId)
  if (linked) return linked
  if (
    redactionJob.value &&
    ['pending', 'running', 'review'].includes(redactionJob.value.status)
  ) {
    return null
  }
  const explicitlySelected = artifacts.value.find(
    (artifact) => artifact.id === selectedArtifactId.value,
  )
  if (explicitlySelected) return explicitlySelected
  const sourceId = redactionJob.value?.source_document_id ?? selectedDocumentId.value
  return artifacts.value.find((artifact) => artifact.source_document_id === sourceId) ?? null
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

function restoreWorkspaceSelection(): void {
  let job = jobs.value.find(
    (item) => item.id === redactionJobId.value && item.kind === 'redaction',
  )
  if (!job) {
    const preferredSourceId = selectedDocumentId.value
    const restrictToRequestedDocument = requestedDocumentId.value === preferredSourceId
    job =
      jobs.value.find(
        (item) =>
          item.kind === 'redaction' &&
          item.status === 'review' &&
          item.source_document_id === preferredSourceId,
      ) ??
      (!restrictToRequestedDocument
        ? jobs.value.find((item) => item.kind === 'redaction' && item.status === 'review')
        : undefined) ??
      jobs.value.find(
        (item) =>
          item.kind === 'redaction' &&
          ['pending', 'running'].includes(item.status) &&
          item.source_document_id === preferredSourceId,
      ) ??
      (!restrictToRequestedDocument
        ? jobs.value.find(
            (item) => item.kind === 'redaction' && ['pending', 'running'].includes(item.status),
          )
        : undefined) ??
      jobs.value.find(
        (item) =>
          item.kind === 'redaction' &&
          item.result_artifact_id !== null &&
          item.source_document_id === preferredSourceId,
      ) ??
      (!restrictToRequestedDocument
        ? jobs.value.find(
            (item) => item.kind === 'redaction' && item.result_artifact_id !== null,
          )
        : undefined)
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
  try {
    const [loadedJobs, loadedArtifacts] = await Promise.all([
      toolsApi.listJobs(),
      toolsApi.listArtifacts(),
    ])
    jobs.value = loadedJobs
    artifacts.value = loadedArtifacts
    restoreWorkspaceSelection()
  } catch (error) {
    handle(error)
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

function artifactDeleted(artifactId: number): void {
  artifacts.value = artifacts.value.filter((artifact) => artifact.id !== artifactId)
  if (selectedArtifactId.value === artifactId) selectedArtifactId.value = null
  void loadWorkspace()
}

onMounted(async () => {
  window.addEventListener('pointermove', pointerMove)
  window.addEventListener('pointerup', pointerUp)
  window.addEventListener('pointercancel', cancelInteraction)
  if (!documentsStore.documents.length) await documentsStore.load(false)
  const linkedDocumentId = pdfDocuments.value.some(
    (document) => document.id === requestedDocumentId.value,
  )
    ? requestedDocumentId.value
    : null
  selectedDocumentId.value = linkedDocumentId ?? documentsStore.selectedId ?? pdfDocuments.value[0]?.id ?? null
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
    <header class="page-intro">
      <div>
        <span class="eyebrow">{{ t('tools.local_label') }}</span>
        <h2>{{ t('tools.title') }}</h2>
        <p>{{ t('tools.subtitle') }}</p>
      </div>
      <label class="document-picker">
        <span>{{ t('tools.source_document') }}</span>
        <select
          v-model="selectedDocumentId"
          class="select"
          :disabled="sourceLocked"
          @change="sourceDocumentChanged"
        >
          <option :value="null">{{ t('tools.choose_pdf') }}</option>
          <option v-for="document in pdfDocuments" :key="document.id" :value="document.id">
            {{ document.filename }} · {{ formatBytes(document.size_bytes) }}
          </option>
        </select>
        <small v-if="sourceLocked">{{ t('tools.redaction.source_locked') }}</small>
      </label>
    </header>

    <nav class="tool-cards" :aria-label="t('tools.title')">
      <button
        v-for="tool in (['redaction', 'compression', 'conversion'] as Tool[])"
        :key="tool"
        class="tool-card"
        :class="{ active: activeTool === tool }"
        type="button"
        @click="activeTool = tool"
      >
        <span class="tool-icon" aria-hidden="true">{{ tool === 'redaction' ? '▰' : tool === 'compression' ? '↘' : '⇄' }}</span>
        <strong>{{ t(`tools.${tool}.title`) }}</strong>
        <span>{{ t(`tools.${tool}.description`) }}</span>
      </button>
    </nav>

    <section v-if="activeTool === 'compression'" class="tool-workspace panel">
      <div class="panel-head"><h3 class="panel-title">{{ t('tools.compression.title') }}</h3></div>
      <div class="panel-body">
        <div class="compression-modes">
          <label v-for="mode in (['low', 'recommended', 'extreme'] as CompressionMode[])" :key="mode" class="mode-card" :class="{ selected: compressionMode === mode }">
            <input v-model="compressionMode" type="radio" :value="mode" />
            <span><strong>{{ t(`tools.compression.${mode}`) }}</strong><em v-if="mode === 'recommended'">{{ t('tools.recommended') }}</em></span>
            <small>{{ t(`tools.compression.${mode}_saving`) }}</small>
            <p>{{ t(`tools.compression.${mode}_help`) }}</p>
          </label>
        </div>
        <p class="control-help">{{ t('tools.compression.estimate_note') }}</p>
        <button class="button primary" type="button" :disabled="submitting || !selectedDocumentId" @click="compress">
          {{ t('tools.compression.action') }}
        </button>
      </div>
    </section>

    <section v-else-if="activeTool === 'conversion'" class="tool-workspace conversion-grid">
      <article class="panel">
        <div class="panel-head"><h3 class="panel-title">Word → PDF</h3></div>
        <div class="panel-body">
          <p class="section-help">{{ t('tools.conversion.word_help') }}</p>
          <input class="file-field" type="file" accept=".doc,.docx,.odt" @change="chooseFile" />
          <button class="button primary" type="button" :disabled="submitting || !wordFile" @click="convertWord">{{ t('tools.conversion.to_pdf') }}</button>
        </div>
      </article>
      <article class="panel">
        <div class="panel-head"><h3 class="panel-title">PDF → Word <span class="beta">Beta</span></h3></div>
        <div class="panel-body">
          <p class="section-help">{{ t('tools.conversion.pdf_help') }}</p>
          <p class="control-help">{{ t('tools.conversion.ocr_help') }}</p>
          <button class="button primary" type="button" :disabled="submitting || !selectedDocumentId" @click="convertPdf">{{ t('tools.conversion.to_word') }}</button>
        </div>
      </article>
    </section>

    <section v-else class="tool-workspace panel">
      <div class="panel-head"><h3 class="panel-title">{{ t('tools.redaction.title') }}</h3></div>
      <div class="panel-body">
        <div
          v-if="redactionJob && ['pending', 'running'].includes(redactionJob.status)"
          class="redaction-processing"
        >
          <p class="section-help">
            {{ t('tools.redaction.protected_processing') }}
          </p>
          <div class="job-progress">
            <progress :value="redactionJob.progress" max="100"></progress>
            <span>{{ t(`tools.stage.${redactionJob.stage}`, redactionJob.stage) }} · {{ redactionJob.progress }}%</span>
          </div>
        </div>

        <div v-else-if="redactionJob?.status !== 'review'" class="redaction-setup">
          <p class="section-help">{{ t('tools.redaction.help') }}</p>
          <div class="category-grid">
            <label v-for="category in (['personal', 'financial', 'visual', 'service', 'context'] as RedactionCategory[])" :key="category" class="check-card">
              <input v-model="categories" type="checkbox" :value="category" />
              <span><strong>{{ t(`tools.redaction.${category}`) }}</strong><small>{{ t(`tools.redaction.${category}_help`) }}</small></span>
            </label>
          </div>
          <button class="button primary" type="button" :disabled="submitting || !selectedDocumentId || !categories.length" @click="previewRedaction">{{ t('tools.redaction.find') }}</button>
        </div>

        <div v-else class="redaction-review">
          <div class="review-toolbar">
            <div>
              <strong>{{ t('tools.redaction.found', { count: editableFindings.length }) }}</strong>
              <small class="redaction-editor-help">{{ t('tools.redaction.editor_help') }}</small>
            </div>
            <div class="page-switcher">
              <button class="icon-btn" type="button" :disabled="currentPage <= 1" @click="currentPage--">‹</button>
              <span>{{ currentPage }} / {{ pageCount }}</span>
              <button class="icon-btn" type="button" :disabled="currentPage >= pageCount" @click="currentPage++">›</button>
            </div>
          </div>
          <div ref="previewElement" class="redaction-preview" @pointerdown="startDrawing">
            <img :src="toolsApi.pagePreviewUrl(redactionJob.id, currentPage)" :alt="t('tools.redaction.page_preview', { page: currentPage })" />
            <div
              v-for="finding in pageFindings"
              :key="finding.id"
              class="finding-overlay"
              :class="{ excluded: !selectedFindingIds.includes(finding.id) }"
              :style="{ left: `${finding.rect.x}%`, top: `${finding.rect.y}%`, width: `${finding.rect.width}%`, height: `${finding.rect.height}%` }"
              :title="`${finding.category}: ${finding.text || t(finding.category === 'MANUAL' ? 'tools.redaction.manual_item' : 'tools.redaction.visual_item')}`"
            >
              <button class="finding-toggle" type="button" @click.stop="toggleFinding(finding.id)">
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
              ></button>
            </div>
            <div
              v-if="draftRect"
              class="finding-overlay draft"
              :style="{ left: `${draftRect.x}%`, top: `${draftRect.y}%`, width: `${draftRect.width}%`, height: `${draftRect.height}%` }"
            ></div>
          </div>
          <div class="finding-list">
            <label v-for="finding in pageFindings" :key="finding.id">
              <input v-model="selectedFindingIds" type="checkbox" :value="finding.id" />
              <span>{{ finding.category }} · {{ finding.text || t(finding.category === 'MANUAL' ? 'tools.redaction.manual_item' : 'tools.redaction.visual_item') }}</span>
            </label>
          </div>
          <div class="apply-bar">
            <label><input v-model="redactionMode" type="radio" value="black" /> {{ t('tools.redaction.black') }}</label>
            <label><input v-model="redactionMode" type="radio" value="pseudonymize" /> {{ t('tools.redaction.pseudonymize') }}</label>
            <button class="button primary" type="button" :disabled="submitting || !selectedFindingIds.length" @click="applyRedaction">{{ t('tools.redaction.apply', { count: selectedFindingIds.length }) }}</button>
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

    <section class="jobs-panel panel">
      <div class="panel-head"><h3 class="panel-title">{{ t('tools.jobs') }}</h3></div>
      <div class="job-list panel-body">
        <p v-if="!jobs.length" class="compact-empty">{{ t('tools.no_jobs') }}</p>
        <article v-for="job in jobs" v-else :key="job.id" class="job-row">
          <div><strong>{{ job.source_filename }}</strong><span>{{ t(`tools.kind.${job.kind}`) }}</span></div>
          <div v-if="['pending', 'running'].includes(job.status)" class="job-progress"><progress :value="job.progress" max="100"></progress><span>{{ t(`tools.stage.${job.stage}`, job.stage) }} · {{ job.progress }}%</span></div>
          <span v-else class="badge" :class="job.status === 'completed' ? 'processed' : job.status === 'failed' ? 'failed' : 'neutral'">{{ t(`tools.status.${job.status}`) }}</span>
          <span v-if="job.kind === 'compression' && job.status === 'completed'" class="saving">−{{ job.result_meta.savings_percent ?? 0 }}%</span>
          <a v-if="job.status === 'completed'" class="button small" :href="toolsApi.downloadUrl(job.id)">{{ t('documents.download') }}</a>
          <span v-if="job.error_message" class="job-error">{{ job.error_message }}</span>
        </article>
      </div>
    </section>
  </main>
</template>
