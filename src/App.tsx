import { useEffect, useState } from 'react'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { AppShell } from './components/layout/AppShell'
import { ensureApi } from './lib/api'
import { FragmentsPage } from './pages/fragments/FragmentsPage'
import { SetupPage } from './pages/setup/SetupPage'
import { CapturePage } from './pages/capture/CapturePage'
import { RescuePage } from './pages/rescue/RescuePage'
import { CombatantsPage } from './pages/combatants/CombatantsPage'
import { OptimizerPage } from './pages/optimizer/OptimizerPage'
import { AboutPage } from './pages/about/AboutPage'
import { HomePage } from './pages/home/HomePage'
import { EncyclopediaPage } from './pages/encyclopedia/EncyclopediaPage'
import { CardsTab } from './pages/encyclopedia/components/CardsTab'
import { EquipmentsTab } from './pages/encyclopedia/components/EquipmentsTab'
import { EngravingsTab } from './pages/encyclopedia/components/EngravingsTab'
import { GlossaryTab } from './pages/encyclopedia/components/GlossaryTab'
import { BattlesPage } from './pages/battles/BattlesPage'
import { SimulateTab } from './pages/simulator/SimulateTab'
import { OverviewTab, AnalyticsTab, HistoryTab } from './pages/battle/BattleTabs'
import { DeckBuilderPage } from './pages/deck-builder/DeckBuilderPage'
import { GuidesPage } from './pages/guides/GuidesPage'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      staleTime: 30_000,
      refetchOnWindowFocus: false,
    },
  },
})

function AppRoutes() {
  const { t } = useTranslation()
  const [apiReady, setApiReady] = useState(false)

  // Wait for the port and token before rendering. A page that fetches or opens a WebSocket on
  // mount would otherwise use the default port and no token at all. Resolves immediately in dev.
  useEffect(() => { ensureApi().then(() => setApiReady(true)) }, [])
  if (!apiReady) {
    return <div className="flex h-screen items-center justify-center bg-[#121212] text-sm text-[#b3b3b3]">{t('app.starting')}</div>
  }

  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<AppShell />}>
          <Route index element={<HomePage />} />
          <Route path="optimizer"  element={<OptimizerPage />} />
          <Route path="fragments"  element={<FragmentsPage />} />
          <Route path="combatants" element={<CombatantsPage />} />
          <Route path="scoring"    element={<Navigate to="/combatants" replace />} />
          <Route path="encyclopedia" element={<EncyclopediaPage />}>
            <Route index element={<Navigate to="cards" replace />} />
            <Route path="cards"      element={<CardsTab />} />
            <Route path="equipments" element={<EquipmentsTab />} />
            <Route path="engravings" element={<EngravingsTab />} />
            <Route path="glossary"   element={<GlossaryTab />} />
          </Route>
          <Route path="cards" element={<Navigate to="/encyclopedia/cards" replace />} />
          <Route path="deck-builder" element={<DeckBuilderPage />} />
          <Route path="guides" element={<GuidesPage />} />
          <Route path="battles" element={<BattlesPage />}>
            <Route index element={<Navigate to="simulate" replace />} />
            <Route path="simulate"  element={<SimulateTab />} />
            <Route path="overview"  element={<OverviewTab />} />
            <Route path="analytics" element={<AnalyticsTab />} />
            <Route path="history"   element={<HistoryTab />} />
          </Route>
          <Route path="simulator"  element={<Navigate to="/battles/simulate" replace />} />
          <Route path="battle"     element={<Navigate to="/battles/overview" replace />} />
          <Route path="capture"    element={<CapturePage />} />
          <Route path="setup"      element={<SetupPage />} />
          <Route path="rescue"     element={<RescuePage />} />
          <Route path="about"      element={<AboutPage />} />
          <Route path="*"          element={<Navigate to="/fragments" replace />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <AppRoutes />
    </QueryClientProvider>
  )
}
