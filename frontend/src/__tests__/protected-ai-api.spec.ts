import { aiAnalysisApi } from '@/api/ai'
import { toolsApi } from '@/api/tools'

describe('protected artifact and AI API clients', () => {
  it('loads the provider disclosure used by the consent dialog', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          provider: 'gemini',
          model: 'gemini-test',
          service_tier: 'paid',
          max_remote_retention_hours: 48,
          requires_verified_artifact: true,
        }),
        { status: 200, headers: { 'Content-Type': 'application/json' } },
      ),
    )
    vi.stubGlobal('fetch', fetchMock)

    await aiAnalysisApi.getProviderInfo()

    expect(fetchMock).toHaveBeenCalledWith('/api/ai/provider-info', {
      credentials: 'same-origin',
    })
  })

  it('creates an AI job with explicit consent and retention', async () => {
    const response = { id: 17, status: 'pending' }
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(response), {
        status: 202,
        headers: { 'Content-Type': 'application/json' },
      }),
    )
    vi.stubGlobal('fetch', fetchMock)

    await aiAnalysisApi.createJob({
      artifact_id: 9,
      task: 'layout_review',
      retention: 'retain_48h',
      consent_to_external_processing: true,
      acknowledge_provider_data_terms: true,
    })

    expect(fetchMock).toHaveBeenCalledWith('/api/ai/jobs', {
      credentials: 'same-origin',
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        artifact_id: 9,
        task: 'layout_review',
        retention: 'retain_48h',
        consent_to_external_processing: true,
        acknowledge_provider_data_terms: true,
      }),
    })
  })

  it('builds artifact preview/download URLs and deletes through the artifact endpoint', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(null, { status: 204 }))
    vi.stubGlobal('fetch', fetchMock)

    expect(toolsApi.artifactPagePreviewUrl(12, 3)).toBe('/api/tools/artifacts/12/pages/3')
    expect(toolsApi.artifactDownloadUrl(12)).toBe('/api/tools/artifacts/12/download')
    await toolsApi.deleteArtifact(12)

    expect(fetchMock).toHaveBeenCalledWith('/api/tools/artifacts/12', {
      credentials: 'same-origin',
      method: 'DELETE',
    })
  })

  it('cancels an active AI job through its action endpoint', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ id: 21, status: 'cancelled' }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    )
    vi.stubGlobal('fetch', fetchMock)

    await aiAnalysisApi.cancelJob(21)

    expect(fetchMock).toHaveBeenCalledWith('/api/ai/jobs/21/cancel', {
      credentials: 'same-origin',
      method: 'POST',
    })
  })
})
