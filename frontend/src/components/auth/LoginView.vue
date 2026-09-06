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
const passwordVisible = ref(false)
const errorKey = ref('')
const errorFallback = ref('')
const retryAfter = ref<string | null>(null)
const errorMessage = computed(() => errorKey.value
  ? t(errorKey.value, { seconds: retryAfter.value || t('errors.a_few') })
  : errorFallback.value)
const usernameInput = ref<HTMLInputElement | null>(null)
const submitting = computed(() => authStore.status === 'checking')

watch(
  () => authStore.loginMessageKey,
  (key) => {
    errorKey.value = key || ''
    errorFallback.value = ''
    void nextTick(() => usernameInput.value?.focus())
  },
  { immediate: true },
)

async function submit(): Promise<void> {
  errorKey.value = ''
  errorFallback.value = ''
  try {
    await authStore.login({
      username: username.value,
      password: password.value,
    })
    password.value = ''
    passwordVisible.value = false
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) {
      errorKey.value = 'auth.invalid_credentials'
    } else if (error instanceof ApiError && error.status === 429) {
      errorKey.value = 'errors.rate_limit'
      retryAfter.value = error.retryAfter
    } else if (error instanceof ApiError) {
      errorFallback.value = error.message
    } else {
      errorKey.value = 'errors.request_failed'
    }
  }
}
</script>

<template>
  <section class="auth-view">
    <article class="auth-card">
      <div class="auth-brand">
        <p class="auth-eyebrow">{{ t('header.title') }}</p>
        <h1 class="auth-title">{{ t('auth.title') }}</h1>
        <p class="auth-copy">{{ t('auth.subtitle') }}</p>
      </div>
      <form class="auth-form" :aria-busy="submitting" @submit.prevent="submit">
        <label class="auth-field">
          <span>{{ t('auth.username') }}</span>
          <input
            ref="usernameInput"
            v-model="username"
            class="field"
            name="username"
            autocomplete="username"
            maxlength="100"
            :aria-describedby="errorMessage ? 'login-error' : undefined"
            required
          />
        </label>
        <div class="auth-field">
          <label for="login-password">{{ t('auth.password') }}</label>
          <div class="password-field">
            <input
              id="login-password"
              v-model="password"
              class="field"
              name="password"
              :type="passwordVisible ? 'text' : 'password'"
              autocomplete="current-password"
              maxlength="1024"
              :aria-describedby="errorMessage ? 'login-error' : undefined"
              required
            />
            <button
              class="password-toggle"
              type="button"
              aria-controls="login-password"
              @click="passwordVisible = !passwordVisible"
            >
              {{ t(passwordVisible ? 'auth.hide_password' : 'auth.show_password') }}
            </button>
          </div>
        </div>
        <p v-if="errorMessage" id="login-error" class="auth-error" role="alert">{{ errorMessage }}</p>
        <button
          class="button primary auth-submit"
          :class="{ loading: submitting }"
          type="submit"
          :disabled="submitting"
        >
          {{ t(submitting ? 'auth.signing_in' : 'auth.sign_in') }}
        </button>
      </form>
      <LanguageSwitcher auth />
    </article>
  </section>
</template>
