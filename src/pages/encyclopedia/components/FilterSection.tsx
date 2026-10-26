import { useTranslation } from 'react-i18next'

/** Props for FilterSection. */
interface FilterSectionProps {
  /** The filter's label. */
  label: string
  /** The values to pick from. */
  options: string[]
  /** The picked value, or null for all. */
  value: string | null
  /** Called with the picked value, or null for all. */
  onChange: (v: string | null) => void
  /** Turns a value into its label, when the value is not readable as is. */
  format?: (v: string) => string
}

/**
 * A labelled list of filter buttons with an "All" choice first.
 * @param props The label, the values, the picked value and the change handler.
 * @returns The filter buttons.
 */
export function FilterSection({ label, options, value, onChange, format = v => v }: FilterSectionProps) {
  const { t } = useTranslation()
  return (
    <div className="flex flex-col gap-0.5">
      <p className="mb-0.5 text-xs font-medium text-[#8a8a8a]">{label}</p>
      {[null, ...options].map(opt => (
        <button
          key={opt ?? ''}
          type="button"
          aria-pressed={value === opt}
          onClick={() => onChange(opt)}
          className={`truncate rounded px-2 py-1.5 text-left text-sm transition-colors ${
            value === opt ? 'bg-[#c084fc] font-semibold text-[#1a1022]' : 'text-[#b3b3b3] hover:bg-[#222] hover:text-[#e5e7eb]'
          }`}
        >
          {opt === null ? t('encyclopedia.all') : format(opt)}
        </button>
      ))}
    </div>
  )
}
