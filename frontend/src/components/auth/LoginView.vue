<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import { ApiError } from '@/api/client'
import LanguageSwitcher from '@/components/common/LanguageSwitcher.vue'
import { useAuthStore } from '@/stores/auth'

const { t } = useI18n()
const authStore = useAuthStore()
const username = ref('')
const password = ref('')
const errorMessage = ref('')
const usernameInput = ref<HTMLInputElement | null>(null)
const submitting = computed(() => authStore.status === 'checking')

watch(
  () => authStore.loginMessageKey,
  (key) => {
    errorMessage.value = key ? t(key) : ''
    void nextTick(() => usernameInput.value?.focus())
  },
  { immediate: true },
)

async function submit(): Promise<void> {
  errorMessage.value = ''
  try {
    await authStore.login({
      username: username.value,
      password: password.value,
    })
    password.value = ''
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) {
      errorMessage.value = t('auth.invalid_credentials')
    } else if (error instanceof ApiError && error.status === 429) {
      errorMessage.value = t('errors.rate_limit', {
        seconds: error.retryAfter || t('errors.a_few'),
      })
    } else {
      errorMessage.value = error instanceof Error ? error.message : t('errors.request_failed')
    }
  }
}
</script>

<template>
  <section class="auth-view">
    <article class="auth-card">
      <div class="auth-brand">
        <p class="auth-eyebrow">Document Console</p>
        <h1 class="auth-title">{{ t('auth.title') }}</h1>
        <p class="auth-copy">{{ t('auth.subtitle') }}</p>
      </div>
      <form class="auth-form" @submit.prevent="submit">
        <label class="auth-field">
          <span>{{ t('auth.username') }}</span>
          <input
            ref="usernameInput"
            v-model="username"
            class="field"
            name="username"
            autocomplete="username"
            maxlength="100"
            required
          />
        </label>
        <label class="auth-field">
          <span>{{ t('auth.password') }}</span>
          <input
            v-model="password"
            class="field"
            name="password"
            type="password"
            autocomplete="current-password"
            maxlength="1024"
            required
          />
        </label>
        <p v-if="errorMessage" class="auth-error" role="alert">{{ errorMessage }}</p>
        <button
          class="button primary auth-submit"
          :class="{ loading: submitting }"
          type="submit"
          :disabled="submitting"
        >
          {{ t('auth.sign_in') }}
        </button>
      </form>
      <LanguageSwitcher auth />
    </article>
  </section>
</template>
