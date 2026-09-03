import { useEffect, useState } from 'react'

import { inTauri } from '@/lib/api'

export function useApiPort(): number {
  const envPort = Number(import.meta.env.VITE_API_PORT ?? 7842)
  const [port, setPort] = useState<number>(envPort)

  useEffect(() => {
    if (!inTauri()) return               // dev mode - use env var
    import('@tauri-apps/api/core')
      .then(({ invoke }) => invoke<number>('get_api_port'))
      .then(setPort)
      .catch(console.error)
  }, [])

  return port
}
