import { ApiError, requestJson } from '@/api/client'

describe('requestJson', () => {
  it('returns a typed JSON response and uses same-origin credentials', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ status: 'ok' }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    )
    vi.stubGlobal('fetch', fetchMock)

    await expect(requestJson<{ status: string }>('/health')).resolves.toEqual({
      status: 'ok',
    })
    expect(fetchMock).toHaveBeenCalledWith('/health', {
      credentials: 'same-origin',
    })
  })

  it('normalizes API errors and preserves Retry-After', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ detail: 'Rate limit exceeded' }), {
          status: 429,
          headers: {
            'Content-Type': 'application/json',
            'Retry-After': '17',
          },
        }),
      ),
    )

    const error = await requestJson('/api/documents').catch((reason) => reason)

    expect(error).toBeInstanceOf(ApiError)
    expect(error).toMatchObject({
      message: 'Rate limit exceeded',
      status: 429,
      retryAfter: '17',
    })
  })

  it('accepts a successful empty response', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(new Response(null, { status: 204 })),
    )

    await expect(
      requestJson<void>('/api/auth/logout', { method: 'POST' }),
    ).resolves.toBeUndefined()
  })
})
