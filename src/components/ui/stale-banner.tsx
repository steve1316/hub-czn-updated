import { Play, RotateCcw } from 'lucide-react'
import { cn } from '@/lib/utils'
import { PRIMARY_ACTION } from './action-classes'

/** Props for StaleBanner. */
interface StaleBannerProps {
  /** Says the result on screen no longer matches the settings. */
  message: string
  /** Label of the button that runs again. */
  runLabel: string
  /** Starts a new run. The button is hidden when this is missing. */
  onRun?: () => void
  /** Whether the run button is disabled. */
  disabled?: boolean
}

/**
 * A banner over a result whose settings have changed since it ran, with a button to run again.
 * @param props See `StaleBannerProps`.
 * @returns The banner.
 */
export function StaleBanner({ message, runLabel, onRun, disabled }: StaleBannerProps) {
  return (
    <div role="status" className="mb-3 flex items-center gap-3 rounded-lg border border-[#c084fc55] bg-[#c084fc14] px-4 py-2.5">
      <RotateCcw size={15} className="shrink-0 text-[#c084fc]" />
      <p className="flex-1 text-sm text-[#ffffff]">{message}</p>
      {onRun && (
        <button type="button" onClick={onRun} disabled={disabled} className={cn(PRIMARY_ACTION, 'shrink-0 px-3 py-1.5')}>
          <Play size={13} />
          {runLabel}
        </button>
      )}
    </div>
  )
}
