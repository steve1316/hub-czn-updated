import { describe, it, expect, beforeEach, vi } from 'vitest'

// The Tauri command is dynamically imported inside api.ts, so it has to be mocked up front.
const invoke = vi.fn()
vi.mock('@tauri-apps/api/core', () => ({ invoke }))

/** Reimport api.ts with fresh module state, since the token is cached at module scope. */
async function freshApi() {
  vi.resetModules()
  return import('./api')
}

describe('ensureToken', () => {
  beforeEach(() => {
    invoke.mockReset()
    // The suite runs in the node environment, so there is no window to attach the global to.
    // Only __TAURI_INTERNALS__ is set, because that is all the packaged app actually gets.
    vi.stubGlobal('window', { __TAURI_INTERNALS__: {} })
  })

  it('does not cache an empty token', async () => {
    // Regression: the first call used to be cached even when it came back empty, which left every
    // later request unauthenticated for the rest of the session and showed "Missing or invalid
    // API token" on every page.
    const api = await freshApi()
    invoke.mockResolvedValueOnce('')
    expect(await api.ensureToken()).toBe('')

    invoke.mockResolvedValueOnce('real-token')
    expect(await api.ensureToken()).toBe('real-token')
  })

  it('caches a real token and stops asking Tauri', async () => {
    const api = await freshApi()
    invoke.mockResolvedValue('real-token')
    expect(await api.ensureToken()).toBe('real-token')
    expect(await api.ensureToken()).toBe('real-token')
    expect(invoke).toHaveBeenCalledTimes(1)
  })

  it('puts the token in the WebSocket query string', async () => {
    const api = await freshApi()
    invoke.mockResolvedValue('real-token')
    await api.ensureToken()
    expect(api.wsUrl('/ws')).toContain('?token=real-token')
  })
})

describe('ensureApi', () => {
  beforeEach(() => {
    invoke.mockReset()
    // The suite runs in the node environment, so there is no window to attach the global to.
    // Only __TAURI_INTERNALS__ is set, because that is all the packaged app actually gets.
    vi.stubGlobal('window', { __TAURI_INTERNALS__: {} })
  })

  it('resolves the port before the token so no request uses the default port', async () => {
    const api = await freshApi()
    invoke.mockImplementation(async (cmd: string) => (cmd === 'get_api_port' ? 7845 : 'real-token'))

    await api.ensureApi()

    expect(invoke).toHaveBeenCalledWith('get_api_port')
    expect(api.wsUrl('/ws')).toBe('ws://127.0.0.1:7845/ws?token=real-token')
  })
})

describe('inTauri', () => {
  beforeEach(() => { invoke.mockReset() })

  it('detects the shell without window.__TAURI__', async () => {
    // Regression: every call used to be gated on window.__TAURI__, which only exists when
    // withGlobalTauri is on. It is off, so the packaged app never invoked anything - the token
    // stayed empty and Setup showed "Missing or invalid API token".
    const api = await freshApi()
    vi.stubGlobal('window', { __TAURI_INTERNALS__: {} })
    expect(api.inTauri()).toBe(true)

    invoke.mockResolvedValue('real-token')
    expect(await api.ensureToken()).toBe('real-token')
    expect(invoke).toHaveBeenCalledWith('get_api_token')
  })

  it('stays out of the way in a plain browser', async () => {
    const api = await freshApi()
    vi.stubGlobal('window', {})
    expect(api.inTauri()).toBe(false)
    expect(await api.ensureToken()).toBe('')
    expect(invoke).not.toHaveBeenCalled()
  })
})

describe('request errors', () => {
  beforeEach(() => {
    vi.stubGlobal('window', {})
  })

  it('keeps the status so a page can tell "nothing yet" from a failure', async () => {
    const api = await freshApi()
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({ detail: 'No battle data captured yet' }), { status: 404 })))
    const err = await api.api.battleOverview().catch(e => e)
    expect(err).toBeInstanceOf(api.ApiError)
    expect(err.status).toBe(404)
    expect(err.message).toBe('No battle data captured yet')
    expect(api.isNotFound(err)).toBe(true)
    expect(api.isNotFound(new Error('boom'))).toBe(false)
  })
  it('treats "No data loaded" as nothing captured yet, whatever the status', async () => {
    const api = await freshApi()
    for (const status of [400, 404, 422]) {
      vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({ detail: 'No data loaded. Call /api/load first.' }), { status })))
      expect(api.isNoData(await api.api.fragments().catch(e => e))).toBe(true)
    }
  })

  it('does not treat a real failure as nothing captured yet', async () => {
    const api = await freshApi()
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({ detail: 'boom' }), { status: 500 })))
    expect(api.isNoData(await api.api.fragments().catch(e => e))).toBe(false)
    expect(api.isNoData(new TypeError('Failed to fetch'))).toBe(false)
  })
})
