import { useEffect, useState } from 'react'
import { setApiToken } from '@/lib/api'

/**
 * Grabs the API token that Tauri read off the sidecar's stdout. Runs early so the WebSocket hooks
 * have it by the time they connect.
 *
 * @returns The token, or an empty string in dev mode unless VITE_API_TOKEN is set.
 */
export function useApiToken(): string {
  const [token, setToken] = useState<string>((import.meta.env.VITE_API_TOKEN as string | undefined) ?? '')

  useEffect(() => {
    if (!window.__TAURI__) return        // dev mode - use the env var
    import('@tauri-apps/api/core')
      .then(({ invoke }) => invoke<string>('get_api_token'))
      .then(t => {
        setApiToken(t)                   // update the client before React re-renders
        setToken(t)
      })
      .catch(console.error)
  }, [])

  return token
}
