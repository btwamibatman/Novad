<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'

import { useApiErrorHandler } from '@/composables/useApiErrorHandler'
import { useToasts } from '@/composables/useToasts'
import { useDocumentsStore } from '@/stores/documents'

const { t } = useI18n()
const documentsStore = useDocumentsStore()
const { handle } = useApiErrorHandler()
const { show } = useToasts()
const fileInput = ref<HTMLInputElement | null>(null)
const selectedFile = ref<File | null>(null)
const dragover = ref(false)

function updateFile(event: Event): void {
  const input = event.target as HTMLInputElement
  selectedFile.value = input.files?.[0] ?? null
}

async function upload(file: File | null): Promise<void> {
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
  } catch (error) {
    handle(error)
  }
}

async function drop(event: DragEvent): Promise<void> {
  dragover.value = false
  await upload(event.dataTransfer?.files[0] ?? null)
}
</script>

<template>
  <article class="panel">
    <div class="panel-head">
      <h2 class="panel-title">{{ t('upload.title') }}</h2>
      <span class="muted">{{ t('common.pdf_only') }}</span>
    </div>
    <div class="panel-body">
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
            <p class="upload-copy">{{ t('upload.help') }}</p>
          </div>
          <input
            ref="fileInput"
            class="field"
            type="file"
            accept=".pdf,application/pdf"
            required
            @change="updateFile"
          />
          <button
            class="button primary"
            :class="{ loading: documentsStore.isPending('upload') }"
            type="submit"
            :disabled="documentsStore.busy"
            :aria-busy="documentsStore.isPending('upload')"
          >
            {{
              documentsStore.isPending('upload')
                ? t('upload.uploading')
                : t('upload.action')
            }}
          </button>
        </div>
      </form>
    </div>
  </article>
</template>
