<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink } from 'vue-router'

import LanguageSwitcher from '@/components/common/LanguageSwitcher.vue'
import ThemeToggle from '@/components/common/ThemeToggle.vue'
import { useToasts } from '@/composables/useToasts'
import { useAuthStore } from '@/stores/auth'
import { useDocumentsStore } from '@/stores/documents'

const { t } = useI18n()
const authStore = useAuthStore()
const documentsStore = useDocumentsStore()
const { show } = useToasts()
const loggingOut = ref(false)

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
    <div class="header-start">
      <div class="brand">
        <h1 class="brand-title">{{ t('header.title') }}</h1>
        <p class="brand-subtitle">{{ t('header.subtitle') }}</p>
      </div>
      <nav class="main-nav" :aria-label="t('nav.label')">
        <RouterLink to="/documents">{{ t('nav.documents') }}</RouterLink>
        <RouterLink to="/tools">{{ t('nav.tools') }}</RouterLink>
      </nav>
    </div>
    <div class="actions">
      <LanguageSwitcher />
      <ThemeToggle />
      <details class="profile-menu">
        <summary role="button" :aria-label="t('profile.menu')">
          <span class="profile-avatar" aria-hidden="true">{{ authStore.username.slice(0, 1).toUpperCase() }}</span>
          <span>{{ authStore.username }}</span>
        </summary>
        <div class="profile-popover">
          <span class="muted">{{ authStore.username }}</span>
          <button class="menu-action danger-text" type="button" :disabled="loggingOut" @click="logout">
            {{ t('auth.sign_out') }}
          </button>
        </div>
      </details>
    </div>
  </header>
</template>
