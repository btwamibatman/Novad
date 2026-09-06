import { mkdir } from 'node:fs/promises'
import { resolve } from 'node:path'
import { expect, test, type Page } from '@playwright/test'
import { makeDocument } from '../src/__tests__/fixtures'
import type { DocumentRead, ToolJobRead } from '../src/types/document'
import en from '../src/i18n/en.json'

const reviewDirectory = resolve(import.meta.dirname, '../../artifacts/ui-review')
const longFilename = 'Отчёт_по_производственной_практике_и_индивидуальным_заданиям_Абдигалым_Хамза_2026_окончательная_версия.pdf'
const session = {
  session_id: 'ui-review-session', expires_at: '2099-01-01T00:00:00Z',
  user: { id: 1, username: 'hamza' },
}

function job(overrides: Partial<ToolJobRead> = {}): ToolJobRead {
  return {
    id: 11, source_document_id: 1, kind: 'compression', status: 'completed',
    stage: 'completed', progress: 100, source_filename: 'Practice report.pdf',
    source_content_type: 'application/pdf', options: {}, findings: [],
    result_filename: 'Practice report-compressed.pdf', result_content_type: 'application/pdf',
    result_size_bytes: 204800, result_artifact_id: null,
    result_meta: { original_size_bytes: 1048576, result_size_bytes: 204800, savings_percent: 80.5 },
    error_message: null, created_at: '2026-09-06T10:00:00Z',
    started_at: '2026-09-06T10:00:00Z', finished_at: '2026-09-06T10:00:05Z',
    ...overrides,
  }
}

function sampleDocuments(): DocumentRead[] {
  return [
    makeDocument({ filename: 'Practice report.pdf', size_bytes: 1048576,
      language_distribution: { en: 0.7, ru: 0.3 }, word_count: 2418, char_count: 15842 }),
    makeDocument({ id: 2, filename: longFilename, size_bytes: 2457600,
      detected_language: 'ru', language_distribution: { ru: 0.8, kk: 0.2 } }),
    makeDocument({ id: 3, filename: 'Scanned agreement.pdf', status: 'analyzing',
      size_bytes: 5406720, analysis_progress: { stage: 'ocr', completed_pages: 2, total_pages: 5 } }),
    makeDocument({ id: 4, filename: 'Damaged document.pdf', status: 'failed',
      error_message: 'PDF analysis failed: document is invalid or corrupted' }),
  ]
}

interface MockState {
  authenticated: boolean
  documents: DocumentRead[]
  jobs: ToolJobRead[]
  failLogin: boolean
  failUpload: boolean
  failList: boolean
  listGate: Promise<void> | null
  calls: Array<{ path: string; body: unknown }>
}

async function mockApi(page: Page, overrides: Partial<MockState> = {}) {
  const state: MockState = {
    authenticated: true, documents: sampleDocuments(), jobs: [],
    failLogin: false, failUpload: false, failList: false, listGate: null, calls: [],
    ...overrides,
  }
  await page.route('**/api/**', async (route) => {
    const request = route.request()
    const path = new URL(request.url()).pathname
    if (request.method() === 'POST') {
      state.calls.push({ path, body: request.headers()['content-type']?.includes('application/json')
        ? request.postDataJSON() : request.postData() })
    }
    if (path === '/api/auth/me') {
      await route.fulfill(state.authenticated ? { json: session } : { status: 401, json: { detail: 'Authentication required' } })
    } else if (path === '/api/auth/login') {
      state.authenticated = !state.failLogin
      await route.fulfill(state.failLogin ? { status: 401, json: { detail: 'Invalid credentials' } } : { json: session })
    } else if (path === '/api/dashboard/summary') {
      await route.fulfill({ json: {
        total_documents: state.documents.length,
        processed_documents: state.documents.filter((document) => document.status === 'processed').length,
        failed_documents: state.documents.filter((document) => document.status === 'failed').length,
        storage_bytes: state.documents.reduce((total, document) => total + document.size_bytes, 0),
        detected_languages: { en: 1, ru: 1 },
      } })
    } else if (path === '/api/documents' && request.method() === 'GET') {
      if (state.listGate) await state.listGate
      await route.fulfill(state.failList ? { status: 503, json: { detail: 'Document service unavailable' } } : { json: state.documents })
    } else if (path === '/api/documents/upload') {
      if (state.failUpload) {
        await route.fulfill({ status: 413, json: { detail: 'File exceeds the upload limit' } })
      } else {
        const uploaded = makeDocument({ id: 5, filename: 'uploaded.pdf', status: 'uploaded', extracted_text: '' })
        state.documents = [uploaded, ...state.documents]
        await route.fulfill({ status: 201, json: uploaded })
      }
    } else if (path === '/api/tools/jobs') {
      await route.fulfill({ json: state.jobs })
    } else if (path === '/api/tools/artifacts' || path === '/api/ai/jobs') {
      await route.fulfill({ json: [] })
    } else if (path === '/api/ai/provider-info') {
      await route.fulfill({ json: { provider: 'mock', model: 'mock', service_tier: 'paid', max_remote_retention_hours: 48, requires_verified_artifact: true } })
    } else if (path === '/api/tools/redaction/preview') {
      const body = request.postDataJSON()
      const source = state.documents.find((document) => document.id === body.document_id)!
      const created = job({ id: 20, source_document_id: source.id, source_filename: source.filename,
        kind: 'redaction', status: 'review', stage: 'review', progress: 70,
        result_filename: null, result_size_bytes: null, result_meta: { page_count: 1 },
        options: { operation: 'preview', categories: body.categories },
        findings: [{ id: 'email-1', page: 1, group: 'personal', category: 'EMAIL',
          text: 'example@example.com', confidence: 0.99, pdf_rect: [20, 40, 80, 60],
          rect: { x: 10, y: 20, width: 40, height: 5 } }],
      })
      state.jobs = [created, ...state.jobs]
      await route.fulfill({ status: 202, json: created })
    } else if (path.endsWith('/apply-redaction')) {
      const current = state.jobs.find((item) => item.id === 20)!
      Object.assign(current, { status: 'failed', stage: 'failed', progress: 90,
        error_message: 'Unable to apply redactions safely', options: { operation: 'apply' } })
      await route.fulfill({ json: current })
    } else if (path === '/api/tools/word-to-pdf') {
      const created = job({ id: 21, kind: 'word_to_pdf', source_document_id: null,
        source_filename: 'Outline.docx', result_filename: 'Outline.pdf' })
      state.jobs = [created, ...state.jobs]
      await route.fulfill({ status: 202, json: created })
    } else if (/\/pages\/\d+$/.test(path)) {
      await route.fulfill({ contentType: 'image/svg+xml', body: '<svg xmlns="http://www.w3.org/2000/svg" width="595" height="842"><rect width="595" height="842" fill="#fff"/><text x="60" y="70" font-size="24" fill="#263246">Practice report</text><text x="60" y="186" font-size="18" fill="#263246">example@example.com</text></svg>' })
    } else {
      await route.fulfill({ status: 404, json: { detail: `Unmocked endpoint: ${path}` } })
    }
  })
  return state
}

async function screenshot(page: Page, name: string) {
  await mkdir(reviewDirectory, { recursive: true })
  await page.screenshot({ path: resolve(reviewDirectory, `${name}.png`), fullPage: true, animations: 'disabled' })
}

async function expectNoPageOverflow(page: Page) {
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBe(true)
}

test.beforeEach(async ({ page }) => {
  page.on('pageerror', (error) => { throw error })
  await page.addInitScript(() => {
    localStorage.setItem('document-console-language', 'en')
    localStorage.setItem('document-console-theme', 'dark')
  })
})

test('keyboard upload restores focus, preserves errors and updates the table after success', async ({ page }) => {
  const state = await mockApi(page, { failUpload: true })
  await page.goto('/web/dist/')
  const upload = page.getByRole('button', { name: 'Upload', exact: true })
  await upload.focus()
  await page.keyboard.press('Enter')
  await expect(upload).toHaveAttribute('aria-expanded', 'true')
  await expect(page.getByRole('button', { name: /Choose (a )?file/ })).toBeFocused()
  expect(await page.locator(':focus').evaluate((element) => getComputedStyle(element).outlineStyle)).not.toBe('none')
  await page.keyboard.press('Escape')
  await expect(upload).toBeFocused()
  await expect(upload).toHaveAttribute('aria-expanded', 'false')
  await page.keyboard.press('Enter')
  const fileChooserPromise = page.waitForEvent('filechooser')
  await page.keyboard.press('Enter')
  await (await fileChooserPromise).setFiles({ name: 'uploaded.pdf', mimeType: 'application/pdf', buffer: Buffer.from('%PDF-1.7 test') })
  await screenshot(page, 'documents-upload-desktop')
  await page.getByRole('button', { name: 'Upload document', exact: true }).click()
  await expect(page.getByText('File exceeds the upload limit').first()).toBeVisible()
  await expect(upload).toHaveAttribute('aria-expanded', 'true')
  await page.setViewportSize({ width: 390, height: 844 })
  await expectNoPageOverflow(page)
  await screenshot(page, 'documents-upload-failure-mobile')
  state.failUpload = false
  await page.getByRole('button', { name: 'Upload document', exact: true }).click()
  await expect(page.getByRole('button', { name: 'uploaded.pdf', exact: true })).toBeVisible()
  await expect(upload).toHaveAttribute('aria-expanded', 'false')
  await expect(page.locator('#document-selection')).toContainText('uploaded.pdf')
})

test('document details stay contextual and selected source survives navigation to tools', async ({ page }) => {
  await mockApi(page)
  await page.goto('/web/dist/')
  await expect(page.locator('#document-selection')).toHaveCount(0)
  await expect(page.getByRole('columnheader')).toHaveText(['File', 'Status', 'Size', 'Added', 'Actions'])
  await page.getByRole('button', { name: longFilename, exact: true }).focus()
  await page.keyboard.press('Enter')
  await expect(page.locator('#document-selection')).toContainText('Russian')
  await expect(page.locator('#document-selection')).toContainText('Kazakh')
  await expect(page.locator('#document-selection')).toContainText('80%')
  await expect(page.locator('#document-selection')).not.toContainText('AI: none')
  await page.getByRole('link', { name: 'Tools', exact: true }).click()
  await page.getByRole('button', { name: 'Change document', exact: true }).click()
  await expect(page.locator('.document-picker select')).toHaveValue('2')
  await page.getByRole('tab', { name: 'Compress PDF' }).focus()
  await page.keyboard.press('Enter')
  await expect(page.getByRole('radio', { name: /Recommended · Balanced/ })).toBeChecked()
  await page.keyboard.press('ArrowRight')
  await expect(page.getByRole('tab', { name: 'Convert a file' })).toBeFocused()
  await expect(page.getByRole('tab', { name: 'Convert a file' })).toHaveAttribute('aria-selected', 'true')
})

test('redaction separates detected findings from applied protection and preserves readable failures', async ({ page }) => {
  const state = await mockApi(page)
  await page.goto('/web/dist/')
  await page.getByRole('link', { name: 'Tools', exact: true }).click()
  for (const value of ['personal', 'financial', 'visual']) {
    await expect(page.locator(`.category-grid input[value="${value}"]`)).toBeChecked()
  }
  for (const value of ['service', 'context']) {
    await expect(page.locator(`.category-grid input[value="${value}"]`)).not.toBeChecked()
  }
  await page.getByRole('button', { name: 'Find data', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Apply to 1 areas' })).toBeVisible()
  await expect(page.getByRole('link', { name: 'Download protected PDF', exact: true })).toHaveCount(0)
  expect(state.calls.find((call) => call.path.endsWith('/preview'))?.body).toEqual({ document_id: 1, categories: ['personal', 'financial', 'visual'] })
  await screenshot(page, 'tools-review-desktop')
  await page.getByRole('button', { name: 'Apply to 1 areas' }).click()
  await expect(page.getByText(en['tools.refinement.redaction_failed']).first()).toBeVisible()
  await expect(page.getByRole('link', { name: 'Download protected PDF', exact: true })).toHaveCount(0)
  await page.locator('.task-row details summary').click()
  await expect(page.getByText('Unable to apply redactions safely', { exact: true })).toBeVisible()
  expect(state.calls.find((call) => call.path.endsWith('/apply-redaction'))?.body).toEqual({ areas: [{ id: 'email-1', page: 1, rect: { x: 10, y: 20, width: 40, height: 5 } }], mode: 'black' })
  await screenshot(page, 'tools-redaction-failure-desktop')
})

test('Word conversion accepts a local DOCX when the document library has no PDFs', async ({ page }) => {
  const state = await mockApi(page, { documents: [] })
  await page.goto('/web/dist/')
  await page.getByRole('link', { name: 'Tools', exact: true }).click()
  await page.getByRole('tab', { name: 'Convert a file' }).click()
  await page.locator('input[type="file"]').setInputFiles({ name: 'Outline.docx', mimeType: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document', buffer: Buffer.from('mock docx') })
  await expect(page.getByText('Outline.docx', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'Convert to PDF', exact: true }).click()
  await expect(page.getByRole('link', { name: /Download/ })).toBeVisible()
  expect(state.calls.find((call) => call.path.endsWith('/word-to-pdf'))?.body).toContain('filename="Outline.docx"')
  await screenshot(page, 'tools-conversion-desktop')
})

test('login password visibility is keyboard accessible and errors follow the language', async ({ page }) => {
  const state = await mockApi(page, { authenticated: false, failLogin: true })
  await page.goto('/web/dist/')
  const password = page.locator('input[name="password"]')
  await page.getByLabel('Username').fill('hamza')
  await password.fill('demo-password')
  await page.getByRole('button', { name: 'Show password' }).focus()
  await page.keyboard.press('Space')
  await expect(password).toHaveAttribute('type', 'text')
  await expect(page.getByRole('button', { name: 'Hide password' })).toBeFocused()
  await page.keyboard.press('Space')
  await expect(password).toHaveAttribute('type', 'password')
  await page.getByRole('button', { name: 'Sign in', exact: true }).click()
  await expect(page.getByRole('alert')).toContainText('Invalid username or password.')
  await page.getByRole('button', { name: 'RUS', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Вход', exact: true })).toBeVisible()
  await expect(page.getByRole('alert')).not.toContainText('Invalid username')
  await screenshot(page, 'login-desktop-ru')
  await page.setViewportSize({ width: 390, height: 844 })
  await expectNoPageOverflow(page)
  await screenshot(page, 'login-mobile-ru')
  state.failLogin = false
  await page.getByRole('button', { name: 'ENG', exact: true }).click()
  await page.getByRole('button', { name: 'Sign in', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Documents', exact: true })).toBeVisible()
})

test('loading, empty and fetch failure states are visible and recoverable', async ({ page }) => {
  let releaseList!: () => void
  const state = await mockApi(page, { documents: [], listGate: new Promise<void>((resolve) => { releaseList = resolve }) })
  await page.goto('/web/dist/')
  await expect(page.getByText('Loading', { exact: true }).first()).toBeVisible()
  await screenshot(page, 'documents-loading-desktop')
  releaseList()
  state.listGate = null
  await expect(page.getByRole('button', { name: 'Upload', exact: true })).toBeEnabled()
  await expect(page.getByText(en['documents.empty_title'], { exact: true })).toBeVisible()
  await screenshot(page, 'documents-empty-desktop')
  state.failList = true
  await page.reload()
  await expect(page.getByText(/Document service unavailable/).first()).toBeVisible()
  await screenshot(page, 'documents-load-failure-desktop')
  state.failList = false
  state.documents = [makeDocument()]
  await page.reload()
  await expect(page.getByRole('button', { name: 'sample.pdf', exact: true })).toBeVisible()
})

test('desktop and narrow layouts keep long filenames and task results readable', async ({ page }) => {
  await mockApi(page, { jobs: [job(), job({ id: 12, kind: 'redaction', status: 'failed', stage: 'failed',
    progress: 90, source_document_id: 2, source_filename: longFilename, result_filename: null,
    result_size_bytes: null, result_meta: {}, error_message: 'Unable to apply redactions safely' }),
    job({ id: 13, kind: 'word_to_pdf', source_document_id: null, source_filename: 'Outline.docx', result_filename: 'Outline.pdf' }),
  ] })
  await page.setViewportSize({ width: 1440, height: 1000 })
  await page.goto('/web/dist/')
  await expect(page.getByRole('button', { name: longFilename, exact: true })).toBeVisible()
  await expectNoPageOverflow(page)
  await screenshot(page, 'documents-desktop')
  await page.getByRole('button', { name: longFilename, exact: true }).click()
  await screenshot(page, 'documents-details-desktop')
  await page.setViewportSize({ width: 390, height: 844 })
  await expectNoPageOverflow(page)
  await screenshot(page, 'documents-mobile')
  await page.getByRole('link', { name: 'Tools', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Recent tasks', exact: true })).toBeVisible()
  await expectNoPageOverflow(page)
  await screenshot(page, 'tools-mobile')
  await page.setViewportSize({ width: 1440, height: 1000 })
  await page.getByRole('tab', { name: 'Compress PDF' }).click()
  await expect(page.getByText(/80.5%/)).toBeVisible()
  await expect(page.getByText(/200 KB/).first()).toBeVisible()
  const badges = page.locator('.task-list .task-badge')
  await expect(badges).toHaveCount(3)
  for (const badge of await badges.all()) {
    const bounds = await badge.boundingBox()
    expect(bounds?.width).toBeLessThan(180)
  }
  await screenshot(page, 'tools-compression-desktop')
  await page.getByRole('button', { name: 'RUS', exact: true }).click()
  await screenshot(page, 'tools-compression-desktop-ru')
})
