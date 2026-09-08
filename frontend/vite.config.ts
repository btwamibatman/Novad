import { fileURLToPath, URL } from 'node:url'

import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vitest/config'

const apiTarget = process.env.DEV_API_TARGET || 'http://localhost:8000'
const apiProxy = { target: apiTarget, changeOrigin: false }

export default defineConfig(({ command }) => ({
  plugins: [vue()],
  base: command === 'serve' ? '/' : '/web/dist/',
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: {
    watch: {
      usePolling: process.env.DEV_USE_POLLING === 'true',
      interval: 300,
    },
    proxy: {
      '/api': apiProxy,
      '/health': apiProxy,
      '/docs': apiProxy,
      '/redoc': apiProxy,
      '/openapi.json': apiProxy,
    },
  },
  build: {
    outDir: '../app/web/dist',
    emptyOutDir: true,
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/__tests__/setup.ts'],
    include: ['src/**/*.spec.ts'],
  },
}))
