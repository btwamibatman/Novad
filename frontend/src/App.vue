<script setup lang="ts">
import { onMounted, watch, watchEffect } from 'vue'
import { useI18n } from 'vue-i18n'

import LoginView from '@/components/auth/LoginView.vue'
import ToastHost from '@/components/common/ToastHost.vue'
import AppShell from '@/components/layout/AppShell.vue'
import { useApiErrorHandler } from '@/composables/useApiErrorHandler'
import { useToasts } from '@/composables/useToasts'
import { useAuthStore } from '@/stores/auth'
import { useDocumentsStore } from '@/stores/documents'

const { t } = useI18n()
const authStore = useAuthStore()
const documentsStore = useDocumentsStore()
const { handle } = useApiErrorHandler()
const { show } = useToasts()

async function loadApplicationData(): Promise<void> {
  try {
    await documentsStore.load(false)
  } catch (error) {
    handle(error)
  }
}

onMounted(async () => {
  try {
    await authStore.checkSession()
  } catch (error) {
    authStore.clear()
    show(error instanceof Error ? error.message : t('errors.request_failed'), 'error')
  }
})

watch(
  () => authStore.session,
  (session, previousSession) => {
    if (!session) {
      documentsStore.clear()
    } else if (!previousSession) {
      void loadApplicationData()
    }
  },
)

watchEffect(() => {
  document.title = t('page.title')
})
</script>

<template>
  <LoginView v-if="!authStore.isAuthenticated" />
  <AppShell v-else />
  <ToastHost />
</template>
