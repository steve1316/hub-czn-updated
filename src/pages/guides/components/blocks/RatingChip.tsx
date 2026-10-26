import { useTranslation } from 'react-i18next'
import { cn } from '@/lib/utils'
import { ratingTone, type RatingTone } from '../../guides.utils'

// Chip colours by tone: 6 gold, 5 purple, 4 blue, 3 grey and 2 or less red.
const TONE_CLASSES: Record<RatingTone, string> = {
  gold: 'bg-[#facc15]/18 text-[#facc15]',
  purple: 'bg-[#c084fc]/22 text-[#d8b4fe]',
  blue: 'bg-[#60a5fa]/18 text-[#93c5fd]',
  grey: 'bg-[#94a3b8]/16 text-[#cbd5e1]',
  red: 'bg-[#f87171]/14 text-[#fca5a5]',
}

/** Props for RatingChip. */
interface RatingChipProps {
  /** The author's rating, such as "5/5". */
  rating: string
  /** The author's comment on this rating, quoted in a tooltip. When set, even to "", the chip is focusable and shows the tooltip. */
  quote?: string
}

/**
 * A rating chip coloured by its score, with an optional tooltip restating where and how the author rated it.
 * @param props The rating and the author's comment.
 * @returns The chip.
 */
export function RatingChip({ rating, quote }: RatingChipProps) {
  const { t } = useTranslation()
  const chip = (
    <span className={cn('shrink-0 rounded px-1.5 py-px text-[11px] font-bold', TONE_CLASSES[ratingTone(rating)], quote !== undefined && 'border-b border-dotted border-current')}>
      {rating}
    </span>
  )
  if (quote === undefined) return chip
  return (
    <span tabIndex={0} className="group relative shrink-0 cursor-help outline-none">
      {chip}
      <span className="absolute right-0 bottom-[calc(100%+6px)] z-10 hidden w-max max-w-80 rounded-md border border-[#3a3a3a] bg-[#0d0d0d] px-2.5 py-2 text-xs leading-normal whitespace-normal text-[#cbd5e1] shadow-[0_6px_18px_rgba(0,0,0,.5)] group-hover:block group-focus:block">
        <b className="block text-[11px] text-[#b3b3b3]">{t('guides.ratedIn', { rating })}</b>
        {quote && <span className="mt-0.5 block text-[#ffffff]">"{quote}"</span>}
      </span>
    </span>
  )
}
