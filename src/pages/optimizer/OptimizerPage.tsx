import { useState, useRef, useEffect, useCallback, useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { Swords } from 'lucide-react'
import { useApiPort } from '@/hooks/useApiPort'
import i18n from '@/i18n'
import { api, wsUrl } from '@/lib/api'
import { EmptyState } from '@/components/ui/empty-state'
import { settingsKey } from '@/lib/run-settings'
import type { OptimizerConfig, OptimizeProgress, OptimizeResult } from '@/lib/types'
import { OptimizerPanel } from './OptimizerPanel'
import { ResultsArea } from './ResultsArea'
import { runnableConfig } from './optimizer-run'

type JobState = 'idle' | 'running' | 'done' | 'cancelled' | 'error'

const DEFAULT_CONFIG: OptimizerConfig = {
  char_name: '',
  four_piece_sets: [],
  two_piece_sets: [],
  main_stat_4: null,
  main_stat_5: null,
  main_stat_6: null,
  top_percent: 100,
  include_equipped: true,
  excluded_heroes: [],
  max_results: 10,
  stat_weights: null,
  allow_wildcards: false,
  min_priority_substats: 0,
  stat_constraints: null,
}

export function OptimizerPage() {
  const { t } = useTranslation()
  const port = useApiPort()
  const { data: status } = useQuery({
    queryKey: ['status'],
    queryFn: () => api.status(),
    refetchInterval: 5_000,
  })
  const [config, setConfig] = useState<OptimizerConfig>(DEFAULT_CONFIG)
  const [jobState, setJobState] = useState<JobState>('idle')
  const [progress, setProgress] = useState<OptimizeProgress | null>(null)
  const [results, setResults] = useState<OptimizeResult[]>([])
  const [selectedRank, setSelectedRank] = useState<number | null>(null)
  const [jobError, setJobError] = useState<string | null>(null)
  const [runError, setRunError] = useState<string | null>(null)
  const [runConfig, setRunConfig] = useState<OptimizerConfig | null>(null)

  // Ref so WS onclose callback can read current jobState without stale closure
  const jobStateRef = useRef<JobState>('idle')
  jobStateRef.current = jobState

  const configRef = useRef<OptimizerConfig>(DEFAULT_CONFIG)
  configRef.current = config

  const runConfigRef = useRef<OptimizerConfig | null>(null)
  runConfigRef.current = runConfig

  // Restore last session state
  useEffect(() => {
    try {
      const raw = localStorage.getItem('czn_optimizer_state')
      if (!raw) return
      const saved = JSON.parse(raw) as {
        config: OptimizerConfig
        runConfig?: OptimizerConfig
        results: OptimizeResult[]
        selectedRank: number | null
      }
      if (saved.config) {
        setConfig({ ...DEFAULT_CONFIG, ...saved.config })
      }
      if (saved.results?.length) {
        setResults(saved.results)
        setSelectedRank(saved.selectedRank ?? null)
        setRunConfig({ ...DEFAULT_CONFIG, ...(saved.runConfig ?? saved.config) })
        setJobState('done')
      }
    } catch { /* malformed — fall back to default */ }
  }, [])

  // Cancel any in-progress job when the user navigates away
  useEffect(() => {
    return () => {
      if (jobStateRef.current === 'running') {
        api.optimizeCancel().catch(() => {})
      }
    }
  }, [])

  // WebSocket: open on mount, reopen if port changes
  useEffect(() => {
    const ws = new WebSocket(wsUrl('/ws'))

    ws.onmessage = (e: MessageEvent) => {
      let msg: Record<string, unknown>
      try {
        msg = JSON.parse(e.data as string) as Record<string, unknown>
      } catch {
        return
      }

      switch (msg.type) {
        case 'optimize.progress':
          setProgress({
            checked: msg.checked as number,
            total: msg.total as number,
            found: msg.found as number,
          })
          break
        case 'optimize.done': {
          const newResults = msg.results as OptimizeResult[]
          setResults(newResults)
          setJobState('done')
          setProgress(null)
          try {
            localStorage.setItem(
              'czn_optimizer_state',
              JSON.stringify({ config: configRef.current, runConfig: runConfigRef.current, results: newResults, selectedRank: null })
            )
          } catch { /* storage quota — ignore */ }
          break
        }
        case 'optimize.cancelled':
          setJobState('cancelled')
          setResults([])
          setProgress(null)
          break
        case 'optimize.error':
          setJobState('error')
          setJobError((msg.message as string) ?? i18n.t('optimizer.unknownError'))
          setProgress(null)
          break
      }
    }

    let intentionalClose = false
    ws.onclose = () => {
      if (!intentionalClose && jobStateRef.current === 'running') {
        setJobState('error')
        setJobError(i18n.t('optimizer.connectionLost'))
        setProgress(null)
      }
    }

    return () => {
      intentionalClose = true
      ws.close()
    }
  }, [port])

  // Results stay on screen after a settings change. The results area marks them out of date instead.
  const handleConfigChange = useCallback((newConfig: OptimizerConfig) => {
    setConfig(newConfig)
    try {
      const raw = localStorage.getItem('czn_optimizer_state')
      const prev = raw ? (JSON.parse(raw) as Record<string, unknown>) : {}
      localStorage.setItem('czn_optimizer_state', JSON.stringify({ ...prev, config: newConfig }))
    } catch { /* ignore */ }
  }, [])

  const handleRun = useCallback(async () => {
    setRunError(null)
    setJobState('running')
    setProgress(null)
    setResults([])
    setSelectedRank(null)
    setJobError(null)
    setRunConfig(config)
    try {
      await api.optimizeStart(runnableConfig(config))
    } catch (e) {
      const msg = e instanceof Error ? e.message : i18n.t('optimizer.startError')
      setRunError(
        msg.includes('already running') ? i18n.t('optimizer.alreadyRunning') : msg
      )
      setJobState('idle')
    }
  }, [config])

  const handleCancel = useCallback(async () => {
    await api.optimizeCancel().catch(() => {})
  }, [])

  const handleSelectRank = useCallback((rank: number) => {
    setSelectedRank((prev) => (prev === rank ? null : rank))
  }, [])

  const stale = useMemo(
    () => jobState === 'done' && runConfig != null && settingsKey(runnableConfig(runConfig)) !== settingsKey(runnableConfig(config)),
    [jobState, runConfig, config],
  )

  if (status && !status.data_loaded) {
    return <EmptyState icon={Swords} title={t('optimizer.noData')} hint={t('optimizer.noDataHint')} className="h-full" />
  }

  return (
    <div className="flex h-full overflow-hidden">
      <OptimizerPanel
        config={config}
        onChange={handleConfigChange}
        onRun={handleRun}
        onCancel={handleCancel}
        isRunning={jobState === 'running'}
        progress={progress}
        runError={runError}
      />
      <ResultsArea
        jobState={jobState}
        progress={progress}
        results={results}
        selectedRank={selectedRank}
        onSelectRank={handleSelectRank}
        jobError={jobError}
        charId={runConfig?.char_name ?? config.char_name}
        stale={stale}
        onRun={config.char_name !== '' ? handleRun : undefined}
      />
    </div>
  )
}
