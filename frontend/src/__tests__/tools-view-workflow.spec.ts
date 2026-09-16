import { flushPromises, shallowMount } from '@vue/test-utils'

import ProtectedArtifactAI from '@/components/tools/ProtectedArtifactAI.vue'
import ToolsView from '@/views/ToolsView.vue'
import type { ToolJobRead } from '@/types/document'

const mocks = vi.hoisted(() => ({
  listJobs: vi.fn(),
  listArtifacts: vi.fn(),
  loadDocuments: vi.fn(),
  handleError: vi.fn(),
  showToast: vi.fn(),
  redactionPreview: vi.fn(),
  applyRedaction: vi.fn(),
  wordToPdf: vi.fn(),
  setJobHidden: vi.fn(),
  routeQuery: {} as Record<string, string | undefined>,
}))

vi.mock('vue-i18n', () => ({
  useI18n: () => ({ t: (key: string) => key }),
}))

vi.mock('vue-router', () => ({
  useRoute: () => ({ query: mocks.routeQuery }),
}))

vi.mock('@/api/tools', () => ({
  toolsApi: {
    listJobs: mocks.listJobs,
    listArtifacts: mocks.listArtifacts,
    redactionPreview: mocks.redactionPreview,
    applyRedaction: mocks.applyRedaction,
    wordToPdf: mocks.wordToPdf,
    setJobHidden: mocks.setJobHidden,
    pagePreviewUrl: (jobId: number, page: number) => `/api/tools/jobs/${jobId}/pages/${page}`,
    downloadUrl: (jobId: number) => `/api/tools/jobs/${jobId}/download`,
  },
}))

vi.mock('@/stores/documents', () => ({
  useDocumentsStore: () => ({
    documents: [
      {
        id: 7,
        filename: 'source.pdf',
        content_type: 'application/pdf',
        size_bytes: 1000,
      },
      {
        id: 8,
        filename: 'other.pdf',
        content_type: 'application/pdf',
        size_bytes: 2000,
      },
    ],
    selectedId: null,
    load: mocks.loadDocuments,
  }),
}))

vi.mock('@/composables/useApiErrorHandler', () => ({
  useApiErrorHandler: () => ({ handle: mocks.handleError }),
}))

vi.mock('@/composables/useToasts', () => ({
  useToasts: () => ({ show: mocks.showToast }),
}))

function reviewJob(): ToolJobRead {
  return {
    id: 41,
    source_document_id: 7,
    kind: 'redaction',
    status: 'review',
    stage: 'review',
    progress: 70,
    source_filename: 'source.pdf',
    source_content_type: 'application/pdf',
    options: {},
    findings: [
      {
        id: 'pii-1',
        page: 2,
        group: 'personal',
        category: 'EMAIL',
        text: 'hidden@example.com',
        confidence: 0.99,
        pdf_rect: [1, 2, 3, 4],
        rect: { x: 10, y: 20, width: 30, height: 5 },
      },
    ],
    result_filename: null,
    result_content_type: null,
    result_size_bytes: null,
    result_artifact_id: null,
    result_meta: { page_count: 3 },
    error_message: null,
    created_at: '2026-08-20T10:00:00Z',
    started_at: null,
    finished_at: null,
  }
}

describe('ToolsView protected workflow restoration', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    for (const key of Object.keys(mocks.routeQuery)) delete mocks.routeQuery[key]
  })

  it('restores a review job after reload and locks its source document', async () => {
    mocks.listJobs.mockResolvedValue([reviewJob()])
    mocks.listArtifacts.mockResolvedValue([])

    const wrapper = shallowMount(ToolsView)
    await flushPromises()

    const sourceSelect = wrapper.get('.document-picker select')
    expect(sourceSelect.element).toHaveProperty('disabled', true)
    expect((sourceSelect.element as HTMLSelectElement).value).toBe('7')
    expect(wrapper.text()).toContain('tools.redaction.source_locked')
    expect(wrapper.get('.redaction-preview img').attributes('src')).toBe(
      '/api/tools/jobs/41/pages/2',
    )
    expect(wrapper.text()).toContain('EMAIL')

    await wrapper.findAll('[role="tab"]')[1]!.trigger('click')
    await sourceSelect.setValue('8')
    expect((sourceSelect.element as HTMLSelectElement).value).toBe('8')
    await wrapper.findAll('[role="tab"]')[0]!.trigger('click')
    expect((sourceSelect.element as HTMLSelectElement).value).toBe('7')
    expect(sourceSelect.element).toHaveProperty('disabled', true)
    wrapper.unmount()
  })

  it('keeps service and context detection as explicit opt-ins', async () => {
    mocks.listJobs.mockResolvedValue([])
    mocks.listArtifacts.mockResolvedValue([])

    const wrapper = shallowMount(ToolsView)
    await flushPromises()
    const categoryInputs = wrapper.findAll('.category-grid input[type="checkbox"]')
    const checkedByValue = Object.fromEntries(
      categoryInputs.map((input) => [
        input.attributes('value'),
        (input.element as HTMLInputElement).checked,
      ]),
    )

    expect(checkedByValue).toEqual({
      personal: true,
      financial: true,
      visual: true,
      service: false,
      context: false,
    })
    wrapper.unmount()
  })

  it('honors protected-flow document and task query parameters', async () => {
    mocks.routeQuery.document_id = '8'
    mocks.routeQuery.task = 'summary'
    mocks.listJobs.mockResolvedValue([
      {
        ...reviewJob(),
        id: 42,
        source_document_id: 8,
        status: 'completed',
        stage: 'completed',
        progress: 100,
        findings: [],
        result_artifact_id: 9,
      },
    ])
    mocks.listArtifacts.mockResolvedValue([
      {
        id: 9,
        source_document_id: 8,
        kind: 'protected_pdf',
        status: 'ready_for_ai',
        filename: 'protected-other.pdf',
        content_type: 'application/pdf',
        size_bytes: 1000,
        source_sha256: 'source',
        artifact_sha256: 'artifact',
        privacy_policy: {
          categories: ['personal', 'financial', 'visual'],
          redaction_mode: 'black',
          selected_finding_count: 1,
          manual_confirmation: true,
          flattened: true,
          selectable_text: false,
          render_dpi: 200,
          image_format: 'jpeg',
          jpeg_quality: 90,
        },
        policy_version: '1',
        detector_version: 'privacy-v1',
        coverage_report: { page_count: 1, checked_pages: [1] },
        verification_report: { passed: true },
        error_message: null,
        created_at: '2026-08-20T10:00:00Z',
        updated_at: '2026-08-20T10:00:00Z',
        verified_at: '2026-08-20T10:00:00Z',
      },
    ])

    const wrapper = shallowMount(ToolsView)
    await flushPromises()

    expect((wrapper.get('.document-picker select').element as HTMLSelectElement).value).toBe('8')
    expect(wrapper.getComponent(ProtectedArtifactAI).props('initialTask')).toBe('summary')
    wrapper.unmount()
  })

  it('does not show an old protected artifact when the current redaction failed', async () => {
    mocks.listJobs.mockResolvedValue([
      { ...reviewJob(), status: 'failed', stage: 'failed', error_message: 'Unable to apply redactions safely' },
      { ...reviewJob(), id: 40, status: 'completed', result_artifact_id: 9 },
    ])
    mocks.listArtifacts.mockResolvedValue([
      { id: 9, source_document_id: 7, status: 'ready_for_ai', filename: 'old-protected.pdf' },
    ])
    const wrapper = shallowMount(ToolsView)
    await flushPromises()

    expect(wrapper.findComponent(ProtectedArtifactAI).exists()).toBe(false)
    const failedTask = wrapper.findAll('.task-row')[0]!
    expect(failedTask.get('.task-badge').classes()).toContain('failed')
    expect(failedTask.text()).toContain('tools.refinement.redaction_failed')
    expect(failedTask.find('a').exists()).toBe(false)
    expect(failedTask.get('details').text()).toContain('Unable to apply redactions safely')
    wrapper.unmount()
  })

  it('keeps the requested PDF selected even when another PDF has an unfinished review', async () => {
    mocks.routeQuery.document_id = '8'
    mocks.listJobs.mockResolvedValue([reviewJob()])
    mocks.listArtifacts.mockResolvedValue([])
    const wrapper = shallowMount(ToolsView)
    await flushPromises()

    expect(wrapper.get('.source-filename').text()).toBe('other.pdf')
    expect(wrapper.find('.redaction-review').exists()).toBe(false)
    wrapper.unmount()
  })

  it('distinguishes detection from applying and submits only reviewed areas', async () => {
    mocks.listJobs.mockResolvedValue([reviewJob()])
    mocks.listArtifacts.mockResolvedValue([])
    mocks.applyRedaction.mockResolvedValue({ ...reviewJob(), status: 'pending', stage: 'queued', options: { operation: 'apply' } })
    const wrapper = shallowMount(ToolsView)
    await flushPromises()

    expect(wrapper.get('.review-notice').text()).toBe('tools.refinement.review_notice')
    expect(wrapper.findAll('.task-row')[0]!.find('progress').exists()).toBe(false)
    await wrapper.get('.apply-bar .button').trigger('click')
    await flushPromises()

    expect(mocks.applyRedaction).toHaveBeenCalledWith(41, [
      { id: 'pii-1', page: 2, rect: { x: 10, y: 20, width: 30, height: 5 } },
    ], 'black')
    expect(wrapper.get('.redaction-processing').text()).toContain('tools.redaction.protected_processing')
    wrapper.unmount()
  })

  it('uploads a Word file directly independently of the selected PDF', async () => {
    mocks.listJobs.mockResolvedValue([])
    mocks.listArtifacts.mockResolvedValue([])
    mocks.wordToPdf.mockResolvedValue({ ...reviewJob(), kind: 'word_to_pdf', source_document_id: null, status: 'pending' })
    const wrapper = shallowMount(ToolsView)
    await flushPromises()
    await wrapper.findAll('[role="tab"]')[2]!.trigger('click')

    const file = new File(['word'], 'source.docx', { type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' })
    const input = wrapper.get('input[type="file"]')
    Object.defineProperty(input.element, 'files', { value: [file] })
    await input.trigger('change')
    expect(wrapper.get('.word-source').text()).toContain('source.docx')
    await wrapper.findAll('.conversion-operation')[0]!.get('.button.primary').trigger('click')
    await flushPromises()

    expect(mocks.wordToPdf).toHaveBeenCalledWith(file)
    expect(wrapper.get('.source-summary .source-filename').text()).toBe('source.pdf')
    wrapper.unmount()
  })

  it('shows both compression sizes and never stretches a completed status into a progress bar', async () => {
    mocks.listJobs.mockResolvedValue([{
      ...reviewJob(), kind: 'compression', status: 'completed', result_filename: 'compressed.pdf',
      result_size_bytes: 100, result_meta: { original_size_bytes: 1000, savings_percent: 90 },
    }])
    mocks.listArtifacts.mockResolvedValue([])
    const wrapper = shallowMount(ToolsView)
    await flushPromises()

    const task = wrapper.get('.task-row')
    expect(task.text()).toContain('1000 B')
    expect(task.text()).toContain('100 B')
    expect(task.text()).toContain('tools.refinement.reduction')
    expect(task.find('progress').exists()).toBe(false)
    expect(task.get('a').attributes('href')).toBe('/api/tools/jobs/41/download')
    wrapper.unmount()
  })

  it('provides keyboard tab navigation and manual area controls', async () => {
    mocks.listJobs.mockResolvedValue([reviewJob()])
    mocks.listArtifacts.mockResolvedValue([])
    const wrapper = shallowMount(ToolsView)
    await flushPromises()

    await wrapper.findAll('[role="tab"]')[0]!.trigger('keydown', { key: 'ArrowRight' })
    expect(wrapper.findAll('[role="tab"]')[1]!.attributes('aria-selected')).toBe('true')
    await wrapper.findAll('[role="tab"]')[1]!.trigger('keydown', { key: 'Home' })
    await wrapper.get('.add-area').trigger('click')
    expect(wrapper.findAll('.finding-overlay')).toHaveLength(2)
    const area = wrapper.findAll('.finding-overlay')[1]!
    await area.get('.resize-se').trigger('keydown', { key: 'ArrowRight' })
    expect(area.attributes('style')).toContain('width: 26%')
    wrapper.unmount()
  })

  it('deletes a box completely, restores it with undo and submits only remaining boxes', async () => {
    mocks.listJobs.mockResolvedValue([reviewJob()])
    mocks.listArtifacts.mockResolvedValue([])
    mocks.applyRedaction.mockResolvedValue({ ...reviewJob(), status: 'pending' })
    const wrapper = shallowMount(ToolsView)
    await flushPromises()
    expect(wrapper.findAll('.resize-handle')).toHaveLength(0)
    await wrapper.get('.finding-list-row .button').trigger('click')
    expect(wrapper.findAll('.finding-overlay')).toHaveLength(0)
    expect(wrapper.findAll('.finding-list-row')).toHaveLength(0)
    expect(wrapper.get('.apply-bar .primary').attributes('disabled')).toBeDefined()
    await wrapper.get('.undo-area').trigger('click')
    expect(wrapper.findAll('.finding-overlay')).toHaveLength(1)
    await wrapper.get('.add-area').trigger('click')
    await wrapper.findAll('.finding-list-row')[0]!.get('.button').trigger('click')
    await wrapper.get('.apply-bar .primary').trigger('click')
    await flushPromises()
    const submitted = mocks.applyRedaction.mock.calls[0]![1]
    expect(submitted).toHaveLength(1)
    expect(submitted[0].id).toMatch(/^manual-/)
    wrapper.unmount()
  })

  it('draws freely and through the draw button, moves boxes and undoes edits', async () => {
    mocks.listJobs.mockResolvedValue([reviewJob()])
    mocks.listArtifacts.mockResolvedValue([])
    const wrapper = shallowMount(ToolsView)
    await flushPromises()
    const preview = wrapper.get('.redaction-preview')
    vi.spyOn(preview.element, 'getBoundingClientRect').mockReturnValue({
      x: 0, y: 0, left: 0, top: 0, right: 1000, bottom: 1000, width: 1000, height: 1000, toJSON: () => ({}),
    })
    async function dragEmpty() {
      preview.element.dispatchEvent(new MouseEvent('pointerdown', { bubbles: true, button: 0, clientX: 500, clientY: 500 }))
      window.dispatchEvent(new MouseEvent('pointermove', { clientX: 700, clientY: 600 }))
      window.dispatchEvent(new MouseEvent('pointerup'))
      await flushPromises()
    }
    preview.element.dispatchEvent(new MouseEvent('pointerdown', { bubbles: true, button: 0, clientX: 500, clientY: 500 }))
    window.dispatchEvent(new MouseEvent('pointerup'))
    await flushPromises()
    expect(wrapper.findAll('.finding-overlay')).toHaveLength(1)
    await dragEmpty()
    expect(wrapper.findAll('.finding-overlay')).toHaveLength(2)
    await wrapper.get('.undo-area').trigger('click')
    expect(wrapper.findAll('.finding-overlay')).toHaveLength(1)
    await wrapper.get('.draw-area').trigger('click')
    await dragEmpty()
    expect(wrapper.findAll('.finding-overlay')).toHaveLength(2)
    expect(wrapper.get('.draw-area').attributes('aria-pressed')).toBe('false')
    const added = wrapper.findAll('.finding-overlay')[1]!
    expect(added.attributes('style')).toContain('left: 50%')
    added.element.dispatchEvent(new MouseEvent('pointerdown', { bubbles: true, button: 0, clientX: 600, clientY: 550 }))
    window.dispatchEvent(new MouseEvent('pointermove', { clientX: 1100, clientY: 1100 }))
    window.dispatchEvent(new MouseEvent('pointerup'))
    await flushPromises()
    expect(added.attributes('style')).toContain('left: 80%')
    expect(added.attributes('style')).toContain('top: 90%')
    await wrapper.get('.undo-area').trigger('click')
    expect(wrapper.findAll('.finding-overlay')[1]!.attributes('style')).toContain('left: 50%')
    await wrapper.get('.undo-area').trigger('click')
    expect(wrapper.findAll('.finding-overlay')).toHaveLength(1)
    wrapper.unmount()
  })

  it('cancels unfinished drawing and resizing with Escape', async () => {
    mocks.listJobs.mockResolvedValue([reviewJob()])
    mocks.listArtifacts.mockResolvedValue([])
    const wrapper = shallowMount(ToolsView)
    await flushPromises()
    const preview = wrapper.get('.redaction-preview')
    vi.spyOn(preview.element, 'getBoundingClientRect').mockReturnValue({
      x: 0, y: 0, left: 0, top: 0, right: 1000, bottom: 1000, width: 1000, height: 1000, toJSON: () => ({}),
    })
    await wrapper.get('.draw-area').trigger('click')
    preview.element.dispatchEvent(new MouseEvent('pointerdown', { bubbles: true, button: 0, clientX: 500, clientY: 500 }))
    window.dispatchEvent(new MouseEvent('pointermove', { clientX: 700, clientY: 600 }))
    await preview.trigger('keydown', { key: 'Escape' })
    window.dispatchEvent(new MouseEvent('pointerup'))
    await flushPromises()
    expect(wrapper.findAll('.finding-overlay')).toHaveLength(1)
    await wrapper.get('.finding-select').trigger('click')
    wrapper.get('.resize-se').element.dispatchEvent(new MouseEvent('pointerdown', { bubbles: true, button: 0, clientX: 400, clientY: 250 }))
    window.dispatchEvent(new MouseEvent('pointermove', { clientX: 800, clientY: 600 }))
    await preview.trigger('keydown', { key: 'Escape' })
    expect(wrapper.get('.finding-overlay').attributes('style')).toContain('width: 30%')
    expect(wrapper.get('.undo-area').attributes('disabled')).toBeDefined()
    wrapper.unmount()
  })

  it('shows active jobs first, limits history and filters completed jobs by document', async () => {
    const completed = Array.from({ length: 7 }, (_, index) => ({
      ...reviewJob(), id: 100 + index, status: 'completed' as const,
      source_document_id: index === 0 ? 8 : 7,
    }))
    mocks.listJobs.mockResolvedValue([...completed, reviewJob()])
    mocks.listArtifacts.mockResolvedValue([])
    const wrapper = shallowMount(ToolsView)
    await flushPromises()
    expect(wrapper.findAll('.task-row')).toHaveLength(6)
    expect(wrapper.findAll('.task-row')[0]!.attributes('data-job-id')).toBe('41')
    await wrapper.get('.history-more').trigger('click')
    expect(wrapper.findAll('.task-row')).toHaveLength(8)
    await wrapper.get('.history-controls select').setValue('document')
    expect(wrapper.findAll('.task-row')).toHaveLength(6)
    expect(wrapper.find('[data-job-id="100"]').exists()).toBe(false)
    wrapper.unmount()
  })

  it('persists hiding a finished job and can restore it from hidden history', async () => {
    const finished = { ...reviewJob(), status: 'completed' as const }
    mocks.listJobs.mockResolvedValue([finished])
    mocks.listArtifacts.mockResolvedValue([])
    mocks.setJobHidden.mockImplementation(async (_, hidden) => ({ ...finished, hidden_from_history: hidden }))
    const wrapper = shallowMount(ToolsView)
    await flushPromises()
    await wrapper.get('.history-hide').trigger('click')
    await flushPromises()
    expect(mocks.setJobHidden).toHaveBeenCalledWith(41, true)
    expect(wrapper.find('.task-row').exists()).toBe(false)
    await wrapper.get('.history-controls input').setValue(true)
    expect(wrapper.find('.task-row').exists()).toBe(true)
    await wrapper.get('.history-hide').trigger('click')
    await flushPromises()
    expect(mocks.setJobHidden).toHaveBeenCalledWith(41, false)
    expect(wrapper.find('.task-row').exists()).toBe(false)
    await wrapper.get('.history-controls input').setValue(false)
    expect(wrapper.find('.task-row').exists()).toBe(true)
    wrapper.unmount()
  })
})
