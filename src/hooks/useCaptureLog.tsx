import { createContext, useState, useEffect, useCallback, useContext, type ReactNode } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { wsUrl } from '@/lib/api'
import { useApiPort } from '@/hooks/useApiPort'
import type { CaptureLogMessage } from '@/lib/types'

/** Queries that read the live snapshot, refetched when the sidecar says it was updated. */
export const SNAPSHOT_QUERY_KEYS = [['fragments'], ['combatants'], ['status'], ['rescue-records']] as const

/** How long saves must go quiet before the snapshot queries refetch. */
const REFETCH_DEBOUNCE_MS = 500

/** What the capture log context hands to consumers. */
interface CaptureLogValue {
  /** The most recent capture log lines, oldest first. */
  messages: CaptureLogMessage[]
  /** Whether the capture-log WebSocket is currently open. */
  connected: boolean
  /** Empties the log lines. */
  clear: () => void
}

const CaptureLogContext = createContext<CaptureLogValue | null>(null)

/**
 * Opens the single capture-log WebSocket for the whole app. The server hands each message to one connection, so only one may exist.
 * A `snapshot_updated` event is not a log line, it makes the snapshot queries refetch.
 *
 * @param props - The children to wrap.
 * @returns The provider element.
 */
export function CaptureLogProvider({ children }: { children: ReactNode }) {
  const port = useApiPort()
  const qc = useQueryClient()
  const [messages, setMessages] = useState<CaptureLogMessage[]>([])
  const [connected, setConnected] = useState(false)

  useEffect(() => {
    let destroyed = false
    let retryTimer: ReturnType<typeof setTimeout> | null = null
    let refetchTimer: ReturnType<typeof setTimeout> | null = null
    let ws: WebSocket | null = null

    // A burst of saves makes one refetch, fired once the burst has been quiet for a moment.
    function scheduleRefetch() {
      if (refetchTimer !== null) clearTimeout(refetchTimer)
      refetchTimer = setTimeout(() => {
        refetchTimer = null
        SNAPSHOT_QUERY_KEYS.forEach(queryKey => qc.invalidateQueries({ queryKey }))
      }, REFETCH_DEBOUNCE_MS)
    }

    function connect() {
      if (destroyed) return
      const socket = new WebSocket(wsUrl('/ws/capture-log'))
      ws = socket

      socket.onopen = () => setConnected(true)
      socket.onclose = () => {
        setConnected(false)
        if (!destroyed) retryTimer = setTimeout(connect, 2000)
      }
      socket.onerror = () => socket.close()
      socket.onmessage = (e) => {
        try {
          const msg = JSON.parse(e.data)
          if (msg.type === 'snapshot_updated') {
            scheduleRefetch()
            return
          }
          setMessages(prev => [...prev.slice(-499), msg as CaptureLogMessage])
        } catch {
          // ignore malformed messages
        }
      }
    }

    connect()
    return () => {
      destroyed = true
      if (retryTimer !== null) clearTimeout(retryTimer)
      if (refetchTimer !== null) clearTimeout(refetchTimer)
      ws?.close()
    }
  }, [port, qc])

  const clear = useCallback(() => setMessages([]), [])

  return <CaptureLogContext.Provider value={{ messages, connected, clear }}>{children}</CaptureLogContext.Provider>
}

/**
 * Reads the shared capture log.
 *
 * @returns The log lines, whether the socket is connected, and a function that clears the lines.
 */
export function useCaptureLog(): CaptureLogValue {
  const value = useContext(CaptureLogContext)
  if (!value) throw new Error('useCaptureLog must be used inside CaptureLogProvider')
  return value
}
