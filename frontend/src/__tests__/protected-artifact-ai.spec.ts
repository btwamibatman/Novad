import { config, flushPromises, mount } from '@vue/test-utils'

import ProtectedArtifactAI from '@/components/tools/ProtectedArtifactAI.vue'
import { i18n } from '@/i18n'
import type { AIAnalysisJobRead, DocumentArtifactRead } from '@/types/document'

const apiMocks = vi.hoisted(() => ({
  listJobs: vi.fn(),
  getProviderInfo: vi.fn(),
  getJob: vi.fn(),
  createJob: vi.fn(),
  deleteRemoteFile: vi.fn(),
  cancelJob: vi.fn(),
  deleteArtifact: vi.fn(),
}))

vi.mock('@/api/ai', () => ({
  aiAnalysisApi: {
    listJobs: apiMocks.listJobs,
    getProviderInfo: apiMocks.getProviderInfo,
    getJob: apiMocks.getJob,
    createJob: apiMocks.createJob,
    deleteRemoteFile: apiMocks.deleteRemoteFile,
    cancelJob: apiMocks.cancelJob,
  },
}))

vi.mock('@/api/tools', () => ({
  toolsApi: {
    artifactPagePreviewUrl: (artifactId: number, page: number) =>
      `/api/tools/artifacts/${artifactId}/pages/${page}`,
    artifactDownloadUrl: (artifactId: number) => `/api/tools/artifacts/${artifactId}/download`,
    deleteArtifact: apiMocks.deleteArtifact,
  },
}))

function readyArtifact(): DocumentArtifactRead {
  return {
    id: 9,
    source_document_id: 4,
    kind: 'protected_pdf',
    status: 'ready_for_ai',
    filename: 'protected-report.pdf',
    content_type: 'application/pdf',
    size_bytes: 1024,
    source_sha256: 'source',
    artifact_sha256: 'artifact',
    privacy_policy: {
      categories: ['personal', 'financial', 'visual'],
      redaction_mode: 'black',
      selected_finding_count: 2,
      manual_confirmation: true,
      flattened: true,
      selectable_text: false,
      render_dpi: 200,
      image_format: 'jpeg',
      jpeg_quality: 90,
    },
    policy_version: '1',
    detector_version: 'document-redaction-v1',
    coverage_report: {
      page_count: 3,
      checked_pages: [1, 2, 3],
      unchecked_pages: [],
      verification_completed: true,
    },
    verification_report: { passed: true, risks: [] },
    error_message: null,
    created_at: '2026-08-20T10:00:00Z',
    updated_at: '2026-08-20T10:00:00Z',
    verified_at: '2026-08-20T10:00:00Z',
  }
}

function analysisJob(overrides: Partial<AIAnalysisJobRead> = {}): AIAnalysisJobRead {
  return {
    id: 21,
    artifact_id: 9,
    task: 'content_review',
    status: 'pending',
    stage: 'queued',
    progress: 0,
    worker_active: false,
    provider: 'gemini',
    model: null,
    retention: 'delete_after_analysis',
    result: {},
    usage: {},
    attempts: 0,
    not_before: null,
    error_code: null,
    public_error: null,
    remote_file_present: false,
    remote_cleanup_status: 'not_applicable',
    remote_cleanup_error: null,
    provider_file_expires_at: null,
    created_at: '2026-08-20T10:00:00Z',
    started_at: null,
    finished_at: null,
    ...overrides,
  }
}

describe('ProtectedArtifactAI', () => {
  beforeAll(() => {
    config.global.plugins = [i18n]
  })
  beforeEach(() => {
    vi.clearAllMocks()
    i18n.global.locale.value = 'ru'
    apiMocks.getProviderInfo.mockResolvedValue({
      provider: 'Gemini',
      model: 'gemini-test',
      service_tier: 'paid',
      max_remote_retention_hours: 48,
      requires_verified_artifact: true,
    })
  })
  afterEach(() => {
    vi.useRealTimers()
  })
  afterAll(() => {
    config.global.plugins = []
  })

  it('blocks AI submission when artifact verification needs review', async () => {
    apiMocks.listJobs.mockResolvedValue([])
    const artifact = readyArtifact()
    artifact.status = 'needs_review'
    artifact.verification_report = { passed: false, risks: ['privacy_findings_remain'] }

    const wrapper = mount(ProtectedArtifactAI, {
      props: { artifact, sourceJob: null },
    })
    await flushPromises()

    expect(wrapper.text()).toContain('AI-загрузка заблокирована')
    expect(wrapper.findAll('button').some((button) => button.text().includes('Использовать защищённую'))).toBe(false)
    wrapper.unmount()
  })

  it('requires both consents and sends only the selected protected artifact', async () => {
    apiMocks.listJobs.mockResolvedValue([])
    apiMocks.createJob.mockResolvedValue(
      analysisJob({ task: 'layout_review', retention: 'retain_48h' }),
    )

    const wrapper = mount(ProtectedArtifactAI, {
      props: { artifact: readyArtifact(), sourceJob: null, initialTask: 'layout_review' },
    })
    await flushPromises()

    expect(wrapper.text()).toContain('Проверено страниц: 3 / 3')
    await wrapper.get('button.primary').trigger('click')

    const dialog = wrapper.get('[role="dialog"]')
    expect(dialog.text()).toContain('только проверенная защищённая PDF-копия')
    expect(dialog.text()).toContain('AI-провайдер: Gemini')
    expect(dialog.text()).toContain('gemini-test')
    expect(dialog.text()).toContain('Тариф сервиса: Платный')
    expect((dialog.get('select').element as HTMLSelectElement).value).toBe('layout_review')
    expect(dialog.get('button[type="submit"]').attributes('disabled')).toBeDefined()

    await dialog.get('input[value="retain_48h"]').setValue()
    const consentChecks = dialog.findAll('input[type="checkbox"]')
    await consentChecks[0]!.setValue(true)
    await consentChecks[1]!.setValue(true)
    await dialog.get('form').trigger('submit')
    await flushPromises()

    expect(apiMocks.createJob).toHaveBeenCalledWith({
      artifact_id: 9,
      task: 'layout_review',
      retention: 'retain_48h',
      consent_to_external_processing: true,
      acknowledge_provider_data_terms: true,
    })
    expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
    expect(wrapper.text()).toContain('Проверка оформления')
    wrapper.unmount()
  })

  it('renders protected status and consent in the English locale', async () => {
    i18n.global.locale.value = 'en'
    apiMocks.listJobs.mockResolvedValue([])

    const wrapper = mount(ProtectedArtifactAI, {
      props: { artifact: readyArtifact(), sourceJob: null, initialTask: 'summary' },
    })
    await flushPromises()

    expect(wrapper.text()).toContain('Ready for AI')
    expect(wrapper.text()).toContain('Use protected copy for AI')
    await wrapper.get('button.primary').trigger('click')
    const dialog = wrapper.get('[role="dialog"]')
    expect(dialog.text()).toContain('Confirm AI analysis')
    expect(dialog.text()).toContain('Service tier: Paid')
    expect(dialog.text()).toContain('Delete after analysis')
    expect((dialog.get('select').element as HTMLSelectElement).value).toBe('summary')
    wrapper.unmount()
  })

  it('restores and renders structured results with clickable page evidence', async () => {
    apiMocks.listJobs.mockResolvedValue([
      analysisJob({
        status: 'completed',
        stage: 'completed',
        progress: 100,
        model: 'gemini-test',
        result: {
          task: 'content_review',
          overview: 'Документ в целом последователен.',
          verdict: 'Нужна одна правка.',
          coverage: { pages_reviewed: [1, 2, 3], complete: true, limitations: [] },
          key_points: [
            {
              text: 'Основной тезис',
              page: 2,
              evidence: 'Проверяемый фрагмент',
              evidence_verified: true,
            },
          ],
          findings: [
            {
              category: 'consistency',
              severity: 'medium',
              page: 3,
              evidence: 'Разные обозначения',
              explanation: 'Термин используется непоследовательно.',
              suggestion: 'Унифицировать термин.',
              confidence: 0.9,
              basis: 'native_text',
              requires_human_review: false,
              evidence_verified: true,
            },
          ],
        },
      }),
    ])

    const wrapper = mount(ProtectedArtifactAI, {
      props: { artifact: readyArtifact(), sourceJob: null },
    })
    await flushPromises()

    expect(wrapper.text()).toContain('Документ в целом последователен.')
    expect(wrapper.text()).toContain('Проверяемый фрагмент')
    const pageLink = wrapper.findAll('.citation-link').find((item) => item.text() === 'стр. 2')
    expect(pageLink).toBeDefined()
    await pageLink!.trigger('click')
    expect(wrapper.get('.final-preview img').attributes('src')).toBe(
      '/api/tools/artifacts/9/pages/2',
    )
    wrapper.unmount()
  })

  it('polls the active job detail until a structured result is ready', async () => {
    vi.useFakeTimers()
    apiMocks.listJobs.mockResolvedValue([analysisJob()])
    apiMocks.getJob.mockResolvedValue(
      analysisJob({
        status: 'completed',
        stage: 'completed',
        progress: 100,
        result: {
          task: 'content_review',
          overview: 'Результат после polling.',
          verdict: '',
          key_points: [],
          findings: [],
          coverage: { pages_reviewed: [1, 2, 3], complete: true, limitations: [] },
        },
      }),
    )

    const wrapper = mount(ProtectedArtifactAI, {
      props: { artifact: readyArtifact(), sourceJob: null },
    })
    await flushPromises()
    await vi.advanceTimersByTimeAsync(2000)
    await flushPromises()

    expect(apiMocks.getJob).toHaveBeenCalledWith(21)
    expect(wrapper.text()).toContain('Результат после polling.')
    wrapper.unmount()
  })

  it('cancels an active AI analysis from its progress state', async () => {
    apiMocks.listJobs.mockResolvedValue([analysisJob({ status: 'running', progress: 35 })])
    apiMocks.cancelJob.mockResolvedValue(
      analysisJob({ status: 'cancelled', stage: 'cancelled', progress: 35 }),
    )
    vi.spyOn(window, 'confirm').mockReturnValue(true)

    const wrapper = mount(ProtectedArtifactAI, {
      props: { artifact: readyArtifact(), sourceJob: null },
    })
    await flushPromises()
    const cancelButton = wrapper.findAll('button').find((button) => button.text() === 'Отменить анализ')
    expect(cancelButton).toBeDefined()
    await cancelButton!.trigger('click')
    await flushPromises()

    expect(apiMocks.cancelJob).toHaveBeenCalledWith(21)
    expect(wrapper.text()).toContain('Отменено')
    wrapper.unmount()
  })

  it('reloads all linked jobs after deleting a shared remote file', async () => {
    const first = analysisJob({
      status: 'completed',
      remote_file_present: true,
      remote_cleanup_status: 'retained',
      provider_file_expires_at: '2026-08-22T10:00:00Z',
    })
    const second = analysisJob({
      id: 22,
      status: 'completed',
      remote_file_present: true,
      remote_cleanup_status: 'retained',
      provider_file_expires_at: '2026-08-22T10:00:00Z',
    })
    apiMocks.listJobs
      .mockResolvedValueOnce([first, second])
      .mockResolvedValueOnce([
        { ...first, remote_file_present: false, provider_file_expires_at: null },
        { ...second, remote_file_present: false, provider_file_expires_at: null },
      ])
    apiMocks.deleteRemoteFile.mockResolvedValue({
      ...first,
      remote_file_present: false,
      provider_file_expires_at: null,
    })

    const wrapper = mount(ProtectedArtifactAI, {
      props: { artifact: readyArtifact(), sourceJob: null },
    })
    await flushPromises()
    const deleteButton = wrapper
      .findAll('button')
      .find((button) => button.text().includes('Удалить копию у AI-провайдера'))
    expect(deleteButton).toBeDefined()
    await deleteButton!.trigger('click')
    await flushPromises()

    expect(apiMocks.deleteRemoteFile).toHaveBeenCalledWith(21)
    expect(apiMocks.listJobs).toHaveBeenCalledTimes(2)
    expect(wrapper.text()).not.toContain('Сначала удалите все сохранённые копии')
    wrapper.unmount()
  })

  it('shows cleanup expiry and disables remote deletion while cleanup is pending', async () => {
    apiMocks.listJobs.mockResolvedValue([
      analysisJob({
        status: 'completed',
        remote_file_present: true,
        remote_cleanup_status: 'pending',
        provider_file_expires_at: '2026-08-22T10:00:00Z',
      }),
    ])

    const wrapper = mount(ProtectedArtifactAI, {
      props: { artifact: readyArtifact(), sourceJob: null },
    })
    await flushPromises()

    expect(wrapper.text()).toContain('2026')
    expect(wrapper.get('.remote-delete-button').attributes('disabled')).toBeDefined()
    wrapper.unmount()
  })

  it('reconciles an elapsed remote expiry and releases the local artifact action', async () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-08-20T10:00:00Z'))
    const retained = analysisJob({
      status: 'completed',
      remote_file_present: true,
      remote_cleanup_status: 'retained',
      provider_file_expires_at: '2026-08-20T10:00:01Z',
    })
    apiMocks.listJobs
      .mockResolvedValueOnce([retained])
      .mockResolvedValueOnce([
        {
          ...retained,
          remote_file_present: false,
          remote_cleanup_status: 'deleted',
          provider_file_expires_at: null,
        },
      ])

    const wrapper = mount(ProtectedArtifactAI, {
      props: { artifact: readyArtifact(), sourceJob: null },
    })
    await flushPromises()
    await vi.advanceTimersByTimeAsync(2000)
    await flushPromises()

    expect(apiMocks.listJobs).toHaveBeenCalledTimes(2)
    expect(wrapper.find('.remote-delete-button').exists()).toBe(false)
    expect(wrapper.get('.artifact-actions .button.danger').attributes('disabled')).toBeUndefined()
    wrapper.unmount()
  })
})
