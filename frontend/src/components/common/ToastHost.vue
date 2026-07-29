<script setup lang="ts">
import { useToasts } from '@/composables/useToasts'

const { toasts, remove } = useToasts()
</script>

<template>
  <div class="toast-stack" aria-live="polite">
    <button
      v-for="toast in toasts"
      :key="toast.id"
      class="toast"
      :class="toast.type"
      type="button"
      @click="remove(toast.id)"
    >
      {{ toast.message }}
    </button>
  </div>
</template>
