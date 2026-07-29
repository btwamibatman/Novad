<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'

import LanguageSwitcher from '@/components/common/LanguageSwitcher.vue'
import ThemeToggle from '@/components/common/ThemeToggle.vue'
import { useApiErrorHandler } from '@/composables/useApiErrorHandler'
import { useToasts } from '@/composables/useToasts'
import { useAuthStore } from '@/stores/auth'
import { useDocumentsStore } from '@/stores/documents'

const { t } = useI18n()
const authStore = useAuthStore()
const documentsStore = useDocumentsStore()
const { handle } = useApiErrorHandler()
const { show } = useToasts()
const loggingOut = ref(false)

async function refresh(): Promise<void> {
  try {
    await documentsStore.load()
  } catch (error) {
    handle(error)
  }
}

async function logout(): Promise<void> {
  loggingOut.value = true
  try {
    await authStore.logout()
  } catch (error) {
    show(error instanceof Error ? error.message : t('errors.request_failed'), 'error')
  } finally {
    documentsStore.clear()
    loggingOut.value = false
  }
}
</script>

<template>
  <header class="topbar">
    <div class="brand">
      <h1 class="brand-title">{{ t('header.title') }}</h1>
      <p class="brand-subtitle">{{ t('header.subtitle') }}</p>
    </div>
    <div class="actions">
      <LanguageSwitcher />
      <span class="current-user">{{ authStore.username }}</span>
      <button
        class="button"
        type="button"
        :disabled="documentsStore.busy"
        @click="refresh"
      >
        {{ t('actions.refresh') }}
      </button>
      <button class="button" type="button" :disabled="loggingOut" @click="logout">
        {{ t('auth.sign_out') }}
      </button>
      <ThemeToggle />
    </div>
  </header>
</template>
