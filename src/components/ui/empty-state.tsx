import * as React from 'react'
import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { Radio, RefreshCw, TriangleAlert, type LucideIcon } from 'lucide-react'
import { ApiError } from '@/lib/api'
import { PRIMARY_ACTION, SECONDARY_ACTION } from './action-classes'

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

/** Props for GoToCaptureButton. */
interface GoToCaptureButtonProps {
  /** Button text. Defaults to "Go to Capture". */
  label?: string
}

/** Props for LoadError. */
interface LoadErrorProps {
  /** One line saying what failed to load. */
  title: string
  /** The thrown error. An API error shows its own message, anything else means the service is down. */
  error: unknown
  /** Loads it again. */
  onRetry: () => void
  /** Extra classes for the outer box. */
  className?: string
}

/**
 * A button that opens the Capture page, the next step whenever a page has no captured data.
 * @param props See `GoToCaptureButtonProps`.
 * @returns The button.
 */
export function GoToCaptureButton({ label }: GoToCaptureButtonProps) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  return (
    <button type="button" onClick={() => navigate('/capture')} className={PRIMARY_ACTION}>
      <Radio size={15} />
      {label ?? t('empty.goToCapture')}
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
    <button type="button" onClick={onClick} className={SECONDARY_ACTION}>
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

/**
 * The block shown when a page's data failed to load, with the reason and a retry button.
 * @param props See `LoadErrorProps`.
 * @returns The error block.
 */
export function LoadError({ title, error, onRetry, className }: LoadErrorProps) {
  const { t } = useTranslation()
  return (
    <EmptyState
      icon={TriangleAlert}
      title={title}
      hint={error instanceof ApiError ? error.message : t('empty.serviceDown')}
      action={<RetryButton onClick={onRetry} />}
      className={className}
    />
  )
}
