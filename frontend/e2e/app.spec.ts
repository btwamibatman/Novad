import { expect, test, type Page } from '@playwright/test'
import type { DocumentRead } from '../src/types/document'

const session = {
  session_id: 'test-session',
  expires_at: '2099-01-01T00:00:00Z',
  user: { id: 1, username: 'admin' },
}

const baseDocument: DocumentRead = {
  id: 1,
  user_id: 1,
  filename: 'sample.pdf',
  content_type: 'application/pdf',
  size_bytes: 1024,
  status: 'processed',
  analysis_progress: {},
  extracted_text: 'Extracted sample text',
  extraction_quality: 'high',
  extraction_quality_meta: {},
  detected_language: 'en',
  language_distribution: { en: 1 },
  word_count: 3,
  char_count: 21,
  error_message: null,
  ai_summary: '',
  ai_model: null,
  ai_error: null,
  ai_summary_meta: {},
  content_review: '',
  content_review_model: null,
  content_review_error: null,
  content_review_mode: null,
  content_review_meta: {},
  layout_review: '',
  layout_review_model: null,
  layout_review_error: null,
  layout_review_meta: {},
  created_at: '2026-07-29T10:00:00Z',
  updated_at: '2026-07-29T10:00:00Z',
}

interface MockApiState {
  authenticated: boolean
  document: DocumentRead
  analysisListRequests: number
  deleted: boolean
}

async function installMockApi(page: Page, initiallyAuthenticated: boolean) {
  const state: MockApiState = {
    authenticated: initiallyAuthenticated,
    document: structuredClone(baseDocument),
    analysisListRequests: 0,
    deleted: false,
  }

  await page.route('http://127.0.0.1:5173/api/**', async (route) => {
    const request = route.request()
    const url = new URL(request.url())
    const path = url.pathname

    if (path === '/api/auth/me') {
      await route.fulfill(
        state.authenticated
          ? { json: session }
          : { status: 401, json: { detail: 'Authentication required' } },
      )
      return
    }
    if (path === '/api/auth/login') {
      state.authenticated = true
      await route.fulfill({ json: session })
      return
    }
    if (path === '/api/auth/logout') {
      state.authenticated = false
      await route.fulfill({ status: 204 })
      return
    }
    if (path === '/api/dashboard/summary') {
      await route.fulfill({
        json: {
          total_documents: state.deleted ? 0 : 1,
          processed_documents:
            !state.deleted && state.document.status === 'processed' ? 1 : 0,
          failed_documents:
            !state.deleted && state.document.status === 'failed' ? 1 : 0,
          storage_bytes: state.deleted ? 0 : state.document.size_bytes,
          detected_languages: state.deleted ? {} : { en: 1 },
        },
      })
      return
    }
    if (path === '/api/documents' && request.method() === 'GET') {
      if (state.document.status === 'analyzing') {
        state.analysisListRequests += 1
        if (state.analysisListRequests >= 2) {
          state.document.status = 'processed'
          state.document.analysis_progress = {}
        }
      }
      await route.fulfill({ json: state.deleted ? [] : [state.document] })
      return
    }
    if (path === '/api/documents/upload') {
      state.document = {
        ...structuredClone(baseDocument),
        filename: 'uploaded.pdf',
        status: 'uploaded',
        extracted_text: '',
      }
      state.deleted = false
      await route.fulfill({ status: 201, json: state.document })
      return
    }
    if (path.endsWith('/analyze')) {
      state.document.status = 'analyzing'
      state.document.analysis_progress = {
        stage: 'queued',
        completed_pages: 0,
        total_pages: null,
      }
      state.analysisListRequests = 0
      await route.fulfill({ status: 202, json: state.document })
      return
    }
    if (path.endsWith('/summarize')) {
      state.document.ai_summary = 'Generated summary'
      state.document.ai_model = 'mock-model'
      await route.fulfill({ json: state.document })
      return
    }
    if (path.endsWith('/content-review')) {
      state.document.content_review = '**Content review completed**'
      state.document.content_review_mode = 'quick'
      state.document.content_review_meta = { complete: true, batch_count: 1 }
      await route.fulfill({ json: state.document })
      return
    }
    if (path.endsWith('/layout-review')) {
      state.document.layout_review = 'Layout review completed'
      state.document.layout_review_meta = { complete: true, reviewed_pages: [1] }
      await route.fulfill({ json: state.document })
      return
    }
    if (path.endsWith('/ask')) {
      await route.fulfill({
        json: {
          answer: 'AI answer',
          model: 'mock-model',
          truncated_context: false,
          privacy_applied: true,
          masked_entity_count: 1,
        },
      })
      return
    }
    if (path === '/api/documents/1' && request.method() === 'DELETE') {
      state.deleted = true
      await route.fulfill({ status: 204 })
      return
    }
    await route.fulfill({ status: 404, json: { detail: 'Not found' } })
  })

  return state
}

test.beforeEach(async ({ page }) => {
  page.on('pageerror', (error) => {
    throw error
  })
  await page.addInitScript(() => {
    localStorage.setItem('document-console-language', 'en')
  })
})

test('login, inspect a document and logout', async ({ page }) => {
  await installMockApi(page, false)

  await page.goto('/web/dist/')
  await expect(page.getByRole('heading', { name: 'Sign in' })).toBeVisible()

  await page.getByRole('button', { name: 'RUS' }).click()
  await expect(page.getByRole('heading', { name: 'Вход' })).toBeVisible()
  await page.getByRole('button', { name: 'ENG' }).click()

  await page.getByLabel('Username').fill('admin')
  await page.getByLabel('Password').fill('secret')
  await page.getByRole('button', { name: 'Sign in' }).click()

  await expect(page.getByText('sample.pdf').first()).toBeVisible()
  await page.getByText('sample.pdf').first().click()
  await expect(page.getByText('Extracted sample text')).toBeVisible()

  await page.getByRole('button', { name: 'Toggle theme' }).click()
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'light')

  await page.getByRole('button', { name: 'Sign out' }).click()
  await expect(page.getByRole('heading', { name: 'Sign in' })).toBeVisible()
})

test('analysis, AI reviews and chat retain their behavior', async ({ page }) => {
  await installMockApi(page, true)

  await page.goto('/web/dist/')
  await expect(page.getByText('sample.pdf').first()).toBeVisible()
  await page.getByText('sample.pdf').first().click()

  await page.getByRole('button', { name: 'Analyze', exact: true }).click()
  await expect(
    page.locator('tr[data-document-id="1"] .badge.analyzing').first(),
  ).toBeVisible()
  await expect(
    page.locator('tr[data-document-id="1"] .badge.processed').first(),
  ).toBeVisible({ timeout: 5000 })

  await page.getByRole('button', { name: 'Summarize' }).click()
  await expect(page.getByText('Generated summary')).toBeVisible()

  await page.getByRole('button', { name: 'Review content' }).click()
  await expect(page.getByText('Content review completed')).toBeVisible()

  page.once('dialog', (dialog) => dialog.accept())
  await page.getByRole('button', { name: 'Review layout visually' }).click()
  await expect(page.getByText('Layout review completed', { exact: true })).toBeVisible()

  await page.getByRole('button', { name: 'Open AI chat' }).click()
  await page.getByPlaceholder('Ask about the selected document...').fill('Question')
  await page.getByRole('button', { name: 'Send' }).click()
  await expect(page.getByText('Question')).toBeVisible()
  await expect(page.getByText('AI answer')).toBeVisible()
})

test('upload and delete update the document list', async ({ page }) => {
  await installMockApi(page, true)

  await page.goto('/web/dist/')
  await expect(page.getByText('sample.pdf').first()).toBeVisible()

  await page.locator('input[type="file"]').setInputFiles({
    name: 'uploaded.pdf',
    mimeType: 'application/pdf',
    buffer: Buffer.from('%PDF-1.7 test'),
  })
  await page.getByRole('button', { name: 'Upload document' }).click()
  await expect(page.getByText('uploaded.pdf').first()).toBeVisible()

  page.once('dialog', (dialog) => dialog.accept())
  await page.getByRole('button', { name: 'Delete', exact: true }).click()
  await expect(page.getByText('No documents for this filter.')).toBeVisible()
})
