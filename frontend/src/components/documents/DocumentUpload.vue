<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import { useApiErrorHandler } from '@/composables/useApiErrorHandler'
import { useToasts } from '@/composables/useToasts'
import { useDocumentsStore } from '@/stores/documents'

const { t } = useI18n()
const emit = defineEmits<{ close: [] }>()
const documentsStore = useDocumentsStore()
const { handle } = useApiErrorHandler()
const { show } = useToasts()
const fileInput = ref<HTMLInputElement | null>(null)
const selectedFile = ref<File | null>(null)
const dragover = ref(false)
const fileTrigger = ref<HTMLButtonElement | null>(null)

onMounted(() => fileTrigger.value?.focus())

function updateFile(event: Event): void {
  const input = event.target as HTMLInputElement
  selectedFile.value = input.files?.[0] ?? null
}

async function upload(file: File | null): Promise<void> {
  if (documentsStore.busy) return
  if (!file) {
    show(t('upload.choose_pdf'), 'error')
    return
  }
  if (!file.name.toLocaleLowerCase().endsWith('.pdf')) {
    show(t('upload.pdf_only'), 'error')
    return
  }
  try {
    await documentsStore.upload(file)
    selectedFile.value = null
    if (fileInput.value) {
      fileInput.value.value = ''
    }
    show(t('upload.completed'), 'success')
    emit('close')
  } catch (error) {
    handle(error)
  }
}

function drop(event: DragEvent): void {
  dragover.value = false
  if (!documentsStore.busy) selectedFile.value = event.dataTransfer?.files[0] ?? null
}
</script>

<template>
  <section class="upload-area" :aria-label="t('upload.title')" @keydown.esc.stop.prevent="emit('close')">
      <form @submit.prevent="upload(selectedFile)">
        <div
          class="upload-zone"
          :class="{ dragover }"
          @dragover.prevent="dragover = true"
          @dragleave="dragover = false"
          @drop.prevent="drop"
        >
          <div>
            <p class="upload-title">{{ t('upload.add_document') }}</p>
            <p id="upload-help" class="upload-copy">{{ t('upload.help') }}</p>
          </div>
          <input
            ref="fileInput"
            hidden
            type="file"
            accept=".pdf,application/pdf"
            tabindex="-1"
            @change="updateFile"
          />
          <div class="upload-file-choice">
            <button ref="fileTrigger" class="button" type="button" :disabled="documentsStore.busy" aria-describedby="upload-help" @click="fileInput?.click()">{{ t('upload.choose_file') }}</button>
            <span class="upload-filename" role="status">{{ selectedFile?.name ?? t('upload.no_file') }}</span>
          </div>
          <div class="upload-actions">
          <button
            class="button primary"
            :class="{ loading: documentsStore.isPending('upload') }"
            type="submit"
            :disabled="documentsStore.busy || !selectedFile"
            :aria-busy="documentsStore.isPending('upload')"
          >
            {{
              documentsStore.isPending('upload')
                ? t('upload.uploading')
                : t('upload.action')
            }}
          </button>
          <button class="button" type="button" @click="emit('close')">{{ t('common.cancel') }}</button>
          </div>
        </div>
      </form>
  </section>
</template>

<style scoped>
.upload-area { margin-bottom: 20px; }
.upload-zone { min-height: 0; padding: 20px; gap: 16px; }
.upload-title { margin-bottom: 6px; font-size: 17px; font-weight: 600; }
.upload-file-choice, .upload-actions { display: flex; align-items: center; flex-wrap: wrap; gap: 12px; }
.upload-filename { color: var(--text-soft); overflow-wrap: anywhere; min-width: 0; }
</style>
