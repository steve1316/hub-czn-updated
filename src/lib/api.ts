import type {
  ApiStatus, GameData, LoadResponse, MemoryFragment,
  SetupStatus, SetupActionResponse, RemoveCertResponse, ClearRedirectResponse, CaptureStatus,
  CaptureStartRequest, CaptureStopResponse, CaptureSettings, CaptureSettingsChange, RescueBanner,
  Combatant, CombatantStats, ScoringPriorities,
  OptimizerConfig, EquipmentSet, Monster, AboutInfo, CharPreset,
  SimulateRequest, SimulateDamageResponse, DeckInfo,
  CardEntry, CardCharacter, BattleRecord, BattleAnalytics,
  BattleOverview,
  DeckBuilderCombatantResponse,
  ExtractStatus, ExtractSettings,
} from './types'

/** A failed API call, keeping the HTTP status next to the server's message. */
export class ApiError extends Error {
  /** The HTTP status code of the failed response. */
  status: number

  /**
   * @param message The server's `detail` text, or the status text when there is none.
   * @param status The HTTP status code.
   */
  constructor(message: string, status: number) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

/**
 * Whether an error is the API saying there is nothing there yet, as opposed to a real failure.
 *
 * @param err Any thrown value.
 * @returns True for an `ApiError` with status 404.
 */
export function isNotFound(err: unknown): boolean {
  return err instanceof ApiError && err.status === 404
}

/**
 * Whether an error is the sidecar saying no capture has been loaded yet. The routes answer this with 400, 404 or 422, so
 * the message is what identifies it.
 *
 * @param err Any thrown value.
 * @returns True for an `ApiError` whose message starts with "No data loaded".
 */
export function isNoData(err: unknown): boolean {
  return err instanceof ApiError && err.message.startsWith('No data loaded')
}

let _port: number = Number(import.meta.env.VITE_API_PORT ?? 7842)
let _token: string = (import.meta.env.VITE_API_TOKEN as string | undefined) ?? ''

export function setApiPort(port: number): void {
  _port = port
}

function base(): string {
  const envUrl = import.meta.env.VITE_API_URL as string | undefined
  return envUrl ?? `http://127.0.0.1:${_port}`
}

/** Build a WebSocket URL with the token in the query string, since sockets cannot send headers. */
export function wsUrl(path: string): string {
  const url = base().replace(/^http/, 'ws')
  return _token ? `${url}${path}?token=${encodeURIComponent(_token)}` : `${url}${path}`
}

let _tokenPromise: Promise<string> | null = null
let _bootstrapPromise: Promise<void> | null = null

/** How often the app asks whether the sidecar is up at launch, in milliseconds. */
const API_READY_POLL_MS = 250
/** How long the app waits for the sidecar at launch before rendering anyway, so a sidecar that never starts still shows its errors. */
const API_READY_TIMEOUT_MS = 60_000

/**
 * True when the page is running inside the Tauri shell.
 *
 * Do not check `window.__TAURI__` here. That global only exists when `withGlobalTauri` is turned on
 * in tauri.conf.json, and it is not, so it is always undefined in the packaged app.
 * `__TAURI_INTERNALS__` is what the Tauri API itself uses and is always injected.
 *
 * @returns True if Tauri commands can be invoked.
 */
export function inTauri(): boolean {
  return typeof window !== 'undefined' && '__TAURI_INTERNALS__' in window
}

/**
 * Fetch the token from Tauri once and remember it. App waits on this before rendering, so the
 * synchronous `wsUrl()` always has it by the time a socket opens.
 *
 * Tauri makes the token before it starts the sidecar, so it is ready at once. An empty answer means something went wrong (or dev mode, where the
 * token comes from `.env.development`), so it is not cached - otherwise one bad reply would leave every later request unauthenticated.
 *
 * @returns The API token, or an empty string in dev mode.
 */
export async function ensureToken(): Promise<string> {
  if (_token) return _token
  if (!inTauri()) return _token
  if (!_tokenPromise) {
    _tokenPromise = import('@tauri-apps/api/core')
      .then(({ invoke }) => invoke<string>('get_api_token'))
      .catch(() => '')
      .then(t => {
        if (t) _token = t
        else _tokenPromise = null
        return t
      })
  }
  return _tokenPromise
}

/**
 * Resolve the sidecar's port and token into module state, then wait until the sidecar answers. Tauri knows the port and token straight away, but the
 * bundled sidecar takes a few seconds to start, and a page that fetched in that window would show its fallback (such as an unticked setting) for
 * good. Doing it in one place keeps the port from arriving after a page has already started fetching.
 */
export async function ensureApi(): Promise<void> {
  if (!_bootstrapPromise) {
    _bootstrapPromise = (async () => {
      if (inTauri()) {
        const { invoke } = await import('@tauri-apps/api/core')
        const port = await invoke<number>('get_api_port').catch(() => 0)
        if (port) _port = port
      }
      await ensureToken()
      if (inTauri()) await waitForApi()
    })()
  }
  return _bootstrapPromise
}

/** Ask the sidecar for its status until it answers, giving up after `API_READY_TIMEOUT_MS`. */
async function waitForApi(): Promise<void> {
  const deadline = Date.now() + API_READY_TIMEOUT_MS
  while (Date.now() < deadline) {
    try {
      await request('/api/status')
      return
    } catch (err) {
      // Any HTTP answer means the sidecar is up. Only a failed connection means it is still starting.
      if (err instanceof ApiError) return
      await new Promise(resolve => setTimeout(resolve, API_READY_POLL_MS))
    }
  }
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const hasBody = options?.body != null
  const token = await ensureToken()
  const res = await fetch(`${base()}${path}`, {
    ...options,
    headers: {
      ...(hasBody && { 'Content-Type': 'application/json' }),
      ...(token && { 'X-Hub-Token': token }),
      ...options?.headers,
    },
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new ApiError((err as { detail: string }).detail ?? res.statusText, res.status)
  }
  return res.json() as Promise<T>
}

export function assetUrl(path: string): string {
  return `${base()}${path}`
}

export const api = {
  status: () => request<ApiStatus>('/api/status'),

  load: (path: string) =>
    request<LoadResponse>('/api/load', {
      method: 'POST',
      body: JSON.stringify({ path }),
    }),

  fragments: (params?: { slot?: number; set_id?: number; unequipped?: boolean }) => {
    const qs = new URLSearchParams()
    if (params?.slot != null) qs.set('slot', String(params.slot))
    if (params?.set_id != null) qs.set('set_id', String(params.set_id))
    if (params?.unequipped) qs.set('unequipped', 'true')
    const query = qs.toString() ? `?${qs}` : ''
    return request<MemoryFragment[]>(`/api/fragments${query}`)
  },

  gameData: () => request<GameData>('/api/game-data'),

  setupStatus: () => request<SetupStatus>('/api/setup/status'),

  clearRedirect: () =>
    request<ClearRedirectResponse>('/api/setup/clear-redirect', { method: 'POST' }),

  generateCert: () =>
    request<SetupActionResponse>('/api/setup/generate-cert', { method: 'POST' }),

  openCert: () =>
    request<SetupActionResponse>('/api/setup/open-cert', { method: 'POST' }),

  installCertificate: () =>
    request<SetupActionResponse>('/api/setup/install-certificate', { method: 'POST' }),

  removeCertificate: () =>
    request<RemoveCertResponse>('/api/setup/remove-certificate', { method: 'POST' }),

  extractStatus: () => request<ExtractStatus>('/api/game-data/extract/status'),

  saveExtractConfig: (body: Partial<ExtractSettings>) =>
    request<ExtractSettings>('/api/game-data/extract/config', { method: 'POST', body: JSON.stringify(body) }),

  startExtract: () => request<{ ok: boolean }>('/api/game-data/extract/start', { method: 'POST' }),

  cancelExtract: () => request<{ ok: boolean }>('/api/game-data/extract/cancel', { method: 'POST' }),

  applyCharacters: (dryRun: boolean) =>
    request<{ ok: boolean }>('/api/game-data/apply', { method: 'POST', body: JSON.stringify({ dry_run: dryRun }) }),

  captureStatus: () => request<CaptureStatus>('/api/capture/status'),

  captureStart: (body: CaptureStartRequest) =>
    request('/api/capture/start', { method: 'POST', body: JSON.stringify(body) }),

  captureStop: () => request<CaptureStopResponse>('/api/capture/stop', { method: 'POST' }),

  captureSetRegion: (region: 'global' | 'asia') =>
    request<SetupActionResponse>('/api/capture/set-region', { method: 'POST', body: JSON.stringify({ region }) }),

  captureSettings: () => request<CaptureSettings>('/api/capture/settings'),

  captureSetSettings: (body: CaptureSettingsChange) =>
    request<CaptureSettings>('/api/capture/settings', { method: 'POST', body: JSON.stringify(body) }),

  captureOpenSnapshots: () =>
    request<SetupActionResponse>('/api/capture/open-snapshots', { method: 'POST' }),

  autoscrollStart: (pagesCount: number) => request<{ ok: boolean }>('/api/autoscroll/start', { method: 'POST', body: JSON.stringify({ pages_count: pagesCount }) }),
  autoscrollStop:  () => request<{ ok: boolean }>('/api/autoscroll/stop',  { method: 'POST' }),
  combatantsExport: () => request<unknown[]>('/api/combatants/export'),

  rescueRecords: () => request<RescueBanner[]>('/api/rescue/records'),

  combatants: () => request<Combatant[]>('/api/combatants'),

  combatantStats: (charId: string) =>
    request<CombatantStats>(`/api/combatants/${encodeURIComponent(charId)}/stats`),

  scoringPriorities: () => request<ScoringPriorities>('/api/scoring/priorities'),

  saveScoringPriorities: (weights: Record<string, number>) =>
    request<ScoringPriorities>('/api/scoring/priorities', {
      method: 'POST',
      body: JSON.stringify({ weights }),
    }),

  optimizeSets: () => request<EquipmentSet[]>('/api/optimize/sets'),

  // Sprint 2h1: monster catalog feeds the Optimizer's Monster Picker dropdown.
  monsterCatalog: () => request<Monster[]>('/api/optimize/monster-catalog'),

  optimizeStart: (config: OptimizerConfig) =>
    request<{ job_id: string }>('/api/optimize/start', {
      method: 'POST',
      body: JSON.stringify(config),
    }),

  optimizeCancel: () =>
    request<{ cancelled: boolean }>('/api/optimize/cancel', { method: 'POST' }),

  about: () => request<AboutInfo>('/api/about'),

  simulateDamage: (body: SimulateRequest) =>
    request<SimulateDamageResponse>('/api/simulate/damage', {
      method: 'POST',
      body: JSON.stringify(body),
    }),

  simulateDecks: (charName: string) =>
    request<DeckInfo[]>(`/api/simulate/decks/${encodeURIComponent(charName)}`),

  cardCharacters: () => request<CardCharacter[]>('/api/cards/characters'),

  cards: (charResId?: number) => {
    const qs = charResId != null ? `?char_res_id=${charResId}` : ''
    return request<CardEntry[]>(`/api/cards${qs}`)
  },

deckBuilderCombatant: (charResId: number) =>
  request<DeckBuilderCombatantResponse>(`/api/deck-builder/combatants/${charResId}`),


  battleHistory: (limit = 20) =>
    request<BattleRecord[]>(`/api/battle/history?limit=${limit}`),

  battleAnalytics: () => request<BattleAnalytics>('/api/battle/analytics'),

  battleOverview: () => request<BattleOverview>('/api/battle/overview'),

  charPreset: (charId: number) =>
    request<CharPreset>(`/api/scoring/char-preset/${charId}`),

  charWeights: (charId: string) =>
    request<ScoringPriorities>(`/api/scoring/char-weights/${encodeURIComponent(charId)}`),

  saveCharWeights: (charId: string, weights: Record<string, number>) =>
    request<ScoringPriorities>(`/api/scoring/char-weights/${encodeURIComponent(charId)}`, {
      method: 'POST',
      body: JSON.stringify({ weights }),
    }),

  deleteCharWeights: (charId: string) =>
    request<{ ok: boolean }>(`/api/scoring/char-weights/${encodeURIComponent(charId)}`, {
      method: 'DELETE',
    }),
}
