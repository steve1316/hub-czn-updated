import { Outlet } from 'react-router-dom'
import { Sidebar } from './Sidebar'
import { CaptureLogProvider } from '@/hooks/useCaptureLog'

export function AppShell() {
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
