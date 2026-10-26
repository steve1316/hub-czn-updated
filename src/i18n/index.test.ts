import { describe, it, expect, vi, beforeEach } from 'vitest'

describe('i18n language', () => {
  beforeEach(() => {
    vi.resetModules()
  })

  it('forces a stored pt-BR language to en', async () => {
    const store: Record<string, string> = { 'hub-czn.lang': 'pt-BR' }
    vi.stubGlobal('localStorage', {
      getItem: (k: string) => store[k] ?? null,
      setItem: (k: string, v: string) => {
        store[k] = v
      },
    })
    const { default: i18n } = await import('./index')
    expect(i18n.language).toBe('en')
    expect(store['hub-czn.lang']).toBe('en')
  })
})
