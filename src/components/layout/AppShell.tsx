import { useEffect } from 'react'
import { Outlet } from 'react-router-dom'
import { Sidebar } from './Sidebar'
import { CaptureLogProvider } from '@/hooks/useCaptureLog'
import { stepUiScale } from '@/lib/ui-scale'

// Ctrl + these keys change the interface size
const SCALE_KEYS: Record<string, -1 | 0 | 1> = { '=': 1, '+': 1, '-': -1, '_': -1, '0': 0 }

export function AppShell() {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const dir = e.ctrlKey && !e.altKey ? SCALE_KEYS[e.key] : undefined
      if (dir === undefined) return
      e.preventDefault()
      stepUiScale(dir)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  return (
    <CaptureLogProvider>
      <div className="flex h-screen overflow-hidden bg-[#121212] text-[#ffffff]">
        <Sidebar />
        <main className="flex-1 overflow-auto">
          <Outlet />
        </main>
      </div>
    </CaptureLogProvider>
  )
}
