import * as React from 'react'
import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { Radio, RefreshCw, type LucideIcon } from 'lucide-react'

/** Props for EmptyState. */
interface EmptyStateProps {
  /** Icon shown above the title. */
  icon?: LucideIcon
  /** One line saying what is missing. */
  title: string
  /** What to do about it, in a sentence. */
  hint?: string
  /** Buttons under the hint. Defaults to a "Go to Capture" button. */
  action?: React.ReactNode
  /** Extra classes for the outer box. */
  className?: string
}

/**
 * A button that opens the Capture page, the next step whenever a page has no captured data.
 * @returns The button.
 */
export function GoToCaptureButton() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  return (
    <button
      type="button"
      onClick={() => navigate('/capture')}
      className="inline-flex items-center gap-2 rounded-md bg-[#c084fc] px-4 py-2 text-sm font-semibold text-[#1a1022] hover:bg-[#d8b4fe]"
    >
      <Radio size={15} />
      {t('empty.goToCapture')}
    </button>
  )
}

/**
 * A quieter button that runs a query again after it failed or came back empty.
 * @param onClick Called when the button is pressed.
 * @returns The button.
 */
export function RetryButton({ onClick }: { onClick: () => void }) {
  const { t } = useTranslation()
  return (
    <button
      type="button"
      onClick={onClick}
      className="inline-flex items-center gap-2 rounded-md border border-[#3a3a3a] px-4 py-2 text-sm text-[#b3b3b3] hover:border-[#555555] hover:text-[#ffffff]"
    >
      <RefreshCw size={15} />
      {t('empty.retry')}
    </button>
  )
}

/**
 * A centred message for a page with nothing to show yet, with a next step.
 * @param props See `EmptyStateProps`.
 * @returns The empty state block.
 */
export function EmptyState({ icon: Icon, title, hint, action, className }: EmptyStateProps) {
  return (
    <div role="status" className={`flex flex-col items-center justify-center gap-2 p-8 text-center${className ? ` ${className}` : ''}`}>
      {Icon && <Icon size={36} className="mb-1 text-[#8a8a8a]" />}
      <p className="text-base font-semibold text-[#ffffff]">{title}</p>
      {hint && <p className="max-w-md text-balance text-sm text-[#b3b3b3]">{hint}</p>}
      <div className="mt-3 flex gap-2">{action ?? <GoToCaptureButton />}</div>
    </div>
  )
}
