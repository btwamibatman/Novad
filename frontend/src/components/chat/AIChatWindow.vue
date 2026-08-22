<script setup lang="ts">
import {
  computed,
  nextTick,
  onBeforeUnmount,
  onMounted,
  ref,
  watch,
} from 'vue'
import { useI18n } from 'vue-i18n'

import { aiAnalysisApi } from '@/api/ai'
import { useDocumentChat } from '@/composables/useDocumentChat'
import { useDocumentsStore } from '@/stores/documents'
import type { AIProviderInfo } from '@/types/document'

interface DragState {
  pointerId: number
  offsetX: number
  offsetY: number
}

const { t } = useI18n()
const documentsStore = useDocumentsStore()
const chat = useDocumentChat()
const popup = ref<HTMLElement | null>(null)
const dragHandle = ref<HTMLElement | null>(null)
const input = ref<HTMLTextAreaElement | null>(null)
const messageList = ref<HTMLElement | null>(null)
const question = ref('')
const providerInfo = ref<AIProviderInfo | null>(null)
const providerInfoState = ref<'loading' | 'ready' | 'error'>('loading')
let drag: DragState | null = null

const positioned = computed(() => Boolean(chat.position.value) && !chat.maximized.value)
const style = computed(() =>
  positioned.value && chat.position.value
    ? {
        left: `${chat.position.value.left}px`,
        top: `${chat.position.value.top}px`,
      }
    : {},
)
const disabled = computed(
  () => !chat.selectedDocument.value || documentsStore.busy || chat.asking.value,
)
const stateText = computed(() =>
  chat.selectedDocument.value
    ? t('chat.answering_from', { id: chat.selectedDocument.value.id })
    : t('chat.analyze_first'),
)
const providerDisclosure = computed(() => {
  if (providerInfo.value) {
    return t('chat.provider_disclosure', {
      provider: providerInfo.value.provider,
      model: providerInfo.value.model,
      tier: providerInfo.value.service_tier,
    })
  }
  return t(
    providerInfoState.value === 'error'
      ? 'chat.provider_unavailable'
      : 'chat.provider_loading',
  )
})

function move(left: number, top: number): void {
  if (!popup.value) return
  const rect = popup.value.getBoundingClientRect()
  const margin = 8
  const maxLeft = Math.max(margin, window.innerWidth - rect.width - margin)
  const maxTop = Math.max(margin, window.innerHeight - rect.height - margin)
  chat.position.value = {
    left: Math.min(Math.max(margin, left), maxLeft),
    top: Math.min(Math.max(margin, top), maxTop),
  }
}

function stopDrag(event?: PointerEvent): void {
  if (!drag || (event && event.pointerId !== drag.pointerId)) return
  if (dragHandle.value?.hasPointerCapture(drag.pointerId)) {
    dragHandle.value.releasePointerCapture(drag.pointerId)
  }
  drag = null
  document.body.classList.remove('ai-chat-dragging')
}

function startDrag(event: PointerEvent): void {
  const target = event.target as Element
  if (
    chat.maximized.value ||
    event.button !== 0 ||
    target.closest('button, input, select, textarea, a') ||
    !popup.value
  ) {
    return
  }
  const rect = popup.value.getBoundingClientRect()
  drag = {
    pointerId: event.pointerId,
    offsetX: event.clientX - rect.left,
    offsetY: event.clientY - rect.top,
  }
  move(rect.left, rect.top)
  dragHandle.value?.setPointerCapture(event.pointerId)
  document.body.classList.add('ai-chat-dragging')
  event.preventDefault()
}

function continueDrag(event: PointerEvent): void {
  if (!drag || event.pointerId !== drag.pointerId) return
  move(event.clientX - drag.offsetX, event.clientY - drag.offsetY)
}

function toggleMaximized(): void {
  stopDrag()
  chat.maximized.value = !chat.maximized.value
  if (!chat.maximized.value && chat.position.value) {
    move(chat.position.value.left, chat.position.value.top)
  }
}

async function toggleOpen(): Promise<void> {
  chat.open.value = !chat.open.value
  if (chat.open.value) {
    await nextTick()
    input.value?.focus()
  }
}

function changeDocument(event: Event): void {
  chat.abortRequest()
  const value = Number((event.target as HTMLSelectElement).value)
  chat.selectedDocumentId.value = value || null
}

async function submit(): Promise<void> {
  const currentQuestion = question.value
  if (!currentQuestion.trim()) return
  question.value = ''
  await chat.ask(currentQuestion)
}

function keepInsideViewport(): void {
  if (!chat.maximized.value && chat.position.value) {
    move(chat.position.value.left, chat.position.value.top)
  }
}

function stopDragOnBlur(): void {
  stopDrag()
}

watch(
  () => chat.messages.value,
  async () => {
    await nextTick()
    if (messageList.value) {
      messageList.value.scrollTop = messageList.value.scrollHeight
    }
  },
  { deep: true },
)

onMounted(async () => {
  window.addEventListener('blur', stopDragOnBlur)
  window.addEventListener('resize', keepInsideViewport)
  try {
    providerInfo.value = await aiAnalysisApi.getProviderInfo()
    providerInfoState.value = 'ready'
  } catch {
    providerInfo.value = null
    providerInfoState.value = 'error'
  }
})

onBeforeUnmount(() => {
  window.removeEventListener('blur', stopDragOnBlur)
  window.removeEventListener('resize', keepInsideViewport)
  chat.clearSessionMessages()
  stopDrag()
})
</script>

<template>
  <section
    v-show="chat.open.value"
    ref="popup"
    class="ai-chat-popup"
    :class="{ positioned, maximized: chat.maximized.value }"
    :style="style"
    :aria-label="t('chat.label')"
  >
    <div
      ref="dragHandle"
      class="ai-chat-head"
      @pointerdown="startDrag"
      @pointermove="continueDrag"
      @pointerup="stopDrag"
      @pointercancel="stopDrag"
    >
      <div>
        <h2 class="panel-title">{{ t('chat.title') }}</h2>
        <p class="ai-chat-subtitle">{{ stateText }}</p>
      </div>
      <div class="ai-chat-head-actions">
        <button
          class="button small icon-btn"
          type="button"
          :aria-label="t(chat.maximized.value ? 'chat.restore' : 'chat.maximize')"
          :title="t(chat.maximized.value ? 'chat.restore' : 'chat.maximize')"
          @click="toggleMaximized"
        >
          <span aria-hidden="true">{{ chat.maximized.value ? '❐' : '⛶' }}</span>
        </button>
        <button
          class="button small icon-btn"
          type="button"
          :aria-label="t('chat.close')"
          @click="chat.open.value = false"
        >
          ×
        </button>
      </div>
    </div>
    <div class="ai-chat-body">
      <div class="ai-chat-context">
        <select
          class="select"
          :value="chat.selectedDocumentId.value ?? ''"
          :aria-label="t('chat.document_select')"
          :disabled="!chat.processedDocuments.value.length"
          @change="changeDocument"
        >
          <option v-if="!chat.processedDocuments.value.length" value="">
            {{ t('chat.no_processed') }}
          </option>
          <option
            v-for="document in chat.processedDocuments.value"
            :key="document.id"
            :value="document.id"
          >
            #{{ document.id }} {{ document.filename }}
          </option>
        </select>
        <p class="control-help">
          {{ t('chat.extracted_text_notice') }} {{ providerDisclosure }}
          <a
            v-if="providerInfo?.provider.toLowerCase() === 'gemini'"
            href="https://ai.google.dev/gemini-api/terms"
            target="_blank"
            rel="noopener noreferrer"
          >{{ t('chat.provider_terms') }}</a>
        </p>
      </div>
      <div ref="messageList" class="ai-chat-messages">
        <div v-if="!chat.selectedDocument.value" class="empty">
          {{ t('chat.processed_appear') }}
        </div>
        <div v-else-if="!chat.messages.value.length" class="empty">
          {{ t('chat.ask_question') }}
        </div>
        <div
          v-for="(message, index) in chat.messages.value"
          v-else
          :key="`${message.role}-${index}`"
          class="ai-chat-message"
          :class="message.role"
        >
          {{ message.content }}
        </div>
      </div>
      <form class="ai-chat-form" @submit.prevent="submit">
        <textarea
          ref="input"
          v-model="question"
          class="field ai-chat-input"
          rows="3"
          maxlength="1000"
          :placeholder="t('chat.placeholder')"
          :disabled="disabled"
        ></textarea>
        <button class="button primary" type="submit" :disabled="disabled">
          {{ t('chat.send') }}
        </button>
      </form>
    </div>
  </section>
  <button
    class="ai-chat-toggle"
    type="button"
    :aria-label="t('chat.open')"
    @click="toggleOpen"
  >
    AI
  </button>
</template>

<style scoped>
.ai-chat-context {
  display: grid;
  gap: 8px;
}

.ai-chat-context .control-help {
  margin: 0;
}
</style>
