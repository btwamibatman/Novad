<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import { toolsApi } from '@/api/tools'
import { useApiErrorHandler } from '@/composables/useApiErrorHandler'
import { useToasts } from '@/composables/useToasts'
import { useDocumentsStore } from '@/stores/documents'
import type {
  CompressionMode,
  RedactionCategory,
  RedactionMode,
  ToolJobRead,
} from '@/types/document'
import { formatBytes } from '@/utils/format'

type Tool = 'redaction' | 'compression' | 'conversion'

const { t } = useI18n()
const documentsStore = useDocumentsStore()
const { handle } = useApiErrorHandler()
const { show } = useToasts()
const activeTool = ref<Tool>('redaction')
const jobs = ref<ToolJobRead[]>([])
const selectedDocumentId = ref<number | null>(null)
const compressionMode = ref<CompressionMode>('recommended')
const wordFile = ref<File | null>(null)
const categories = ref<RedactionCategory[]>(['personal', 'financial'])
const redactionMode = ref<RedactionMode>('black')
const redactionJobId = ref<number | null>(null)
const selectedFindingIds = ref<string[]>([])
const currentPage = ref(1)
const submitting = ref(false)
let pollTimer: ReturnType<typeof setInterval> | null = null

const pdfDocuments = computed(() =>
  documentsStore.documents.filter((document) => document.content_type === 'application/pdf'),
)
const redactionJob = computed(
  () => jobs.value.find((job) => job.id === redactionJobId.value) ?? null,
)
const pageCount = computed(() => Number(redactionJob.value?.result_meta.page_count ?? 1))
const pageFindings = computed(() =>
  (redactionJob.value?.findings ?? []).filter((finding) => finding.page === currentPage.value),
)
const hasRunningJobs = computed(() =>
  jobs.value.some((job) => ['pending', 'running'].includes(job.status)),
)

watch(
  () => redactionJob.value?.status,
  (status) => {
    if (status === 'review' && redactionJob.value) {
      selectedFindingIds.value = redactionJob.value.findings.map((finding) => finding.id)
      currentPage.value = redactionJob.value.findings[0]?.page ?? 1
    }
  },
)

async function loadJobs(): Promise<void> {
  try {
    jobs.value = await toolsApi.listJobs()
  } catch (error) {
    handle(error)
  }
}

async function run(request: () => Promise<ToolJobRead>): Promise<void> {
  submitting.value = true
  try {
    const job = await request()
    jobs.value = [job, ...jobs.value.filter((item) => item.id !== job.id)]
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
      selectedFindingIds.value,
      redactionMode.value,
    ),
  )
}

function toggleFinding(id: string): void {
  selectedFindingIds.value = selectedFindingIds.value.includes(id)
    ? selectedFindingIds.value.filter((item) => item !== id)
    : [...selectedFindingIds.value, id]
}

function chooseFile(event: Event): void {
  wordFile.value = (event.target as HTMLInputElement).files?.[0] ?? null
}

onMounted(async () => {
  if (!documentsStore.documents.length) await documentsStore.load(false)
  selectedDocumentId.value = documentsStore.selectedId ?? pdfDocuments.value[0]?.id ?? null
  await loadJobs()
  pollTimer = setInterval(() => {
    if (hasRunningJobs.value) void loadJobs()
  }, 1500)
})

onBeforeUnmount(() => {
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
        <select v-model="selectedDocumentId" class="select">
          <option :value="null">{{ t('tools.choose_pdf') }}</option>
          <option v-for="document in pdfDocuments" :key="document.id" :value="document.id">
            {{ document.filename }} · {{ formatBytes(document.size_bytes) }}
          </option>
        </select>
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
        <div v-if="redactionJob?.status !== 'review'" class="redaction-setup">
          <p class="section-help">{{ t('tools.redaction.help') }}</p>
          <div class="category-grid">
            <label v-for="category in (['personal', 'financial', 'visual', 'service'] as RedactionCategory[])" :key="category" class="check-card">
              <input v-model="categories" type="checkbox" :value="category" />
              <span><strong>{{ t(`tools.redaction.${category}`) }}</strong><small>{{ t(`tools.redaction.${category}_help`) }}</small></span>
            </label>
          </div>
          <button class="button primary" type="button" :disabled="submitting || !selectedDocumentId || !categories.length" @click="previewRedaction">{{ t('tools.redaction.find') }}</button>
        </div>

        <div v-else class="redaction-review">
          <div class="review-toolbar">
            <strong>{{ t('tools.redaction.found', { count: redactionJob.findings.length }) }}</strong>
            <div class="page-switcher">
              <button class="icon-btn" type="button" :disabled="currentPage <= 1" @click="currentPage--">‹</button>
              <span>{{ currentPage }} / {{ pageCount }}</span>
              <button class="icon-btn" type="button" :disabled="currentPage >= pageCount" @click="currentPage++">›</button>
            </div>
          </div>
          <div class="redaction-preview">
            <img :src="toolsApi.pagePreviewUrl(redactionJob.id, currentPage)" :alt="t('tools.redaction.page_preview', { page: currentPage })" />
            <button
              v-for="finding in pageFindings"
              :key="finding.id"
              class="finding-overlay"
              :class="{ excluded: !selectedFindingIds.includes(finding.id) }"
              :style="{ left: `${finding.rect.x}%`, top: `${finding.rect.y}%`, width: `${finding.rect.width}%`, height: `${finding.rect.height}%` }"
              type="button"
              :title="`${finding.category}: ${finding.text || t('tools.redaction.visual_item')}`"
              @click="toggleFinding(finding.id)"
            >
              <span>{{ selectedFindingIds.includes(finding.id) ? '✓' : '×' }}</span>
            </button>
          </div>
          <div class="finding-list">
            <label v-for="finding in pageFindings" :key="finding.id">
              <input v-model="selectedFindingIds" type="checkbox" :value="finding.id" />
              <span>{{ finding.category }} · {{ finding.text || t('tools.redaction.visual_item') }}</span>
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
