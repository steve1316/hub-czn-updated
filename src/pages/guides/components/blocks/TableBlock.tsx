import { useTranslation } from 'react-i18next'
import { cn } from '@/lib/utils'
import { resolveLang, localized } from '../../guides.utils'
import type { TableRow } from '../../guides.types'
import { RatingChip } from './RatingChip'

/** Props for TableBlock. */
interface TableBlockProps {
  /** The table's rows, in sheet order. */
  rows: TableRow[]
}

/**
 * A sheet table whose rows each end in a rating, such as the Desire Synergy combinations.
 * @param props The table's rows.
 * @returns The table.
 */
export function TableBlock({ rows }: TableBlockProps) {
  const { i18n } = useTranslation()
  const lang = resolveLang(i18n.language)

  return (
    <div className="overflow-x-auto rounded-lg border border-[#282828] bg-[#181818]">
      <table className="w-full text-xs">
        <tbody>
          {rows.map((row, i) => (
            <tr key={i} className={cn(i > 0 && 'border-t border-[#282828]')}>
              {row.cells.map((cell, j) => (
                <td key={j} className={cn('px-3 py-2 leading-relaxed', j === 0 && row.cells.length > 1 ? 'font-bold text-[#ffffff]' : 'text-[#b3b3b3]')}>
                  {localized(cell, lang)}
                </td>
              ))}
              <td className="w-px px-3 py-2 text-right">
                <RatingChip rating={row.rating} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
