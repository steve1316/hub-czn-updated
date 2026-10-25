import { cn } from '@/lib/utils'

/** Props for CostGem. */
interface CostGemProps {
  /** The card's cost, -1 for an X cost. Nothing is drawn when it is absent. */
  cost?: number
  /** Whether to draw the smaller gem used in rows and legends. */
  small?: boolean
  /** Extra classes, such as a position over the card art. */
  className?: string
}

/**
 * The game-style cost gem of a card.
 * @param props The cost, the size and any extra classes.
 * @returns The gem, or nothing when the cost is unknown.
 */
export function CostGem({ cost, small = false, className }: CostGemProps) {
  if (cost === undefined) return null
  const x = cost < 0
  return (
    <span
      className={cn(
        'inline-grid place-items-center rounded border bg-linear-to-b font-extrabold leading-none text-white [text-shadow:0_1px_2px_#000]',
        x ? 'border-[#c084fc] from-[#4c1d95] to-[#24104a]' : 'border-[#60a5fa] from-[#1e3a8a] to-[#0f1d4a]',
        small ? 'h-[17px] min-w-4 px-[3px] text-[11px]' : 'h-[22px] min-w-5 px-1 text-sm',
        className,
      )}
    >
      {x ? 'X' : cost}
    </span>
  )
}
